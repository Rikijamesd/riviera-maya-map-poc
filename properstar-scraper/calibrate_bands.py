"""Find exact price-band edges for a city -- free, using Properstar's own backend.

plan_city.py estimates band edges by sampling listing prices off the public site,
which came out ~20% off on Tulum. That margin forces conservative band sizes, and
conservative bands mean more paid calls than the data actually requires.

Properstar's backend search API reports an exact `total` for any price filter, for
free. Its pagination is broken (every page returns the same 25 rows, so it cannot
collect a city -- see scrape_api.py), but the *counts* are exact and that is all
band calibration needs. Binary-searching those counts gives edges that pack each
band right up against the retrievable cap, minimising the paid calls that follow.

Bands are cut per property type, because parse.bot's property_type filter takes a
single value and a plan that omits it searches every type -- in Cancun that means
~1,080 land and commercial listings the apartment/house counts never saw, which
overflows the cap on the first slice. The saving over plan_city.py comes from
exactness rather than from merging types: plan_city.py must target ~1,650 per band
to absorb its ~20% sampling error, while exact counts can pack bands to ~1,900.

    python calibrate_bands.py --city cancun --transaction buy
    python calibrate_bands.py --city cancun --target 1900 --out plans/cancun-buy.json

Writes a plan fetch_city.py consumes. Costs 0 credits.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import time
from datetime import datetime, timezone

from scrape_api import Search

UPSTREAM_CAP = 2000


def count(s: Search, lo, hi) -> int:
    """Exact number of listings in a price band. One free request."""
    return s.query(lo, hi, 1).get("total") or 0


def find_edge(s: Search, lo, target: int, ceiling: int) -> int | None:
    """Smallest price E such that count(lo, E) >= target, by binary search.

    `ceiling` bounds the search; None-low bands start from 0.
    """
    low = lo or 0
    high = ceiling
    if count(s, lo, high) < target:
        return None  # the rest of the range fits in one band
    for _ in range(24):
        mid = (low + high) // 2
        if mid <= (lo or 0) or mid >= high:
            break
        n = count(s, lo, mid)
        if n < target:
            low = mid
        else:
            high = mid
        if high - low <= max(500, high // 200):
            break
        time.sleep(0.15)
    return high


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--city", required=True)
    ap.add_argument("--country", default="mexico")
    ap.add_argument("--transaction", default="buy", choices=("buy", "rent"))
    ap.add_argument("--target", type=int, default=1900,
                    help="listings per band; must stay under the 2000 cap")
    ap.add_argument("--types", default="apartment,house",
                    help="comma-separated property types, banded separately to "
                         "match parse.bot's single-valued property_type filter; "
                         "empty string bands on price across all types")
    ap.add_argument("--out", help="plan path (default plans/<city>-<transaction>.json)")
    args = ap.parse_args()

    if args.target >= UPSTREAM_CAP:
        sys.exit(f"--target must be below the {UPSTREAM_CAP} retrievable cap")

    types = [t.strip() for t in args.types.split(",") if t.strip()]
    # parse.bot's property_type filter takes one value, so each type is banded
    # separately and carries its own property_type into the plan. Banding on
    # price alone (--types "") searches EVERY property type -- in Cancun that
    # drags in ~1,080 land and commercial listings the apartment/house counts
    # never saw, which is exactly what made an earlier price-only plan blow the
    # 2,000 cap on its first slice.
    slices, total = [], 0
    for kind in (types or [None]):
        s = Search(args.country, args.city, args.transaction,
                   kind or "apartment-house")
        n_total = count(s, None, None)
        total += n_total
        print(f"{args.city} {args.transaction} [{kind or 'all types'}]: "
              f"{n_total:,} listings, targeting {args.target}/band")

        # A sane upper bound to search within: climb until the band stops growing.
        ceiling = 1_000_000
        while count(s, None, ceiling) < n_total and ceiling < 2_000_000_000:
            ceiling *= 4

        lo, made = None, 0
        while True:
            edge = find_edge(s, lo, args.target, ceiling)
            if edge is None:
                n = count(s, lo, None)
                slices.append({"lo": lo, "hi": None, "expected": n, "kind": kind})
                print(f"  {('>' + format(lo, ',')) if lo else 'all':>22}  {n:>6}")
                break
            n = count(s, lo, edge)
            slices.append({"lo": lo, "hi": edge, "expected": n, "kind": kind})
            print(f"  {(f'{lo:,}-{edge:,}' if lo else f'<{edge:,}'):>22}  {n:>6}")
            lo = edge
            made += 1
            if made > 60:
                sys.exit("too many bands -- raise --target or check the city slug")
        print()

    over = [x for x in slices if x["expected"] > UPSTREAM_CAP]
    covered = sum(x["expected"] for x in slices)
    print(f"\n{len(slices)} bands, {covered:,} listings covered "
          f"(city total {total:,}), {s.requests} free requests, 0 credits")
    if over:
        print(f"  ! {len(over)} band(s) exceed the {UPSTREAM_CAP} cap -- "
              f"lower --target and re-run")

    plan = {
        "city": args.city,
        "country": args.country,
        "transaction": args.transaction,
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "city_total": total,
        "retrievable": UPSTREAM_CAP,
        "target_per_band": args.target,
        "calibration": "exact counts from Properstar's backend search API (0 credits)",
        "projected_calls": len(slices),
        "slices": [],
    }
    for x in slices:
        params = {}
        if x.get("kind"):
            params["property_type"] = x["kind"]
        if x["lo"] is not None:
            params["min_price"] = x["lo"]
        if x["hi"] is not None:
            params["max_price"] = x["hi"]
        rng = (f"{x['lo'] // 1000}k-{x['hi'] // 1000}k" if x["lo"] and x["hi"]
               else f"<{x['hi'] // 1000}k" if x["hi"]
               else f">{x['lo'] // 1000}k")
        lbl = f"{x['kind'][:3]} {rng}" if x.get("kind") else rng
        plan["slices"].append({"label": lbl, "params": params,
                               "expected": x["expected"]})

    out = args.out or f"plans/{args.city}-{args.transaction}.json"
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(plan, fh, indent=2)
    print(f"\nwrote {out}\n  run: python fetch_city.py --plan {out}")


if __name__ == "__main__":
    main()
