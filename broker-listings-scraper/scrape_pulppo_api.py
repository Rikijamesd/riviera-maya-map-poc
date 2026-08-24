"""
Pulls Pulppo's full listing inventory for a given state directly from its
own public REST API (api.pulppo.com/property/search), discovered via
network inspection of pulppo.com's search flow - offset/limit paginated,
no auth required.

Usage:
  python scrape_pulppo_api.py --state-id V1-B-69 --state-name "Ciudad de Mexico" --out listings_pulppo_cdmx.csv
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import truststore
import requests

truststore.inject_into_ssl()

HERE = Path(__file__).parent
API = "https://api.pulppo.com/property/search"
SITE = "https://pulppo.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
PAGE_SIZE = 50
REQUEST_DELAY = 0.6

_META_DESC_RE = re.compile(r'<meta\s+name="description"\s+content="([^"]*)"', re.IGNORECASE)


def slugify(rec: dict) -> str:
    listing = rec.get("listing") or {}
    slug_title = (listing.get("title") or "propiedad").lower()
    slug = "".join(c if c.isalnum() else "-" for c in slug_title).strip("-")
    return f"{slug}-{rec.get('_id', '')}"


def fetch_meta_description(session: requests.Session, rec: dict) -> str:
    """Only 8% of Pulppo search-API records carry editorial text (extra.summary) -
    it's reserved for developer/pre-construction listings. For everything else,
    the real listing detail page still renders a real, page-visible og:description
    meta tag (auto-composed from type/location/specs/price, not blank filler),
    fetched here as a fallback so ordinary resale units aren't dropped."""
    url = f"{SITE}/propiedades/{slugify(rec)}"
    for attempt in range(3):
        try:
            r = session.get(url, timeout=20)
            if r.status_code != 200:
                time.sleep(1.5 * (attempt + 1))
                continue
            m = _META_DESC_RE.search(r.text)
            return html.unescape(m.group(1)).strip() if m else ""
        except Exception:
            time.sleep(1.5 * (attempt + 1))
    return ""


def fetch_missing_descriptions(recs: list[dict], workers: int = 8) -> None:
    def has_desc(rec):
        extra = (rec.get("listing") or {}).get("extra") or {}
        return bool((extra.get("summary") or extra.get("description") or extra.get("subtitle") or "").strip())

    targets = [r for r in recs if not has_desc(r)]
    print(f"\n{len(recs) - len(targets)}/{len(recs)} already have editorial text; "
          f"fetching detail-page fallback description for the other {len(targets)} ({workers} parallel workers)...")

    def worker(rec):
        s = requests.Session()
        s.headers.update(HEADERS)
        return rec, fetch_meta_description(s, rec)

    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(worker, r) for r in targets]
        for fut in as_completed(futures):
            rec, desc = fut.result()
            rec["_fallback_description"] = desc
            done += 1
            if done % 250 == 0 or done == len(targets):
                print(f"    detail-page descriptions: {done}/{len(targets)}")

FIELDS = [
    "Broker", "Broker URL", "Platform", "Listing URL", "Listing Name", "Property Type",
    "Price", "Currency", "Bedrooms", "Bathrooms", "Size", "Size Unit", "Description", "Images",
    "Country", "State", "City", "Latitude", "Longitude", "Sale or Rent",
]


def fetch_page(session: requests.Session, address: dict, operation: str, offset: int) -> dict:
    params = {
        "limit": PAGE_SIZE,
        "offset": offset,
        "operation": operation,
        "currency": "MXN",
        "address": json.dumps(address),
    }
    for attempt in range(4):
        try:
            r = session.get(API, params=params, timeout=30)
            if r.status_code != 200:
                time.sleep(2 * (attempt + 1))
                continue
            return r.json()
        except Exception as e:
            print(f"    ! error offset={offset} attempt {attempt + 1}: {e}")
            time.sleep(2 * (attempt + 1))
    return {}


def to_row(rec: dict, operation: str) -> dict:
    listing = rec.get("listing") or {}
    address = rec.get("address") or {}
    attrs = rec.get("attributes") or {}
    company = rec.get("company") or {}
    coords = (address.get("location") or {}).get("coordinates") or [None, None]
    lon, lat = (coords + [None, None])[:2]

    price_obj = listing.get("price") or {}
    images = [p.get("url") for p in (rec.get("pictures") or []) if p.get("url")][:8]

    listing_url = f"{SITE}/propiedades/{slugify(rec)}"

    return {
        "Broker": company.get("name") or "Pulppo",
        "Broker URL": "https://pulppo.com",
        "Platform": "Pulppo (native API)",
        "Listing URL": listing_url,
        "Listing Name": listing.get("title") or "",
        "Property Type": rec.get("type") or "Unknown",
        "Price": price_obj.get("price") or listing.get("value"),
        "Currency": price_obj.get("currency") or "MXN",
        "Bedrooms": attrs.get("suites"),
        "Bathrooms": attrs.get("bathrooms"),
        "Size": attrs.get("totalSurface") or attrs.get("roofedSurface"),
        "Size Unit": attrs.get("surfaceMeasurement") or "m2",
        "Description": (listing.get("extra") or {}).get("summary") or (listing.get("extra") or {}).get("description")
                       or (listing.get("extra") or {}).get("subtitle") or rec.get("_fallback_description") or "",
        "Images": "; ".join(images),
        "Country": (address.get("country") or {}).get("name") or "Mexico",
        "State": (address.get("state") or {}).get("name"),
        "City": (address.get("city") or {}).get("name"),
        "Latitude": lat,
        "Longitude": lon,
        "Sale or Rent": "Rent" if operation == "rent" else "Sale",
    }


def fetch_all(session: requests.Session, address: dict, operation: str) -> list[dict]:
    first = fetch_page(session, address, operation, 0)
    total = first.get("totalCount", 0)
    print(f"  {operation}: totalCount={total}")

    results = list(first.get("result") or [])
    seen_ids = {r["_id"] for r in results}

    offset = PAGE_SIZE
    while len(seen_ids) < total:
        time.sleep(REQUEST_DELAY)
        data = fetch_page(session, address, operation, offset)
        page_results = data.get("result") or []
        if not page_results:
            print(f"    offset {offset} empty, stopping")
            break
        new = [r for r in page_results if r["_id"] not in seen_ids]
        for r in new:
            seen_ids.add(r["_id"])
            results.append(r)
        print(f"    offset {offset}: +{len(new)} (total {len(results)}/{total})")
        if not new:
            print("    all duplicates, stopping")
            break
        offset += PAGE_SIZE
        if offset > 20000:
            print("    safety cap reached")
            break

    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-id", required=True, help="e.g. V1-B-69")
    parser.add_argument("--state-name", required=True, help="e.g. 'Ciudad de Mexico'")
    parser.add_argument("--out", default=str(HERE / "listings_pulppo.csv"))
    args = parser.parse_args()

    session = requests.Session()
    session.headers.update(HEADERS)

    address = {"country": {"name": "Mexico", "id": "MX"}, "state": {"name": args.state_name, "id": args.state_id}}

    all_rows = []
    for operation in ["sale", "rent"]:
        print(f"[{operation}]")
        recs = fetch_all(session, address, operation)
        fetch_missing_descriptions(recs)
        all_rows.extend(to_row(r, operation) for r in recs)

    print(f"\nTotal rows collected: {len(all_rows)}")
    with open(args.out, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
