# SimTrack — working context

## START HERE (workplan, 2026-09-14 — owner is low on tokens; be frugal)

Rules for this session: do not re-read the whole repo, do not redesign
anything, do not reopen decisions listed below, do not ask the owner to
report test results. Read only the files a task names. Verify with the test
commands, commit small, push. One task at a time, in this order:

1. **Confirm the web-view window opens on Windows.** Owner runs
   `.\start.bat`. If it crashes: read `%LOCALAPPDATA%\SimTrack\simtrack.log`
   or the terminal, fix, push. If pywebview itself won't load, the app must
   have fallen back to the classic window — that is acceptable for launch.
   Files: `desktop.py`, `desktop.html`, `server_windows.py` (entry point only).
2. **Confirm CI builds the exe with pywebview.** Check
   github.com/Palminze/SimTrack/actions → latest *build-exe*. If the
   PyInstaller step fails, the fix is in `SimTrack.spec` (collect_all list /
   hiddenimports). Done when the artifact zip exists and `SimTrack.exe`
   opens on the owner's PC.
3. **EULA acceptance on first run.** In `desktop.html` add an overlay
   ("I accept the terms" → link to docs/terms.html text) shown until
   `state.eula_accepted` is true; add `Api.accept_eula()` in `desktop.py`
   writing a flag file in `certs.user_dir()`; include `eula_accepted` in
   `app_state()` in `server_windows.py`. Extend `tools/test_state.py`.
   ~60 lines total. Do not add license-key checks (deliberately month 2).
4. **Fill the site constants** when the owner provides them: the three
   values at the bottom of `docs/index.html` (checkout URL, Discord, email).
   Nothing else on the site needs changing.
5. **Sign the exe** once the owner has a code-signing cert: add a signtool
   step to `.github/workflows/build-exe.yml` after PyInstaller, cert + password
   from GitHub secrets. Then delete the "Windows warns me" FAQ answer's
   first sentence in `docs/index.html` and `README.md`.
6. **After the repo is private:** scrub `cert.pem`/`key.pem` from history
   (`git filter-repo --path cert.pem --path key.pem --invert-paths`, force
   push; owner re-clones on Windows).
7. Month 2, only if sales happen: license activation via Lemon Squeezy's
   license API; 6-DOF translation; per-game profiles; tray icon.

Verify any change with (all run on any OS, ~20 s total):
```
python3 tools/ft_selftest.py && python3 tools/test_handshake.py && \
python3 tools/test_certs.py && python3 tools/test_pose_math.py && \
python3 tools/test_helmet.py && python3 tools/test_state.py && \
python3 tools/e2e_test.py
```
Launch plan for the owner (not for you to redo):
https://claude.ai/code/artifact/f901a401-3da4-4857-b63f-65fa039e8742

---

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
- **Desktop window is `desktop.html` in pywebview (Edge WebView2)** with a
  Three.js helmet: smooth 96×64 shell, clearcoat paint, glossy smoked visor,
  procedural studio env map, ACES. It polls `app_state()` / `qr_matrix()`
  from `server_windows.py` at 30fps over the JS bridge (`tools/test_state.py`
  guards that contract). `desktop.run()` returns False if pywebview or the
  runtime is missing → the tkinter window (`helmet.py`, flat polygons) opens
  instead; `--classic` forces it. Three.js r158 UMD is self-hosted in
  `assets/three.min.js`.
- Mirror convention lives in two places that must agree: `YAW_SIGN /
  PITCH_SIGN / ROLL_SIGN` at the top of `desktop.html`'s script and of
  `helmet.py` (both currently +1, −1, −1). Flip both if a real test shows an
  axis moving the wrong way.

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

## Open items

See START HERE at the top — that list is the current order. Owner-side
items not for a session to do: Lemon Squeezy account, code-signing cert
purchase, repo private (kills GitHub Pages unless Pro, or move `docs/` to
its own public repo), Discord server, the friend's beta-tester post.

## Sales site

`docs/` is the public sales page (GitHub Pages) in the product's identity:
`index.html` (hero, how it works, games in three tiers, price, FAQ),
`terms.html`, `privacy.html`, `refunds.html`, `legal.css`, `fonts/`, `img/`.
The three constants at the bottom of `index.html` wire checkout, Discord
and email. Keep "verified" honest: only games a named person ran.

## Style

Keep answers short. Give % progress during multi-step work. Never ask the
owner to report back after hardware or in-game tests.
