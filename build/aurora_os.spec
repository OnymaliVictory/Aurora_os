# PyInstaller recipe: turns Aurora OS into a Windows program (no Python needed on the shop computer).
# Run from the project folder:   pyinstaller build/aurora_os.spec --noconfirm
import os
root = os.path.abspath(os.path.join(SPECPATH, ".."))
a = Analysis(
    [os.path.join(root, "run.py")],
    pathex=[root],
    datas=[(os.path.join(root, "aurora", "templates"), "templates"),
           (os.path.join(root, "aurora", "static"), "static")],
    hiddenimports=["waitress", "webview", "webview.platforms.winforms", "webview.platforms.edgechromium"],
    excludes=["tkinter", "pytest", "playwright"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="AuroraOS", console=False,
          icon=os.path.join(root, "build", "aurora.ico"))
coll = COLLECT(exe, a.binaries, a.datas, name="AuroraOS")
