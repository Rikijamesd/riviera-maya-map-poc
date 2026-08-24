import os
import re
import time

import requests
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

PARSEBOT_API_KEY = os.environ["PARSEBOT_API_KEY"]
PARSEBOT_SEARCH_URL = os.environ["PARSEBOT_SEARCH_URL"]
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

BATCH_SIZE = 200  # rows per Supabase upsert call


def fetch_all_listings(city="cancun", country="mexico"):
    page = 1
    all_listings = []

    while True:
        response = requests.get(
            PARSEBOT_SEARCH_URL,
            headers={"X-API-Key": PARSEBOT_API_KEY},
            params={"city": city, "country": country, "page": str(page)},
        )
        response.raise_for_status()
        data = response.json()
        listings = data.get("data", {}).get("listings", [])

        if not listings:
            break

        all_listings.extend(listings)
        print(f"page {page}: +{len(listings)} (total {len(all_listings)})")

        total = data.get("data", {}).get("total_results", 0)
        if len(all_listings) >= total:
            break

        page += 1
        time.sleep(1.2)  # respect Parse.bot rate limit

    return all_listings


def parse_price(price_raw):
    if not price_raw:
        return None, None
    match = re.match(r"([A-Z]{3})\s*([\d,]+)", price_raw)
    if not match:
        return None, None
    currency, amount = match.groups()
    return currency, float(amount.replace(",", ""))


def to_row(listing):
    currency, amount = parse_price(listing.get("price"))
    return {
        "id": listing["id"],
        "url": listing.get("url"),
        "is_project": bool(listing.get("is_project", False)),
        "location": listing.get("location"),
        "title": listing.get("title"),
        "highlights": listing.get("highlights"),
        "bedrooms": listing.get("bedrooms"),
        "bathrooms": listing.get("bathrooms"),
        "size_sqft": listing.get("size_sqft"),
        "property_type": listing.get("property_type"),
        "price_raw": listing.get("price"),
        "price_currency": currency,
        "price_amount": amount,
        "pictures": listing.get("pictures", []),
        "latitude": listing.get("latitude"),
        "longitude": listing.get("longitude"),
    }


def main():
    listings = fetch_all_listings()
    print(f"fetched {len(listings)} listings total")

    rows = [to_row(listing) for listing in listings]

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        supabase.table("cancun_listings").upsert(batch, on_conflict="id").execute()
        print(f"upserted rows {i}-{i + len(batch)}")

    print("done")


if __name__ == "__main__":
    main()
