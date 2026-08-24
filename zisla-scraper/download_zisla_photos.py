"""
Downloads every development photo from Zisla (zisla.com) and organizes them
so each photo is traceable back to its development.

Layout:
  <out-dir>\\<urlAlias>\\<urlAlias>_001.webp, _002.webp, ...
  <out-dir>\\photo-manifest.csv   (Development, Development ID, urlAlias, Photo Index, Filename, Local Path, Source URL)

urlAlias is Zisla's own routing slug for the property (e.g. "quintana_roo-tulum-wamai")
and is guaranteed unique - it's what they use for the property's own URL - so it
doubles as a safe, human-readable folder name / unique identifier.

Resumable: re-running skips any photo file that's already on disk.

Usage:
  python download_zisla_photos.py
  python download_zisla_photos.py --out-dir "D:\\zisla-photos" --max-concurrency 8
  python download_zisla_photos.py --test          # only first 5 developments
  python download_zisla_photos.py --thumbnails    # smaller thumbnail images instead of full-res
"""
from __future__ import annotations

import argparse
import csv
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

from zisla_common import HEADERS, fetch_developments

INVALID_CHARS = re.compile(r'[<>:"/\\|?*]')


def safe_folder_name(name: str) -> str:
    return INVALID_CHARS.sub("_", name)


def download_one(url: str, path: Path) -> str:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        path.write_bytes(resp.content)
        return "OK"
    except Exception as e:
        return f"FAIL: {e}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default=r"G:\My Drive\zisla-tracker\photos")
    parser.add_argument("--max-concurrency", type=int, default=8)
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--thumbnails", action="store_true")
    args = parser.parse_args()

    print("Fetching developments from zisla.com ...")
    developments = fetch_developments()
    print(f"Total developments: {len(developments)}")

    if args.test:
        print("TEST MODE: limiting to first 5 developments")
        developments = developments[:5]

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Building download queue and manifest...")
    queue: list[tuple[str, Path]] = []
    manifest_rows = []

    for p in developments:
        photos = p.get("photos") or []
        if not photos:
            continue
        localized = p.get("localized") or {}
        folder = safe_folder_name(localized.get("urlAlias") or p["_id"])
        dev_dir = out_dir / folder
        dev_dir.mkdir(parents=True, exist_ok=True)

        for idx, photo in enumerate(photos, start=1):
            rel_url = (photo.get("thumbnail") if args.thumbnails else None) or photo.get("url")
            if not rel_url:
                continue
            ext = Path(rel_url).suffix or ".webp"
            filename = f"{folder}_{idx:03d}{ext}"
            local_path = dev_dir / filename
            full_url = f"https://www.zisla.com{rel_url}"

            queue.append((full_url, local_path))
            manifest_rows.append(
                {
                    "Development": localized.get("title"),
                    "Development ID": p.get("_id"),
                    "urlAlias": localized.get("urlAlias"),
                    "Photo Index": idx,
                    "Filename": filename,
                    "Local Path": str(local_path),
                    "Source URL": full_url,
                }
            )

    print(f"Queued {len(queue)} photos across {len(developments)} developments")
    manifest_path = out_dir / "photo-manifest.csv"
    with manifest_path.open("w", newline="", encoding="utf-8") as f:
        if manifest_rows:
            writer = csv.DictWriter(f, fieldnames=list(manifest_rows[0].keys()))
            writer.writeheader()
            writer.writerows(manifest_rows)
    print(f"Wrote manifest: {manifest_path}")

    to_download = [(url, path) for url, path in queue if not path.exists()]
    already_have = len(queue) - len(to_download)
    if already_have:
        print(f"{already_have} already on disk, skipping")
    print(f"Downloading {len(to_download)} photos with {args.max_concurrency} concurrent workers...")

    if not to_download:
        print("Nothing to download.")
        return

    failed = []
    done = 0
    with ThreadPoolExecutor(max_workers=args.max_concurrency) as pool:
        futures = {pool.submit(download_one, url, path): (url, path) for url, path in to_download}
        for future in as_completed(futures):
            url, path = futures[future]
            result = future.result()
            done += 1
            if result != "OK":
                failed.append({"Url": url, "Path": str(path)})
            if done % 250 == 0 or done == len(to_download):
                print(f"  {done} / {len(to_download)} downloaded ({len(failed)} failed so far)")

    print(f"Done. {len(to_download) - len(failed)} succeeded, {len(failed)} failed.")
    if failed:
        failed_path = out_dir / "failed-downloads.csv"
        with failed_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["Url", "Path"])
            writer.writeheader()
            writer.writerows(failed)
        print(f"Failed downloads logged to {failed_path} - re-run the script to retry them (existing files are skipped).")


if __name__ == "__main__":
    main()
