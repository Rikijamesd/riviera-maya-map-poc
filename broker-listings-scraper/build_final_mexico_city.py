"""
Same pipeline as build_final_5regions.py, extended for Mexico City: merges
the newly-scraped CDMX broker listings into the already-deduped
all-regions dataset, re-runs dedup, and tags/filters rows for Mexico City
(now a target region rather than an "unrelated -> drop" keyword).
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

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
    "Mexico City": [
        "mexico city", "ciudad de mexico", "ciudad de méxico", "cdmx",
        "polanco", "condesa", "roma norte", "roma sur", "santa fe",
        "lomas de chapultepec", "las lomas", "coyoacan", "coyoacán",
        "san angel", "san ángel", "pedregal", "bosques de las lomas",
        "interlomas", "del valle", "narvarte", "reforma", "chapultepec",
        "polanco", "napoles", "nápoles", "juarez", "cuauhtemoc", "cuauhtémoc",
    ],
    "Other Riviera Maya": [
        "akumal", "puerto aventuras", "bacalar", "holbox", "cozumel", "mahahual",
        "riviera maya", "quintana roo",
    ],
    "Puerto Escondido": [
        "puerto escondido", "zicatela", "huatulco", "mazunte", "san agustinillo",
        "puerto angel", "puerto ángel",
    ],
}

UNRELATED_REGION_KEYWORDS = [
    "merida", "mérida", "yucatan", "yucatán", "monterrey", "veracruz",
    "guadalajara", "san miguel de allende",
    "queretaro", "querétaro", "chiapas", "puebla",
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
    base_path = HERE / "listings_all_regions_deduped.xlsx"
    new_raw_path = HERE / "listings_mexico_city_raw.xlsx"

    base_rows = load_rows(base_path)
    print(f"Loaded {len(base_rows)} rows from existing all-regions deduped dataset")

    # Strip the prior dedup bookkeeping columns so re-dedup starts clean
    for r in base_rows:
        r.pop("Source Count", None)
        r.pop("Source Brokers", None)
        r.pop("Source URLs", None)
        r.pop("Region Match", None)

    new_rows = load_rows(new_raw_path)
    print(f"Loaded {len(new_rows)} raw rows from newly-scraped Mexico City sites")

    all_rows = base_rows + new_rows
    print(f"Combined raw total: {len(all_rows)}")

    deduped = dedup(all_rows, use_image_hash=True)
    print(f"Deduped to {len(deduped)} unique listings ({len(all_rows) - len(deduped)} duplicates merged)")

    out_xlsx = HERE / "listings_all_regions_deduped_v2.xlsx"
    write_workbook(deduped, out_xlsx)
    print(f"Wrote {out_xlsx}")

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
    out_csv = HERE / "all_regions_listings_filtered_v2.csv"
    with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=all_fields)
        writer.writeheader()
        writer.writerows(kept_rows)
    print(f"\nWrote {out_csv} ({len(kept_rows)} rows)")

    region_rows = [r for r in kept_rows if "Mexico City" in r["Region Match"].split("; ")]
    out_path = HERE / "listings_mexico_city.csv"
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=all_fields)
        writer.writeheader()
        writer.writerows(region_rows)
    print(f"Wrote {out_path} ({len(region_rows)} rows)")


if __name__ == "__main__":
    main()
