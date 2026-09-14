# SimTrack — working context

Phone-camera head tracking for sim racing. MediaPipe runs in the phone
browser, pose streams over WebSocket to the PC, the PC writes FreeTrack shared
memory, and two client DLLs hand it to games. Customers install one thing.

## Machines

- **Mac** (`~/simtrack`) — development. No shared memory here; the game side
  cannot be exercised, everything else can.
- **Windows** (`C:\Users\mielk\SimTrack`) — the gaming PC. All real testing.
- Sync is this git repo, SSH remote `git@github.com:Palminze/SimTrack.git`.

## Decisions (owner's, final)

- **Fully commercial, closed source.** `LICENSE` is proprietary as of
  2026-09-14; v0.1.0 stays MIT and forkable forever. Repo must go private —
  still public as of this writing, owner's click.
- **No OpenTrack, no tunnel, no third party.** SimTrack is its own
  certificate authority (`certs.py`) and ships its own game client DLLs.
  The earlier "buy a domain + wildcard cert" plan is **unnecessary for HTTPS**
  now; a domain would only matter for a future license server.
- **TrackIR interface emulation accepted** with its NaturalPoint risk, flagged
  three times. One IP-lawyer hour recommended before selling.

## Architecture

```
PHONE  index.html (https only)  MediaPipe → One Euro → calibrate → WebSocket
PC     server_windows.py
         :8080 http   setup.html + /simtrack-ca.crt   (one-time phone onboarding)
         :8443 https  index.html + assets/ + /ws       (the tracker)
         certs.py     local CA in %LOCALAPPDATA%\SimTrack, leaf for the LAN IP
         freetrack.py FT_SharedMem (108-byte FreeTrack 2.0) + GameID handshake
         UDP :4242    optional, for OpenTrack users
GAMES  bin/NPClient(.64).dll        → TrackIR titles (AC, iRacing, ACC)
       bin/freetrackclient(.64).dll → FreeTrack titles (ETS2, ATS, BeamNG)
       found via HKCU registry keys set at startup
```

`BASE` is `sys._MEIPASS` when frozen (PyInstaller onedir) else the source dir;
`config.json` is read from next to the exe. Frozen runs log to
`%LOCALAPPDATA%\SimTrack\simtrack.log` (no console).

## Verified

- FreeTrack byte layout, radians, mutex, handshake — `tools/ft_selftest.py`,
  `tools/test_handshake.py`.
- UDP → OpenTrack → Assetto Corsa moved the in-game view (2026-09-08, on the
  Windows PC, synthetic sweep). Port is **4242**.
- Certificate authority meets iOS leaf rules — `tools/test_certs.py`.
- http/https surface, wss pipeline, asset MIME + traversal, hostile input,
  recentre on disconnect — `tools/e2e_test.py` (31 checks).
- GUI builds all cards (fake-Tk smoke run; a real bug was found this way once).
- `helmet.py` draws a flat-shaded racing helmet on a tkinter canvas that
  mirrors the driver (`tools/test_helmet.py`). If a real test shows an axis
  moving the wrong way, flip the matching `YAW_SIGN / PITCH_SIGN / ROLL_SIGN`
  at the top of that file — nothing else encodes the mirror convention.

## Not yet verified — the owner will run these

1. **A real head driving Assetto Corsa** through the DLL path (no OpenTrack).
   Unknown until then: pose accuracy, whether One Euro defaults (minCutoff
   4.5→0.5, beta 0.05) feel right, axis directions (`invert_*` in config).
2. **Phone certificate install flow** on a real iPhone and Android.
3. **The CI-built `SimTrack.exe`** on the Windows PC (`build-exe.yml` artifact).

Do not ask the owner to report back; they will initiate.

## Do not re-investigate

- "Requested device was not found" on the PC browser was `getUserMedia` on a
  PC with no webcam, printed by our own page. The server was fine.
- OpenTrack "not receiving": it was not bound until relaunched; a `4376` read
  off its dialog was the output port. Ask the OS what is bound, not the UI.
- `cert.pem`/`key.pem` exist in public git history (commit `e8c97c4`);
  scrub before any buyer audit. A dead GitHub PAT was in `.git/config`, gone.
- Assetto Corsa has **no FreeTrack toggle**; it reads TrackIR automatically.
- **Axis crosstalk is geometry, not tracker noise.** A phone below the monitor
  looks up at the head, so a pure yaw decomposes in camera Euler angles into
  yaw + roll + pitch (25° tilt: 13.7° phantom roll). Centering therefore
  stores the rest orientation R0 and measures every frame as R0ᵀ·R; angle
  subtraction cannot fix this. `tools/test_pose_math.py` shows both.
- Games with `since != V160` in `dll/games.csv` scramble their data; the
  handshake supplies the table. Pose writes stop at byte 92 so they never
  clobber the handshake tail.

## Provenance

`dll/PROVENANCE.txt`. `npclient.c` is linuxtrack's clean-room permissive
implementation (vendored via opentrack contrib); `freetrackclient.c` was
written for SimTrack, not taken from opentrack's GPL-descended one;
`games.csv` is FaceTrackNoIR heritage under its 2015 permissive relicense.

## Open items, in order

1. Owner's three verifications above.
2. Repo private.
3. Code signing (Microsoft Artifact Signing $9.99/mo if eligible, else OV
   cert ~$219/yr) — until then testers click through SmartScreen.
4. Scrub `e8c97c4` certs from history before any external audit.
5. Nice-to-have: 6DOF translation, per-game profiles, tray icon, autostart.

## Style

Keep answers short. Give % progress during multi-step work. Never ask the
owner to report back after hardware or in-game tests.
