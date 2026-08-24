"""
Converts a raw parse.bot / Inmuebles24 search_listings JSON response (the
{"status": "success", "data": {"listings": [...]}} shape) into the standard
listings CSV schema used across all other sources in this pipeline.

Usage:
  python convert_parsebot_inmuebles24.py --in "Cancun rentals 1.txt" --out listings_inmuebles24_cancun_rentals_deptos.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent))
from scraper_common import extract_property_type

FIELDS = [
    "Broker", "Broker URL", "Platform", "Listing URL", "Listing Name", "Property Type",
    "Price", "Currency", "Bedrooms", "Bathrooms", "Size", "Size Unit", "Description", "Images",
    "Country", "State", "City", "Latitude", "Longitude", "Sale or Rent",
]


def to_row(rec: dict) -> dict:
    title = rec.get("title") or ""
    desc = rec.get("description") or ""
    return {
        "Broker": rec.get("agency_name") or "Inmuebles24",
        "Broker URL": rec.get("agency_url") or "",
        "Platform": "Inmuebles24 (via parse.bot API)",
        "Listing URL": rec.get("url") or "",
        "Listing Name": title,
        "Property Type": extract_property_type(title, desc),
        "Price": rec.get("price"),
        "Currency": rec.get("currency") or "MXN",
        "Bedrooms": rec.get("bedrooms"),
        "Bathrooms": rec.get("bathrooms"),
        "Size": rec.get("size_m2") or rec.get("land_size_m2"),
        "Size Unit": "m2",
        "Description": desc,
        "Images": "; ".join(rec.get("image_urls") or []),
        "Country": rec.get("country") or "Mexico",
        "State": rec.get("state"),
        "City": rec.get("city") or rec.get("neighborhood"),
        "Latitude": rec.get("latitude"),
        "Longitude": rec.get("longitude"),
        "Sale or Rent": "Rent" if rec.get("for_sale_or_rent") == "for_rent" else "Sale",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="in_path", required=True)
    parser.add_argument("--out", dest="out_path", required=True)
    args = parser.parse_args()

    with open(args.in_path, encoding="utf-8") as f:
        payload = json.load(f)

    if payload.get("status") != "success":
        raise SystemExit(f"Unexpected status: {payload.get('status')}")

    d = payload["data"]
    listings = d.get("listings") or []
    print(f"search_params: {d.get('search_params')}")
    print(f"count={d.get('count')} total_available={d.get('total_available')} pages_fetched={d.get('pages_fetched')}")
    print(f"Listings in file: {len(listings)}")

    rows = [to_row(r) for r in listings]

    with_desc = sum(1 for r in rows if (r.get("Description") or "").strip())
    with_beds = sum(1 for r in rows if r.get("Bedrooms") not in (None, ""))
    print(f"With description: {with_desc}/{len(rows)} | With bedrooms: {with_beds}/{len(rows)}")

    with open(args.out_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {args.out_path} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
