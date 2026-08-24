"""Backfill price_usd, price_per_m2, size_m2, and province on properstar_listings.

Derivation, matching the conventions already used in tlrm's resale_listings import
scripts (see tlrm/import-resale-bcs.mjs):
  - size_m2 = size_sqft / 10.7639
  - price_usd = parse "CUR amount" out of the raw price string, convert via the same
    RATES_PER_USD table tlrm's importers use. This dataset is 100% GBP (scraped from
    properstar.co.uk), confirmed by scanning every row before writing this script.
  - price_per_m2 = price_usd / size_m2, only when both exist
  - province: a straight city -> state lookup. Unlike tlrm's BCS/Nayarit imports (one
    broad regional scrape needing town-name regex matching per row), this dataset was
    already collected one city at a time, so province is unambiguous per file.

Usage:
    python backfill_derived_columns.py               # dry run, prints a sample
    python backfill_derived_columns.py --apply        # writes to Supabase
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re

import truststore

truststore.inject_into_ssl()

from dotenv import load_dotenv

load_dotenv()
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "cancun-ingestion", ".env"))

BATCH_SIZE = 200
SQFT_PER_M2 = 10.7639

RATES_PER_USD = {"USD": 1, "MXN": 18.5, "EUR": 0.92, "GBP": 0.79, "CAD": 1.37, "COP": 4100}

CITY_PROVINCE = {
    "tulum": "Quintana Roo",
    "playa-del-carmen": "Quintana Roo",
    "cancun": "Quintana Roo",
    "puerto-morelos": "Quintana Roo",
    "mexico-city": "Ciudad de México",
    "puerto-vallarta": "Jalisco",
    "los-cabos": "Baja California Sur",
    "la-paz": "Baja California Sur",
    "sayulita": "Nayarit",
}

PRICE_RE = re.compile(r"^([A-Z]{3})\s+([\d,]+(?:\.\d+)?)$")


def to_usd(price_raw: str | None) -> float | None:
    if not price_raw:
        return None
    m = PRICE_RE.match(price_raw)
    if not m:
        return None
    currency, amount = m.group(1), float(m.group(2).replace(",", ""))
    rate = RATES_PER_USD.get(currency)
    if not rate:
        return None
    return round(amount / rate, 2)


def to_m2(size_sqft) -> float | None:
    if size_sqft is None:
        return None
    return round(float(size_sqft) / SQFT_PER_M2, 2)


FILENAME_RE = re.compile(r"^properstar_(.+?)(_rent)?\.json$")


def discover_files() -> list[tuple[str, str, str]]:
    here = os.path.dirname(os.path.abspath(__file__))
    out = []
    for path in sorted(glob.glob(os.path.join(here, "properstar_*.json"))):
        name = os.path.basename(path)
        m = FILENAME_RE.match(name)
        if not m:
            continue
        city = m.group(1)
        if city.endswith("_full"):
            city = city[: -len("_full")]
        if city not in CITY_PROVINCE:
            continue
        out.append((path, city, "rent" if m.group(2) else "buy"))
    return out


def build_updates() -> list[dict]:
    updates = []
    for path, city, transaction in discover_files():
        with open(path, encoding="utf-8") as f:
            items = json.load(f)
        province = CITY_PROVINCE[city]
        for item in items:
            if item.get("id") is None:
                continue
            price_usd = to_usd(item.get("price"))
            size_m2 = to_m2(item.get("size_sqft"))
            price_per_m2 = round(price_usd / size_m2, 2) if price_usd is not None and size_m2 else None
            updates.append({
                "id": item["id"],
                # Postgres validates NOT NULL constraints on the whole row before
                # checking ON CONFLICT, so a partial upsert payload that omits these
                # fails outright even though the row already exists. Including them
                # (with their real, already-correct values) makes the INSERT branch
                # legal; the ON CONFLICT DO UPDATE then just re-sets them to the same
                # value they already had.
                "city": city,
                "transaction": transaction,
                "price_usd": price_usd,
                "price_per_m2": price_per_m2,
                "size_m2": size_m2,
                "province": province,
            })
    return updates


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    updates = build_updates()
    print(f"{len(updates):,} rows to update")

    have_usd = sum(1 for u in updates if u["price_usd"] is not None)
    have_m2 = sum(1 for u in updates if u["size_m2"] is not None)
    print(f"  price_usd populated: {have_usd:,}")
    print(f"  size_m2 populated:   {have_m2:,}")
    print("\nsample:")
    for u in updates[:3]:
        print(" ", u)

    if not args.apply:
        print("\ndry run: no changes written. Re-run with --apply to upsert.")
        return

    from supabase import create_client

    supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    for i in range(0, len(updates), BATCH_SIZE):
        batch = updates[i:i + BATCH_SIZE]
        supabase.table("properstar_listings").upsert(batch, on_conflict="id").execute()
        print(f"  updated rows {i}-{i + len(batch)}/{len(updates)}", flush=True)

    print("\ndone")


if __name__ == "__main__":
    main()
