# SimTrack

**Head tracking for sim racing, using the phone you already own.**

Prop your phone on the monitor, open a link, and your in-game view follows
your head. No hardware, no phone app, nothing else to install on the PC.

- **Works with:** Assetto Corsa, iRacing, Assetto Corsa Competizione (TrackIR
  titles), Euro Truck Simulator 2, American Truck Simulator, BeamNG.drive
  (FreeTrack titles), and anything else through OpenTrack.
- **Needs:** a Windows 10/11 gaming PC, an iPhone or Android phone with a front
  camera, and both on the same WiFi.
- **Privacy:** the camera image never leaves the phone. Only three angles per
  frame travel to your PC over your own network.

---

## Install (PC)

1. Unzip `SimTrack-windows.zip` anywhere (e.g. `C:\SimTrack`).
2. Run **`SimTrack.exe`**.
3. Windows will ask twice on first run:
   - **SmartScreen** — "Windows protected your PC": click *More info → Run
     anyway*. Test builds are not code-signed yet.
   - **Firewall** — "Allow SimTrack to communicate": tick *Private networks*
     and click *Allow*. Without this your phone can't reach the PC.

A window opens with a QR code. Leave it open while you race — the helmet in
it mirrors your head once the phone is connected, so you can confirm every
axis at a glance before launching a game.

## Connect the phone (one time, about a minute)

1. **Scan the QR code** with your phone's camera. A setup page opens.
2. **Install the SimTrack certificate.** Your phone's browser only allows the
   camera on secure links, so SimTrack makes its own certificate for your PC.
   The setup page walks you through it:
   - *iPhone:* Download → Settings → *Profile Downloaded* → Install → then
     Settings → General → About → **Certificate Trust Settings** → switch on
     *SimTrack Local CA*. (That last toggle is the step people miss.)
   - *Android:* Settings → Security → Encryption & credentials → Install a
     certificate → CA certificate → pick `simtrack-ca.crt`.
3. **Open the tracker** from the link on that page and allow the camera.
   Add it to your home screen — next time it's one tap.

You only do this once per phone. If your PC's network address changes later,
SimTrack reissues its certificate automatically and the phone still trusts it.

## Race

1. Start **SimTrack**, then the game (that order — games look for head
   tracking when they launch).
2. Prop the phone on the monitor facing you, about arm's length away.
3. Sit in your normal driving position, look straight ahead, tap
   **Calibrate**.
4. Drive. The **Smoothing** slider trades steadiness for responsiveness —
   start around 60.

Keep the tracker page open. SimTrack stops the phone from sleeping, but a
call or switching apps pauses tracking until you come back; the game view
recentres rather than sticking. Plug the phone in for long sessions — camera
plus face tracking is heavy on battery.

### Per-game notes

| Game | What to do |
|---|---|
| Assetto Corsa, iRacing, ACC | Nothing. They detect head tracking on launch. |
| Euro Truck Simulator 2, ATS | Options → Controls → Head tracking → **FreeTrack** |
| BeamNG.drive | Settings → Controls → search "head tracking" → **FreeTrack** |
| Anything else | Install OpenTrack, set Input to *UDP over network*, port `4242` |

## When something doesn't work

**The QR code won't scan** — type the address shown under it into the
phone's browser instead.

**"This connection is not private" / certificate warning** — step 2 isn't
finished. On iPhone, the *Certificate Trust Settings* toggle is almost always
the missing piece.

**The camera won't start** — you're on the plain `http://` address. The
camera only works on the `https://` tracker link from the setup page.

**The view doesn't move in the game** — the game was started before SimTrack.
Quit the game, make sure SimTrack shows *Phone connected · tracking active*,
start the game again.

**The phone can't load the page at all** — the PC and phone are on different
networks (guest WiFi, mobile data), or the firewall prompt was declined. Both
must be on the same WiFi; re-allow SimTrack in *Windows Security → Firewall &
network protection → Allow an app*.

**Left/right feels reversed** — create a `config.json` next to `SimTrack.exe`:

```json
{ "invert_yaw": true }
```

(`invert_pitch` and `invert_roll` work the same way.)

**Reporting a bug** — send the log file from
`%LOCALAPPDATA%\SimTrack\simtrack.log` (paste that path into Explorer's
address bar) together with what you expected to happen.

---

## For developers

Run from source on Windows: install Python 3.10+ from python.org (tick *Add
to PATH*), then double-click `start.bat`. It installs the three dependencies
and launches the same app.

```bash
python3 tools/ft_selftest.py     # FreeTrack byte layout
python3 tools/test_handshake.py  # game-ID handshake
python3 tools/test_certs.py      # certificate authority
python3 tools/test_pose_math.py  # why CENTER subtracts a rotation, not angles
python3 tools/e2e_test.py        # phone → server → game pipeline, http + https
```

All four run on any platform. On the gaming PC, `python tools\ft_check.py
emit` sweeps a synthetic head into the game link with no phone involved.

`pyinstaller SimTrack.spec` produces the distributable folder; CI builds it on
every push (`build-exe.yml`) and the game client DLLs on changes under `dll/`
(`build-dlls.yml`).

## License

Proprietary — see `LICENSE`. Third-party components and their terms are listed
in `dll/PROVENANCE.txt`. (Version 0.1.0 was published under MIT and remains
available under it.)
