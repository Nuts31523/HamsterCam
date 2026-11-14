from PyInstaller.utils.hooks import collect_dynamic_libs


analysis = Analysis(
    ["main.py"],
    pathex=[],
    binaries=collect_dynamic_libs("mediapipe"),
    datas=[("models/face_landmarker.task", "models")],
    hiddenimports=["pyvirtualcam._native_windows_obs", "pyvirtualcam._native_windows_unity_capture"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "PyQt5", "PyQt6", "PySide2"],
    noarchive=False,
)
# Qt links to the ICU ABI supplied by Windows. A same-named ICU from another
# project's PATH can otherwise be picked up and shadow the Windows library.
system_icu = {"icu.dll", "icuuc.dll", "icuin.dll"}
analysis.binaries = [
    entry for entry in analysis.binaries
    if entry[0].rsplit("\\", 1)[-1].lower() not in system_icu
]
modules = PYZ(analysis.pure)
exe = EXE(
    modules,
    analysis.scripts,
    [],
    name="HamsterCam",
    exclude_binaries=True,
    console=False,
    upx=False,
)
distribution = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    name="HamsterCam",
    upx=False,
)
