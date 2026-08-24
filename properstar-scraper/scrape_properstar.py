"""Scrape Properstar search-result listings for a given location/URL.

How it works: Properstar server-renders its first 20 search results into a
`window.__INITIAL_STATE__` JSON blob embedded in the page HTML (Redux store
dump), rather than exposing a public search API. The site also sits behind
an Azure WAF JavaScript challenge, so the *first* request needs a real
browser (Scrapling's StealthyFetcher) and a short wait for the challenge to
resolve. That challenge issues a `token` cookie (a ~1hr guest JWT) and an
`afd_azwaf_jsclearance` cookie (~12hr WAF pass) -- both plain, non-httpOnly
cookies. Reusing them on subsequent plain HTTP requests (no browser) skips
the WAF challenge entirely: ~2s/page instead of ~10-20s/page. If a page ever
comes back non-200 (cookies expired), the script re-bootstraps via the
browser and keeps going. Pagination is via a `?p=N` query param (each page
is its own server render, not a client-side XHR).
"""
from __future__ import annotations

import csv
import json
import random
import time

from scrapling.fetchers import Fetcher, StealthyFetcher

BASE_URL = "https://www.properstar.co.uk/mexico/tulum/buy/apartment-house"
MAX_PAGES = 150  # 20 listings/page; raise cautiously -- ~8,500 results exist for this search
OUTPUT_CSV = "properstar_tulum_listings.csv"
OUTPUT_JSON = "properstar_tulum_listings.json"

COUNTRY_NAMES = {"MX": "Mexico"}

FIELDS = [
    "id", "title", "url", "price", "location", "latitude", "longitude",
    "bedrooms", "bathrooms", "size_sqft", "property_type", "advertiser", "pictures",
]


def extract_initial_state(html: str) -> dict:
    """Pull the `window.__INITIAL_STATE__ = {...}` JSON blob out of the raw
    page HTML using brace-matching (a regex can't safely handle nested
    braces inside quoted strings)."""
    marker = "window.__INITIAL_STATE__ = "
    start = html.find(marker)
    if start == -1:
        raise ValueError("__INITIAL_STATE__ not found in page (WAF challenge page?)")
    start += len(marker)

    depth = 0
    in_str = False
    esc = False
    i = start
    while i < len(html):
        c = html[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    i += 1
                    break
        i += 1

    return json.loads(html[start:i])


def bootstrap_cookies() -> dict[str, str]:
    """Solve the WAF's JS challenge once via a real browser and return the
    resulting session cookies for reuse on plain (browser-less) requests."""
    print("Bootstrapping session via browser (solving WAF challenge)...")
    page = StealthyFetcher.fetch(BASE_URL, headless=True, network_idle=True, wait=8000)
    if page.status != 200:
        raise RuntimeError(f"bootstrap failed with status {page.status}")
    return {c["name"]: c["value"] for c in page.cookies}


def fetch_search_page(page_num: int, cookies: dict[str, str]) -> str:
    """Fetch one search-results page's raw HTML via a plain HTTP request,
    reusing the bootstrapped WAF-clearance cookies (no browser needed)."""
    url = BASE_URL if page_num == 1 else f"{BASE_URL}?p={page_num}"
    page = Fetcher.get(url, stealthy_headers=True, cookies=cookies)
    if page.status != 200:
        raise RuntimeError(f"status {page.status}")
    return page.body.decode("utf-8") if isinstance(page.body, bytes) else page.body


def format_price(price: dict) -> str:
    values = [v for v in price.get("values", []) if v.get("currencyId") and v.get("value") is not None]
    for v in values:
        if v["currencyId"] == "GBP":
            return f"GBP {v['value']:,.0f}"
    if values:
        return f"{values[0]['currencyId']} {values[0]['value']:,.0f}"
    return ""


def format_location(location: dict) -> str:
    parts = []
    if location.get("showAddress") and location.get("address1"):
        parts.append(location["address1"])
    if location.get("city"):
        parts.append(location["city"])
    country = COUNTRY_NAMES.get(location.get("countryISO"), location.get("countryISO"))
    if country:
        parts.append(country)
    return ", ".join(parts)


def size_in_sqft(area: dict) -> float | None:
    for v in area.get("values", []):
        if v.get("unit", {}).get("id") == "SquareFoot" and v.get("living") is not None:
            return v["living"]
    living = area.get("living")
    if living is not None and area.get("unit", {}).get("id") == "SquareMeter":
        return round(living * 10.7639, 2)
    return living


def get_advertiser(listing: dict, accounts: dict) -> str:
    account_id = str(listing.get("contactAccountId", ""))
    account = accounts.get(account_id)
    if account and account.get("name"):
        return account["name"][0]["text"]
    return ""


def map_listing(listing: dict, accounts: dict) -> dict:
    title = listing.get("title") or []
    return {
        "id": listing["id"],
        "title": title[0]["text"] if title else listing.get("automaticTitle", ""),
        "url": f"https://www.properstar.co.uk/listing/{listing['id']}",
        "price": format_price(listing.get("price", {})),
        "location": format_location(listing.get("location", {})),
        "latitude": listing.get("location", {}).get("latitude"),
        "longitude": listing.get("location", {}).get("longitude"),
        "bedrooms": listing.get("numberOf", {}).get("bedrooms"),
        "bathrooms": listing.get("numberOf", {}).get("bathrooms"),
        "size_sqft": size_in_sqft(listing.get("area", {})),
        "property_type": listing.get("type", {}).get("id", ""),
        "advertiser": get_advertiser(listing, accounts),
        "pictures": [
            item["url"] for item in listing.get("resources", {}).get("pictures", {}).get("items", [])
        ],
    }


def main() -> None:
    all_listings: dict[int, dict] = {}  # keyed by id, dedupes across pages
    cookies = bootstrap_cookies()

    page_num = 1
    while page_num <= MAX_PAGES:
        print(f"Fetching page {page_num}/{MAX_PAGES}...")
        try:
            html = fetch_search_page(page_num, cookies)
            state = extract_initial_state(html)
        except Exception as exc:
            print(f"  page {page_num} failed ({exc}), re-bootstrapping session...")
            cookies = bootstrap_cookies()
            continue  # retry the same page with fresh cookies

        results = state["search"]["results"]
        listings = results["listings"]
        accounts = state["entities"]["account"]

        if not listings:
            print("  no more listings, stopping")
            break

        for listing in listings:
            record = map_listing(listing, accounts)
            all_listings[record["id"]] = record

        print(f"  got {len(listings)} listings (total collected: {len(all_listings)})")

        page_num += 1
        if page_num <= MAX_PAGES:
            time.sleep(random.uniform(0.5, 1.5))  # be polite between requests

    records = list(all_listings.values())

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for r in records:
            row = dict(r)
            row["pictures"] = "; ".join(row["pictures"])
            writer.writerow(row)

    print(f"\nSaved {len(records)} listings to {OUTPUT_CSV} and {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
