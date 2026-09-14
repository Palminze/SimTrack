# PyInstaller build recipe -- run: pyinstaller SimTrack.spec --noconfirm
# Produces dist/SimTrack/SimTrack.exe with everything beside it (onedir), which
# starts fast; onefile would unpack 23MB of MediaPipe on every launch.

a = Analysis(
    ["server_windows.py"],
    pathex=["."],
    binaries=[],
    datas=[
        ("index.html", "."),
        ("setup.html", "."),
        ("assets", "assets"),
        ("bin", "bin"),
        ("dll/games.csv", "dll"),
    ],
    hiddenimports=[],
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
