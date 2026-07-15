from __future__ import annotations

import hashlib
import re
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SOURCE_SHA256 = "0EF1C3988F4711352F4ABDF4A2EC1B3081E80A02F75FAE28A3B545A88DC82A16"
ICO_SIZES = {(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48), (64, 64), (128, 128), (256, 256)}
PNG_SIZES = {
    "assets/fuelopt-icon-1024.png": 1024,
    "static/icons/fuelopt-16.png": 16,
    "static/icons/fuelopt-32.png": 32,
    "static/icons/fuelopt-48.png": 48,
    "static/icons/fuelopt-180.png": 180,
    "static/icons/fuelopt-192.png": 192,
    "static/icons/fuelopt-512.png": 512,
}


def _assert(condition: bool, message: object) -> None:
    if not condition:
        raise AssertionError(message)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def run() -> None:
    source = ROOT / "assets" / "source" / "fuelopt-icon-approved.png"
    prepared = ROOT / "assets" / "fuelopt-icon-1024.png"
    ico = ROOT / "assets" / "fuelopt.ico"
    favicon = ROOT / "static" / "favicon.ico"
    for path in (source, prepared, ico, favicon):
        _assert(path.is_file(), f"Required brand asset is missing: {path.relative_to(ROOT)}")

    _assert(_sha256(source) == EXPECTED_SOURCE_SHA256, "Approved source SHA-256 changed")
    with Image.open(source) as image:
        _assert(image.format == "PNG", image.format)
        _assert(image.size == (1254, 1254), image.size)

    for relative, expected_size in PNG_SIZES.items():
        path = ROOT / relative
        _assert(path.is_file(), f"Required PNG is missing: {relative}")
        with Image.open(path) as image:
            _assert(image.format == "PNG", f"{relative}: {image.format}")
            _assert(image.size == (expected_size, expected_size), f"{relative}: {image.size}")
            _assert("A" in image.mode, f"{relative}: alpha channel missing")

    with Image.open(prepared) as image:
        _assert(bool(image.info.get("icc_profile")), "Prepared PNG has no embedded sRGB profile")
        alpha = image.getchannel("A")
        corners = (alpha.getpixel((0, 0)), alpha.getpixel((1023, 0)), alpha.getpixel((0, 1023)), alpha.getpixel((1023, 1023)))
        _assert(corners == (0, 0, 0, 0), f"Prepared PNG corners are not transparent: {corners}")
        _assert(alpha.getpixel((512, 512)) == 255, "Prepared PNG center is transparent")

    _assert(ico.read_bytes()[:4] == b"\x00\x00\x01\x00", "fuelopt.ico is not an ICO container")
    with Image.open(ico) as image:
        _assert(set(image.ico.sizes()) == ICO_SIZES, f"ICO sizes differ: {sorted(image.ico.sizes())}")
        for size in ICO_SIZES:
            frame = image.ico.getimage(size)
            _assert(frame.mode == "RGBA", f"ICO {size[0]}x{size[1]} is not 32-bit RGBA")
            _assert(frame.getpixel((0, 0))[3] == 0, f"ICO {size[0]}x{size[1]} corner is opaque")

    spec = (ROOT / "FuelOpt.spec").read_text(encoding="utf-8")
    installer = (ROOT / "installer" / "FuelOpt.iss").read_text(encoding="utf-8")
    index = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    generator = (ROOT / "scripts" / "generate_brand_assets.py").read_text(encoding="utf-8")
    _assert('ROOT / "assets" / "fuelopt.ico"' in spec and "icon=str(ICON_PATH)" in spec, "PyInstaller icon reference missing")
    _assert("Required application icon is missing" in spec, "PyInstaller must fail clearly when the ICO is absent")
    _assert(r'#define AppIconSource "..\assets\fuelopt.ico"' in installer, "Inno Setup ICO source missing")
    _assert("SetupIconFile={#AppIconSource}" in installer, "Inno Setup icon reference missing")
    _assert("/static/favicon.ico" in index and "/static/icons/fuelopt-32.png" in index, "index.html favicon references missing")

    tracked_brand_graphics = {path.relative_to(ROOT).as_posix() for path in (ROOT / "assets").rglob("*") if path.is_file() and path.suffix.lower() in {".png", ".ico", ".svg"}}
    _assert(tracked_brand_graphics == {"assets/source/fuelopt-icon-approved.png", "assets/fuelopt-icon-1024.png", "assets/fuelopt.ico"}, tracked_brand_graphics)
    _assert(not list((ROOT / "assets").rglob("*.svg")), "Raster wrapper must not be presented as a vector master")
    _assert("http://" not in generator and "https://" not in generator, "Generator must not fetch external graphics")

    concept_names = ("9367d54c", "concepto", "concept-guide", "logo-guide")
    repository_names = "\n".join(path.relative_to(ROOT).as_posix().lower() for path in ROOT.rglob("*") if path.is_file())
    for token in concept_names:
        _assert(token not in repository_names, f"Concept image appears to be included: {token}")

    personal_path = re.compile(r"(?:[A-Za-z]:\\Users\\|/Users/|OneDrive[\\/]Escritorio)", re.IGNORECASE)
    for relative in ("FuelOpt.spec", "installer/FuelOpt.iss", "scripts/generate_brand_assets.py", "assets/README.md"):
        _assert(not personal_path.search((ROOT / relative).read_text(encoding="utf-8")), f"Personal path found in {relative}")

    print("OK: FuelOpt brand assets are structurally valid")


if __name__ == "__main__":
    run()
