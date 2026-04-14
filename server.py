"""
ClipSync  v2.0  —  Windows ↔ iPhone Clipboard Sync Server
═══════════════════════════════════════════════════════════
Local-network clipboard sync + file transfer.
No cloud, no accounts, no internet required.

Run:  pip install -r requirements.txt
Then: python server.py
"""

import asyncio
import hashlib
import json
import random
import secrets
import socket
import string
import threading
import time
import base64
import io
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional

import pyperclip
import qrcode
import uvicorn
from fastapi import (
    FastAPI, WebSocket, WebSocketDisconnect,
    HTTPException, UploadFile, File, Header, Query
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, Response
from starlette.websockets import WebSocketState

# ── Dirs ──────────────────────────────────────────────────────────────────────
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
STATIC_DIR = Path("static")
STATIC_DIR.mkdir(exist_ok=True)

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="ClipSync", docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Logging ───────────────────────────────────────────────────────────────────
def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")

# ── Helpers ───────────────────────────────────────────────────────────────────
def _clip_hash(text: str) -> str:
    normalized = text.strip().replace('\r\n', '\n').replace('\r', '\n')
    return hashlib.md5(normalized.encode("utf-8", errors="replace")).hexdigest()

def _local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()

def _no_cache() -> dict:
    return {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
    }

# ── State ─────────────────────────────────────────────────────────────────────
class SyncState:
    def __init__(self):
        self.session_token: str  = secrets.token_urlsafe(32)
        self.pin: str            = self._new_pin()
        self.pin_expiry: float   = time.time() + 300
        self.authorized_tokens: set[str] = set()

        self.clients: list[WebSocket] = []
        self._lock = asyncio.Lock()

        # Clipboard echo prevention
        self._last_hash: str      = ""
        self._from_ios: bool      = False
        self._last_ios_time: float = 0.0
        self._last_win_text: str   = ""  # actual text for Win→iOS (avoids re-hashing)

        self.server_ip: str = _local_ip()
        self.port: int      = 8765

    @staticmethod
    def _new_pin() -> str:
        return "".join(random.choices(string.digits, k=6))

    def refresh_pin(self):
        self.pin        = self._new_pin()
        self.pin_expiry = time.time() + 300
        log(f"PIN refreshed → {self.pin}")

    def record_ios_clip(self, text: str):
        """iOS sent us text — write to Windows clipboard, mark as iOS-origin."""
        h = _clip_hash(text)
        self._last_hash = h
        self._from_ios  = True
        self._last_ios_time = time.time()
        try:
            pyperclip.copy(text)
        except Exception as e:
            log(f"pyperclip.copy failed: {e}")

    def is_new_from_windows(self, text: str) -> bool:
        """Check if clipboard text is genuinely new and from Windows (not an iOS echo)."""
        h = _clip_hash(text)

        # Same hash = no change
        if h == self._last_hash:
            return False

        # Within 2s of an iOS write — this is an echo from pyperclip.copy()
        if self._from_ios:
            elapsed = time.time() - self._last_ios_time
            if elapsed < 2.0:
                self._last_hash = h
                return False
            # Beyond 2s — flip back to Windows mode and absorb this one change
            self._last_hash = h
            self._from_ios = False
            return False

        # Genuine Windows clipboard change
        self._last_hash = h
        self._last_win_text = text
        return True

    @property
    def base_url(self) -> str:
        return f"http://{self.server_ip}:{self.port}"

    @property
    def connect_url(self) -> str:
        return f"{self.base_url}?session={self.session_token}"

state = SyncState()

# ── QR Code ───────────────────────────────────────────────────────────────────
def make_qr_b64(url: str) -> str:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=8, border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#00ff88", back_color="#0a0a0f")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()

# ── Broadcast ─────────────────────────────────────────────────────────────────
async def broadcast(message: str, exclude: WebSocket = None):
    """Send message to all connected clients. Remove dead ones."""
    dead = []
    sent = 0
    for ws in list(state.clients):
        if ws is exclude:
            continue
        try:
            await ws.send_text(message)
            sent += 1
        except Exception as e:
            log(f"Broadcast send failed: {e}")
            dead.append(ws)
    for ws in dead:
        try:
            state.clients.remove(ws)
        except ValueError:
            pass
    if sent > 0:
        log(f"Broadcast delivered to {sent} client(s)")

# ── Clipboard monitor (background thread) ────────────────────────────────────
def clipboard_monitor(loop: asyncio.AbstractEventLoop):
    log("Clipboard monitor started")
    # Seed initial hash
    try:
        initial = pyperclip.paste()
        state._last_hash = _clip_hash(initial)
        state._last_win_text = initial
    except Exception:
        pass

    fail_count = 0
    while True:
        try:
            text = pyperclip.paste()
            if text and text.strip() and state.is_new_from_windows(text):
                n_clients = len(state.clients)
                if n_clients > 0:
                    payload = json.dumps({
                        "type": "clipboard",
                        "text": text,
                        "from": "windows",
                        "ts": time.time()
                    })
                    future = asyncio.run_coroutine_threadsafe(broadcast(payload), loop)
                    # Wait briefly to confirm delivery
                    try:
                        future.result(timeout=2)
                    except Exception as e:
                        log(f"Broadcast error: {e}")
                    log(f"▲ Win→iOS  ({n_clients} clients)  {text[:80]!r}")
                else:
                    log(f"▲ Win clip changed but no clients connected")
            fail_count = 0
        except Exception as e:
            fail_count += 1
            if fail_count <= 3:
                log(f"Clipboard read error: {e}")
        time.sleep(0.6)  # 600ms — faster polling for better responsiveness

# ═══════════════════════════════════════════════════════════════════════════════
#  REST  API
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/info")
async def api_info():
    if time.time() > state.pin_expiry:
        state.refresh_pin()
    return {
        "pin":       state.pin,
        "url":       state.connect_url,
        "qr_b64":    make_qr_b64(state.connect_url),
        "clients":   len(state.clients),
        "server_ip": state.server_ip,
        "pin_expiry_in": max(0, int(state.pin_expiry - time.time())),
    }

@app.get("/api/dashboard_status")
async def dashboard_status():
    return {
        "clients":        len(state.clients),
        "pin":            state.pin,
        "pin_expiry_in":  max(0, int(state.pin_expiry - time.time())),
    }

@app.post("/api/auth")
async def api_auth(body: dict):
    submitted = str(body.get("pin", "")).strip()
    session   = body.get("session", "")

    if session and session != state.session_token:
        raise HTTPException(403, "Invalid session — rescan the QR code")
    if time.time() > state.pin_expiry:
        raise HTTPException(403, "PIN expired — click 'New PIN' on the dashboard")
    if submitted != state.pin:
        raise HTTPException(403, "Wrong PIN")

    token = secrets.token_urlsafe(32)
    state.authorized_tokens.add(token)
    state.refresh_pin()
    return {"auth_token": token}

@app.post("/api/clipboard")
async def api_clipboard_post(
    body: dict,
    x_auth_token: Optional[str] = Header(None)
):
    if x_auth_token not in state.authorized_tokens:
        raise HTTPException(403, "Unauthorized")
    text = body.get("text", "").strip()
    if text:
        state.record_ios_clip(text)
        log(f"▼ iOS→Win (HTTP)  {text[:80]!r}")
        await broadcast(json.dumps({"type": "clipboard", "text": text, "from": "ios"}))
    return {"ok": True}

@app.get("/api/clipboard")
async def api_clipboard_get(x_auth_token: Optional[str] = Header(None)):
    if x_auth_token not in state.authorized_tokens:
        raise HTTPException(403, "Unauthorized")
    try:
        text = pyperclip.paste()
    except Exception:
        text = ""
    return {"text": text, "hash": _clip_hash(text)}

@app.post("/api/refresh_pin")
async def api_refresh_pin():
    state.refresh_pin()
    return {"pin": state.pin, "expiry_in": 300}

@app.post("/api/upload")
async def api_upload(
    file: UploadFile = File(...),
    x_auth_token: Optional[str] = Header(None)
):
    if x_auth_token not in state.authorized_tokens:
        raise HTTPException(403, "Unauthorized")
    if not file.filename:
        raise HTTPException(400, "No filename")

    safe = Path(file.filename).name
    dest = UPLOAD_DIR / safe
    if dest.exists():
        dest = UPLOAD_DIR / f"{dest.stem}_{int(time.time())}{dest.suffix}"

    data = await file.read()
    dest.write_bytes(data)
    size_kb = len(data) / 1024
    log(f"📁 File received: {dest.name}  ({size_kb:.1f} KB)")
    await broadcast(json.dumps({"type": "file_received", "name": dest.name, "size": len(data)}))
    return {"ok": True, "saved_as": dest.name, "size": len(data)}

@app.get("/api/files")
async def api_files(x_auth_token: Optional[str] = Header(None)):
    if x_auth_token not in state.authorized_tokens:
        raise HTTPException(403, "Unauthorized")
    files = []
    for f in UPLOAD_DIR.iterdir():
        if f.is_file() and not f.name.startswith('.'):
            st = f.stat()
            files.append({"name": f.name, "size": st.st_size, "modified": st.st_mtime})
    files.sort(key=lambda x: x["modified"], reverse=True)
    return {"files": files}

@app.get("/api/download/{filename}")
async def api_download(filename: str, token: str = Query("")):
    if token not in state.authorized_tokens:
        raise HTTPException(403, "Unauthorized")
    path = UPLOAD_DIR / Path(filename).name
    if not path.exists():
        raise HTTPException(404, "File not found")
    return FileResponse(
        path,
        filename=path.name,
        headers={"Content-Disposition": f'attachment; filename="{path.name}"'}
    )

# ═══════════════════════════════════════════════════════════════════════════════
#  WebSocket — stable connection with ping/pong keepalive
# ═══════════════════════════════════════════════════════════════════════════════

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    authenticated = False
    try:
        # Auth handshake
        raw = await asyncio.wait_for(ws.receive_text(), timeout=15)
        msg = json.loads(raw)
        token = msg.get("auth_token", "")

        if token not in state.authorized_tokens:
            await ws.send_text(json.dumps({"type": "error", "msg": "unauthorized"}))
            await ws.close(code=4001)
            return

        authenticated = True
        state.clients.append(ws)
        await ws.send_text(json.dumps({"type": "connected"}))
        log(f"✓ Client connected  ({len(state.clients)} total)")

        # Push current Windows clipboard after a brief delay
        # (ensures client has processed the 'connected' message first)
        await asyncio.sleep(0.3)
        try:
            cur = pyperclip.paste()
            if cur and cur.strip():
                await ws.send_text(json.dumps({
                    "type": "clipboard",
                    "text": cur,
                    "from": "windows",
                    "ts": time.time()
                }))
                log(f"  → Pushed initial clipboard to client: {cur[:60]!r}")
        except Exception as e:
            log(f"  → Initial clipboard push failed: {e}")

        # Message loop
        while True:
            message = await ws.receive()
            msg_type = message.get("type", "")

            if msg_type in ("websocket.disconnect", "websocket.close"):
                break

            raw_msg = message.get("text")
            if raw_msg is None:
                raw_bytes = message.get("bytes")
                if raw_bytes:
                    try:
                        raw_msg = raw_bytes.decode("utf-8")
                    except Exception:
                        continue
                else:
                    continue

            try:
                m = json.loads(raw_msg)
                t = m.get("type")

                if t == "clipboard":
                    text = m.get("text", "").strip()
                    if text:
                        state.record_ios_clip(text)
                        log(f"▼ iOS→Win (WS)  {text[:80]!r}")
                        relay = json.dumps({
                            "type": "clipboard",
                            "text": text,
                            "from": "ios",
                            "ts": time.time()
                        })
                        await broadcast(relay, exclude=ws)

                elif t == "ping":
                    await ws.send_text(json.dumps({"type": "pong", "ts": time.time()}))

            except (json.JSONDecodeError, KeyError):
                pass

    except WebSocketDisconnect:
        pass
    except asyncio.TimeoutError:
        log("WS auth timeout (15s)")
    except Exception as e:
        err = str(e)
        if "1000" not in err and "1001" not in err and "1005" not in err:
            log(f"WS error: {e}")
    finally:
        if authenticated and ws in state.clients:
            state.clients.remove(ws)
        try:
            if ws.client_state == WebSocketState.CONNECTED:
                await ws.close()
        except Exception:
            pass
        log(f"Client disconnected  ({len(state.clients)} remaining)")

# ═══════════════════════════════════════════════════════════════════════════════
#  Static / PWA
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/")
async def serve_pwa():
    p = STATIC_DIR / "index.html"
    if p.exists():
        return HTMLResponse(p.read_text(encoding="utf-8"), headers=_no_cache())
    return HTMLResponse("<h1>ClipSync</h1><p>Put index.html in static/</p>")

@app.get("/sw.js")
async def serve_sw():
    p = STATIC_DIR / "sw.js"
    if p.exists():
        return Response(p.read_text(encoding="utf-8"), media_type="application/javascript", headers=_no_cache())
    return Response("", media_type="application/javascript")

@app.get("/manifest.json")
async def manifest():
    return JSONResponse({
        "name": "ClipSync",
        "short_name": "ClipSync",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#0a0a0f",
        "theme_color": "#00ff88",
        "icons": [
            {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"},
        ]
    })

# ═══════════════════════════════════════════════════════════════════════════════
#  Dashboard
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/dashboard")
async def dashboard():
    data = await api_info()
    qr_img  = data["qr_b64"]
    pin     = data["pin"]
    url     = data["url"]
    clients = data["clients"]
    expiry  = data["pin_expiry_in"]

    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ClipSync Dashboard</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Inter:wght@300;400;600;700&display=swap');
*{{box-sizing:border-box;margin:0;padding:0}}
:root{{--bg:#0a0a0f;--bg2:#111118;--bg3:#16161f;--border:#1e1e2e;--accent:#00ff88;--muted:#444458;--text:#e8e8f0;--danger:#ff3366}}
body{{background:var(--bg);color:var(--text);font-family:'Inter',sans-serif;min-height:100vh;display:flex;align-items:center;justify-content:center;
  background-image:radial-gradient(ellipse 55% 45% at 15% 10%,rgba(0,255,136,.07) 0%,transparent 65%),radial-gradient(ellipse 45% 55% at 85% 90%,rgba(0,80,255,.05) 0%,transparent 65%)}}
.wrap{{background:var(--bg2);border:1px solid var(--border);border-radius:24px;padding:44px 40px;text-align:center;max-width:440px;width:92%;box-shadow:0 0 100px rgba(0,255,136,.06)}}
.logo{{font-size:.8rem;font-weight:700;letter-spacing:.35em;color:var(--accent);margin-bottom:4px}}
.version{{font-size:.6rem;color:var(--muted);letter-spacing:.2em;margin-bottom:32px}}
.qr-wrap{{border-radius:16px;overflow:hidden;display:inline-block;border:2px solid var(--accent);margin-bottom:28px;box-shadow:0 0 28px rgba(0,255,136,.12)}}
.qr-wrap img{{display:block;width:192px;height:192px}}
.pin-label{{font-size:.58rem;letter-spacing:.25em;color:var(--muted);text-transform:uppercase;margin-bottom:8px}}
.pin{{font-family:'JetBrains Mono',monospace;font-size:2.4rem;font-weight:700;letter-spacing:.35em;color:var(--accent);background:var(--bg3);border:1px solid var(--border);border-radius:12px;padding:12px 24px;display:inline-block;margin-bottom:8px}}
.timer{{font-family:'JetBrains Mono',monospace;font-size:.65rem;color:var(--muted);margin-bottom:20px}}.timer.warn{{color:var(--danger)}}
.url{{font-family:'JetBrains Mono',monospace;font-size:.62rem;color:#2a2a3e;padding:10px 14px;background:var(--bg3);border:1px solid var(--border);border-radius:8px;word-break:break-all;margin-bottom:20px;cursor:pointer;transition:color .2s}}.url:hover{{color:var(--accent)}}
.actions{{display:flex;gap:8px;margin-bottom:20px}}
.btn{{flex:1;padding:11px;border-radius:10px;border:none;cursor:pointer;font-family:'Inter',sans-serif;font-size:.78rem;font-weight:600;letter-spacing:.04em;transition:all .18s}}
.btn-primary{{background:var(--accent);color:#0a0a0f}}.btn-primary:hover{{background:#00e07a}}
.btn-ghost{{background:transparent;color:var(--muted);border:1px solid var(--border)}}.btn-ghost:hover{{background:var(--bg3);color:var(--text)}}
.footer{{display:flex;align-items:center;justify-content:center;gap:8px;font-size:.7rem;color:var(--muted)}}
.dot{{width:7px;height:7px;border-radius:50%;background:var(--muted);flex-shrink:0;transition:background .3s}}.dot.live{{background:var(--accent);animation:pulse 1.6s ease-in-out infinite}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.25}}}}
</style></head><body>
<div class="wrap">
  <p class="logo">CLIPSYNC</p><p class="version">v2.0 · Local Network Sync</p>
  <div class="qr-wrap"><img src="data:image/png;base64,{qr_img}" alt="QR"></div>
  <p class="pin-label">One-Time PIN</p><div class="pin" id="pin">{pin}</div>
  <p class="timer" id="timer">Expires in {expiry//60}:{expiry%60:02d}</p>
  <div class="url" onclick="copyUrl()" title="Click to copy">{url}</div>
  <div class="actions"><button class="btn btn-primary" onclick="newPin()">↻ New PIN</button><button class="btn btn-ghost" onclick="copyUrl()">⎘ Copy URL</button></div>
  <div class="footer"><span class="dot {'live' if clients>0 else ''}" id="dot"></span><span id="clients">{clients} device(s) connected</span></div>
</div>
<script>
let secondsLeft={expiry};
function tick(){{if(secondsLeft<=0){{document.getElementById('timer').textContent='Expired — click New PIN';document.getElementById('timer').className='timer warn';return}}secondsLeft--;const m=Math.floor(secondsLeft/60),s=secondsLeft%60;document.getElementById('timer').textContent=`Expires in ${{m}}:${{s.toString().padStart(2,'0')}}`;if(secondsLeft<60)document.getElementById('timer').className='timer warn';setTimeout(tick,1000)}}tick();
async function newPin(){{const r=await fetch('/api/refresh_pin',{{method:'POST'}});const d=await r.json();document.getElementById('pin').textContent=d.pin;document.getElementById('timer').className='timer';secondsLeft=d.expiry_in}}
function copyUrl(){{navigator.clipboard.writeText(document.querySelector('.url').textContent).then(()=>{{const el=document.querySelector('.url');el.style.color='var(--accent)';setTimeout(()=>el.style.color='',1200)}})}}
async function pollStatus(){{try{{const r=await fetch('/api/dashboard_status');const d=await r.json();document.getElementById('dot').className='dot'+(d.clients>0?' live':'');document.getElementById('clients').textContent=d.clients+' device(s) connected';if(d.pin!==document.getElementById('pin').textContent)document.getElementById('pin').textContent=d.pin}}catch{{}}setTimeout(pollStatus,4000)}}pollStatus();
</script></body></html>""")

# ═══════════════════════════════════════════════════════════════════════════════
#  Startup
# ═══════════════════════════════════════════════════════════════════════════════

@app.on_event("startup")
async def startup():
    loop = asyncio.get_running_loop()
    t = threading.Thread(target=clipboard_monitor, args=(loop,), daemon=True)
    t.start()

    print()
    print("═"*56)
    print("   ██████╗██╗     ██╗██████╗ ███████╗██╗   ██╗███╗  ██╗")
    print("  ██╔════╝██║     ██║██╔══██╗██╔════╝╚██╗ ██╔╝████╗ ██║")
    print("  ██║     ██║     ██║██████╔╝███████╗ ╚████╔╝ ██╔██╗██║")
    print("  ██║     ██║     ██║██╔═══╝ ╚════██║  ╚██╔╝  ██║╚████║")
    print("  ╚██████╗███████╗██║██║     ███████║   ██║   ██║ ╚███║")
    print("   ╚═════╝╚══════╝╚═╝╚═╝     ╚══════╝   ╚═╝   ╚═╝  ╚══╝")
    print("═"*56)
    print(f"\n  Server    {state.base_url}")
    print(f"  Dashboard {state.base_url}/dashboard")
    print(f"  PIN       {state.pin}  (5 min)")
    print(f"\n  Notifications: OFF (terminal log only)")
    print("═"*56 + "\n")

if __name__ == "__main__":
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=8765,
        reload=False,
        log_level="warning",
    )
