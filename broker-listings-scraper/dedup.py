"""
Deduplicates scraped listings across brokers - the same physical unit is
very often marketed by multiple brokers (cross-posting, referral networks,
shared platforms like Tokko Broker) with different wording and prices.

Matching strategy (a listing pair is a probable duplicate if ANY of these hold):
  1. Same first-photo perceptual hash (Hamming distance <= IMAGE_HASH_MAX_DIST) -
     the strongest signal: brokers overwhelmingly reuse the same marketing
     photos for the same unit even when price/description text differs.
  2. Both have lat/lon within ~150m AND price within PRICE_TOLERANCE AND
     bedroom counts match (when both known).
  3. Same City AND bedroom/bathroom counts match AND price within
     PRICE_TOLERANCE AND size within SIZE_TOLERANCE.
  4. Listing-name text similarity above NAME_SIMILARITY_MIN AND price within
     PRICE_TOLERANCE (catches the same pre-construction unit resold/reposted
     under near-identical titles by different brokers).

To keep the O(n^2) pairwise comparison tractable, listings are first bucketed
("blocked") by rounded price + bedroom count - genuine duplicates almost
always share both, so this cuts comparison volume drastically without
meaningfully hurting recall.

Usage:
  python dedup.py --in listings_v2.xlsx --out listings_deduped.xlsx
  python dedup.py --in listings_v2.xlsx --out listings_deduped.xlsx --no-image-hash   # faster, skips photo downloads
"""
from __future__ import annotations

import argparse
import difflib
import io
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
import truststore
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

truststore.inject_into_ssl()

try:
    import imagehash
    from PIL import Image

    HAS_IMAGEHASH = True
except ImportError:
    HAS_IMAGEHASH = False

HERE = Path(__file__).parent

PRICE_TOLERANCE = 0.08   # 8%
SIZE_TOLERANCE = 0.12    # 12%
NAME_SIMILARITY_MIN = 0.82
IMAGE_HASH_MAX_DIST = 8  # out of 64 bits
DISTANCE_METERS_MAX = 150
HASH_WORKERS = 24  # concurrent image downloads for perceptual hashing (I/O-bound, not CPU-bound)

HEADER_FILL = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
HEADER_FONT = Font(bold=True, color="FFFFFF")


class UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def load_rows(path: Path) -> list[dict]:
    wb = load_workbook(path, data_only=True)
    rows = []
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        if ws.max_row < 2:
            continue
        headers = [c.value for c in ws[1]]
        for r in ws.iter_rows(min_row=2, values_only=True):
            d = dict(zip(headers, r))
            d["Sale or Rent"] = sheet_name.replace("For ", "")
            rows.append(d)
    return rows


def to_float(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(str(v).replace(",", ""))
    except (ValueError, TypeError):
        return None


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    from math import atan2, cos, radians, sin, sqrt

    r = 6371000
    p1, p2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(p1) * cos(p2) * sin(dlambda / 2) ** 2
    return 2 * r * atan2(sqrt(a), sqrt(1 - a))


_image_hash_cache: dict[str, "imagehash.ImageHash | None"] = {}


def hash_first_image(images_field: str | None) -> "imagehash.ImageHash | None":
    if not HAS_IMAGEHASH or not images_field:
        return None
    url = images_field.split(";")[0].strip()
    if not url:
        return None
    if url in _image_hash_cache:
        return _image_hash_cache[url]
    try:
        resp = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        img = Image.open(io.BytesIO(resp.content))
        h = imagehash.phash(img)
        _image_hash_cache[url] = h
        return h
    except Exception:
        _image_hash_cache[url] = None
        return None


def within_tolerance(a: float | None, b: float | None, tol: float) -> bool:
    if a is None or b is None:
        return False
    if a == 0 or b == 0:
        return a == b
    return abs(a - b) / max(a, b) <= tol


def beds_match(a, b) -> bool:
    fa, fb = to_float(a), to_float(b)
    if fa is None or fb is None:
        return False
    return fa == fb


def is_probable_duplicate(r1: dict, r2: dict, h1, h2) -> bool:
    # Signal 1: image hash
    if h1 is not None and h2 is not None:
        if (h1 - h2) <= IMAGE_HASH_MAX_DIST:
            return True

    price1, price2 = to_float(r1.get("Price")), to_float(r2.get("Price"))

    # Signal 2: geo proximity + price + beds
    lat1, lon1 = to_float(r1.get("Latitude")), to_float(r1.get("Longitude"))
    lat2, lon2 = to_float(r2.get("Latitude")), to_float(r2.get("Longitude"))
    if None not in (lat1, lon1, lat2, lon2):
        if haversine_m(lat1, lon1, lat2, lon2) <= DISTANCE_METERS_MAX and within_tolerance(price1, price2, PRICE_TOLERANCE):
            if r1.get("Bedrooms") is None or r2.get("Bedrooms") is None or beds_match(r1.get("Bedrooms"), r2.get("Bedrooms")):
                return True

    # Signal 3: same city + specs match
    city1, city2 = (r1.get("City") or "").strip().lower(), (r2.get("City") or "").strip().lower()
    if city1 and city1 == city2:
        if beds_match(r1.get("Bedrooms"), r2.get("Bedrooms")) and within_tolerance(price1, price2, PRICE_TOLERANCE):
            if within_tolerance(to_float(r1.get("Size")), to_float(r2.get("Size")), SIZE_TOLERANCE):
                return True

    # Signal 4: near-identical title + similar price
    name1, name2 = r1.get("Listing Name"), r2.get("Listing Name")
    if name1 and name2 and within_tolerance(price1, price2, PRICE_TOLERANCE):
        ratio = difflib.SequenceMatcher(None, name1.lower(), name2.lower()).ratio()
        if ratio >= NAME_SIMILARITY_MIN:
            return True

    return False


def block_key(row: dict) -> tuple:
    price = to_float(row.get("Price"))
    price_bucket = round(price / 10000) if price else None
    beds = to_float(row.get("Bedrooms"))
    return (price_bucket, beds)


def dedup(rows: list[dict], use_image_hash: bool) -> list[dict]:
    n = len(rows)
    hashes = [None] * n
    if use_image_hash and HAS_IMAGEHASH:
        print(f"Hashing first photo for {n} listings ({HASH_WORKERS} concurrent downloads, best-effort, skips on failure)...")
        images = [r.get("Images") for r in rows]
        done = 0
        with ThreadPoolExecutor(max_workers=HASH_WORKERS) as pool:
            for i, h in enumerate(pool.map(hash_first_image, images)):
                hashes[i] = h
                done += 1
                if done % 100 == 0:
                    print(f"  hashed {done}/{n}")

    blocks: dict[tuple, list[int]] = {}
    for i, r in enumerate(rows):
        blocks.setdefault(block_key(r), []).append(i)

    uf = UnionFind(n)
    for indices in blocks.values():
        for a in range(len(indices)):
            for b in range(a + 1, len(indices)):
                i, j = indices[a], indices[b]
                if is_probable_duplicate(rows[i], rows[j], hashes[i], hashes[j]):
                    uf.union(i, j)

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(uf.find(i), []).append(i)

    def completeness(r: dict) -> int:
        return sum(1 for v in r.values() if v not in (None, ""))

    deduped_rows = []
    for group_indices in groups.values():
        best_idx = max(group_indices, key=lambda i: completeness(rows[i]))
        canonical = dict(rows[best_idx])
        sources = sorted({rows[i]["Broker"] for i in group_indices})
        urls = sorted({rows[i]["Listing URL"] for i in group_indices if rows[i].get("Listing URL")})
        canonical["Source Count"] = len(group_indices)
        canonical["Source Brokers"] = "; ".join(sources)
        canonical["Source URLs"] = "; ".join(urls)
        deduped_rows.append(canonical)

    return deduped_rows


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
        buckets.get(r.get("Sale or Rent", "Unknown"), buckets["Unknown"]).append(r)

    all_fields = list(rows[0].keys()) if rows else []

    for sheet_name, bucket_rows in [("For Sale", buckets["Sale"]), ("For Rent", buckets["Rent"]), ("Unclassified", buckets["Unknown"])]:
        ws = wb.create_sheet(sheet_name)
        ws.append(all_fields)
        for r in bucket_rows:
            ws.append([r.get(f) for f in all_fields])
        if bucket_rows:
            style_sheet(ws, len(all_fields))
    wb.save(out_path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="in_path", required=True)
    parser.add_argument("--out", dest="out_path", required=True)
    parser.add_argument("--no-image-hash", action="store_true", help="skip downloading/hashing photos (faster, less accurate)")
    args = parser.parse_args()

    rows = load_rows(Path(args.in_path))
    print(f"Loaded {len(rows)} raw listing rows")

    deduped = dedup(rows, use_image_hash=not args.no_image_hash)
    print(f"Deduped to {len(deduped)} unique listings ({len(rows) - len(deduped)} duplicates merged)")

    write_workbook(deduped, Path(args.out_path))
    print(f"Wrote {args.out_path}")


if __name__ == "__main__":
    main()
