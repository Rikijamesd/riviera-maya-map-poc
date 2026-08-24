"""
Combines the newly-scraped 5-region broker listings with the existing
Tulum-pipeline dataset, re-runs dedup across everything (since many brokers
serve multiple regions and could cross-post), then tags every row with which
of the 5 new target regions (plus Tulum/Riviera Maya/Other) its text
actually references, and writes final per-purpose CSVs.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from openpyxl import load_workbook

from dedup import dedup, load_rows, write_workbook

HERE = Path(__file__).parent

REGION_KEYWORDS = {
    "Cancun": ["cancun", "cancún", "puerto cancun", "zona hotelera cancun"],
    "Playa del Carmen": ["playa del carmen", "playacar"],
    "Puerto Morelos": ["puerto morelos"],
    "Tulum": ["tulum"],
    "Puerto Vallarta": [
        "puerto vallarta", "vallarta", "nuevo vallarta", "bucerias", "bucerías",
        "punta de mita", "punta mita", "sayulita", "riviera nayarit", "nayarit",
    ],
    "Baja California Sur": [
        "los cabos", "cabo san lucas", "san jose del cabo", "san josé del cabo",
        "la paz", "todos santos", "east cape", "baja california sur",
        "cabo pulmo", "loreto",
    ],
    "Other Riviera Maya": [
        "akumal", "puerto aventuras", "bacalar", "holbox", "cozumel", "mahahual",
        "riviera maya", "quintana roo",
    ],
}

UNRELATED_REGION_KEYWORDS = [
    "merida", "mérida", "yucatan", "yucatán", "monterrey", "veracruz",
    "guadalajara", "mexico city", "ciudad de mexico", "cdmx", "san miguel de allende",
    "queretaro", "querétaro", "chiapas", "oaxaca", "puebla",
]


def row_text(row: dict) -> str:
    parts = [
        row.get("Listing Name") or "",
        row.get("Description") or "",
        row.get("City") or "",
        row.get("State") or "",
        row.get("Broker") or "",
    ]
    return " ".join(parts).lower()


def classify_regions(row: dict) -> list[str]:
    text = row_text(row)
    matches = [region for region, kws in REGION_KEYWORDS.items() if any(kw in text for kw in kws)]
    return matches


def is_unrelated(row: dict, matched_regions: list[str]) -> bool:
    if matched_regions:
        return False
    text = row_text(row)
    return any(kw in text for kw in UNRELATED_REGION_KEYWORDS)


def main():
    combined_raw_path = HERE / "listings_combined.xlsx"
    new_raw_path = HERE / "listings_5regions.xlsx"

    old_rows = load_rows(combined_raw_path)
    print(f"Loaded {len(old_rows)} raw rows from existing Tulum-pipeline dataset")

    new_rows = load_rows(new_raw_path)
    print(f"Loaded {len(new_rows)} raw rows from newly-scraped 5-region sites")

    all_rows = old_rows + new_rows
    print(f"Combined raw total: {len(all_rows)}")

    deduped = dedup(all_rows, use_image_hash=True)
    print(f"Deduped to {len(deduped)} unique listings ({len(all_rows) - len(deduped)} duplicates merged)")

    out_xlsx = HERE / "listings_all_regions_deduped.xlsx"
    write_workbook(deduped, out_xlsx)
    print(f"Wrote {out_xlsx}")

    # Tag every row with region signal(s)
    dropped_unrelated = 0
    kept_rows = []
    for row in deduped:
        matches = classify_regions(row)
        if is_unrelated(row, matches):
            dropped_unrelated += 1
            continue
        row["Region Match"] = "; ".join(matches) if matches else "No Location Signal"
        kept_rows.append(row)

    print(f"Dropped {dropped_unrelated} rows referencing a clearly unrelated region")
    print(f"Kept {len(kept_rows)} rows")

    # Per-region counts (a row can count toward multiple regions if it mentions several)
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

    # Write full combined CSV (all 5 new regions + Tulum + unlabeled)
    all_fields = list(kept_rows[0].keys()) if kept_rows else []
    out_csv = HERE / "all_regions_listings_filtered.csv"
    with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=all_fields)
        writer.writeheader()
        writer.writerows(kept_rows)
    print(f"\nWrote {out_csv} ({len(kept_rows)} rows)")

    # Also write one CSV per new region, restricted to rows that match ONLY
    # that region (or that region + Tulum/Other Riviera Maya, since those are
    # adjacent markets) -- i.e. a focused deliverable per city.
    new_regions = ["Cancun", "Playa del Carmen", "Puerto Morelos", "Puerto Vallarta", "Baja California Sur"]
    for region in new_regions:
        region_rows = [r for r in kept_rows if region in r["Region Match"].split("; ")]
        if not region_rows:
            continue
        safe_name = region.lower().replace(" ", "_")
        out_path = HERE / f"listings_{safe_name}.csv"
        with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=all_fields)
            writer.writeheader()
            writer.writerows(region_rows)
        print(f"Wrote {out_path} ({len(region_rows)} rows)")


if __name__ == "__main__":
    main()
