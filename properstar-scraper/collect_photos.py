"""Collect every listing's full photo list for a city, free, off the ListGlobally search API.

The "buy" listings on the site came through parse.bot, whose Properstar scraper returns only
the first 5 pictures. The free search API (scrape_api.py) returns all of them. This collects
just {listing id: [picture urls]} per city into photos/<city>.json, leaving the city data
files alone; push_photos.py then writes the longer lists into resale_listings.pictures.

    python collect_photos.py cancun tulum playa-del-carmen mexico-city

0 credits. Re-running a city overwrites its photos file.
"""
from __future__ import annotations

import json
import os
import sys

from scrape_api import Search, collect

OUT_DIR = "photos"


def run(city: str, max_requests: int = 6000) -> None:
    s = Search("mexico", city, "buy", "apartment-house")
    out: dict = {}
    try:
        collect(s, None, None, out, max_requests)
    except KeyboardInterrupt:
        print("\ninterrupted -- writing what was collected so far")
    photos = {str(k): v["pictures"] for k, v in out.items() if v.get("pictures")}
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, f"{city}.json"), "w", encoding="utf-8") as fh:
        json.dump(photos, fh)
    n = sum(len(v) for v in photos.values())
    print(f"\n{city}: {len(photos)} listings, {n} pictures "
          f"(avg {n / max(len(photos), 1):.1f}) in {s.requests} requests, 0 credits", flush=True)


if __name__ == "__main__":
    for c in sys.argv[1:] or sys.exit(__doc__):
        run(c)
