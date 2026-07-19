from __future__ import annotations

import argparse
import hashlib
from collections import deque
from pathlib import Path

from PIL import Image, ImageCms, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
APPROVED_SHA256 = "33A01D179FB6297AB711DB5980D45E6A15A568053D1A1AD94279579008ACECCD"
ORIGINAL_SIZE = (1254, 1254)
ICO_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)
WEB_SIZES = (16, 32, 48, 180, 192, 512)
SRGB_PROFILE = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def validate_source(path: Path) -> Image.Image:
    if not path.is_file():
        raise FileNotFoundError(f"Approved brand source not found: {path}")
    actual_hash = sha256(path)
    if actual_hash != APPROVED_SHA256:
        raise ValueError(
            "Brand source SHA-256 does not match the approved image: "
            f"expected {APPROVED_SHA256}, got {actual_hash}"
        )
    with Image.open(path) as source:
        if source.format != "PNG":
            raise ValueError(f"Approved brand source must be PNG, got {source.format!r}")
        if source.size != ORIGINAL_SIZE:
            raise ValueError(
                f"Approved brand source must be {ORIGINAL_SIZE[0]}x{ORIGINAL_SIZE[1]}, "
                f"got {source.width}x{source.height}"
            )
        return source.convert("RGB")


def connected_exterior_mask(image: Image.Image) -> Image.Image:
    """Select only the pale neutral background connected to the canvas border."""
    width, height = image.size
    pixels = image.load()
    exterior = bytearray(width * height)
    queue: deque[tuple[int, int]] = deque()

    def eligible(x: int, y: int) -> bool:
        red, green, blue = pixels[x, y]
        return min(red, green, blue) >= 225 and max(red, green, blue) - min(red, green, blue) <= 35

    def enqueue(x: int, y: int) -> None:
        offset = y * width + x
        if not exterior[offset] and eligible(x, y):
            exterior[offset] = 255
            queue.append((x, y))

    for x in range(width):
        enqueue(x, 0)
        enqueue(x, height - 1)
    for y in range(height):
        enqueue(0, y)
        enqueue(width - 1, y)

    while queue:
        x, y = queue.popleft()
        if x:
            enqueue(x - 1, y)
        if x + 1 < width:
            enqueue(x + 1, y)
        if y:
            enqueue(x, y - 1)
        if y + 1 < height:
            enqueue(x, y + 1)

    return Image.frombytes("L", image.size, bytes(exterior))


def prepared_icon(source: Image.Image) -> Image.Image:
    exterior = connected_exterior_mask(source)
    alpha = Image.new("L", source.size, 255)
    alpha_pixels = alpha.load()
    exterior_pixels = exterior.load()
    width, height = source.size
    for y in range(height):
        for x in range(width):
            if exterior_pixels[x, y]:
                alpha_pixels[x, y] = 0

    rgba = source.convert("RGBA")
    rgba.putalpha(alpha)
    return rgba.resize((1024, 1024), Image.Resampling.LANCZOS)


def save_png(image: Image.Image, path: Path, size: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    resized = image if image.size == (size, size) else image.resize((size, size), Image.Resampling.LANCZOS)
    resized.save(
        path,
        format="PNG",
        optimize=False,
        compress_level=9,
        icc_profile=SRGB_PROFILE,
    )


def save_ico(image: Image.Image, path: Path, sizes: tuple[int, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(
        path,
        format="ICO",
        sizes=[(size, size) for size in sizes],
        bitmap_format="bmp",
    )


def contact_sheet(source: Image.Image, prepared: Image.Image, path: Path) -> None:
    entries = [("Original", source.convert("RGBA")), ("Prepared", prepared)]
    entries.extend((f"{size}x{size}", prepared.resize((size, size), Image.Resampling.LANCZOS)) for size in (256, 64, 48, 32, 24, 16))
    tile = 300
    row_height = 480
    sheet = Image.new("RGB", (tile * 4, row_height * 2), "#d7d7d7")
    draw = ImageDraw.Draw(sheet)
    for index, (label, icon) in enumerate(entries):
        x = (index % 4) * tile
        y = (index // 4) * row_height
        checker = Image.new("RGB", (256, 256), "white")
        checker_draw = ImageDraw.Draw(checker)
        for cy in range(0, 256, 16):
            for cx in range(0, 256, 16):
                if (cx // 16 + cy // 16) % 2:
                    checker_draw.rectangle((cx, cy, cx + 15, cy + 15), fill="#bdbdbd")
        preview = icon.copy()
        preview.thumbnail((256, 256), Image.Resampling.LANCZOS)
        checker.paste(preview, ((256 - preview.width) // 2, (256 - preview.height) // 2), preview)
        sheet.paste(checker, (x + 22, y + 36))
        draw.text((x + 22, y + 12), label, fill="black")
        if icon.width < 256:
            scale = max(1, min(4, 128 // icon.width))
            zoom = icon.resize((icon.width * scale, icon.height * scale), Image.Resampling.NEAREST)
            sheet.paste(zoom, (x + 22, y + 316), zoom)
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path, format="PNG", compress_level=9)


def generate(source_path: Path, contact_sheet_path: Path | None) -> None:
    source = validate_source(source_path)
    prepared = prepared_icon(source)

    save_png(prepared, ROOT / "assets" / "fuelopt-icon-1024.png", 1024)
    save_ico(prepared, ROOT / "assets" / "fuelopt.ico", ICO_SIZES)
    for size in WEB_SIZES:
        save_png(prepared, ROOT / "static" / "icons" / f"fuelopt-{size}.png", size)
    save_ico(prepared, ROOT / "static" / "favicon.ico", (16, 32, 48))
    if contact_sheet_path is not None:
        contact_sheet(source, prepared, contact_sheet_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate FuelOpt brand assets from the approved raster source.")
    parser.add_argument(
        "source",
        nargs="?",
        type=Path,
        default=ROOT / "assets" / "source" / "fuelopt-icon-approved.png",
    )
    parser.add_argument("--contact-sheet", type=Path, help="Optional untracked visual QA sheet.")
    args = parser.parse_args()
    generate(args.source.resolve(), args.contact_sheet.resolve() if args.contact_sheet else None)
    print(f"Approved source SHA-256: {sha256(args.source.resolve())}")
    print("Generated FuelOpt PNG and multi-resolution ICO assets.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
