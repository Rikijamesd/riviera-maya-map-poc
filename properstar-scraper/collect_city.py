"""Collect a city's sale AND rental listings as two separate datasets.

One command per city. For each market it plans first (free), then picks the
cheapest route that still reaches 100%:

  * market fits under Properstar's 2,000-result ceiling -> scrape_free.py, no
    credits, and it recovers `date_listed` which parse.bot leaves empty
  * market exceeds the ceiling -> price-band slicing via parse.bot, roughly
    1 credit per 1,000 listings

Planning never spends credits, so `--plan-only` is always safe. Paid collection
requires --yes; without it the script prints the cost and stops.

    python collect_city.py --city tulum --plan-only
    python collect_city.py --city tulum --yes

Outputs (two datasets, never merged -- sale and rental prices are not comparable):
    properstar_<city>.csv        sale
    properstar_<city>_rent.csv   rental
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
UPSTREAM_CAP = 2000
CREDIT_USD = 0.03
MARKETS = ("buy", "rent")


def run(script: str, *args: str) -> int:
    cmd = [sys.executable, "-u", os.path.join(HERE, script), *args]
    print(f"\n$ {' '.join([script, *args])}\n", flush=True)
    return subprocess.call(cmd, cwd=HERE)


def plan_path(city: str, market: str) -> str:
    suffix = "" if market == "buy" else f"-{market}"
    return os.path.join(HERE, "plans", f"{city}{suffix}.json")


def plan_market(city: str, country: str, market: str, target: int,
                sample_pages: int) -> dict | None:
    rc = run("plan_city.py", "--city", city, "--country", country,
             "--transaction", market, "--target", str(target),
             "--sample-pages", str(sample_pages))
    if rc != 0:
        print(f"  planning failed for {market}; skipping this market")
        return None
    path = plan_path(city, market)
    if not os.path.exists(path):
        print(f"  no plan written for {market}; skipping")
        return None
    with open(path, encoding="utf-8") as f:
        plan = json.load(f)
    plan["_path"] = path
    return plan


def route(plan: dict) -> tuple[str, int]:
    """Pick the collection route. Returns (route, projected_credits)."""
    total = plan.get("city_total") or 0
    if total == 0:
        return "none", 0
    if total <= UPSTREAM_CAP:
        return "free", 0
    return "parsebot", plan.get("projected_calls", 0)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", required=True, help="Properstar city slug, e.g. cancun")
    ap.add_argument("--country", default="mexico")
    ap.add_argument("--target", type=int, default=950,
                    help="listings per price band (page limit is 1000)")
    ap.add_argument("--sample-pages", type=int, default=30)
    ap.add_argument("--plan-only", action="store_true",
                    help="plan both markets and stop (never spends credits)")
    ap.add_argument("--yes", action="store_true",
                    help="authorise parse.bot spend for markets over the cap")
    args = ap.parse_args()

    print(f"=== planning {args.city} ({args.country}) ===")
    plans: dict[str, dict] = {}
    for market in MARKETS:
        plan = plan_market(args.city, args.country, market,
                           args.target, args.sample_pages)
        if plan:
            plans[market] = plan

    if not plans:
        sys.exit("could not plan either market")

    print(f"\n=== {args.city}: routes ===")
    billable = 0
    for market, plan in plans.items():
        how, credits = route(plan)
        total = plan.get("city_total") or 0
        billable += credits
        detail = {
            "free": "free (fits under the 2,000 cap, includes date_listed)",
            "parsebot": f"parse.bot, {credits} credits (~${credits * CREDIT_USD:.2f})",
            "none": "no listings",
        }[how]
        print(f"  {market:5} {total:>6} listings -> {detail}")

    if billable:
        print(f"\ntotal billable: {billable} credits (~${billable * CREDIT_USD:.2f})")
    else:
        print("\ntotal billable: 0 credits -- both markets collectable free")

    if args.plan_only:
        print("\nplan-only: nothing collected, nothing billed")
        return

    if billable and not args.yes:
        print(f"\nrefusing to spend {billable} credits without --yes.")
        print("Re-run with --yes to collect, or --plan-only to just inspect.")
        return

    print(f"\n=== collecting {args.city} ===")
    results: list[tuple[str, str, int]] = []
    for market, plan in plans.items():
        how, credits = route(plan)
        if how == "none":
            continue
        if how == "free":
            rc = run("scrape_free.py", "--city", args.city, "--country", args.country,
                     "--transaction", market)
        else:
            rc = run("fetch_city.py", "--plan", plan["_path"])
        results.append((market, "ok" if rc == 0 else "FAILED",
                        credits if how == "parsebot" else 0))

    suffix = {"buy": "", "rent": "_rent"}
    print(f"\n=== {args.city}: done ===")
    for market, status, credits in results:
        path = os.path.join(HERE, f"properstar_{args.city}{suffix[market]}.csv")
        rows = ""
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                rows = f"{sum(1 for _ in f) - 1} rows"
        print(f"  {market:5} {status:7} {rows:>12}  {os.path.basename(path)}"
              f"{f'  ({credits} credits)' if credits else '  (free)'}")


if __name__ == "__main__":
    main()
