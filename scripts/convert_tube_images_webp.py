#!/usr/bin/env python3
"""
Convert tube thumbnail images (JPG/PNG) to WebP at thumbnail dimensions.
Run once. Keep originals for fallback. nginx will serve WebP automatically.

Usage:
  python scripts/convert_tube_images_webp.py
  python scripts/convert_tube_images_webp.py --force   # overwrite existing webp
  python scripts/convert_tube_images_webp.py --dry-run # preview only
"""
import argparse
from pathlib import Path
from PIL import Image

TUBE_IMG_DIR = Path(__file__).parent.parent / "static" / "images" / "tube"
MAX_WIDTH = 480
WEBP_QUALITY = 82


def convert(src: Path, force: bool) -> str:
    dst = src.with_suffix(".webp")
    if dst.exists() and not force:
        return "SKIP"
    img = Image.open(src).convert("RGB")
    if img.width > MAX_WIDTH:
        ratio = MAX_WIDTH / img.width
        img = img.resize((MAX_WIDTH, int(img.height * ratio)), Image.LANCZOS)
    img.save(dst, "webp", quality=WEBP_QUALITY, method=6)
    orig_kb = src.stat().st_size // 1024
    webp_kb = dst.stat().st_size // 1024
    return f"OK ({orig_kb}KB → {webp_kb}KB)"


def main():
    parser = argparse.ArgumentParser(description="Convert tube thumbnails to WebP")
    parser.add_argument("--force", action="store_true", help="Overwrite existing WebP files")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no writes")
    args = parser.parse_args()

    sources = sorted(
        p for p in TUBE_IMG_DIR.iterdir()
        if p.suffix.lower() in (".jpg", ".jpeg", ".png") and p.stem + ".webp" != p.name
    )

    ok = skipped = 0
    total_orig = total_webp = 0

    for src in sources:
        if args.dry_run:
            print(f"  {src.name} → (would convert)")
            continue
        result = convert(src, args.force)
        status = "SKIP" if result == "SKIP" else "OK"
        print(f"  {src.name:<45} {result}")
        if status == "SKIP":
            skipped += 1
        else:
            ok += 1
            total_orig += src.stat().st_size
            dst = src.with_suffix(".webp")
            total_webp += dst.stat().st_size

    if not args.dry_run:
        print(f"\nDone: {ok} converted, {skipped} skipped / {len(sources)} total")
        if ok > 0:
            saved_pct = int(100 * (1 - total_webp / total_orig)) if total_orig else 0
            print(f"Size: {total_orig // 1024 // 1024}MB → {total_webp // 1024 // 1024}MB ({saved_pct}% saved)")
    else:
        print(f"\n[DRY RUN] {len(sources)} files would be processed")


if __name__ == "__main__":
    main()
