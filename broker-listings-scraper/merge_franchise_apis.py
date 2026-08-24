"""
Merges the RE/MAX and Century 21 Mexico API-sourced listings into the
existing all-regions deduped dataset, re-runs dedup across everything (in
case of overlap), and re-tags regions.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dedup import dedup, load_rows, write_workbook
from build_final_mexico_city import REGION_KEYWORDS, UNRELATED_REGION_KEYWORDS, classify_regions, is_unrelated

HERE = Path(__file__).parent


def load_csv_rows(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def main():
    base_rows = load_rows(HERE / "listings_all_regions_deduped_v4.xlsx")
    print(f"Loaded {len(base_rows)} rows from existing all-regions deduped dataset (v4: base + RE/MAX + Century21 + Pulppo)")
    for r in base_rows:
        r.pop("Source Count", None)
        r.pop("Source Brokers", None)
        r.pop("Source URLs", None)
        r.pop("Region Match", None)

    ampi_rows = load_rows(HERE / "listings_ampi_cdmx.xlsx")
    print(f"Loaded {len(ampi_rows)} rows from AMPI independent-broker scrape")

    all_rows = base_rows + ampi_rows
    print(f"Combined raw total: {len(all_rows)}")

    deduped = dedup(all_rows, use_image_hash=True)
    print(f"Deduped to {len(deduped)} unique listings ({len(all_rows) - len(deduped)} duplicates merged)")

    out_xlsx = HERE / "listings_all_regions_deduped_v5.xlsx"
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
    out_csv = HERE / "all_regions_listings_filtered_v5.csv"
    with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=all_fields)
        writer.writeheader()
        writer.writerows(kept_rows)
    print(f"\nWrote {out_csv} ({len(kept_rows)} rows)")

    cdmx_rows = [r for r in kept_rows if "Mexico City" in r["Region Match"].split("; ")]
    out_path = HERE / "listings_mexico_city.csv"
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=all_fields)
        writer.writeheader()
        writer.writerows(cdmx_rows)
    print(f"Wrote {out_path} ({len(cdmx_rows)} rows)")


if __name__ == "__main__":
    main()
