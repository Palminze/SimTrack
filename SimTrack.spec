# PyInstaller build recipe -- run: pyinstaller SimTrack.spec --noconfirm
# Produces dist/SimTrack/SimTrack.exe with everything beside it (onedir), which
# starts fast; onefile would unpack 23MB of MediaPipe on every launch.

from PyInstaller.utils.hooks import collect_all

# pywebview's Windows backend is .NET-hosted (pythonnet + clr_loader); PyInstaller
# needs to be told to carry all of it or the web view silently fails to import.
_datas, _binaries, _hidden = [], [], []
for pkg in ("webview", "pythonnet", "clr_loader", "proxy_tools", "bottle"):
    try:
        d, b, h = collect_all(pkg)
        _datas += d; _binaries += b; _hidden += h
    except Exception:
        pass

a = Analysis(
    ["server_windows.py"],
    pathex=["."],
    binaries=_binaries,
    datas=[
        ("index.html", "."),
        ("setup.html", "."),
        ("desktop.html", "."),
        ("assets", "assets"),
        ("bin", "bin"),
        ("dll/games.csv", "dll"),
    ] + _datas,
    hiddenimports=["clr"] + _hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter.test", "unittest", "pydoc"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SimTrack",
    debug=False,
    strip=False,
    upx=False,
    console=False,          # GUI app; output goes to %LOCALAPPDATA%\SimTrack\simtrack.log
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="SimTrack",
)
