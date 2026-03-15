#!/usr/bin/env python3
"""
Download full-resolution images from the Corning NY History photo archive.
https://corningnyhistory.com/local-history-photo-archive/

Usage:
    python download_archive.py [--output-dir ./photos] [--workers 4] [--delay 0.5]

Dependencies:
    pip install requests beautifulsoup4
"""

import argparse
import time
from pathlib import Path
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://corningnyhistory.com/local-history-photo-archive/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; archive-downloader/1.0)"
}


def fetch_image_urls(page_url: str) -> list[str]:
    """Parse the archive page and return all unique image URLs."""
    resp = requests.get(page_url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    urls = []
    seen = set()
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if "corningnyhistory.com/wp-content/uploads" in src:
            clean = src.split("?")[0]
            if clean not in seen:
                seen.add(clean)
                urls.append(clean)

    return urls


def download_image(url: str, output_dir: Path, delay: float) -> tuple[str, str]:
    """
    Download a single image. Returns (url, status) where status is one of:
    'ok', 'skipped', or an error message.
    """
    filename = Path(urlparse(url).path).name
    dest = output_dir / filename

    if dest.exists():
        return url, "skipped"

    time.sleep(delay)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=60, stream=True)
        resp.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                f.write(chunk)
        return url, "ok"
    except Exception as exc:
        return url, f"error: {exc}"


def main():
    parser = argparse.ArgumentParser(description="Download Corning NY History photo archive.")
    parser.add_argument("--output-dir", default="./photos", help="Destination folder (default: ./photos)")
    parser.add_argument("--workers", type=int, default=4, help="Concurrent download threads (default: 4)")
    parser.add_argument("--delay", type=float, default=0.25, help="Per-thread delay between requests in seconds (default: 0.25)")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Fetching image list from {BASE_URL} ...")
    urls = fetch_image_urls(BASE_URL)
    print(f"Found {len(urls)} images.")

    ok = skipped = errors = 0

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(download_image, url, output_dir, args.delay): url
            for url in urls
        }
        for i, future in enumerate(as_completed(futures), 1):
            url, status = future.result()
            filename = Path(urlparse(url).path).name
            if status == "ok":
                ok += 1
                print(f"[{i}/{len(urls)}] downloaded  {filename}")
            elif status == "skipped":
                skipped += 1
                print(f"[{i}/{len(urls)}] skipped     {filename}")
            else:
                errors += 1
                print(f"[{i}/{len(urls)}] FAILED      {filename}  ({status})")

    print(f"\nDone. {ok} downloaded, {skipped} skipped, {errors} failed.")
    print(f"Files saved to: {output_dir.resolve()}")


if __name__ == "__main__":
    main()