"""
Scrapes property listings from every broker site in sites.csv and writes a
two-tab (Sale / Rent) Excel workbook.

For each broker:
  1. Fetch the homepage.
  2. Find links that look like individual listing pages.
  3. Visit up to --max-per-site of those pages and extract structured data
     (JSON-LD structured data first, then Open Graph tags, then regex
     heuristics on the visible text - whichever gives more).
  4. Classify each listing as Sale / Rent / Unknown and best-effort geocode
     its city/state to lat/lon.

This is a generic scraper working across ~140 unrelated site structures, so
coverage and field completeness vary a lot by site - some sites publish rich
structured data (JSON-LD) and yield complete rows; others yield just a price
and a title. Rows with no listing links found at all are skipped (logged to
skipped_sites.csv) rather than guessed at.

Usage:
  python scrape_listings.py
  python scrape_listings.py --max-per-site 25 --out listings.xlsx
  python scrape_listings.py --sites sites.csv --limit-sites 10   # quick test run
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

# Some broker names use stylized Unicode (emoji, mathematical alphanumerics)
# that Windows' default console codepage can't print - replace rather than crash.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from playwright.sync_api import sync_playwright

from scraper_common import (
    build_record,
    detect_platform,
    fetch_html,
    find_candidate_links,
    find_next_page_link,
    geocode,
    normalize_url,
)

CATEGORY_CRAWL_LIMIT = 4  # how many distinct category/index sections to try per site
MAX_PAGES_PER_CATEGORY = 25  # pagination depth ceiling per category, so a broken "next" loop can't run forever


def discover_listing_links(browser, home_html: str, home_url: str, limit: int) -> list[str]:
    listing_links, category_links = find_candidate_links(home_html, home_url)
    if len(listing_links) >= limit:
        return listing_links[:limit]

    for cat_url in category_links[:CATEGORY_CRAWL_LIMIT]:
        if len(listing_links) >= limit:
            break

        page_url = cat_url
        for _ in range(MAX_PAGES_PER_CATEGORY):
            if len(listing_links) >= limit:
                break
            cat_html, cat_final_url = fetch_html(page_url, browser)
            if not cat_html:
                break
            cat_final_url = cat_final_url or page_url

            more_listings, _ = find_candidate_links(cat_html, cat_final_url)
            new_count = 0
            for link in more_listings:
                if link not in listing_links:
                    listing_links.append(link)
                    new_count += 1

            next_url = find_next_page_link(cat_html, cat_final_url)
            if not next_url or next_url == page_url:
                break
            if new_count == 0:
                # Pagination is advancing but yielding nothing new - likely
                # looping or exhausted; stop this category branch.
                break
            page_url = next_url

    return listing_links[:limit]

HERE = Path(__file__).parent

FIELDS = [
    "Broker", "Broker URL", "Platform", "Listing URL", "Listing Name", "Property Type",
    "Price", "Currency", "Bedrooms", "Bathrooms", "Size", "Size Unit", "Description", "Images",
    "Country", "State", "City", "Latitude", "Longitude",
]

HEADER_FILL = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
HEADER_FONT = Font(bold=True, color="FFFFFF")


def style_sheet(ws, col_count: int) -> None:
    for c in range(1, col_count + 1):
        cell = ws.cell(row=1, column=c)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
    ws.row_dimensions[1].height = 20
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(col_count)}1"


def write_workbook(rows: list[dict], out_path: Path) -> None:
    wb = Workbook()
    wb.remove(wb.active)

    buckets = {"Sale": [], "Rent": [], "Unknown": []}
    for r in rows:
        buckets[r.get("Sale or Rent", "Unknown")].append(r)

    for sheet_name, bucket_rows in [("For Sale", buckets["Sale"]), ("For Rent", buckets["Rent"]), ("Unclassified", buckets["Unknown"])]:
        ws = wb.create_sheet(sheet_name)
        ws.append(FIELDS)
        for r in bucket_rows:
            ws.append([r.get(f) for f in FIELDS])
        style_sheet(ws, len(FIELDS))

    wb.save(out_path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sites", default=str(HERE / "sites.csv"))
    parser.add_argument("--out", default=str(HERE / "listings.xlsx"))
    parser.add_argument("--max-per-site", type=int, default=200, help="safety ceiling on listing pages visited per broker (not a target - pagination is followed until exhausted or this is hit)")
    parser.add_argument("--limit-sites", type=int, default=None, help="only process the first N sites (for testing)")
    parser.add_argument("--geocode", action="store_true", help="attempt lat/lon lookup via Nominatim (slower)")
    args = parser.parse_args()

    with open(args.sites, encoding="utf-8-sig") as f:
        sites = list(csv.DictReader(f))
    if args.limit_sites:
        sites = sites[: args.limit_sites]

    print(f"Loaded {len(sites)} broker sites")

    all_rows: list[dict] = []
    skipped: list[dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch()

        for i, row in enumerate(sites, start=1):
            broker_name = row["Broker Name"]
            broker_url = normalize_url(row["URL"])
            print(f"\n[{i}/{len(sites)}] {broker_name} -> {broker_url}")

            home_html, home_final_url = fetch_html(broker_url, browser)
            if not home_html:
                print("  homepage fetch failed")
                skipped.append({"Broker": broker_name, "URL": broker_url, "Reason": "homepage fetch failed"})
                continue

            listing_links = discover_listing_links(browser, home_html, home_final_url or broker_url, args.max_per_site)
            if not listing_links:
                print("  no listing links found")
                skipped.append({"Broker": broker_name, "URL": broker_url, "Reason": "no listing links found"})
                continue

            print(f"  found {len(listing_links)} candidate listing pages")
            site_rows = 0
            for link in listing_links:
                html, final_url = fetch_html(link, browser)
                if not html:
                    continue
                try:
                    record = build_record(html, final_url or link, broker_name, broker_url)
                except Exception as e:
                    print(f"    extraction error on {final_url or link}: {e}")
                    continue
                if not record.get("Price") and not record.get("Listing Name"):
                    continue  # nothing useful extracted

                if args.geocode and (record.get("City") or record.get("State")):
                    lat, lon = geocode(record.get("City"), record.get("State"), record.get("Country"))
                    record["Latitude"] = record.get("Latitude") or lat
                    record["Longitude"] = record.get("Longitude") or lon

                all_rows.append(record)
                site_rows += 1

            print(f"  extracted {site_rows} listings")

            # Save progress after every broker so a crash doesn't lose everything.
            write_workbook(all_rows, Path(args.out))

        browser.close()

    if skipped:
        with open(HERE / "skipped_sites.csv", "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=["Broker", "URL", "Reason"])
            writer.writeheader()
            writer.writerows(skipped)

    print(f"\nDone. {len(all_rows)} listings from {len(sites) - len(skipped)} sites (skipped {len(skipped)}).")
    print(f"Workbook: {args.out}")
    if skipped:
        print(f"Skipped-site log: {HERE / 'skipped_sites.csv'}")


if __name__ == "__main__":
    main()
