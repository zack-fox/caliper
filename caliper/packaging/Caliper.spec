# -*- mode: python ; coding: utf-8 -*-
"""Self-contained macOS app: runtime, built-in rule pack, and workbook masters."""

from pathlib import Path
import tomllib

ROOT = Path(SPECPATH).resolve().parent
with (ROOT / "pyproject.toml").open("rb") as manifest:
    VERSION = tomllib.load(manifest)["project"]["version"]

a = Analysis(
    [str(ROOT / "app" / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(ROOT / "packs"), "packs"),
        (str(ROOT / "templates"), "templates"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Caliper",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Caliper",
)
app = BUNDLE(
    coll,
    name="Caliper.app",
    icon=None,
    bundle_identifier="com.caliper.assessment",
    version=VERSION,
    info_plist={
        "CFBundleDisplayName": "Caliper",
        "CFBundleVersion": VERSION,
        "LSMinimumSystemVersion": "11.0",
    },
)
