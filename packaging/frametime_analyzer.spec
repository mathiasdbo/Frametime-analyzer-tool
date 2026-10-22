# PyInstaller spec: builds one folder holding the desktop GUI ("FrametimeAnalyzer") and the CLI ("fta").
# On macOS the folder is additionally wrapped in "Frametime Analyzer.app".
#
#   pip install -e ".[gui]" pyinstaller
#   pyinstaller packaging/frametime_analyzer.spec --noconfirm
import sys

from PyInstaller.utils.hooks import collect_data_files

HERE = SPECPATH  # noqa: F821 (provided by PyInstaller)
APP_NAME = "FrametimeAnalyzer"
DATAS = collect_data_files("frametime_analyzer")  # Studio web UI / OBS overlay HTML
# Declared dependencies that the code never imports, plus dev / GUI toolkits we don't use
EXCLUDES = ["av", "scipy", "tkinter", "matplotlib", "IPython", "pytest", "PyQt5", "PyQt6", "PySide2"]


def analysis(script):
    return Analysis(  # noqa: F821
        [f"{HERE}/{script}"],
        datas=DATAS,
        hiddenimports=["imageio_ffmpeg.binaries"],
        excludes=EXCLUDES,
        noarchive=False,
    )


gui_a = analysis("fta_gui.py")
cli_a = analysis("fta_cli.py")

gui_exe = EXE(  # noqa: F821
    PYZ(gui_a.pure),  # noqa: F821
    gui_a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    console=False,
    upx=False,
)
cli_exe = EXE(  # noqa: F821
    PYZ(cli_a.pure),  # noqa: F821
    cli_a.scripts,
    [],
    exclude_binaries=True,
    name="fta",
    console=True,
    upx=False,
)

coll = COLLECT(  # noqa: F821
    gui_exe,
    cli_exe,
    gui_a.binaries,
    gui_a.datas,
    cli_a.binaries,
    cli_a.datas,
    name=APP_NAME,
    upx=False,
)

if sys.platform == "darwin":
    app = BUNDLE(  # noqa: F821
        coll,
        name="Frametime Analyzer.app",
        bundle_identifier="io.github.mathiasdbo.frametime-analyzer",
        info_plist={
            "CFBundleShortVersionString": __import__("frametime_analyzer").__version__,
            "NSHighResolutionCapable": True,
            "NSCameraUsageDescription": "Live analysis of capture cards such as the Elgato 4K S.",
        },
    )
