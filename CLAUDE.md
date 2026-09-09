# SimTrack — working context

Phone-camera head tracking for sim racing. MediaPipe runs in the phone browser,
pose streams over WebSocket to the PC, PC writes FreeTrack shared memory (games
read it natively) and UDP 4242 for OpenTrack.

## Machines

- **Mac** (`~/simtrack`) — development. Cannot test FreeTrack; shared memory is Windows-only.
- **Windows** (`C:\Users\<you>\SimTrack`) — the gaming PC. All real testing happens here.
- Sync between them is this git repo. Remote is SSH (`git@github.com:Palminze/SimTrack.git`).

## Goal

Make this clean and sellable. Two decisions already made:

- **Business model: fully commercial, closed source.** Repo goes private, future
  versions relicensed. Note v0.1.0 is MIT and stays forkable forever.
- **HTTPS approach: wildcard domain + real certificate.** Buy a domain, wildcard
  DNS maps `192-168-1-42.yourdomain.com` → that private IP, ship a trusted cert.
  Real HTTPS on pure LAN, no tunnel, lowest latency — how Plex does it.
  Caveat: a wildcard private key shipped inside a distributed binary will get
  extracted and revoked. Per-install certs issued by a license server avoid this
  and double as the license check.

## State of play

### Done (commit bbc7016)

FreeTrack was fundamentally broken and had never worked. The struct was
`<3i 14f i` (72 bytes) with marker points before the pose fields, but FreeTrack
2.0 is 108 bytes with Yaw/Pitch/Roll immediately after the three header ints.
Games reading Yaw at offset 12 got a constant `0.0` — tracking was inert, not
inaccurate. Also: angles were degrees (spec wants radians), no `FT_Mutext`
guard, no `FreeTrackClient.dll` registry path.

Fixed in `freetrack.py`. Server-thread exceptions were also being swallowed —
`server_windows.py` now catches them and the GUI polls health, so a dead server
no longer looks like "waiting for phone…".

### Game routing — corrected 2026-09-08

**Assetto Corsa has no FreeTrack option.** It reads TrackIR and detects it
automatically. The README previously claimed "FreeTrack, works out of the box"
for AC; that was false and is now fixed. AC must go through OpenTrack:
Input = UDP over network 4242, Output = freetrack 2.0 enhanced.

FreeTrack shared memory is the direct path only for **ETS2, ATS, BeamNG**.

SUPERSEDED 2026-09-09: the owner decided OpenTrack must go — customers touch
only SimTrack. Architecture now: SimTrack writes FT_SharedMem (as before), and
two client DLLs serve the games from it directly:

- `bin/NPClient.dll` + `NPClient64.dll` → TrackIR titles (AC, iRacing, ACC).
  Source `dll/npclient.c`, vendored from opentrack contrib — linuxtrack's
  clean-room, permissively licensed implementation (see dll/PROVENANCE.txt).
- `bin/freetrackclient.dll` (+64) → FreeTrack titles (ETS2, ATS, BeamNG).
  Source `dll/freetrackclient.c`, written fresh for SimTrack — opentrack's
  version descends from FreeTrack's GPL Delphi code, so it was NOT copied.

Registry keys (set automatically at server start, `freetrack.py`):
HKCU\Software\FreeTrack\FreeTrackClient\Path and
HKCU\Software\NaturalPoint\NATURALPOINT\NPClient Location → both point at bin/.

GameID handshake: games write their ID into the heap; `poll_game()` answers
with the scramble table from `dll/games.csv` and echoes GameID2. Pose writes
deliberately stop at byte 92 so they never clobber this tail.

DLLs are cross-compiled by `.github/workflows/build-dlls.yml` (mingw, 32+64
bit) and committed to `bin/` by CI — `git pull` after the workflow runs.
NaturalPoint interface-emulation risk was flagged three times and accepted by
the owner; it is inherent to the feature, not to whose code implements it.

### NEXT STEP — run on Windows

```powershell
python tools\ft_check.py udp      # Assetto Corsa, via OpenTrack
python tools\ft_check.py emit     # ETS2 / ATS / BeamNG, direct
```

Both drive a synthetic ±25° sweep, so the game link is provable with **no phone
involved**. `emit` is confirmed working on the Windows PC — shared memory maps
and frames count up. Whether a game reacts is still unverified.

If a FreeTrack game stays static, the missing piece is `FreeTrackClient.dll`
plus its registry path (`tools/ft_check.py register <dir>`) — most FreeTrack
games load that DLL rather than reading shared memory directly.

### VERIFIED 2026-09-08: game side works end to end

**Assetto Corsa reads the data.** SimTrack → UDP → OpenTrack → AC is proven
with synthetic input. The game half of the product is done; every remaining
problem is on the phone side.

Next cheap win before building certificate infrastructure: run the **whole**
chain with the existing cloudflared tunnel to confirm a real head drives the
game. That surfaces pose quality, jitter and axis directions — none of which
can be learned from a synthetic sweep — and it needs no new infrastructure.
Only then is the wildcard-cert work worth starting.

Expect two immediate findings from that test: raw MediaPipe output is jittery
(no smoothing exists yet, open item 4) and axis directions may be inverted
(flags are in `freetrack.py`; the UDP path in `server_windows.py` has none yet).

### VERIFIED 2026-09-08: UDP → OpenTrack works

`python tools\ft_check.py udp` moves OpenTrack's octopus preview. SimTrack's
UDP packet format (six little-endian doubles, x/y/z/yaw/pitch/roll, degrees)
is correct and OpenTrack receives it. **Port is 4242** — the default was right.

Getting there cost most of a session, for reasons worth not repeating:

- OpenTrack was not binding its port at all until it was relaunched. It showed
  a normal window and an apparently-pressed Start the whole time.
- A `4376` read off an OpenTrack dialog was a red herring (output side, not
  input). Do not trust the dialogs — ask the OS what is actually bound:
  `$p = (Get-Process opentrack).Id; netstat -ano -p UDP | Select-String " $p$"`
- An earlier probe reported "nothing listening" against a bound socket because
  it bound loopback instead of the wildcard. Fixed, but it wasted a cycle.

**Do not create a config.json with opentrack_port 4376** — 4242 is correct here.
The setting exists because the port genuinely varies between installs, not
because this machine needs it.

### Diagnosing "no tracking in game"

Check in this order:

```powershell
netstat -ano | findstr <port>
python tools\ft_check.py probe --port <port>
```

### The tunnel was never started on Windows

`start.bat` downloaded `cloudflared.exe` and nothing ever ran it —
`server_windows.py` had no reference to cloudflared at all, so the GUI only
ever showed the LAN HTTP address, which cannot start a phone camera. The
README claimed start.bat "automatically handles this". Only `start.sh` (macOS)
actually launched a tunnel.

Now in `tunnel.py`: downloads cloudflared if missing, launches it, scrapes the
https URL from stderr, and pushes it into the GUI. Failures surface in the
window instead of leaving a blank address.

### Done 2026-09-09 (polish pass)

- **MediaPipe self-hosted**: wasm + face model + bundle live in `assets/`,
  served with explicit MIME types (wasm refuses to stream-compile otherwise)
  and a traversal-proof route. No Google CDN dependency at runtime.
- **index.html rewritten** as the sim-cockpit page: One Euro filter smoothing
  (slider, persisted), the Calibrate button the README always promised,
  screen wake-lock so phones stop sleeping mid-race, LINK/FACE/FPS status
  LEDs, friendly camera-over-http error text.
- demo.html repointed to local assets.

Still needing the owner's purchase: domain (~€12) + small VPS for the
wildcard-cert/license server that retires TryCloudflare. Then: PyInstaller
exe + signing, README rewrite, repo private.

### Open items

1. **`FreeTrackClient.dll`** — not yet shipped. Blocks games that use the DLL path.
2. **Camera needs a secure context.** iOS Safari does not expose `getUserMedia`
   over plain `http://192.168.x.x`. This is why cloudflared exists in `start.bat`.
   The README's "Option A — iOS allows camera over local network HTTP" is WRONG.
   Superseded by the wildcard-cert plan above.
3. **No Calibrate button.** README tells users to click one twice; it does not
   exist in `index.html`. No recenter, no hotkey.
4. **No smoothing.** Raw MediaPipe angles go straight over the wire — jittery.
   README documents a `0.35` smoothing setting that exists nowhere in the code.
5. **Latency claim vs architecture.** Advertises 30–80ms, but the only working
   phone path routes every frame through Cloudflare's edge and back.
6. **3DOF only.** No translation (X/Y/Z), no per-game profiles, no tray icon,
   no autostart — the things people pay for over free alternatives.
7. **Packaging.** "Install Python, run a .py" is not a product. Needs a
   PyInstaller exe + code signing cert (~$200–400/yr) or buyers hit SmartScreen.
8. **`cert.pem` / `key.pem` are in public git history** (commit `e8c97c4`).
   Self-signed localhost certs, low impact, but scrub before any buyer audit.

### Resolved, do not re-investigate

The Windows "port 8080 unreachable" hunt was a false trail. "Requested device
was not found" is the browser's `getUserMedia` error, printed by our own page
at `index.html:269`, which dumps `e.message` into the loading overlay. The PC
had no webcam. **aiohttp was binding port 8080 correctly the whole time.**
Firewall rules and netstat checks were chasing a ghost.

A GitHub PAT was embedded in `.git/config`; the remote is now SSH and the token
was already dead. Confirm it is revoked at github.com/settings/tokens.

## Verifying changes

```bash
python3 tools/ft_selftest.py    # runs anywhere, no Windows needed
```

Checks struct sizes, field offsets, radian conversion, round-tripping, and
inversion flags. Keep it passing — it is the guard against silently
reintroducing a wrong byte layout, which is a failure mode with no error message.

## Style

Keep answers short. Give % progress during multi-step work. Do not ask the user
to report back after hardware or in-game tests — they will initiate.
