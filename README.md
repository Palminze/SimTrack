# SimTrack

**Free, browser-based head tracking for sim racing using your phone's front camera.**

No app install. No hardware. No subscription. Just open a URL on your phone.

![License](https://img.shields.io/badge/license-MIT-blue)
![Python](https://img.shields.io/badge/python-3.8%2B-blue)
![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Windows-lightgrey)

---

## What is SimTrack?

SimTrack turns your phone into a head tracking device for sim racing. Prop your phone on your monitor, open a URL in Safari or Chrome, and your in-game view follows your head movements in real time — left, right, up, down.

It uses [MediaPipe](https://developers.google.com/mediapipe) running entirely in the browser to detect your head pose. No data leaves your local network.

### How it compares

| | SimTrack | SmoothTrack | TrackIR |
|---|---|---|---|
| Cost | **Free** | $10 | $150+ |
| Setup | Browser URL | App install | Hardware + software |
| Camera | Any phone (front cam) | iPhone TrueDepth | Dedicated IR camera |
| Accuracy | Good | Better (depth sensor) | Best |
| Latency | ~30–80ms | ~15ms | ~5ms |

---

## How it works

```
┌─────────────────────────────────────────────────────────────┐
│  Your Phone (Safari/Chrome)                                  │
│  MediaPipe detects head pose → WebSocket → PC               │
└─────────────────────┬───────────────────────────────────────┘
                      │  WebSocket (same WiFi)
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  Your PC  (server_windows.py)                               │
│  ├─ FreeTrack shared memory  → ETS2, ATS, BeamNG            │
│  └─ UDP port 4242 → OpenTrack → Assetto Corsa, ACC, iRacing │
└─────────────────────────────────────────────────────────────┘
```

1. The phone opens a webpage served by your PC
2. MediaPipe runs in the browser, tracking your head at ~30fps
3. Yaw / pitch / roll angles are streamed over WebSocket to the PC
4. The PC writes to FreeTrack shared memory — games read it natively

---

## Game Compatibility

| Game | Protocol | Setup |
|---|---|---|
| Assetto Corsa | TrackIR | ⚙️ Needs OpenTrack |
| Euro Truck Simulator 2 | FreeTrack | ✅ Direct |
| American Truck Simulator | FreeTrack | ✅ Direct |
| BeamNG.drive | FreeTrack | ✅ Direct |
| iRacing | TrackIR / UDP | ⚙️ Needs OpenTrack |
| Assetto Corsa Competizione | TrackIR / UDP | ⚙️ Needs OpenTrack |
| Dirt Rally 2.0 | TrackIR / UDP | ⚙️ Needs OpenTrack |
| rFactor 2 | TrackIR / UDP | ⚙️ Needs OpenTrack |

> **OpenTrack setup for iRacing/ACC:** Install [OpenTrack](https://github.com/opentrack/opentrack/releases), set Input to **UDP over network** on port **4242**, configure output for your game.

---

## Requirements

- **Phone:** iPhone or Android with a front-facing camera
- **PC:** Windows 10/11 (for gaming) or macOS (for demo/testing)
- **Python:** 3.8 or newer → [python.org](https://www.python.org/downloads/)
- **Network:** Phone and PC on the same WiFi

---

## Quick Start — Windows (5 minutes)

### 1. Install Python

Download from [python.org](https://www.python.org/downloads/). During install, check **"Add Python to PATH"**.

### 2. Download SimTrack

```
https://github.com/Palminze/simtrack/archive/refs/heads/main.zip
```

Extract the zip somewhere on your PC (e.g. `C:\SimTrack`).

### 3. Run

Double-click **`start.bat`**

The first run auto-installs `aiohttp` and downloads `cloudflared`. A window opens showing your phone URL.

### 4. Open on Phone

Open the URL shown in the SimTrack window in **Safari (iPhone)** or **Chrome (Android)**. Allow camera access when prompted.

### 5. Enable in game

**Assetto Corsa:** AC reads TrackIR, not FreeTrack, and has no in-game head
tracking toggle. Install [OpenTrack](https://github.com/opentrack/opentrack/releases),
set Input to **UDP over network** port **4242**, set Output to **freetrack 2.0
enhanced**, and press Start. AC then picks it up automatically.

**ETS2 / ATS:** Options → Controls → Head Tracking → FreeTrack → Enable

**BeamNG:** Settings → Controls → search "Head Tracking" → enable FreeTrack

### 6. Calibrate

Sit in your normal driving position, look straight ahead, then click **Calibrate** on the phone page. The view resets to center.

---

## Quick Start — macOS

macOS is supported for development and demo purposes. Full game integration requires Windows.

### 1. Install dependencies

```bash
pip3 install aiohttp
```

### 2. Run

```bash
~/simtrack/start.sh
```

### 3. Demo

Open `http://localhost:8080/demo.html` in your browser for a visual cockpit demo that reacts to your head movements in real time.

---

## iPhone Setup (HTTPS tunnel)

iOS Safari requires HTTPS for camera access. If your iPhone can't reach the PC URL:

### Option A — Same WiFi

**Does not work for the camera.** Browsers only expose `getUserMedia` on secure
origins, so `http://192.168.x.x:8080` cannot start the camera no matter what
permissions you grant. The page loads; the camera does not. Use Option B.

### Option B — Cloudflare Tunnel

SimTrack starts the tunnel itself and shows the `https://…trycloudflare.com`
URL in the window. Open that on your phone — it is the only address that can
start the camera.

> The tunnel URL changes every time you restart. Bookmark it or re-copy after each restart.

---

## Configuration

### Sensitivity

Edit the multipliers in `demo.html` (for the demo) or in your game's head tracking sensitivity settings:

| Setting | Default | Effect |
|---|---|---|
| Yaw multiplier | 12px/° | Higher = more responsive left/right |
| Pitch multiplier | 8px/° | Higher = more responsive up/down |
| Smoothing | 0.35 | 0 = instant/jittery, 1 = very smooth/laggy |

### Reducing latency

- Use the same WiFi network (avoid 5GHz if range is poor)
- Increase lighting on your face — MediaPipe is faster with well-lit subjects
- Move closer to the phone (ideal distance: 60–100cm)
- Avoid VPN on PC or phone during use

---

## Troubleshooting

### Phone page won't load
- Confirm phone and PC are on the same WiFi (not mobile data)
- Check the IP address shown in the SimTrack window is correct
- Temporarily disable Windows Firewall or allow Python through it: **Windows Security → Firewall → Allow an app → Python**

### Camera doesn't start on iPhone
- Safari requires HTTPS for camera. Use the `trycloudflare.com` URL instead of the local IP
- Go to **Settings → Safari → Camera** and allow access

### Head tracking not detected in game
- Start SimTrack **before** launching the game
- Confirm FreeTrack is selected in game settings (not TrackIR or disabled)
- For iRacing/ACC: install OpenTrack and set input to UDP port 4242

### Tracking feels off / wrong direction
- Use the **Calibrate** button while sitting in your normal position looking straight ahead
- If yaw is inverted, it may be a camera-specific quirk — check phone orientation (should face you upright)

### Port 8080 already in use
```bash
# macOS
pkill -f server.py

# Windows (in cmd)
netstat -ano | findstr :8080
taskkill /PID <pid> /F
```

### `start.bat` closes immediately
Right-click `start.bat` → **Run as administrator**, or open a Command Prompt and run:
```
cd C:\SimTrack
python server_windows.py
```
This shows any error messages.

---

## Project Structure

```
simtrack/
├── server.py            # Mac/Linux server (HTTP + WebSocket + OpenTrack UDP)
├── server_windows.py    # Windows server with GUI + FreeTrack shared memory
├── index.html           # Phone tracker (MediaPipe face tracking in browser)
├── demo.html            # Visual cockpit demo for testing without a game
├── start.sh             # macOS one-command launcher
├── start.bat            # Windows one-command launcher
└── requirements.txt     # Python dependencies
```

---

## Contributing

Pull requests are welcome. Key areas that need improvement:

- **Accuracy** — better Euler angle decomposition or Kalman filtering
- **Android testing** — should work but untested
- **NPClient shared memory** — would eliminate the OpenTrack requirement for iRacing/ACC
- **Sensitivity UI** — in-phone calibration and curve editor
- **Auto-discovery** — phone auto-detects PC IP without typing

---

## License

MIT — free for personal and commercial use. See [LICENSE](LICENSE).

---

## Acknowledgements

- [MediaPipe](https://developers.google.com/mediapipe) — face landmark detection
- [OpenTrack](https://github.com/opentrack/opentrack) — reference for game protocols
- [aiohttp](https://docs.aiohttp.org/) — async HTTP + WebSocket server
