"""Run a parse.bot slice plan produced by plan_city.py and collect a whole city.

    python plan_city.py  --city cancun          # free: works out the slices
    python fetch_city.py --plan plans/cancun.json --dry-run
    python fetch_city.py --plan plans/cancun.json

Spend control: two ceilings are enforced in code, not by instruction, and the
script physically cannot issue a request once either is reached. The credit
check reserves the worst-case per-call charge, because the real cost is only
known from the response header after the fact -- without that reservation the
ceiling could be overshot by one call.

Measured economics (Tulum, Aug 2026): `search_homes_filtered` charged exactly
1 credit per call and returned each ~830-row slice in a single page -- 13 calls
for 8,522 listings, $0.39. parse.bot's docs quote ~3-4 credits/call, so the
running total is read from `X-Credits-Charged` rather than assumed.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from collections import deque

try:  # corporate TLS inspection can break certifi; harmless if unneeded
    import truststore

    truststore.inject_into_ssl()
except Exception:
    pass

import requests
from dotenv import load_dotenv

load_dotenv()
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "cancun-ingestion", ".env"))

CREDIT_USD = 0.03  # 1,000 credits per $30
MAX_CALL_CREDITS = 20  # parse.bot's per-call ceiling; reserved before each request

# Measured per-call price, by market. Sale and rental are *separate parse.bot
# scrapers* with separate pricing -- rentals cost 10x. Used only to size the
# projection and the safety ceiling; X-Credits-Charged stays the source of truth.
CREDITS_PER_CALL = {"buy": 1, "rent": 10}
PAGE_SIZE = 2000  # one call returns both upstream pages (see PARSEBOT_FILTERED_URL)
UPSTREAM_CAP = 2000  # Properstar's per-search ceiling; past this, rows are lost

# CSV column order. The JSON output keeps every field the API returns, so a
# newly-added upstream field is never silently dropped -- recovering one would
# otherwise mean paying for the whole run again.
FIELDS = [
    "id", "title", "url", "price", "location", "latitude", "longitude",
    "bedrooms", "bathrooms", "size_sqft", "property_type", "advertiser",
    "date_listed", "pictures",
]


class Budget:
    """Hard spend ceiling on both request count and billed credits."""

    def __init__(self, max_requests: int, max_credits: int):
        self.max_requests = max_requests
        self.max_credits = max_credits
        self.requests = 0
        self.credits = 0

    def authorise(self) -> None:
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


def endpoints(transaction: str = "buy") -> list[str]:
    """Candidate parse.bot endpoints, best first.

    Returned as a list because an unknown endpoint 404s *free* -- so trying the
    filtered variant first costs nothing if it doesn't exist yet, and the run
    upgrades itself automatically once parse.bot ships it. A filtered endpoint is
    strongly preferred: without filters there is no way to slice, so any market
    over 2,000 listings is permanently truncated.
    """
    override = os.environ.get(
        "PARSEBOT_RENT_URL" if transaction == "rent" else "PARSEBOT_FILTERED_URL")
    if override:
        return [override]

    root = os.environ["PARSEBOT_SEARCH_URL"].rsplit("/", 1)[0]
    if transaction == "rent":
        return [f"{root}/search_homes_rental_filtered",
                f"{root}/search_homes_rental"]
    return [f"{root}/search_homes_filtered"]


class Endpoint:
    """Resolves which candidate URL actually exists, then sticks with it.

    An unknown endpoint returns 404 and is not billed, so walking the candidate
    list costs nothing until one answers.
    """

    def __init__(self, candidates: list[str]):
        self.candidates = candidates
        self.resolved: str | None = None

    def urls(self) -> list[str]:
        return [self.resolved] if self.resolved else self.candidates


def fetch_page(ep: Endpoint, key: str, params: dict, city: str, country: str,
               page: int, budget: Budget, retries: int = 2) -> tuple[dict, int]:
    budget.authorise()
    query = {**params, "city": city, "country": country, "page": str(page)}
    last = None
    for url in ep.urls():
        resp = None
        for attempt in range(retries + 1):
            resp = requests.get(url, headers={"X-API-Key": key}, params=query,
                                timeout=600)  # a full 1,000-row slice is slow upstream
            if resp.status_code < 500:
                break  # not a transient upstream error -- handled below, no retry
            if attempt < retries:
                # 502/500 are the upstream having a bad moment, not a bad request
                # of ours -- worth a couple of retries before treating the slice
                # as lost. This is what turned every "failed slice" into a
                # permanent hole in a dataset we'd already paid for.
                wait = 3 * (attempt + 1)
                print(f"    {resp.status_code} from upstream, retrying in "
                      f"{wait}s ({attempt + 1}/{retries})...")
                time.sleep(wait)
        if resp.status_code == 404:
            last = resp
            continue  # endpoint doesn't exist (not billed); try the next
        resp.raise_for_status()
        if ep.resolved != url:
            ep.resolved = url
            print(f"  using endpoint: {url.rsplit('/', 1)[-1]}")
        try:
            charged = int(resp.headers.get("X-Credits-Charged", 0))
        except (TypeError, ValueError):
            charged = 0
        budget.record(charged)
        return resp.json().get("data", {}), charged

    budget.requests -= 1  # nothing was billed; don't count it against the cap
    names = ", ".join(u.rsplit("/", 1)[-1] for u in ep.candidates)
    raise LookupError(
        f"none of these endpoints exist yet: {names}\n"
        f"  (last response: {last.text[:120] if last is not None else 'n/a'})\n"
        f"  For rentals, parse.bot's build may still be in progress. Meanwhile:\n"
        f"    python scrape_free.py --city {city} --transaction rent")


def normalise(listing: dict) -> dict:
    """Keep the listing whole; only tidy the price string.

    Upstream sends "GBP\xa0224,983" with a non-breaking space, which surfaces as
    mojibake in CSV readers.
    """
    row = dict(listing)
    if isinstance(row.get("price"), str):
        row["price"] = row["price"].replace("\xa0", " ").replace("�", " ").strip()
    return row


MAX_SPLIT_DEPTH = 5  # each split roughly halves an over-cap band; needing more
                      # than this means a pathological case (many listings at
                      # one exact price) -- stop retrying that branch, don't
                      # spend on it unboundedly.


def bisect_slice(s: dict) -> tuple[dict, dict] | None:
    """Split one price-banded slice into two narrower bands at its midpoint.

    Used when a slice's real total (learned from the paid response, not the
    free-side sample that sized it) exceeds the cap -- narrower bands recover
    the rows that a single call can't reach. Returns None when the band can't
    usefully be split further (hit the depth limit, or already down to a
    single price), so the caller can fall back to accepting the loss for that
    one band instead of splitting forever.
    """
    params = s["params"]
    lo, hi = params.get("min_price"), params.get("max_price")
    depth = s.get("_split_depth", 0)
    if depth >= MAX_SPLIT_DEPTH:
        return None
    if hi is None:
        mid = lo * 2 if lo else 1000  # open-ended high band: grow the cut point
    elif lo is None:
        mid = hi // 2
    else:
        mid = (lo + hi) // 2
        if mid <= lo or mid >= hi:
            return None  # band too narrow (adjacent prices) to split further

    def make(new_lo: int | None, new_hi: int | None, suffix: str) -> dict:
        p = {"property_type": params["property_type"]}
        if new_lo is not None:
            p["min_price"] = new_lo
        if new_hi is not None:
            p["max_price"] = new_hi
        return {"label": f"{s['label']}{suffix}", "params": p,
                "expected": s["expected"] // 2, "_split_depth": depth + 1}

    return make(lo, mid, "a"), make(mid, hi, "b")


def collect(items: list, into: dict) -> None:
    for item in items:
        row = normalise(item)
        if row.get("id") is not None:
            into[row["id"]] = row


def output_paths(city: str, transaction: str) -> tuple[str, str]:
    sfx = "" if transaction == "buy" else f"_{transaction}"
    return f"properstar_{city}{sfx}.csv", f"properstar_{city}{sfx}.json"


def write_outputs(rows: list[dict], city: str, transaction: str = "buy") -> tuple[str, str]:
    csv_path, json_path = output_paths(city, transaction)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            out = {k: r.get(k) for k in FIELDS}
            out["pictures"] = "; ".join(r.get("pictures") or [])
            w.writerow(out)

    return csv_path, json_path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True, help="plan JSON from plan_city.py")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the plan and projected spend without calling the API")
    ap.add_argument("--max-credits", type=int,
                    help="override the credit ceiling (default: 2x projected + headroom)")
    ap.add_argument("--fresh", action="store_true",
                    help="discard any existing output instead of merging into it "
                         "(default: merge, same as scrape_free.py) -- without this, "
                         "re-running a plan that only contains the slices that failed "
                         "last time adds to what's already collected instead of "
                         "replacing it")
    args = ap.parse_args()

    with open(args.plan, encoding="utf-8") as f:
        plan = json.load(f)

    city, country = plan["city"], plan["country"]
    transaction = plan.get("transaction", "buy")
    slices = plan["slices"]
    projected = plan.get("projected_calls", len(slices))

    rate = CREDITS_PER_CALL.get(transaction, MAX_CALL_CREDITS)
    projected_credits = projected * rate
    max_credits = args.max_credits or (projected_credits * 2 + MAX_CALL_CREDITS)
    max_requests = projected * 2 + 5
    usable = max_credits - MAX_CALL_CREDITS + 1

    print(f"{city} ({country}, {transaction}): {len(slices)} slices, ~{projected} calls projected "
          f"(~{projected_credits} credits / ~${projected_credits * CREDIT_USD:.2f} "
          f"at the measured {rate} credit/call)")
    print(f"hard stops: {max_requests} requests / {max_credits} credits "
          f"-> halts by ~{usable} credits (~${usable * CREDIT_USD:.2f} worst case)\n")
    for s in slices:
        filt = {k: v for k, v in s["params"].items() if k != "property_type"}
        print(f"  {s['label']:18} expect ~{s['expected']:<6} {filt or '(whole type)'}")

    if args.dry_run:
        print("\ndry run: no requests issued, nothing billed")
        return

    key = os.environ.get("PARSEBOT_API_KEY")
    if not key:
        sys.exit("PARSEBOT_API_KEY is not set (see cancun-ingestion/.env.example)")

    ep = Endpoint(endpoints(transaction))
    budget = Budget(max_requests, max_credits)
    listings: dict[int, dict] = {}
    _, json_path_existing = output_paths(city, transaction)
    if not args.fresh and os.path.exists(json_path_existing):
        try:
            with open(json_path_existing, encoding="utf-8") as f:
                listings = {r["id"]: r for r in json.load(f) if r.get("id")}
            print(f"merging into {len(listings)} listings already collected "
                  f"({json_path_existing})\n")
        except (json.JSONDecodeError, KeyError, TypeError):
            print(f"could not read {json_path_existing}; starting fresh\n")
    warnings: list[str] = []
    stopped = False

    names = [u.rsplit("/", 1)[-1] for u in ep.candidates]
    print(f"\ncandidate endpoints (first that exists wins): {names}\n")
    pending: deque[dict] = deque(slices)
    while pending:
        if stopped:
            break
        s = pending.popleft()
        label, params = s["label"], s["params"]
        try:
            data, charged = fetch_page(ep, key, params, city, country, 1, budget)
        except RuntimeError as stop:
            warnings.append(f"{label}: {stop}")
            print(f"  !! {stop} -- halting")
            break
        except LookupError as missing:
            print(f"  !! {missing}")
            warnings.append(str(missing).splitlines()[0])
            break
        except requests.RequestException as err:
            warnings.append(f"{label}: request failed ({err})")
            print(f"  !! {label}: {err}")
            continue

        total = data.get("total_results", 0)
        got = data.get("listings") or []
        collect(got, listings)  # keep this page's rows regardless -- even an
                                 # over-cap band's first page is valid data

        # A band's real total comes from the paid response itself, not the
        # free-side sample that sized it -- that sample can badly misjudge one
        # skewed band (e.g. a dense cluster of cheap listings) while every
        # other band is fine. Rather than aborting the whole city on one bad
        # band, split just that band by price and requeue both halves; only
        # the genuinely oversized bands cost extra calls. The existing
        # request/credit ceiling below still catches it if splitting spirals.
        if total > UPSTREAM_CAP:
            halves = bisect_slice(s)
            if halves:
                print(f"  {label:18} total={total:<6} OVER CAP -- "
                      f"splitting into 2 narrower bands (credits={charged})")
                pending.extendleft(reversed(halves))
                time.sleep(1.2)
                continue
            note = (f"  <-- OVER CAP ({total}); ~{total - UPSTREAM_CAP} unreachable, "
                    f"can't split further")
            warnings.append(f"{label}: {total} exceeds the {UPSTREAM_CAP} cap and "
                            f"can't be split further (hit depth limit or a single price)")
        else:
            note = ""
        print(f"  {label:18} total={total:<6} got={len(got):<5} unique={len(listings):<6} "
              f"credits={charged} (run {budget.credits}){note}")
        # Checkpoint after every real (billed) fetch. A slice can cost real
        # credits and take real time; if the run is interrupted for any
        # reason -- a crash, a kill, hitting the budget ceiling -- everything
        # paid for up to this point is already durably saved, not sitting in
        # memory waiting for a final write that might never happen.
        write_outputs(list(listings.values()), city, transaction)

        # Only page further while more rows can still exist below the cap.
        page = 2
        while len(got) == PAGE_SIZE and (page - 1) * PAGE_SIZE < min(total, UPSTREAM_CAP):
            try:
                data, charged = fetch_page(ep, key, params, city, country, page, budget)
            except RuntimeError as stop:
                warnings.append(f"{label} p{page}: {stop}")
                print(f"  !! {stop} -- halting")
                stopped = True
                break
            except requests.RequestException as err:
                warnings.append(f"{label} p{page}: request failed ({err})")
                break
            got = data.get("listings") or []
            collect(got, listings)
            print(f"  {label:18} page {page}: +{len(got):<5} unique={len(listings):<6} "
                  f"credits={charged} (run {budget.credits})")
            write_outputs(list(listings.values()), city, transaction)  # checkpoint
            page += 1

        time.sleep(1.2)  # respect parse.bot's rate limit

    rows = list(listings.values())
    if not rows:
        # Never let a failed run overwrite a good dataset with an empty file.
        print("\nno listings collected -- leaving any existing output untouched")
        if warnings:
            print("\nwarnings:")
            for w in warnings:
                print(f"  - {w}")
        return
    csv_path, json_path = write_outputs(rows, city, transaction)

    extra = sorted({k for r in rows for k in r} - set(FIELDS))
    if extra:
        print(f"\nextra fields in JSON but not CSV columns: {extra}")

    expected_total = plan.get("city_total") or 0
    pct = f" ({len(rows) / expected_total * 100:.1f}% of {expected_total})" if expected_total else ""
    print(f"\n{len(rows)} unique listings{pct} -> {csv_path} / {json_path}")
    print(f"spend: {budget.requests} requests, {budget.credits} credits "
          f"(~${budget.usd():.2f})")
    if warnings:
        print("\nwarnings:")
        for w in warnings:
            print(f"  - {w}")


if __name__ == "__main__":
    main()
