"""
Scrapes all published property listings from Zisla (zisla.com) via its public
listing API and writes them to an Excel workbook.

Usage:
  python scrape_zisla.py
  python scrape_zisla.py --out "C:\\path\\to\\output.xlsx"
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from zisla_common import fetch_developments, join_true_keys, to_plain_text, write_new_workbook

MAX_CELL_LEN = 32000  # Excel hard-caps a cell's text at 32,767 characters.


def limit_cell_length(text: str) -> str:
    if text and len(text) > MAX_CELL_LEN:
        return text[:MAX_CELL_LEN] + "...[truncated]"
    return text


def build_row(p: dict) -> dict:
    price = p.get("price") or {}
    pesos = p.get("priceInPesos") or {}
    photos = p.get("photos") or []
    coords = (p.get("location") or {}).get("coordinates") or []
    address = p.get("address") or {}
    bedrooms = p.get("bedrooms") or {}
    bathrooms = p.get("bathrooms") or {}
    square = p.get("squareSurface") or {}
    localized = p.get("localized") or {}

    return {
        "ID": p.get("_id"),
        "Title": localized.get("title"),
        "URL": f"https://www.zisla.com/en/properties/{localized.get('urlAlias')}",
        "Purpose": p.get("purpose"),
        "Status": p.get("status"),
        "Type": p.get("type"),
        "Sub Type": p.get("subType"),
        "Country": address.get("country"),
        "Province": address.get("province"),
        "City": address.get("city"),
        "Neighbourhood": address.get("neighbourhood"),
        "Street": address.get("street"),
        "Postal Code": address.get("postalCode"),
        "Price Min (USD)": round(price["min"] / 100, 2) if price.get("min") is not None else None,
        "Price Max (USD)": round(price["max"] / 100, 2) if price.get("max") is not None else None,
        "Price Min (MXN)": round(pesos["min"] / 100, 2) if pesos.get("min") is not None else None,
        "Price Max (MXN)": round(pesos["max"] / 100, 2) if pesos.get("max") is not None else None,
        "Price Hidden": p.get("priceIsNotDisplayed"),
        "Bedrooms Min": bedrooms.get("min"),
        "Bedrooms Max": bedrooms.get("max"),
        "Bathrooms Min": bathrooms.get("min"),
        "Bathrooms Max": bathrooms.get("max"),
        "Sq Surface Min": square.get("min"),
        "Sq Surface Max": square.get("max"),
        "Measured In Sq Ft": p.get("isSquareFeet"),
        "Units Total": p.get("nbOfUnits"),
        "Units Available": p.get("nbOfUnitsAvailable"),
        "Levels": p.get("nbOfLevels"),
        "Financing Offered": p.get("isFinancing"),
        "Latitude": coords[1] if len(coords) > 1 else None,
        "Longitude": coords[0] if len(coords) > 0 else None,
        "Amenities": join_true_keys(p.get("amenities")),
        "Features": join_true_keys(p.get("features")),
        "Developer ID": p.get("developer"),
        "First Day On Site": p.get("firstDayOnSite"),
        "Last Update": p.get("lastUpdate"),
        "Photo Count": len(photos),
        "First Photo URL": f"https://www.zisla.com{photos[0]['url']}" if photos else "",
        "Description": to_plain_text(localized.get("description")),
        "Raw JSON": limit_cell_length(json.dumps(p, separators=(",", ":"))),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(Path(__file__).parent / "zisla-properties.xlsx"))
    args = parser.parse_args()

    print("Fetching property listings from zisla.com ...")
    items = fetch_developments()
    print(f"Total properties fetched: {len(items)}")
    if not items:
        raise SystemExit("No properties were fetched. Zisla's API may have changed.")

    print("Transforming records...")
    rows = [build_row(p) for p in items]

    print(f"Writing Excel workbook to {args.out} ...")
    write_new_workbook(args.out, "Zisla Properties", rows)
    print(f"Saved {len(rows)} properties to {args.out}")


if __name__ == "__main__":
    main()
