"""
Pulls Century 21 Mexico's full listing inventory for a given state directly
from its own results page's JSON mode (?json=true), discovered by watching
network requests on century21mexico.com/v/resultados/... - the page is
server-rendered for SEO but also serves a clean JSON payload of the exact
same result set at the same URL + "?json=true", paginated via /pagina_N/.

Usage:
  python scrape_century21_api.py --estado ciudad-de-mexico --out listings_century21_cdmx.csv
"""
from __future__ import annotations

import argparse
import csv
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
BASE = "https://www.century21mexico.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
PAGE_SIZE = 100
REQUEST_DELAY = 0.8

_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    text = _TAG_RE.sub("", text)
    return re.sub(r"\n{2,}", "\n", text).strip()


def fetch_description(session: requests.Session, url_correcta: str) -> str:
    url = f"{BASE}{url_correcta}?json=true"
    for attempt in range(3):
        try:
            r = session.get(url, timeout=20)
            if r.status_code != 200:
                time.sleep(1.5 * (attempt + 1))
                continue
            obj = r.json()
            desc = (obj.get("entity") or {}).get("descripcion") or ""
            return strip_html(desc)
        except Exception:
            time.sleep(1.5 * (attempt + 1))
    return ""


def fetch_descriptions(recs: list[dict], workers: int = 8) -> None:
    targets = [r for r in recs if r.get("urlCorrectaPropiedad")]
    print(f"\nFetching descriptions for {len(targets)} listings ({workers} parallel workers)...")

    def worker(rec):
        s = requests.Session()
        s.headers.update(HEADERS)
        return rec, fetch_description(s, rec["urlCorrectaPropiedad"])

    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(worker, r) for r in targets]
        for fut in as_completed(futures):
            rec, desc = fut.result()
            rec["_description"] = desc
            done += 1
            if done % 250 == 0 or done == len(targets):
                print(f"    descriptions: {done}/{len(targets)}")

FIELDS = [
    "Broker", "Broker URL", "Platform", "Listing URL", "Listing Name", "Property Type",
    "Price", "Currency", "Bedrooms", "Bathrooms", "Size", "Size Unit", "Description", "Images",
    "Country", "State", "City", "Latitude", "Longitude", "Sale or Rent",
]


def fetch_page(session: requests.Session, estado: str, operacion: str, page: int) -> dict:
    path = f"/v/resultados/en-pais_mexico/en-estado_{estado}/operacion_{operacion}"
    if page > 1:
        path += f"/pagina_{page}"
    url = f"{BASE}{path}?json=true"
    for attempt in range(4):
        try:
            r = session.get(url, timeout=30)
            if r.status_code != 200:
                time.sleep(2 * (attempt + 1))
                continue
            return r.json()
        except Exception as e:
            print(f"    ! error page {page} ({operacion}) attempt {attempt + 1}: {e}")
            time.sleep(2 * (attempt + 1))
    return {}


def to_row(rec: dict, operacion: str) -> dict:
    photos = (rec.get("fotos") or {}).get("propiedadThumbnail") or []
    listing_url = BASE + rec["urlCorrectaPropiedad"] if rec.get("urlCorrectaPropiedad") else ""

    return {
        "Broker": rec.get("nombreAfiliado") or "Century 21 Mexico",
        "Broker URL": "https://www.century21mexico.com",
        "Platform": "Century 21 Mexico (native API)",
        "Listing URL": listing_url,
        "Listing Name": rec.get("encabezado") or rec.get("tipoPropiedadEnTipoOperacion") or "",
        "Property Type": (rec.get("tipoPropiedad") or "Unknown").title(),
        "Price": rec.get("precio"),
        "Currency": rec.get("moneda") or "MXN",
        "Bedrooms": rec.get("recamaras"),
        "Bathrooms": rec.get("banos"),
        "Size": rec.get("m2C") or rec.get("m2T"),
        "Size Unit": "m2",
        "Description": rec.get("_description") or "",
        "Images": "; ".join(photos[:8]),
        "Country": rec.get("pais") or "Mexico",
        "State": rec.get("estado"),
        "City": rec.get("municipio") or rec.get("estado"),
        "Latitude": rec.get("lat"),
        "Longitude": rec.get("lon"),
        "Sale or Rent": "Rent" if operacion == "renta" else "Sale",
    }


def fetch_all(session: requests.Session, estado: str, operacion: str) -> list[dict]:
    first = fetch_page(session, estado, operacion, 1)
    total = first.get("totalHits", "0").replace(",", "")
    total = int(total) if str(total).isdigit() else 0
    print(f"  {operacion}: totalHits={total}")

    results = list(first.get("results") or [])
    seen_ids = {r["id"] for r in results}

    page = 2
    while len(seen_ids) < total:
        time.sleep(REQUEST_DELAY)
        data = fetch_page(session, estado, operacion, page)
        page_results = data.get("results") or []
        if not page_results:
            print(f"    page {page} empty, stopping")
            break
        new = [r for r in page_results if r["id"] not in seen_ids]
        if not new:
            print(f"    page {page} all duplicates, stopping")
            break
        for r in new:
            seen_ids.add(r["id"])
            results.append(r)
        print(f"    page {page}: +{len(new)} (total {len(results)}/{total})")
        page += 1
        if page > 200:
            print("    safety cap on page count reached")
            break

    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--estado", required=True, help="e.g. ciudad-de-mexico")
    parser.add_argument("--out", default=str(HERE / "listings_century21.csv"))
    args = parser.parse_args()

    session = requests.Session()
    session.headers.update(HEADERS)

    all_rows = []
    for operacion in ["venta", "renta"]:
        print(f"[{operacion}]")
        recs = fetch_all(session, args.estado, operacion)
        fetch_descriptions(recs)
        all_rows.extend(to_row(r, operacion) for r in recs)

    print(f"\nTotal rows collected: {len(all_rows)}")
    with open(args.out, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
