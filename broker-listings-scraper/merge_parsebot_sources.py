"""
Merges newly-converted parse.bot-sourced CSVs into the latest deduped
dataset, re-dedups, and re-tags regions to produce the next version.

Usage:
  python merge_parsebot_sources.py --base-version 7 --out-version 8 listings_inmuebles24_playa_rentals_deptos.csv [more.csv ...]
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dedup import dedup, load_rows, write_workbook
from build_final_mexico_city import REGION_KEYWORDS, classify_regions, is_unrelated

HERE = Path(__file__).parent


def load_csv_rows(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-version", type=int, required=True, help="version number of the deduped dataset to start from, e.g. 7")
    parser.add_argument("--out-version", type=int, required=True, help="version number to write, e.g. 8")
    parser.add_argument("csvs", nargs="+", help="new source CSVs to merge in")
    args = parser.parse_args()

    new_csv_paths = [Path(p) for p in args.csvs]

    base_rows = load_rows(HERE / f"listings_all_regions_deduped_v{args.base_version}.xlsx")
    print(f"Loaded {len(base_rows)} rows from v{args.base_version} deduped dataset")

    for r in base_rows:
        r.pop("Source Count", None)
        r.pop("Source Brokers", None)
        r.pop("Source URLs", None)
        r.pop("Region Match", None)

    new_rows: list[dict] = []
    for path in new_csv_paths:
        rows = load_csv_rows(path)
        print(f"Loaded {len(rows)} rows from {path.name}")
        new_rows.extend(rows)

    all_rows = base_rows + new_rows
    print(f"\nCombined raw total: {len(all_rows)}")

    deduped = dedup(all_rows, use_image_hash=True)
    print(f"Deduped to {len(deduped)} unique listings ({len(all_rows) - len(deduped)} duplicates merged)")

    out_xlsx = HERE / f"listings_all_regions_deduped_v{args.out_version}.xlsx"
    write_workbook(deduped, out_xlsx)
    print(f"Wrote {out_xlsx}")

    dropped = 0
    kept_rows = []
    for row in deduped:
        matches = classify_regions(row)
        if is_unrelated(row, matches):
            dropped += 1
            continue
        row["Region Match"] = "; ".join(matches) if matches else "No Location Signal"
        kept_rows.append(row)

    print(f"Dropped {dropped} unrelated-region rows; kept {len(kept_rows)}")

    region_counts = {r: 0 for r in REGION_KEYWORDS}
    region_counts["No Location Signal"] = 0
    for row in kept_rows:
        if row["Region Match"] == "No Location Signal":
            region_counts["No Location Signal"] += 1
        else:
            for r in row["Region Match"].split("; "):
                region_counts[r] += 1
    print("\nRegion counts (rows can match >1 region):")
    for r, c in region_counts.items():
        print(f"  {r}: {c}")

    all_fields = list(kept_rows[0].keys()) if kept_rows else []
    out_csv = HERE / f"all_regions_listings_filtered_v{args.out_version}.csv"
    with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=all_fields)
        writer.writeheader()
        writer.writerows(kept_rows)
    print(f"\nWrote {out_csv} ({len(kept_rows)} rows)")


if __name__ == "__main__":
    main()
