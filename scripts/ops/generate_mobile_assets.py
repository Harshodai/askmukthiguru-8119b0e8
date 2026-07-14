#!/usr/bin/env python3
"""Generate branded Android + iOS app icons and splash screens.

Derives all native mobile assets from public/icon-512.png.
Idempotent: safe to re-run. No external deps beyond Pillow.

Usage:
    python3 scripts/ops/generate_mobile_assets.py
"""

from __future__ import annotations

import json
import struct
import zlib
from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ICON = REPO_ROOT / "public" / "icon-512.png"
SPLASH_BG = (0x0F, 0x17, 0x2A, 0xFF)  # #0f172a opaque
ADAPTIVE_BG = "#0F172A"  # for colors.xml

ANDROID_RES = REPO_ROOT / "android" / "app" / "src" / "main" / "res"
IOS_APPICONSET = (
    REPO_ROOT / "ios" / "App" / "App" / "Assets.xcassets" / "AppIcon.appiconset"
)
IOS_SPLASH = (
    REPO_ROOT / "ios" / "App" / "App" / "Assets.xcassets" / "Splash.imageset"
)

ANDROID_DENSITIES = {
    "mdpi": 48,
    "hdpi": 72,
    "xhdpi": 96,
    "xxhdpi": 144,
    "xxxhdpi": 192,
}
# Adaptive foreground: 108dp per density multiplier
ANDROID_FOREGROUND_DENSITIES = {
    "mdpi": 108,
    "hdpi": 162,
    "xhdpi": 216,
    "xxhdpi": 324,
    "xxxhdpi": 432,
}

written_files: list[str] = []


def _repair_png_crc(data: bytes) -> bytes:
    """Recompute CRCs for all PNG chunks (source file has bad IHDR CRC)."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return data
    out = bytearray(data[:8])
    pos = 8
    while pos < len(data):
        if pos + 8 > len(data):
            break
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        chunk_type = data[pos + 4 : pos + 8]
        chunk_data = data[pos + 8 : pos + 8 + length]
        crc = zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF
        out += struct.pack(">I", length)
        out += chunk_type
        out += chunk_data
        out += struct.pack(">I", crc)
        pos += 8 + length + 4
    return bytes(out)


def _load_icon() -> Image.Image:
    if not SOURCE_ICON.exists():
        raise FileNotFoundError(f"Source icon missing: {SOURCE_ICON}")
    raw = SOURCE_ICON.read_bytes()
    try:
        return Image.open(SOURCE_ICON).convert("RGBA")
    except Exception:
        # Source PNG has corrupted chunk CRCs; repair and retry.
        import io

        fixed = _repair_png_crc(raw)
        return Image.open(io.BytesIO(fixed)).convert("RGBA")


def _save(img: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, format="PNG", optimize=True)
    written_files.append(str(path.relative_to(REPO_ROOT)))


def _centered_on_bg(
    icon: Image.Image, size: tuple[int, int], bg, icon_scale: float
) -> Image.Image:
    """Place icon centered on a solid background of given size."""
    canvas = Image.new("RGBA", size, bg)
    target_w = int(size[0] * icon_scale)
    target_h = int(size[1] * icon_scale)
    resized = icon.resize((target_w, target_h), Image.LANCZOS)
    offset = ((size[0] - target_w) // 2, (size[1] - target_h) // 2)
    canvas.alpha_composite(resized, offset)
    return canvas


def _centered_transparent(
    icon: Image.Image, size: tuple[int, int], icon_scale: float
) -> Image.Image:
    """Icon centered on transparent background (for adaptive foreground)."""
    return _centered_on_bg(icon, size, (0, 0, 0, 0), icon_scale)


def gen_android_icons(icon: Image.Image) -> None:
    for density, px in ANDROID_DENSITIES.items():
        folder = ANDROID_RES / f"mipmap-{density}"
        resized = icon.resize((px, px), Image.LANCZOS)
        _save(resized, folder / "ic_launcher.png")
        _save(resized, folder / "ic_launcher_round.png")
    for density, px in ANDROID_FOREGROUND_DENSITIES.items():
        folder = ANDROID_RES / f"mipmap-{density}"
        fg = _centered_transparent(icon, (px, px), 0.60)
        _save(fg, folder / "ic_launcher_foreground.png")


def gen_android_splash(icon: Image.Image) -> None:
    splash_targets = [
        ("drawable", (1242, 2688)),
        ("drawable-port-mdpi", (480, 800)),
        ("drawable-port-hdpi", (720, 1280)),
        ("drawable-port-xhdpi", (960, 1600)),
        ("drawable-port-xxhdpi", (1280, 1920)),
        ("drawable-port-xxxhdpi", (1440, 2560)),
        ("drawable-land-mdpi", (800, 480)),
        ("drawable-land-hdpi", (1280, 720)),
        ("drawable-land-xhdpi", (1600, 960)),
        ("drawable-land-xxhdpi", (1920, 1280)),
        ("drawable-land-xxxhdpi", (2560, 1440)),
    ]
    for folder, size in splash_targets:
        splash = _centered_on_bg(icon, size, SPLASH_BG, 0.30)
        _save(splash, ANDROID_RES / folder / "splash.png")


def update_android_colors() -> None:
    colors_xml = ANDROID_RES / "values" / "ic_launcher_background.xml"
    if colors_xml.exists():
        content = colors_xml.read_text()
        if ADAPTIVE_BG.lower() not in content.lower():
            new = content.replace("#FFFFFF", ADAPTIVE_BG).replace(
                "#ffffff", ADAPTIVE_BG
            )
            colors_xml.write_text(new)
            written_files.append(str(colors_xml.relative_to(REPO_ROOT)))
        return
    colors_xml.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<resources>\n"
        f'    <color name="ic_launcher_background">{ADAPTIVE_BG}</color>\n'
        "</resources>\n"
    )
    written_files.append(str(colors_xml.relative_to(REPO_ROOT)))


def gen_ios_icon(icon: Image.Image) -> None:
    contents_path = IOS_APPICONSET / "Contents.json"
    contents = json.loads(contents_path.read_text())
    for entry in contents["images"]:
        fname = entry.get("filename")
        size_str = entry.get("size", "1024x1024")
        scale_str = entry.get("scale", "1x") or "1x"
        if not fname:
            continue
        try:
            logical = float(size_str.split("x")[0])
            scale = float(scale_str.rstrip("x") or "1")
        except ValueError:
            continue
        px = int(round(logical * scale))
        if px < 1:
            continue
        resized = icon.resize((px, px), Image.LANCZOS)
        _save(resized, IOS_APPICONSET / fname)


def gen_ios_splash(icon: Image.Image) -> None:
    contents_path = IOS_SPLASH / "Contents.json"
    contents = json.loads(contents_path.read_text())
    size = (2732, 2732)
    for entry in contents["images"]:
        fname = entry.get("filename")
        if not fname:
            continue
        splash = _centered_on_bg(icon, size, SPLASH_BG, 0.30)
        _save(splash, IOS_SPLASH / fname)


def main() -> None:
    icon = _load_icon()
    gen_android_icons(icon)
    gen_android_splash(icon)
    update_android_colors()
    gen_ios_icon(icon)
    gen_ios_splash(icon)
    print(f"Generated {len(written_files)} files:")
    for f in written_files:
        print(f"  {f}")


if __name__ == "__main__":
    main()