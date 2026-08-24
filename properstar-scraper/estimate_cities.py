"""Cost a city (or a whole roadmap of cities) before spending anything.

Free and fast: a cost estimate only needs each market's total, which the public
search page reports directly -- no price sampling needed, so this is ~2 requests
per city rather than the ~60 that full planning takes.

    python estimate_cities.py --cities tulum,cancun,merida
    python estimate_cities.py --cities tulum --markets buy

Reads nothing from parse.bot and spends no credits.

Two routes are costed per market:
  * parse.bot -- ~1 credit per 1,000 listings, ~100% coverage
  * free scraping -- 0 credits, ~74% in one pass, ~93% after two, ~99% after three,
    because Properstar re-serves listings across pages non-deterministically.
    scrape_free.py merges passes, so coverage converges with repeated runs.

Free trades time for money (~3 min per pass per market), not completeness for
money -- but it cannot exceed the 2,000 cap at all, so markets above that still
need parse.bot regardless of how many passes you run.
"""
from __future__ import annotations

import argparse
import math
import sys

from plan_city import Site

CREDIT_USD = 0.03
UPSTREAM_CAP = 2000
BAND_TARGET = 950  # rows per band under optimal planning
FREE_COVERAGE = 0.98  # after 3 merging passes (74% -> 93% -> 98.6% measured)


# Sale and rental are separate parse.bot scrapers on separate pricing; a rental
# call costs 10x a sale call, which flips the free-vs-paid decision for rentals.
CREDITS_PER_CALL = {"buy": 1, "rent": 10}


def calls_for(total: int) -> int:
    """parse.bot calls needed, assuming optimally sized bands."""
    return math.ceil(total / BAND_TARGET) if total else 0


def credits_for(total: int, transaction: str = "buy") -> int:
    return calls_for(total) * CREDITS_PER_CALL.get(transaction, 1)


def market_total(site: Site) -> tuple[int, int]:
    res = site.search()
    if not res:
        return -1, -1
    return res.get("total") or 0, res.get("totalRetrievable") or 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cities", required=True,
                    help="comma-separated slugs, e.g. tulum,cancun,merida")
    ap.add_argument("--country", default="mexico")
    ap.add_argument("--markets", default="buy,rent",
                    help="comma-separated: buy, rent (default both)")
    args = ap.parse_args()

    cities = [c.strip() for c in args.cities.split(",") if c.strip()]
    markets = [m.strip() for m in args.markets.split(",") if m.strip()]

    # WAF cookies are domain-wide, so one browser bootstrap covers every city.
    seed = Site(args.country, cities[0], markets[0])
    seed.bootstrap()
    cookies = seed.cookies

    rows = []
    for city in cities:
        for market in markets:
            site = Site(args.country, city, market)
            site.cookies = cookies
            total, retrievable = market_total(site)
            if total < 0:
                print(f"  ! {city}/{market}: could not read (bad slug?)",
                      file=sys.stderr)
                continue
            rows.append({
                "city": city, "market": market, "total": total,
                "capped": retrievable < total,
                "credits": credits_for(total, market),
                # Free scraping can never see past the upstream cap, so a capped
                # market's free yield is a fraction of 2,000 -- not of the total.
                "free_rows": int(min(total, UPSTREAM_CAP) * FREE_COVERAGE),
            })
            print(f"  read {city}/{market}: {total}", flush=True)

    if not rows:
        sys.exit("nothing to estimate")

    print(f"\n{'city':<18}{'market':<7}{'listings':>9}{'parse.bot':>11}"
          f"{'cost':>8}{'free gets':>11}{'  note'}")
    print("-" * 70)
    for r in rows:
        note = "over cap; free can't finish" if r["capped"] else ""
        print(f"{r['city']:<18}{r['market']:<7}{r['total']:>9,}"
              f"{r['credits']:>9} cr{'$' + format(r['credits'] * CREDIT_USD, '.2f'):>8}"
              f"{r['free_rows']:>11,}  {note}")

    tot_listings = sum(r["total"] for r in rows)
    tot_credits = sum(r["credits"] for r in rows)
    print("-" * 70)
    print(f"{'TOTAL':<25}{tot_listings:>9,}{tot_credits:>9} cr"
          f"{'$' + format(tot_credits * CREDIT_USD, '.2f'):>8}"
          f"{sum(r['free_rows'] for r in rows):>11,}")

    missed = tot_listings - sum(r["free_rows"] for r in rows)
    print(f"\nparse.bot for everything: {tot_credits} credits "
          f"(~${tot_credits * CREDIT_USD:.2f}) for ~{tot_listings:,} listings")
    print(f"free everywhere:          0 credits, but ~{missed:,} listings "
          f"({missed / tot_listings * 100:.0f}%) never collected")
    print(f"\nestimates assume optimal ~{BAND_TARGET}-row bands; run plan_city.py "
          f"per city for exact slices.")


if __name__ == "__main__":
    main()
