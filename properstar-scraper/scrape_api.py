"""Collect a whole city off Properstar's own backend search API -- no credits, no cap.

Properstar's front end is a thin client over ListGlobally. Its search backend
accepts a price filter, and `totalRetrievable` then tracks the *band* rather than
the city -- so the 2,000-result ceiling that forced paid parse.bot price-band
slicing does not bind once you band the search yourself:

    no filter        total 9213   retrievable 2000   <- capped
    price 100k-200k  total 1625   retrievable 1625   <- all of it
    price 200k-300k  total 1462   retrievable 1462

This bands adaptively (bisecting on price whenever a band exceeds the cap, the
same strategy fetch_city.py uses for paid slices) and pages through each band, so
an arbitrarily large city is collectable for nothing.

    python scrape_api.py --city cancun --transaction buy
    python scrape_api.py --city mexico-city --transaction buy --type apartment

Output columns and merge behaviour match scrape_free.py / fetch_city.py, so free
and paid pulls still merge without remapping.

Notes:
  - The bearer is the `token` cookie handed to any anonymous visitor; no login.
  - `pageSize` is clamped to 25 server-side however large a value is sent.
  - search-api.listglobally.com is a different origin from the WAF'd www host, so
    the Azure challenge applies only to the initial page load.
"""
from __future__ import annotations

import argparse
import copy
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request

from plan_city import SITE, Site
from scrape_free import FIELDS, map_listing

API = "https://search-api.listglobally.com/api/v2/searches"
UPSTREAM_CAP = 2000   # per-search retrievable ceiling; bands must stay under it
API_PAGE = 25         # server clamps pageSize to this no matter what we ask for
MAX_DEPTH = 8         # price-bisection depth guard


class Search:
    """One authenticated session against the backend search API."""

    def __init__(self, country: str, city: str, transaction: str, kind: str):
        self.site = Site(country, city, transaction)
        self.site.bootstrap()
        page = self.site.state(kind)
        if not page:
            sys.exit(f"could not read search state for {city}/{kind}")
        self.token = self.site.cookies.get("token")
        if not self.token:
            sys.exit("no `token` cookie on the page load -- cannot authenticate")
        self.descriptor = page["search"]["results"]["params"]
        # portal.portalId, NOT portal.id -- the latter is a dict of URLs, and
        # sending it fails with a JSON parse error naming search.portalId.
        self.portal_id = page["portal"]["portalId"]
        self.requests = 0

    def query(self, lo, hi, page_num: int) -> dict:
        filters = copy.deepcopy(self.descriptor["filters"])
        filters["price"] = {"min": lo, "max": hi}
        params = {**copy.deepcopy(self.descriptor["params"]),
                  "pageSize": API_PAGE, "page": page_num,
                  "saveInDb": False, "sort": "-creationDate"}
        payload = {"search": {"filters": {"listings": filters},
                              "params": params,
                              "portalId": self.portal_id}}
        body = json.dumps(payload).encode()
        headers = {"Content-Type": "application/json",
                   "Accept": "application/json", "Accept-Language": "en",
                   "Origin": SITE, "Referer": SITE + "/",
                   "User-Agent": "Mozilla/5.0"}
        for attempt in range(3):
            req = urllib.request.Request(
                API, data=body,
                headers={**headers, "Authorization": f"Bearer {self.token}"})
            try:
                self.requests += 1
                with urllib.request.urlopen(req, timeout=120) as resp:
                    return json.loads(resp.read().decode("utf-8", "replace"))
            except urllib.error.HTTPError as err:
                if err.code == 401:  # token expired mid-run -- re-issue and retry
                    self.site.bootstrap()
                    self.token = self.site.cookies.get("token", self.token)
                elif err.code >= 500:
                    time.sleep(2 * (attempt + 1))
                else:
                    raise
            except Exception:
                time.sleep(2 * (attempt + 1))
        raise RuntimeError(f"search failed for band {lo}-{hi} page {page_num}")


SEED_PIVOT = 200_000   # GBP; a mid-market first cut for an unbounded search


def next_pivot(lo, hi):
    """Midpoint of a price band, in the filter's display currency."""
    if lo is None and hi is None:
        return SEED_PIVOT
    if lo is None:
        return hi // 2 or None
    if hi is None:
        return lo * 2
    mid = (lo + hi) // 2
    return mid if lo < mid < hi else None


def label(lo, hi) -> str:
    def fmt(v):
        return f"{v // 1000}k" if v and v >= 10_000 else (str(v) if v else "")
    if lo and hi:
        return f"{fmt(lo)}-{fmt(hi)}"
    if hi:
        return f"<{fmt(hi)}"
    if lo:
        return f">{fmt(lo)}"
    return "all"


def collect(s: Search, lo, hi, out: dict, budget: int, depth: int = 0) -> None:
    """Page through one price band, bisecting it first if it exceeds the cap."""
    if s.requests >= budget:
        print(f"  request budget reached ({budget}) -- stopping")
        return

    head = s.query(lo, hi, 1)
    total = head.get("total") or 0
    if total == 0:
        return

    if total > UPSTREAM_CAP and depth < MAX_DEPTH:
        # Bisect on the price axis itself rather than on the listings returned:
        # the API sends each listing's Original price (MXN/USD here) while the
        # filter is denominated in the portal's display currency, so returned
        # values cannot be used to pick a pivot in filter units.
        pivot = next_pivot(lo, hi)
        if pivot and (lo is None or pivot > lo) and (hi is None or pivot < hi):
            print(f"  {label(lo, hi):16} {total:>6} > cap, splitting at {pivot:,}")
            collect(s, lo, pivot, out, budget, depth + 1)
            collect(s, pivot, hi, out, budget, depth + 1)
            return
        print(f"  {label(lo, hi):16} {total:>6} > cap but not splittable "
              f"-- keeping first {UPSTREAM_CAP}")

    pages = (min(total, UPSTREAM_CAP) + API_PAGE - 1) // API_PAGE
    got = 0
    for page_num in range(1, pages + 1):
        if s.requests >= budget:
            print(f"  request budget reached ({budget}) -- stopping")
            return
        data = head if page_num == 1 else s.query(lo, hi, page_num)
        listings = data.get("listings") or []
        if not listings:
            break
        for item in listings:
            out[item["id"]] = map_listing(item, {})
        got += len(listings)
        if page_num % 20 == 0:
            print(f"  {label(lo, hi):16} page {page_num}/{pages}  "
                  f"{got}/{total}  (unique {len(out)})", flush=True)
        time.sleep(0.25)
    print(f"  {label(lo, hi):16} done {got}/{total}  (unique {len(out)})", flush=True)


def write_outputs(rows: list, json_path: str, csv_path: str) -> None:
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=2)
    # Merged runs carry rows from fetch_city.py whose parse.bot payload has
    # fields this collector never produces (e.g. is_project); widen the header
    # rather than let DictWriter raise on them.
    extra = sorted({k for r in rows for k in r} - set(FIELDS))
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS + extra)
        writer.writeheader()
        for row in rows:
            item = dict(row)
            item["pictures"] = "; ".join(item.get("pictures") or [])
            writer.writerow(item)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--city", required=True)
    ap.add_argument("--country", default="mexico")
    ap.add_argument("--transaction", default="buy", choices=("buy", "rent"))
    ap.add_argument("--type", default="apartment-house",
                    help="apartment, house, or apartment-house (default)")
    ap.add_argument("--max-requests", type=int, default=2000,
                    help="hard ceiling on API requests for this run")
    ap.add_argument("--fresh", action="store_true",
                    help="discard existing output instead of merging into it")
    args = ap.parse_args()

    suffix = "" if args.transaction == "buy" else "_rent"
    json_path = f"properstar_{args.city}{suffix}.json"
    csv_path = f"properstar_{args.city}{suffix}.csv"

    out: dict = {}
    if not args.fresh and os.path.exists(json_path):
        with open(json_path, encoding="utf-8") as fh:
            for row in json.load(fh):
                out[row["id"]] = row
    carried = len(out)
    print(f"carried in: {carried} existing rows" if carried else "starting fresh")

    s = Search(args.country, args.city, args.transaction, args.type)
    print(f"authenticated (portalId {s.portal_id}); collecting {args.city} "
          f"{args.transaction} [{args.type}]\n")
    try:
        collect(s, None, None, out, args.max_requests)
    except KeyboardInterrupt:
        print("\ninterrupted -- writing what was collected so far")

    rows = list(out.values())
    write_outputs(rows, json_path, csv_path)
    print(f"\n{len(rows)} unique listings (+{len(rows) - carried} new) "
          f"in {s.requests} requests, 0 credits -> {csv_path} / {json_path}")


if __name__ == "__main__":
    main()
