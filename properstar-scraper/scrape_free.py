"""Collect a city's listings straight off Properstar's public site -- no credits.

Worth using instead of parse.bot whenever a search fits inside Properstar's
2,000-result ceiling, since then free scraping reaches 100% of it. Check first:

    python plan_city.py --city tulum --transaction rent

If the reported `totalRetrievable` equals the total, this script gets everything.
Above the cap it stops at ~2,000 and parse.bot's price-band slicing is needed.

It also recovers one field parse.bot doesn't return: `date_listed`, from
Properstar's own `publicationDate`. Output columns match fetch_city.py so free
and paid pulls merge without remapping.

Trade-off vs parse.bot: free but slower -- 20 listings per page at ~2s, so ~1,500
listings takes ~3 minutes against roughly 2 credits.

Usage:
    python scrape_free.py --city tulum --transaction rent
    python scrape_free.py --city tulum --transaction rent --type apartment
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sys
import time

from plan_city import SITE, Site

SQFT_PER_SQM = 10.7639
COUNTRY_NAMES = {"MX": "Mexico"}

FIELDS = [
    "id", "title", "url", "price", "location", "latitude", "longitude",
    "bedrooms", "bathrooms", "size_sqft", "property_type", "advertiser",
    "date_listed", "pictures",
]


def format_price(price: dict) -> str:
    """Prefer Properstar's own type: "Original" entry (the agent's real listed
    price/currency) over type: "Converted" ones like GBP, which are live
    currency-display conversions that drift independent of the real price -
    see scrape_properstar.py's format_price() for the full story."""
    values = [v for v in price.get("values", [])
              if v.get("currencyId") and v.get("value") is not None]
    for v in values:
        if v.get("type") == "Original":
            return f"{v['currencyId']} {v['value']:,.0f}"
    for v in values:
        if v["currencyId"] == "GBP":
            return f"GBP {v['value']:,.0f}"
    return f"{values[0]['currencyId']} {values[0]['value']:,.0f}" if values else ""


def format_location(loc: dict) -> str:
    parts = []
    if loc.get("showAddress") and loc.get("address1"):
        parts.append(loc["address1"])
    if loc.get("city"):
        parts.append(loc["city"])
    country = COUNTRY_NAMES.get(loc.get("countryISO"), loc.get("countryISO"))
    if country:
        parts.append(country)
    return ", ".join(parts)


def size_sqft(area: dict) -> float | None:
    """Living area in sqft, falling back to total area.

    Properstar publishes either `living` or `total` depending on the listing --
    the backend search API mostly sends `total` only. Reading `living` alone
    returned null on properties that plainly had a size (a 707 m2 penthouse
    among them), which then blocked price-per-m2 and the quality flags."""
    def pick(d):
        return d.get("living") if d.get("living") is not None else d.get("total")

    for v in area.get("values", []):
        if v.get("unit", {}).get("id") == "SquareFoot":
            val = pick(v)
            if val is not None:
                return val
    val = pick(area)
    if val is not None and area.get("unit", {}).get("id") == "SquareMeter":
        return round(val * SQFT_PER_SQM, 2)
    return val


def advertiser(listing: dict, accounts: dict) -> str:
    account = accounts.get(str(listing.get("contactAccountId", "")))
    if account and account.get("name"):
        return account["name"][0]["text"]
    return ""


def map_listing(listing: dict, accounts: dict) -> dict:
    title = listing.get("title") or []
    loc = listing.get("location", {})
    return {
        "id": listing["id"],
        "title": title[0]["text"] if title else listing.get("automaticTitle", ""),
        "url": f"{SITE}/listing/{listing['id']}",
        "price": format_price(listing.get("price", {})),
        "location": format_location(loc),
        "latitude": loc.get("latitude"),
        "longitude": loc.get("longitude"),
        "bedrooms": listing.get("numberOf", {}).get("bedrooms"),
        "bathrooms": listing.get("numberOf", {}).get("bathrooms"),
        "size_sqft": size_sqft(listing.get("area", {})),
        "property_type": (listing.get("subType") or listing.get("type") or {}).get("name", ""),
        "advertiser": advertiser(listing, accounts),
        # Properstar publishes this; parse.bot returns it empty.
        "date_listed": listing.get("publicationDate"),
        "pictures": [
            i["url"] for i in
            listing.get("resources", {}).get("pictures", {}).get("items", [])
            if i.get("url")
        ],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", required=True)
    ap.add_argument("--country", default="mexico")
    ap.add_argument("--transaction", default="buy", choices=("buy", "rent"))
    ap.add_argument("--type", default="apartment-house",
                    help="apartment-house (default), apartment, or house")
    ap.add_argument("--max-pages", type=int, default=200,
                    help="safety stop; 20 listings per page")
    ap.add_argument("--fresh", action="store_true",
                    help="discard any existing output instead of merging into it")
    args = ap.parse_args()

    site = Site(args.country, args.city, args.transaction)
    site.bootstrap()

    first = site.state(args.type)
    if not first:
        sys.exit("could not read the first page")
    res = first["search"]["results"]
    total, retrievable = res.get("total") or 0, res.get("totalRetrievable") or 0
    print(f"{args.city} {args.transaction}: {total} listings, "
          f"{retrievable} retrievable")
    if retrievable < total:
        print(f"  ! capped: {total - retrievable} unreachable free. "
              f"Use plan_city.py + fetch_city.py for full coverage.")

    suffix = "" if args.transaction == "buy" else f"_{args.transaction}"
    json_path = f"properstar_{args.city}{suffix}.json"

    # Properstar's pagination is non-deterministic: each run surfaces a
    # different ~75% subset, so merging successive runs raises coverage. Default
    # to merging rather than replacing (which would also discard a better run).
    listings: dict[int, dict] = {}
    if not args.fresh and os.path.exists(json_path):
        try:
            with open(json_path, encoding="utf-8") as f:
                listings = {r["id"]: r for r in json.load(f) if r.get("id")}
            print(f"  merging into {len(listings)} listings already collected")
        except (json.JSONDecodeError, KeyError, TypeError):
            print(f"  could not read {json_path}; starting fresh")
    carried = len(listings)

    pages = min(args.max_pages, -(-retrievable // 20) if retrievable else args.max_pages)
    # Properstar's pagination overlaps: an individual page can be entirely
    # duplicates while later pages still hold new listings. Only give up after
    # several barren pages in a row -- stopping at the first one loses ~45%.
    barren = 0
    # Measured against what this run has seen, not the merged set -- otherwise a
    # second merging pass looks barren immediately and quits after 5 pages.
    run_seen: set[int] = set()

    for page in range(1, pages + 1):
        state = first if page == 1 else site.state(args.type, page)
        if not state:
            print(f"  page {page}: failed, stopping")
            break
        results = state["search"]["results"]
        batch = results.get("listings") or []
        if not batch:
            break
        accounts = state.get("entities", {}).get("account", {})
        fresh_here = False
        for item in batch:
            row = map_listing(item, accounts)
            listings[row["id"]] = row
            if row["id"] not in run_seen:
                run_seen.add(row["id"])
                fresh_here = True
        barren = 0 if fresh_here else barren + 1
        if barren >= 5:
            print(f"  page {page}: {barren} pages with nothing new, stopping")
            break
        if page % 10 == 0 or page == 1:
            print(f"  page {page}/{pages}: {len(listings)} unique", flush=True)
        time.sleep(random.uniform(0.4, 0.9))

    rows = list(listings.values())
    csv_path = f"properstar_{args.city}{suffix}.csv"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    # Merged runs can carry rows collected by fetch_city.py, whose parse.bot
    # payload has fields this scraper never produces (e.g. is_project). Widen
    # the header to cover them rather than dropping the columns -- DictWriter
    # raises on an unknown key, which used to kill the write *after* the JSON
    # had already been saved, leaving the two outputs out of sync.
    extra = sorted({k for r in rows for k in r} - set(FIELDS))
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS + extra)
        w.writeheader()
        for r in rows:
            out = dict(r)
            out["pictures"] = "; ".join(out.get("pictures") or [])
            w.writerow(out)

    # `total` counts only the type just scraped, while the output file
    # accumulates every type for this city+market. Comparing the two is
    # meaningless on a type slice -- it printed "309.3% of 742". Only show the
    # ratio when this run covered the whole market.
    whole_market = args.type == "apartment-house"
    pct = (f" ({len(rows) / total * 100:.1f}% of {total})"
           if total and whole_market else f" (type: {args.type})")
    delta = f"  (+{len(rows) - carried} new this pass)" if carried else ""
    print(f"\n{len(rows)} unique listings{pct}{delta} -> {csv_path} / {json_path}")
    if total and whole_market and len(rows) < total:
        print(f"  {total - len(rows)} still missing -- re-run this exact command "
              f"to merge another pass (coverage converges: ~74% -> ~93% -> ...)")
    print("credits spent: 0")


if __name__ == "__main__":
    main()
