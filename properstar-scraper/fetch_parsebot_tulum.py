"""Pull the full Tulum listing set from Properstar via the parse.bot API.

Why slicing is required: Properstar hard-caps any single search at 2,000
retrievable results (it returns `totalRetrievable: 2000` alongside `total: 8524`).
parse.bot confirms the same ceiling, and that each unique *filter combination*
gets its own fresh 2,000 window. So the full ~8,524 Tulum listings are only
reachable by splitting into slices that each stay under that cap. This is a
correctness constraint, not a cost optimisation -- an unsliced run silently
returns ~2,000 and looks successful.

Why these slices: property_type + bedroom counts were measured live off the
public site (free), giving exact populations. The two oversized buckets --
apartment 1-bed (2,701) and 2-bed (2,645) -- are split by GBP price bands whose
cut points come from a 1,706-listing free-scraped sample. Bands are sized to
~675 rather than ~1,000 so that even if the sample misjudges the distribution by
2-3x, no band approaches the 2,000 cap.

Cost: parse.bot bills per HTTP request, but a request is not 1 credit --
search_homes averages ~3.4 credits (it solves an Azure WAF challenge upstream)
and is capped at 20 credits per call. At $0.03/credit (1,000 credits per $30)
this plan is ~14 requests / ~48 credits / ~$1.43. Actual spend is read per-call
from the `X-Credits-Charged` response header rather than assumed, so the running
total reflects what is really billed.

Safety: both ceilings below are enforced in code, not by instruction -- the
script physically cannot issue a request once either is reached. Verified
against a stub server that reports runaway result counts.
Run with --dry-run to print the plan and spend nothing.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time

try:  # corporate TLS inspection can break certifi; harmless if unneeded
    import truststore

    truststore.inject_into_ssl()
except Exception:
    pass

import requests
from dotenv import load_dotenv

load_dotenv()
# Fall back to the sibling project's .env so the key lives in one place.
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "cancun-ingestion", ".env"))

CITY = "tulum"
COUNTRY = "mexico"

# Two independent hard stops. MAX_REQUESTS bounds runaway pagination;
# MAX_CREDITS bounds actual billed spend, since credits per call vary (~3.4 avg,
# 20 max). Whichever binds first halts the run.
MAX_REQUESTS = 30
MAX_CREDITS = 40  # ~$1.20; plan needs ~13. Kept tight to preserve credits for other cities.

CREDIT_USD = 0.03  # 1,000 credits per $30
MAX_CALL_CREDITS = 20  # parse.bot's per-call ceiling; reserved before each request
AVG_CALL_CREDITS = 1  # measured: filtered calls charged exactly 1 credit each
PAGE_SIZE = 1000
UPSTREAM_CAP = 2000  # Properstar's per-search ceiling

OUTPUT_CSV = "properstar_tulum_full.csv"
OUTPUT_JSON = "properstar_tulum_full.json"

# CSV column order. The JSON output keeps every field the API returns, whitelist
# or not, so a newly-added upstream field is never silently dropped -- recovering
# one would otherwise mean paying for the whole run again.
FIELDS = [
    "id", "title", "url", "price", "location", "latitude", "longitude",
    "bedrooms", "bathrooms", "size_sqft", "property_type", "advertiser",
    "date_listed", "pictures",
]

def _bands(kind: str, cuts: list[int], population: int) -> list[tuple[str, dict, int]]:
    """Build contiguous price bands covering the whole population of one type.

    Price alone is used as the slicing dimension, deliberately: bedroom filters
    work but leave ~430 apartments with no bedroom value unreachable (and
    `max_bedrooms=0` returns nothing, so studios aren't addressable that way).
    Price bands have no such hole -- every listing has a price, so contiguous
    bands from 0 to infinity partition the type exactly.
    """
    out = []
    edges = [None, *cuts, None]
    each = round(population / (len(cuts) + 1))
    for i in range(len(edges) - 1):
        lo, hi = edges[i], edges[i + 1]
        params: dict = {"property_type": kind}
        if lo is not None:
            params["min_price"] = lo
        if hi is not None:
            params["max_price"] = hi
        label = f"{kind[:3]} {'<' + f'{hi//1000}k' if lo is None else ('>' + f'{lo//1000}k' if hi is None else f'{lo//1000}-{hi//1000}k')}"
        out.append((label, params, each))
    return out


# Cut points derived from the 1,706-listing free-scraped sample; populations
# (6,821 apartments / 1,703 houses) measured live off the public site.
SLICES: list[tuple[str, dict, int]] = [
    *_bands("apartment",
            [86504, 103343, 123882, 142208, 160545, 184009, 213517, 264532, 354813],
            6821),
    *_bands("house", [311999, 593626], 1703),
]


class Budget:
    """Hard spend ceiling on both request count and billed credits."""

    def __init__(self, max_requests: int, max_credits: int):
        self.max_requests = max_requests
        self.max_credits = max_credits
        self.requests = 0
        self.credits = 0

    def authorise(self) -> None:
        """Called before every billable request; raises rather than proceeding.

        The credit check reserves the worst-case per-call charge, because the
        real cost is only known from the response header after the fact. Without
        that reservation the ceiling could be overshot by one call.
        """
        if self.requests >= self.max_requests:
            raise RuntimeError(f"request cap reached ({self.max_requests})")
        if self.credits + MAX_CALL_CREDITS > self.max_credits:
            raise RuntimeError(
                f"credit cap reached ({self.credits} spent; next call could cost "
                f"{MAX_CALL_CREDITS}, exceeding the {self.max_credits} ceiling)"
            )
        self.requests += 1

    def record(self, charged: int) -> None:
        self.credits += charged

    def usd(self) -> float:
        return self.credits * CREDIT_USD


def endpoint() -> str:
    """parse.bot's filtered search endpoint, derived from the base scraper URL."""
    explicit = os.environ.get("PARSEBOT_FILTERED_URL")
    if explicit:
        return explicit
    return os.environ["PARSEBOT_SEARCH_URL"].rsplit("/", 1)[0] + "/search_homes_filtered"


def fetch_page(url: str, key: str, params: dict, page: int, budget: Budget) -> tuple[dict, int]:
    budget.authorise()
    resp = requests.get(
        url,
        headers={"X-API-Key": key},
        params={**params, "city": CITY, "country": COUNTRY, "page": str(page)},
        timeout=600,  # a full 1,000-row slice takes a while upstream
    )
    resp.raise_for_status()
    try:
        charged = int(resp.headers.get("X-Credits-Charged", 0))
    except (TypeError, ValueError):
        charged = 0
    budget.record(charged)
    return resp.json().get("data", {}), charged


def normalise(listing: dict) -> dict:
    """Keep the listing whole; only tidy the price string.

    Upstream sends "GBP\xa0224,983" with a non-breaking space, which surfaces as
    mojibake in CSV readers.
    """
    row = dict(listing)
    if isinstance(row.get("price"), str):
        row["price"] = row["price"].replace("\xa0", " ").replace("�", " ").strip()
    return row


def collect(items: list, into: dict) -> None:
    for item in items:
        row = normalise(item)
        if row.get("id") is not None:
            into[row["id"]] = row


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="print the plan and projected spend without calling the API")
    args = ap.parse_args()

    reqs = sum(max(1, -(-exp // PAGE_SIZE)) for _, _, exp in SLICES)
    est = reqs * AVG_CALL_CREDITS
    # The budget reserves the worst-case per-call charge, so usable credits are
    # MAX_CREDITS minus one call's ceiling.
    usable = MAX_CREDITS - MAX_CALL_CREDITS + 1
    print(f"{len(SLICES)} slices, ~{reqs} requests projected "
          f"(~{est} credits at the measured 1/call, ~${est * CREDIT_USD:.2f})")
    print(f"hard stops: {MAX_REQUESTS} requests / {MAX_CREDITS} credits "
          f"-> halts by ~{usable} credits spent (~${usable * CREDIT_USD:.2f} worst case)\n")
    for label, params, exp in SLICES:
        filt = {k: v for k, v in params.items() if k != "property_type"}
        print(f"  {label:22} expect ~{exp:<6} {filt or '(no extra filters)'}")

    if args.dry_run:
        print("\ndry run: no requests issued, nothing billed")
        return

    key = os.environ.get("PARSEBOT_API_KEY")
    if not key:
        sys.exit("PARSEBOT_API_KEY is not set (see cancun-ingestion/.env.example)")

    url = endpoint()
    budget = Budget(MAX_REQUESTS, MAX_CREDITS)
    listings: dict[int, dict] = {}
    warnings: list[str] = []
    stopped = False

    print(f"\nendpoint: {url}\n")
    for label, params, _ in SLICES:
        if stopped:
            break
        try:
            data, charged = fetch_page(url, key, params, 1, budget)
        except RuntimeError as stop:
            warnings.append(f"{label}: {stop}")
            print(f"  !! {stop} -- halting")
            break

        total = data.get("total_results", 0)
        got = data.get("listings") or []
        collect(got, listings)

        note = ""
        if total > UPSTREAM_CAP:
            note = f"  <-- OVER CAP ({total}); ~{total - UPSTREAM_CAP} unreachable, narrow this band"
            warnings.append(f"{label}: {total} results exceeds the {UPSTREAM_CAP} cap")
        print(f"  {label:22} total={total:<6} got={len(got):<5} unique={len(listings):<6} "
              f"credits={charged} (run {budget.credits}){note}")

        # Only page further while more rows can still exist below the cap.
        page = 2
        while len(got) == PAGE_SIZE and (page - 1) * PAGE_SIZE < min(total, UPSTREAM_CAP):
            try:
                data, charged = fetch_page(url, key, params, page, budget)
            except RuntimeError as stop:
                warnings.append(f"{label} p{page}: {stop}")
                print(f"  !! {stop} -- halting")
                stopped = True
                break
            got = data.get("listings") or []
            collect(got, listings)
            print(f"  {label:22} page {page}: +{len(got):<5} unique={len(listings):<6} "
                  f"credits={charged} (run {budget.credits})")
            page += 1

        time.sleep(1.2)  # respect parse.bot's rate limit

    rows = list(listings.values())

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            out = {k: r.get(k) for k in FIELDS}
            out["pictures"] = "; ".join(r.get("pictures") or [])
            w.writerow(out)

    # Surface any field the API returned that the CSV doesn't carry, so it is
    # visible rather than quietly living only in the JSON.
    seen = {k for r in rows for k in r}
    extra = sorted(seen - set(FIELDS))
    if extra:
        print(f"\nextra fields present in JSON but not CSV columns: {extra}")

    print(f"\n{len(rows)} unique listings -> {OUTPUT_CSV} / {OUTPUT_JSON}")
    print(f"spend: {budget.requests} requests, {budget.credits} credits (~${budget.usd():.2f})")
    if warnings:
        print("\nwarnings:")
        for wmsg in warnings:
            print(f"  - {wmsg}")


if __name__ == "__main__":
    main()
