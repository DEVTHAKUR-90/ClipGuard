
<div align="center">

```
     ██████╗ ██╗     ██╗ ██████╗  ██████╗ ██╗   ██╗ █████╗ ██████╗ ██████╗ 
    ██╔════╝ ██║     ██║ ██╔══██╗██╔════╝ ██║   ██║██╔══██╗██╔══██╗██╔══██╗
    ██║      ██║     ██║ ██████╔╝██║  ███╗██║   ██║███████║██████╔╝██║  ██║
    ██║      ██║     ██║ ██╔═══╝ ██║   ██║██║   ██║██╔══██║██╔══██╗██║  ██║
    ╚██████╗ ███████╗██║ ██║     ╚██████╔╝╚██████╔╝██║  ██║██║  ██║██████╔╝
     ╚═════╝ ╚══════╝╚═╝ ╚═╝      ╚═════╝  ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝ 
```

### Your clipboard, everywhere. Instantly.

**Copy on Windows. Paste on iPhone. And back again.**<br>
No cloud. No sign-ups. No BS. Just your Wi-Fi.

<br>

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![WebSocket](https://img.shields.io/badge/WebSocket-Real--time-4A90D9?style=for-the-badge)

<br>

[Getting Started](#-getting-started) · [How It Works](#-how-it-works) · [Features](#-features) · [Troubleshooting](#-troubleshooting)

<br>

</div>

---

## The Problem

You're on your laptop. You copy a link — a recipe, a GitHub repo, a meeting URL, whatever. Now you need it on your phone. So what do you do?

Email it to yourself? Open WhatsApp Web and send it to your own chat? Type it out letter by letter like it's 2005?

**ClipGuard fixes that.** Copy on Windows, it shows up on your iPhone within a second. Type something on your phone, it lands on your PC clipboard. Files too — drag and drop, done.

And here's the thing: **your data never leaves your house.** No cloud servers. No accounts. No analytics. Everything stays on your local Wi-Fi, between your own devices. That's it.

---

## ✨ Features

**Bi-directional clipboard sync** — Copy anywhere on Windows (Ctrl+C in any app), and it appears on your iPhone instantly. Send text from your phone, and it's on your PC clipboard ready to paste.

**Dual-panel interface** — Separate boxes for sending (iPhone → Windows) and receiving (Windows → iPhone). Each with its own Clear button. No confusion about what went where.

**File transfer** — Pick files on your iPhone and upload them to your PC. Download files from your PC to your phone. Progress bars and everything.

**One-tap authentication** — Scan a QR code with your iPhone camera, type a 6-digit PIN, done. New PIN every 5 minutes. No passwords to remember.

**Works offline** — Install as a PWA on your iPhone (Add to Home Screen in Safari). Once installed, it works without opening Safari.

**Clipboard history** — Every synced item is logged with timestamps. Scroll back and copy anything again.

**Auto-reconnect** — Wi-Fi hiccup? Phone went to sleep? ClipGuard reconnects automatically with exponential backoff. Falls back to HTTP polling if WebSocket drops.

---

## 🚀 Getting Started

You need two things: Python on your Windows PC, and Safari on your iPhone. Both on the same Wi-Fi.

### Install

```bash
git clone https://github.com/YourUsername/ClipGuard.git
cd ClipGuard
pip install -r requirements.txt
```

### Run

```bash
python server.py
```

Or just double-click **`start.bat`**.

You'll see something like this:

```
═══════════════════════════════════════════════════════
   ██████╗██╗     ██╗██████╗ ███████╗██╗   ██╗███╗  ██╗
  ██╔════╝██║     ██║██╔══██╗██╔════╝╚██╗ ██╔╝████╗ ██║
  ██║     ██║     ██║██████╔╝███████╗ ╚████╔╝ ██╔██╗██║
  ██║     ██║     ██║██╔═══╝ ╚════██║  ╚██╔╝  ██║╚████║
  ╚██████╗███████╗██║██║     ███████║   ██║   ██║ ╚███║
   ╚═════╝╚══════╝╚═╝╚═╝     ╚══════╝   ╚═╝   ╚═╝  ╚══╝
═══════════════════════════════════════════════════════

  Server    http://192.168.1.5:8765
  Dashboard http://192.168.1.5:8765/dashboard
  PIN       482910  (5 min)

  Notifications: OFF (terminal log only)
═══════════════════════════════════════════════════════
```

### Connect your iPhone

1. Open that **Dashboard** URL on your PC browser
2. Point your iPhone camera at the **QR code**
3. Type the **6-digit PIN**
4. Green dot says **LIVE** — you're in

That's the entire setup. No accounts, no config files, no port forwarding.

---

## 🔧 How It Works

```
  ┌─────────────────────────────────────┐
  │         YOUR WINDOWS PC             │
  │                                     │
  │  ┌───────────────────────────────┐  │
  │  │   Clipboard Monitor Thread    │  │
  │  │   polls every 600ms           │  │
  │  │   detects Ctrl+C from any app │  │
  │  └──────────┬────────────────────┘  │
  │             │ new text?             │
  │             ▼                       │
  │  ┌───────────────────────────────┐  │
  │  │   FastAPI + WebSocket Server  │──┼──── Wi-Fi ────┐
  │  │   port 8765                   │  │               │
  │  │   broadcasts to all clients   │◄─┼──── Wi-Fi ────┤
  │  └───────────────────────────────┘  │               │
  │             │                       │               │
  │             ▼                       │               │
  │  ┌───────────────────────────────┐  │    ┌──────────┴──────────┐
  │  │   pyperclip.copy()            │  │    │   YOUR iPHONE       │
  │  │   writes to Windows clipboard │  │    │                     │
  │  └───────────────────────────────┘  │    │   Safari PWA        │
  │                                     │    │   WebSocket client  │
  └─────────────────────────────────────┘    │   + HTTP fallback   │
                                             └─────────────────────┘
```

The server runs a background thread that checks your Windows clipboard every 600 milliseconds. When it detects a change — you copied something new — it broadcasts the text to every connected iPhone over WebSocket.

Going the other direction, your iPhone sends text through the WebSocket (or falls back to HTTP POST if the socket drops), and the server writes it to your Windows clipboard using `pyperclip`.

**Echo prevention** is the tricky part. When your iPhone sends text to Windows, `pyperclip.copy()` writes it to the clipboard — which the monitor thread then detects as a "new" clipboard change and tries to broadcast it back. Infinite loop. ClipGuard breaks this cycle with three layers: MD5 hash comparison, a directional origin flag, and a 2-second timestamp debounce window.

---

## 📁 Project Structure

```
ClipGuard/
│
├── server.py               The whole backend — API, WebSocket, clipboard monitor
├── start.bat               Double-click launcher for Windows
├── requirements.txt         pip dependencies
├── README.md                You're reading it
│
├── static/
│   ├── index.html           The entire iPhone app — single file, no frameworks
│   └── sw.js                Service worker for PWA offline caching
│
└── uploads/                 Files transferred from iPhone land here
```

No build step. No bundler. No `node_modules`. One Python file, one HTML file. That's the whole app.

---

## 📦 Dependencies

| Package | What it does |
|---------|-------------|
| **fastapi** | HTTP routes + WebSocket server |
| **uvicorn** | Runs the ASGI app |
| **pyperclip** | Reads & writes the Windows clipboard |
| **qrcode** | Generates the QR code for easy phone pairing |
| **pillow** | Renders the QR as a PNG image |
| **python-multipart** | Handles file uploads |
| **websockets** | WebSocket protocol layer |

Install all of them in one shot:

```bash
pip install -r requirements.txt
```

---

## ⚙️ Configuration

ClipGuard works out of the box. But if you want to tweak things:

| What | Default | Where to change it |
|------|---------|-------------------|
| Server port | `8765` | `server.py` → `self.port` |
| Clipboard poll speed | 600ms | `server.py` → `time.sleep(0.6)` |
| PIN lifetime | 5 minutes | `server.py` → `time.time() + 300` |
| WebSocket ping interval | 15 seconds | `index.html` → `startPing` |
| Auto-copy on iPhone | ON | Toggle in the Settings tab |

---

## 🐛 Troubleshooting

**iPhone shows OFFLINE**<br>
Tap the status badge to force a reconnect. Make sure both devices are on the same Wi-Fi network. If it keeps happening, go to iPhone Settings → Safari → Clear Website Data for your server IP.

**Windows → iPhone isn't showing**<br>
Check the terminal — you should see `▲ Win→iOS (1 clients)` when you copy something. If you see `(0 clients)`, the iPhone isn't connected. Reconnect. If you see the broadcast but the phone doesn't update, go to Settings tab on the phone and check the message counter.

**iPhone → Windows works but the other way doesn't**<br>
Usually a stale service worker cache. On iPhone: Settings → Safari → Advanced → Website Data → find your server IP → Delete. Then reconnect.

**`ConnectionResetError` in the terminal**<br>
Normal. This just means a previous WebSocket connection was closed (phone went to sleep, tab switched, etc.). The phone auto-reconnects.

**PIN keeps expiring**<br>
PINs last 5 minutes. Click "New PIN" on the dashboard. Once authenticated, the session stays active — you don't need a new PIN until you disconnect.

---

## ❓ FAQ

**Can I deploy this on Vercel / Netlify / the cloud?**

No. ClipGuard reads your Windows clipboard using `pyperclip`, which needs a Python process running on your actual computer. Cloud platforms can't access your desktop. This is a local tool by design — and that's a feature, not a limitation. Your clipboard data stays in your house.

**Is this secure?**

Your data never leaves your local network. The PIN-based auth prevents random devices on your Wi-Fi from connecting. For a home network, this is plenty secure. If you're on a shared/public Wi-Fi, don't use this (but you probably shouldn't be syncing clipboards on public Wi-Fi anyway).

**Does it work on Mac?**

Should work — `pyperclip` supports macOS. Haven't tested it extensively, but the architecture is platform-agnostic. Give it a shot and open an issue if something breaks.

**Can I connect multiple phones?**

Yes. The server broadcasts to all connected clients simultaneously. Each device sees the same clipboard updates in real time.

**What about Android?**

It should work in Chrome on Android — the web app is just HTML/JS. The clipboard API behavior might differ slightly. Haven't tested it yet.

---

## 🤝 Contributing

Found a bug? Want to add a feature? PRs are welcome.

1. Fork the repo
2. Create a branch (`git checkout -b fix/something`)
3. Make your changes
4. Test on actual devices (not just localhost)
5. Open a PR with a clear description

---



---

<div align="center">

<br>

**Built because emailing yourself a URL is embarrassing.**

If ClipGuard saved you from that, consider giving it a ⭐

<br>

</div>
