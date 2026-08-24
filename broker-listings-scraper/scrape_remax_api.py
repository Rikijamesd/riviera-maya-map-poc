"""
Pulls RE/MAX Mexico's full listing inventory for a given city directly from
its own public JSON API (discovered via network inspection of
remax.com.mx/propiedades), instead of trying to scrape ~30+ dead individual
agent/office pages that mostly have no crawlable content.

The map/FetchMapData endpoint caps each query at 250 results. To get past
that without touching any bot-detection or auth, this recursively bisects
each property type's price range: if a query returns exactly 250 (cap hit),
split the price band in half and recurse on each half, until every band
returns under 250 or the band is too narrow to usefully split further.

Usage:
  python scrape_remax_api.py --city "Ciudad de Mexico" --out listings_remax_cdmx.csv
"""
from __future__ import annotations

import argparse
import csv
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

_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    text = _TAG_RE.sub("", text)
    return re.sub(r"\n{2,}", "\n", text).strip()


def fetch_description(session: requests.Session, propiedad_id) -> str:
    url = f"{BASE}/ajax/FetchPropiedadFlyerData/{propiedad_id}"
    for attempt in range(3):
        try:
            r = session.get(url, timeout=20)
            if r.status_code != 200:
                time.sleep(1.5 * (attempt + 1))
                continue
            obj, _ = json.JSONDecoder().raw_decode(r.text)
            desc = ((obj.get("data") or {}).get("propiedad") or {}).get("descripcion") or ""
            return strip_html(desc)
        except Exception:
            time.sleep(1.5 * (attempt + 1))
    return ""


def fetch_descriptions(seen: dict, workers: int = 8) -> None:
    ids = list(seen.keys())
    print(f"\nFetching descriptions for {len(ids)} listings ({workers} parallel workers)...")

    def worker(pid):
        s = requests.Session()
        s.headers.update({**HEADERS, "Connection": "keep-alive"})
        return pid, fetch_description(s, pid)

    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(worker, pid) for pid in ids]
        for fut in as_completed(futures):
            pid, desc = fut.result()
            seen[pid]["_description"] = desc
            done += 1
            if done % 250 == 0 or done == len(ids):
                print(f"    descriptions: {done}/{len(ids)}")

HERE = Path(__file__).parent
BASE = "https://www.remax.com.mx"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": f"{BASE}/propiedades",
    # Large responses (1MB+) intermittently get corrupted when reused over the
    # same keep-alive connection (identical "Extra data" JSON errors repeat
    # deterministically on retry using the same session) - force a fresh
    # connection per request to avoid that class of bug entirely.
    "Connection": "close",
}
CAP = 250
MIN_BAND_WIDTH = 1000  # pesos - stop bisecting below this, accept undercount


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    s.get(f"{BASE}/propiedades", timeout=20)
    return s


def resolve_city(s: requests.Session, keyword: str) -> tuple[str, str]:
    r = s.post(f"{BASE}/ajax/FetchKeywordResults",
               data={"search": keyword, "count": "TRUE", "estado_id": "undefined"}, timeout=20)
    data = r.json()["data"]
    ciudades = data.get("ciudades") or []
    if not ciudades:
        raise SystemExit(f"No city match found for '{keyword}'")
    top = ciudades[0]
    return top["values"]["ciudad_id"], top["labels"]["ciudad_nombre"]


def get_property_types(s: requests.Session) -> list[dict]:
    r = s.post(f"{BASE}/ajax/FetchPropiedadTipos", timeout=20)
    return r.json()


REQUEST_DELAY = 1.0  # seconds between requests, be a polite citizen of someone else's API


def fetch_band(s: requests.Session, ciudad_id: str, ciudad_nombre: str, tipo_id: str,
                lo: float | None, hi: float | None) -> list[dict]:
    data = {"moneda": "MXN", "ciudad_id": ciudad_id, "locationKeyword": ciudad_nombre, "tipo": tipo_id}
    if lo is not None:
        data["preciodesde"] = str(int(lo))
    if hi is not None:
        data["preciohasta"] = str(int(hi))
    for attempt in range(4):
        time.sleep(REQUEST_DELAY)
        try:
            r = s.post(f"{BASE}/map/FetchMapData", data=data, timeout=30)
            if r.status_code != 200:
                print(f"    ! HTTP {r.status_code} on attempt {attempt + 1} (tipo={tipo_id}, {lo}-{hi})")
                time.sleep(3 * (attempt + 1))
                continue
            # Tolerate trailing garbage after a complete JSON value (seen when
            # a corrupted keep-alive read concatenates two responses) by only
            # parsing the first valid JSON document in the body.
            obj, _ = json.JSONDecoder().raw_decode(r.text)
            return obj.get("data", {}).get("prop_data", [])
        except Exception as e:
            print(f"    ! error on attempt {attempt + 1} (tipo={tipo_id}, {lo}-{hi}): {e}")
            time.sleep(3 * (attempt + 1))
    print(f"    !! GAVE UP on tipo={tipo_id} band {lo}-{hi} after 4 attempts")
    return []


def fetch_type_recursive(s: requests.Session, ciudad_id: str, ciudad_nombre: str, tipo_id: str,
                          tipo_nombre: str, lo: float, hi: float, seen: dict, depth: int = 0) -> None:
    recs = fetch_band(s, ciudad_id, ciudad_nombre, tipo_id, lo, hi)
    for r in recs:
        seen[r["propiedad_id"]] = r

    if len(recs) < CAP or (hi - lo) < MIN_BAND_WIDTH or depth > 25:
        return

    mid = lo + (hi - lo) / 2
    print(f"    [{tipo_nombre}] band {lo:.0f}-{hi:.0f} hit cap ({len(recs)}), splitting at {mid:.0f}")
    fetch_type_recursive(s, ciudad_id, ciudad_nombre, tipo_id, tipo_nombre, lo, mid, seen, depth + 1)
    fetch_type_recursive(s, ciudad_id, ciudad_nombre, tipo_id, tipo_nombre, mid, hi, seen, depth + 1)


FIELDS = [
    "Broker", "Broker URL", "Platform", "Listing URL", "Listing Name", "Property Type",
    "Price", "Currency", "Bedrooms", "Bathrooms", "Size", "Size Unit", "Description", "Images",
    "Country", "State", "City", "Latitude", "Longitude", "Sale or Rent",
]


def to_row(rec: dict) -> dict:
    price = rec.get("mxn_corriente")
    try:
        price = float(price) if price else None
    except (TypeError, ValueError):
        price = None

    images = [
        f"https://cdn.remax.com.mx/{img['path']}"
        for img in (rec.get("imagenes") or [])
        if img.get("path")
    ][:8]

    size = rec.get("m2_construccion") or rec.get("m2_terreno")
    try:
        size = float(size) if size and float(size) > 0 else None
    except (TypeError, ValueError):
        size = None

    listing_url = f"https://www.remax.com.mx/propiedad/{rec.get('propiedad_id')}"

    return {
        "Broker": "RE/MAX Mexico",
        "Broker URL": "https://www.remax.com.mx",
        "Platform": "RE/MAX Mexico (native API)",
        "Listing URL": listing_url,
        "Listing Name": f"{rec.get('tipo_nombre', '')} en {rec.get('colonia_nombre', '')}".strip(),
        "Property Type": rec.get("tipo_nombre") or "Unknown",
        "Price": price,
        "Currency": "MXN",
        "Bedrooms": rec.get("cuartos") or None,
        "Bathrooms": rec.get("banos") or None,
        "Size": size,
        "Size Unit": "m2" if size else None,
        "Description": rec.get("_description") or "",
        "Images": "; ".join(images),
        "Country": "Mexico",
        "State": rec.get("estado_nombre"),
        "City": rec.get("ciudad_nombre"),
        "Latitude": None,
        "Longitude": None,
        "Sale or Rent": {"1": "Sale", "2": "Rent"}.get(str(rec.get("operacion")), "Unknown"),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", required=True, help="City keyword to search, e.g. 'Ciudad de Mexico'")
    parser.add_argument("--out", default=str(HERE / "listings_remax.csv"))
    parser.add_argument("--max-price", type=float, default=200_000_000)
    args = parser.parse_args()

    s = make_session()
    ciudad_id, ciudad_nombre = resolve_city(s, args.city)
    print(f"Resolved '{args.city}' -> ciudad_id={ciudad_id} ({ciudad_nombre})")

    tipos = get_property_types(s)
    print(f"{len(tipos)} property types to sweep")

    seen: dict[str, dict] = {}
    for i, t in enumerate(tipos, start=1):
        print(f"[{i}/{len(tipos)}] {t['tipo_nombre']}")
        fetch_type_recursive(s, ciudad_id, ciudad_nombre, t["tipo_id"], t["tipo_nombre"], 0, args.max_price, seen)
        print(f"    running unique total: {len(seen)}")

    print(f"\nTotal unique listings collected: {len(seen)}")

    fetch_descriptions(seen)

    rows = [to_row(r) for r in seen.values()]
    with open(args.out, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {args.out} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
