"""
No new Mexico City listings were scraped (all 13 Coldwell Banker CDMX office
subdomains had no crawlable listing links), so there's nothing to merge or
re-dedup. This just re-tags the existing deduped dataset with Mexico City
added as a target region, in case any already-scraped broker's inventory
happens to include a CDMX property.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dedup import load_rows

HERE = Path(__file__).parent

from build_final_mexico_city import REGION_KEYWORDS, UNRELATED_REGION_KEYWORDS, classify_regions, is_unrelated


def main():
    rows = load_rows(HERE / "listings_all_regions_deduped.xlsx")
    print(f"Loaded {len(rows)} rows from existing deduped dataset")

    kept_rows = []
    dropped = 0
    for row in rows:
        matches = classify_regions(row)
        if is_unrelated(row, matches):
            dropped += 1
            continue
        row["Region Match"] = "; ".join(matches) if matches else "No Location Signal"
        kept_rows.append(row)

    print(f"Dropped {dropped} unrelated-region rows; kept {len(kept_rows)}")

    cdmx_rows = [r for r in kept_rows if "Mexico City" in r["Region Match"].split("; ")]
    print(f"Mexico City matches among already-scraped brokers: {len(cdmx_rows)}")

    if cdmx_rows:
        all_fields = list(cdmx_rows[0].keys())
        out_path = HERE / "listings_mexico_city.csv"
        with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=all_fields)
            writer.writeheader()
            writer.writerows(cdmx_rows)
        print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
