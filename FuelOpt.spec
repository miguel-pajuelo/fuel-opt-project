# -*- mode: python ; coding: utf-8 -*-
import os
from importlib.metadata import PackageNotFoundError
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, copy_metadata


ROOT = Path(SPECPATH).resolve()
DIAGNOSTIC_CONSOLE = os.environ.get("FUELOPT_DIAGNOSTIC_CONSOLE") == "1"
BUILD_NAME = "FuelOptDiagnostic" if DIAGNOSTIC_CONSOLE else "FuelOpt"
ICON_PATH = ROOT / "assets" / "fuelopt.ico"
VERSION_FILE = ROOT / "build" / "metadata" / "FuelOpt.version.txt"
LEGAL_BUILD = ROOT / "build" / "legal-runtime"
LEGAL_INVENTORY = LEGAL_BUILD / "THIRD_PARTY_COMPONENTS.json"
LEGAL_TEXTS = LEGAL_BUILD / "third_party"

if not ICON_PATH.is_file():
    raise FileNotFoundError(f"Required application icon is missing: {ICON_PATH}")
if not VERSION_FILE.is_file():
    raise FileNotFoundError(f"Generated VERSIONINFO is missing: {VERSION_FILE}")
if not LEGAL_INVENTORY.is_file() or not LEGAL_TEXTS.is_dir():
    raise FileNotFoundError("Generated runtime legal inventory is missing; run scripts/build_onedir.cmd")

datas = [
    (str(ROOT / "static"), "static"),
    (str(ROOT / "data" / "db" / "gas_stations.sqlite"), "resources/seed"),
    (str(ROOT / "data" / "cache" / "minetur_snapshot.json"), "resources/snapshot"),
    (str(ROOT / "data" / "SEED_PROVENANCE.json"), "resources/seed"),
    (str(ROOT / "LICENSE"), "licenses"),
    (str(ROOT / "NOTICE"), "licenses"),
    (str(ROOT / "docs" / "DATA_SOURCES_AND_ATTRIBUTION.md"), "licenses"),
    (str(ROOT / "docs" / "THIRD_PARTY_NOTICES.md"), "licenses"),
    (str(LEGAL_INVENTORY), "licenses"),
    (str(LEGAL_TEXTS), "licenses/third_party"),
]

# Keep the installed seed's name distinct from the mutable user database.
# PyInstaller data tuples preserve the source filename, so the spec renames it
# after Analysis by mapping it to the expected logical resource name below.
seed_source = str(ROOT / "data" / "db" / "gas_stations.sqlite")

for distribution in (
    "certifi",
    "fastapi",
    "pydantic",
    "requests",
    "slowapi",
    "starlette",
    "uvicorn",
):
    try:
        datas += copy_metadata(distribution)
    except PackageNotFoundError:
        pass

datas += collect_data_files("certifi")
hiddenimports = [
    "app.api.main",
    "app.catalog.refresh_service",
    "app.config",
    "scripts.rebuild_station_catalog",
    "scripts.refresh_catalog",
]

a = Analysis(
    [str(ROOT / "fuelopt_launcher.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "IPython",
        "PyInstaller",
        "_pytest",
        "app.legacy_cli",
        "bcrypt",
        "bs4",
        "cryptography",
        "h2",
        "httpcore",
        "httpx",
        "httptools",
        "jupyter",
        "matplotlib",
        "numpy",
        "pandas",
        "PIL",
        "pymongo",
        "pytest",
        "PySide6",
        "scipy",
        "setuptools",
        "soupsieve",
        "tkinter",
        "uvloop",
        "watchfiles",
        "websockets",
        "wsproto",
        "zstandard",
        "zmq",
    ],
    noarchive=False,
    optimize=0,
)

# Rename only the immutable packaged seed; the user copy is created at runtime.
for index, entry in enumerate(a.datas):
    destination, source, kind = entry
    if str(Path(source).resolve()) == seed_source and destination.endswith("gas_stations.sqlite"):
        a.datas[index] = ("resources/seed/gas_stations.seed.sqlite", source, kind)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=BUILD_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=DIAGNOSTIC_CONSOLE,
    icon=str(ICON_PATH),
    version=str(VERSION_FILE),
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
    upx=False,
    upx_exclude=[],
    name=BUILD_NAME,
)
