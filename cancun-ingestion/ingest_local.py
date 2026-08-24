"""
Ingest a local Properstar dataset export (e.g. from an Apify
properstar-leads-scraper run) into the cancun_listings table.

Usage:
    python ingest_local.py path/to/dataset.json
    python ingest_local.py path/to/dataset.json --dry-run   # write rows.json locally, skip Supabase
"""
import argparse
import json
import os
import sys

import truststore

truststore.inject_into_ssl()  # use the Windows cert store; corporate TLS inspection breaks certifi

from dotenv import load_dotenv

load_dotenv()

BATCH_SIZE = 200

SQFT_PER_SQM = 10.7639


def sqft_from_area(area):
    if not area:
        return None
    for value in area.get("values", []):
        if value.get("unit", {}).get("id") == "SquareFoot":
            return value.get("living")
    living = area.get("living")
    if living is None:
        return None
    return round(living * SQFT_PER_SQM, 2)


def original_price(price):
    if not price:
        return None, None, None
    for value in price.get("values", []):
        if value.get("type") == "Original":
            currency = value.get("currencyId")
            amount = value.get("value")
            raw = f"{currency} {amount:,.0f}" if currency and amount is not None else None
            return raw, currency, amount
    return None, None, None


def to_row(item):
    listing = item["listing"]
    location = listing.get("location", {})
    price_raw, price_currency, price_amount = original_price(listing.get("price"))

    pictures = [
        pic["url"]
        for pic in listing.get("resources", {}).get("pictures", {}).get("items", [])
        if pic.get("url")
    ]

    return {
        "id": listing["id"],
        "url": item.get("_itemUrl"),
        "is_project": listing.get("class") == "UnitListing",
        "location": location.get("city") or location.get("address1"),
        "title": listing.get("automaticTitle") or listing.get("reference"),
        "highlights": listing.get("reference"),
        "bedrooms": listing.get("numberOf", {}).get("bedrooms"),
        "bathrooms": listing.get("numberOf", {}).get("bathrooms"),
        "size_sqft": sqft_from_area(listing.get("area")),
        "property_type": (listing.get("subType") or listing.get("type") or {}).get("name"),
        "price_raw": price_raw,
        "price_currency": price_currency,
        "price_amount": price_amount,
        "pictures": pictures,
        "latitude": location.get("latitude"),
        "longitude": location.get("longitude"),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", help="Path to the dataset JSON file")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip Supabase upsert; write transformed rows to rows.json instead",
    )
    args = parser.parse_args()

    with open(args.dataset, encoding="utf-8") as f:
        items = json.load(f)

    print(f"loaded {len(items)} raw items")

    rows = [to_row(item) for item in items if item.get("listing", {}).get("id")]

    # de-dupe by id, keeping the last occurrence
    by_id = {row["id"]: row for row in rows}
    rows = list(by_id.values())
    print(f"transformed {len(rows)} unique rows")

    if args.dry_run:
        out_path = os.path.join(os.path.dirname(args.dataset) or ".", "rows.json")
        out_path = "rows.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2, ensure_ascii=False)
        print(f"dry run: wrote {out_path}, skipping Supabase")
        return

    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")
    if not supabase_url or not supabase_key:
        print("SUPABASE_URL / SUPABASE_KEY not set (see .env.example). Aborting upsert.")
        sys.exit(1)

    from supabase import create_client

    supabase = create_client(supabase_url, supabase_key)
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        supabase.table("cancun_listings").upsert(batch, on_conflict="id").execute()
        print(f"upserted rows {i}-{i + len(batch)}")

    print("done")


if __name__ == "__main__":
    main()
