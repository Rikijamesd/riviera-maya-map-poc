"""Ingest all collected Properstar city/market JSON files into Supabase.

Reads every properstar_<city>[_rent].json in this directory, tags each row
with the city (from the filename) and transaction (buy/rent), and upserts
into properstar_listings on id -- Properstar's own listing id is the only
dedup key used. Rows are never fuzzy-deduped against each other; if
Properstar itself serves the same listing under two different ids, both are
kept -- that's an explicit choice, not an oversight (see project memory).

The destination table must already exist (see HANDOVER.md for the create
statement) -- this script only has a publishable key, which can't run DDL.

Usage:
    python ingest_properstar.py               # upsert everything
    python ingest_properstar.py --dry-run      # write combined_rows.json, skip Supabase
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys

import truststore

truststore.inject_into_ssl()  # Windows cert store; corporate TLS inspection breaks certifi

from dotenv import load_dotenv

load_dotenv()
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "cancun-ingestion", ".env"))

BATCH_SIZE = 200

# Matches properstar_<city>.json (buy) or properstar_<city>_rent.json (rent).
# Non-greedy city capture so "_rent" isn't swallowed into the city name.
FILENAME_RE = re.compile(r"^properstar_(.+?)(_rent)?\.json$")

# The 9 cities actually collected this batch. An allowlist, not a blacklist of
# known-stale files -- this directory has debris from early-session
# exploration (properstar_tulum_listings.json, an early partial Tulum test
# predating the full 8,522-row collection) that would otherwise silently
# become its own bogus pseudo-city if discovery just globbed everything.
KNOWN_CITIES = {
    "tulum", "playa-del-carmen", "cancun", "puerto-morelos", "mexico-city",
    "puerto-vallarta", "los-cabos", "sayulita", "la-paz",
}

FIELDS = [
    "id", "city", "transaction", "title", "url", "price", "location",
    "latitude", "longitude", "bedrooms", "bathrooms", "size_sqft",
    "property_type", "advertiser", "date_listed", "pictures",
]


def discover_files() -> list[tuple[str, str, str]]:
    """Every properstar_*.json in this directory, as (path, city, transaction)."""
    here = os.path.dirname(os.path.abspath(__file__))
    out = []
    for path in sorted(glob.glob(os.path.join(here, "properstar_*.json"))):
        name = os.path.basename(path)
        m = FILENAME_RE.match(name)
        if not m:
            continue
        city, rent_suffix = m.group(1), m.group(2)
        # properstar_tulum_full.json predates the city/transaction naming
        # convention (see HANDOVER.md) -- same data, different filename.
        if city.endswith("_full"):
            city = city[: -len("_full")]
        if city not in KNOWN_CITIES:
            print(f"  skipping {name} -- '{city}' isn't one of the 9 known "
                  f"cities, looks like leftover debris")
            continue
        out.append((path, city, "rent" if rent_suffix else "buy"))
    return out


def to_row(item: dict, city: str, transaction: str) -> dict | None:
    if item.get("id") is None:
        return None
    row = {k: item.get(k) for k in FIELDS if k not in ("city", "transaction")}
    row["city"] = city
    row["transaction"] = transaction
    return row


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true",
                    help="write combined_rows.json instead of upserting to Supabase")
    args = ap.parse_args()

    files = discover_files()
    if not files:
        sys.exit("no properstar_*.json files found next to this script")

    rows: list[dict] = []
    for path, city, transaction in files:
        with open(path, encoding="utf-8") as f:
            items = json.load(f)
        city_rows = [r for r in (to_row(i, city, transaction) for i in items) if r]
        rows.extend(city_rows)
        print(f"  {os.path.basename(path):42} {len(city_rows):>7,} rows  "
              f"({city}, {transaction})")

    # Global dedup on Properstar's own id only -- deliberately no fuzzy/content
    # dedup here. If the same listing appears under two different ids (a
    # cross-posted or re-listed property), both are kept; only an exact id
    # collision merges. Last file processed wins on a collision, which in
    # practice only matters for the handful of listings near a city boundary
    # that could appear in two adjacent searches.
    by_id = {r["id"]: r for r in rows}
    rows = list(by_id.values())
    print(f"\n{len(rows):,} unique ids across {len(files)} files "
          f"(from {sum(1 for _ in rows)} raw rows read)")

    if args.dry_run:
        out_path = os.path.join(os.path.dirname(__file__), "combined_rows.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
        print(f"\ndry run: wrote {out_path}, skipping Supabase")
        return

    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")
    if not supabase_url or not supabase_key:
        sys.exit("SUPABASE_URL / SUPABASE_KEY not set (see cancun-ingestion/.env)")

    from supabase import create_client

    supabase = create_client(supabase_url, supabase_key)
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        supabase.table("properstar_listings").upsert(batch, on_conflict="id").execute()
        print(f"  upserted rows {i}-{i + len(batch)}/{len(rows)}", flush=True)

    print("\ndone")


if __name__ == "__main__":
    main()
