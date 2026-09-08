"""Build a parse.bot slice plan for a city -- using only free public data.

Properstar caps any single search at 2,000 retrievable results, so a city with
more than that can only be collected by slicing it into filter combinations that
each stay under the cap. This script works out those slices without spending a
single credit:

  1. Solve the site's Azure WAF challenge once with a browser, then reuse the
     resulting cookies for fast plain-HTTP requests (~2s/page instead of ~12s).
  2. Read the exact population per property type off the public site -- the
     search response carries `total` and `totalRetrievable` directly.
  3. Sample listing prices to estimate the price distribution per type.
  4. Cut each type into contiguous GBP price bands of ~TARGET listings.

Price is the slicing dimension on purpose. Bedroom filters work but leave a hole:
some listings carry no bedroom value at all, and `max_bedrooms=0` matches nothing,
so those are unreachable. Bands are left open-ended at the top and bottom so
listings with no price still fall inside one.

Bands target well under the per-call row limit because sample-derived cuts came
out ~20% off on Tulum. That margin used to be cheap: with a 1,000-row page and a
2,000 cap, an overshooting band merely cost one extra page. The endpoint now
returns both upstream pages in a single call, so the page limit and the cap are
both 2,000 and an overshoot silently LOSES the excess. Keep --target at or below
~1,650 so target + 20% still clears the cap.

Usage:
    python plan_city.py --city cancun
    python plan_city.py --city "playa-del-carmen" --target 900 --sample-pages 40

Writes plans/<city>.json, which fetch_city.py consumes.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import statistics
import sys
import time
from datetime import datetime, timezone

from scrapling.fetchers import Fetcher, StealthyFetcher

SITE = "https://www.properstar.co.uk"
TYPES = ("apartment", "house")
UPSTREAM_CAP = 2000
PAGE_ROWS = 20  # listings per public search page
API_PAGE_ROWS = 2000  # parse.bot rows per call (endpoint combines both upstream pages)


def extract_initial_state(html: str) -> dict | None:
    """Pull the `window.__INITIAL_STATE__ = {...}` blob out of the page.

    Brace-matched rather than regexed, since the JSON nests braces inside
    quoted strings.
    """
    marker = "window.__INITIAL_STATE__ = "
    start = html.find(marker)
    if start == -1:
        return None
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
    try:
        return json.loads(html[start:i])
    except json.JSONDecodeError:
        return None


class Site:
    """Free access to Properstar's public search, past the WAF."""

    def __init__(self, country: str, city: str, transaction: str = "buy"):
        self.country = country
        self.city = city
        self.transaction = transaction
        self.cookies: dict[str, str] = {}

    def base(self, kind: str = "apartment-house") -> str:
        return f"{SITE}/{self.country}/{self.city}/{self.transaction}/{kind}"

    def bootstrap(self, attempts: int = 4) -> None:
        """Solve the WAF challenge and keep the resulting cookies.

        A 403 means the challenge didn't settle in time -- it is transient and
        usually clears on a retry with a longer wait. Only 404 (bad slug) is
        genuinely fatal.
        """
        print("solving WAF challenge (one browser load)...", flush=True)
        for attempt in range(1, attempts + 1):
            page = StealthyFetcher.fetch(self.base(), headless=True,
                                         network_idle=True,
                                         wait=8000 + attempt * 3000)
            if page.status == 200:
                self.cookies = {c["name"]: c["value"] for c in page.cookies}
                return
            if page.status == 404:
                sys.exit(f"no such city: {self.base()} returned 404.\n"
                         f"Find the right slug by searching the city on {SITE} "
                         f"and copying it out of the URL (accents are usually "
                         f"dropped, e.g. Cancún -> cancun, Mérida -> merida).")
            print(f"  WAF returned {page.status}, retry {attempt}/{attempts}",
                  flush=True)
            time.sleep(2 * attempt)
        sys.exit(f"could not get past the WAF for {self.base()} "
                 f"after {attempts} attempts")

    def state(self, kind: str = "apartment-house", page_num: int = 1,
              retries: int = 2) -> dict | None:
        """Full `__INITIAL_STATE__` for one search page (results + entities)."""
        url = self.base(kind) + (f"?p={page_num}" if page_num > 1 else "")
        for attempt in range(retries + 1):
            try:
                r = Fetcher.get(url, stealthy_headers=True, cookies=self.cookies)
                body = r.body.decode("utf-8") if isinstance(r.body, bytes) else r.body
                state = extract_initial_state(body)
                if r.status == 200 and state:
                    return state
            except Exception:
                pass
            self.bootstrap()  # cookies likely expired
        return None

    def search(self, kind: str = "apartment-house", page_num: int = 1) -> dict | None:
        state = self.state(kind, page_num)
        return state["search"]["results"] if state else None


def money(v: int) -> str:
    """Compact GBP label. Rentals are monthly (hundreds), sales are hundreds of
    thousands, so 'k' rounding only makes sense above ~10k."""
    return f"{v // 1000}k" if v >= 10_000 else str(v)


def gbp_price(listing: dict) -> int | None:
    """Converted GBP price -- the currency parse.bot's filters use."""
    for v in listing.get("price", {}).get("values", []):
        if v.get("currencyId") == "GBP" and v.get("value") is not None:
            return round(v["value"])
    return None


def type_totals(site: Site) -> dict[str, int]:
    totals = {}
    for kind in TYPES:
        res = site.search(kind)
        if res is None:
            sys.exit(f"could not read totals for {kind}")
        got = res["params"]["filters"].get("types") or []
        expected = kind.capitalize()
        if expected not in got:
            sys.exit(f"filter for '{kind}' came back as types={got}; slug not honoured")
        totals[kind] = res.get("total") or 0
        print(f"  {kind:10} {totals[kind]:>6} listings "
              f"(retrievable in one search: {res.get('totalRetrievable')})")
    return totals


def sample_prices(site: Site, kind: str, pages: int) -> list[int]:
    """Collect GBP prices from the first N public pages of one type."""
    prices: list[int] = []
    for p in range(1, pages + 1):
        res = site.search(kind, p)
        if not res:
            break
        listings = res.get("listings") or []
        if not listings:
            break
        prices.extend(x for x in (gbp_price(l) for l in listings) if x)
        time.sleep(0.4)
    return prices


def build_bands(kind: str, total: int, prices: list[int], target: int) -> list[dict]:
    """Cut one property type into contiguous, open-ended price bands."""
    if total == 0:
        return []
    n = max(1, math.ceil(total / target))
    if n == 1:
        return [{"label": f"{kind[:3]} all", "params": {"property_type": kind},
                 "expected": total}]
    if len(prices) < 40:
        print(f"  ! only {len(prices)} sampled prices for {kind}; "
              f"bands may be uneven", flush=True)

    ordered = sorted(prices)
    cuts = [ordered[round(i * len(ordered) / n)] for i in range(1, n)]
    cuts = sorted(set(cuts))  # drop duplicate cuts in flat distributions

    slices = []
    edges: list[int | None] = [None, *cuts, None]
    each = round(total / (len(cuts) + 1))
    for i in range(len(edges) - 1):
        lo, hi = edges[i], edges[i + 1]
        params: dict = {"property_type": kind}
        if lo is not None:
            params["min_price"] = lo
        if hi is not None:
            params["max_price"] = hi
        if lo is None:
            label = f"{kind[:3]} <{money(hi)}"
        elif hi is None:
            label = f"{kind[:3]} >{money(lo)}"
        else:
            label = f"{kind[:3]} {money(lo)}-{money(hi)}"
        slices.append({"label": label, "params": params, "expected": each})
    return slices


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--city", required=True, help="Properstar city slug, e.g. cancun")
    ap.add_argument("--country", default="mexico")
    ap.add_argument("--transaction", default="buy", choices=("buy", "rent"),
                    help="sale or rental listings (rent support on the parse.bot "
                         "side is unconfirmed -- see README)")
    ap.add_argument("--target", type=int, default=1650,
                    help="listings per band (default 950; page limit is 1000)")
    ap.add_argument("--sample-pages", type=int, default=30,
                    help="public pages to sample per type (20 listings each)")
    ap.add_argument("--out", help="output path (default plans/<city>.json)")
    ap.add_argument("--types", default=",".join(TYPES),
                    help="comma-separated property types to plan (default: both). "
                         "Restrict to the type(s) that actually exceed the cap -- "
                         "a type that already fits free shouldn't be billed just "
                         "because it shares a city with one that doesn't.")
    args = ap.parse_args()

    want_types = [t.strip() for t in args.types.split(",") if t.strip()]
    for t in want_types:
        if t not in TYPES:
            sys.exit(f"unknown type '{t}'; choose from {TYPES}")

    if args.target > API_PAGE_ROWS:
        sys.exit(f"--target above {API_PAGE_ROWS} forces a second page on every band")

    site = Site(args.country, args.city, args.transaction)
    site.bootstrap()

    probe = site.search()
    if probe is None:
        sys.exit("could not read the city's search page")
    city_total = probe.get("total") or 0
    print(f"\n{args.city}: {city_total} listings total "
          f"(cap per search: {probe.get('totalRetrievable')})\n")

    totals = type_totals(site)
    covered = sum(totals.values())
    if covered != city_total:
        print(f"  note: type totals sum to {covered} vs {city_total} overall "
              f"(difference is other property types)")

    print("\nsampling prices...", flush=True)
    slices: list[dict] = []
    for kind, total in totals.items():
        if total == 0 or kind not in want_types:
            continue
        want_pages = min(args.sample_pages, math.ceil(total / PAGE_ROWS))
        prices = sample_prices(site, kind, want_pages) if total > args.target else []
        if prices:
            print(f"  {kind:10} {len(prices)} prices  "
                  f"median GBP {statistics.median(prices):,.0f}")
        slices.extend(build_bands(kind, total, prices, args.target))

    calls = sum(max(1, math.ceil(s["expected"] / API_PAGE_ROWS)) for s in slices)
    plan = {
        "city": args.city,
        "country": args.country,
        "transaction": args.transaction,
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "city_total": city_total,
        # When this equals city_total the whole market fits under Properstar's
        # ceiling, so scrape_free.py can collect 100% of it for no credits.
        "retrievable": probe.get("totalRetrievable") or 0,
        "type_totals": totals,
        "types_planned": want_types,
        "target_per_band": args.target,
        "projected_calls": calls,
        "slices": slices,
    }

    suffix = "" if args.transaction == "buy" else f"-{args.transaction}"
    out = args.out or os.path.join("plans", f"{args.city}{suffix}.json")
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2)

    # Rentals are a separate parse.bot scraper billed at 10x the sale rate.
    rate = 10 if args.transaction == "rent" else 1
    credits = calls * rate
    print(f"\n{len(slices)} slices, ~{calls} calls (~{credits} credits, "
          f"~${credits * 0.03:.2f} at {rate} cr/call) for ~{covered} listings")
    for s in slices:
        filt = {k: v for k, v in s["params"].items() if k != "property_type"}
        print(f"  {s['label']:18} ~{s['expected']:<6} {filt or '(whole type)'}")
    over = [s for s in slices if s["expected"] > UPSTREAM_CAP]
    if over:
        print(f"\n  ! {len(over)} band(s) project over the {UPSTREAM_CAP} cap; "
              f"lower --target")
    print(f"\nwrote {out}\n  run: python fetch_city.py --plan {out}")


if __name__ == "__main__":
    main()
