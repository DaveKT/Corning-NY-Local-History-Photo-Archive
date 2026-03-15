"""
image_catalog.py

Scans a folder of images and produces:
  - image_catalog.csv   : one row per image with metadata
  - image_catalog.log   : errors for files that could not be processed

Usage:
    python image_catalog.py <folder_path> [--output <csv_path>]

Dependencies:
    pip install Pillow
"""

import argparse
import csv
import hashlib
import logging
import os
import sys
from pathlib import Path

from PIL import Image, UnidentifiedImageError

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SUPPORTED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif",
    ".webp", ".ico", ".ppm", ".pgm", ".pbm", ".pnm", ".avif",
}

CSV_FIELDS = [
    "filename",
    "extension",
    "size_bytes",
    "size_human",
    "width_px",
    "height_px",
    "megapixels",
    "colorspace",
    "md5",
    "sha256",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def human_size(size_bytes: int) -> str:
    """Convert bytes to a human-readable string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def file_hashes(path: Path) -> tuple[str, str]:
    """Return (md5_hex, sha256_hex) for a file."""
    md5 = hashlib.md5()
    sha256 = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            md5.update(chunk)
            sha256.update(chunk)
    return md5.hexdigest(), sha256.hexdigest()


def collect_image_row(path: Path) -> dict:
    """Return a metadata dict for a single image file."""
    stat = path.stat()
    size_bytes = stat.st_size
    md5_hex, sha256_hex = file_hashes(path)

    with Image.open(path) as img:
        width, height = img.size
        colorspace = img.mode

    megapixels = round((width * height) / 1_000_000, 2)

    return {
        "filename":    path.name,
        "extension":   path.suffix.lstrip(".").lower(),
        "size_bytes":  size_bytes,
        "size_human":  human_size(size_bytes),
        "width_px":    width,
        "height_px":   height,
        "megapixels":  megapixels,
        "colorspace":  colorspace,
        "md5":         md5_hex,
        "sha256":      sha256_hex,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Catalog images in a folder.")
    parser.add_argument("folder", help="Path to the image folder.")
    parser.add_argument(
        "--output", default=None,
        help="Output CSV path (default: <folder>/image_catalog.csv).",
    )
    args = parser.parse_args()

    folder = Path(args.folder).resolve()
    if not folder.is_dir():
        sys.exit(f"Error: '{folder}' is not a directory.")

    csv_path = Path(args.output) if args.output else folder / "image_catalog.csv"
    log_path = csv_path.with_suffix(".log")

    # Configure error logger
    logging.basicConfig(
        filename=log_path,
        filemode="w",
        level=logging.ERROR,
        format="%(asctime)s  %(levelname)s  %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    candidates = sorted(
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    )

    if not candidates:
        print(f"No supported image files found in '{folder}'.")
        sys.exit(0)

    rows = []
    error_count = 0

    for path in candidates:
        try:
            row = collect_image_row(path)
            rows.append(row)
        except UnidentifiedImageError:
            logging.error("%s — not a recognized image format", path.name)
            error_count += 1
        except PermissionError as exc:
            logging.error("%s — permission denied: %s", path.name, exc)
            error_count += 1
        except Exception as exc:  # noqa: BLE001
            logging.error("%s — unexpected error: %s", path.name, exc)
            error_count += 1

    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Cataloged : {len(rows):,} image(s)")
    print(f"Errors    : {error_count:,}")
    print(f"CSV       : {csv_path}")
    if error_count:
        print(f"Log       : {log_path}")


if __name__ == "__main__":
    main()