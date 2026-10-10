"""Collect UK Rightmove listings straight into tlrm's Supabase database, free.

    python rightmove.py setup                          # create uk_* tables (once)
    python rightmove.py search  --location London --channel sale
    python rightmove.py search  --location London --channel rent
    python rightmove.py geo                            # borough/ward/LSOA via postcodes.io
    python rightmove.py details                        # full description, postcode, costs
    python rightmove.py all     --location London      # search both channels, geo, details
    python rightmove.py refresh --location London      # weekly: re-sweep, mark withdrawn, new-only geo/details
    python rightmove.py status                         # progress so far

Crash-safe by design -- nothing is held in memory between pages:
  * every search page (24 listings) is upserted and its progress committed in
    the same transaction, so a crash loses at most the page in flight;
  * price bands live in uk_scrape_bands, so a restart skips finished bands and
    resumes a half-done band at its next page;
  * details/geo pick up whatever rows still have a NULL *_fetched_at, so they
    resume by construction and never fetch a listing twice.

Rightmove serves at most 42 pages x 24 = 1,008 results per query, so each
location is bisected into contiguous price bands (arbitrary integer prices are
accepted) until every band holds <= 1,000 listings. Counts come free from the
first page of each band, which is also kept as that band's first page of data.

UK data is kept out of the Mexico tables on purpose: resale_listings has no
country column and its indexes/RPCs are Mexico-specific.
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import psycopg2
from psycopg2.extras import Json, execute_values

ENV_FILE = Path(__file__).resolve().parents[2] / "tlrm" / ".env.local"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
PAGE = 24
BAND_MAX = 1000          # Rightmove's hard ceiling is 1,008; keep a margin
MAX_PAGES = 42
CHANNELS = {
    "sale": ("property-for-sale", "includeSSTC"),
    "rent": ("property-to-rent", "includeLetAgreed"),
}
STATUS = {"": "live", "sold stc": "sstc", "under offer": "under_offer",
          "let agreed": "let_agreed", "sold stcm": "sstc"}
ACRE_SQFT = 43560

sys.setrecursionlimit(20000)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows consoles default to cp1252


# --------------------------------------------------------------------------- db

def connect():
    env = ENV_FILE.read_text(encoding="utf-8")
    url = re.search(r"^DATABASE_URL=(.*)$", env, re.M).group(1).strip().strip('"')
    # The password can contain '@', which breaks libpq's URL parser.
    m = re.match(r"postgres(?:ql)?://([^:]+):(.*)@([^@/:]+):(\d+)/([^?]*)", url)
    return psycopg2.connect(user=m.group(1), password=m.group(2), host=m.group(3),
                            port=m.group(4), dbname=m.group(5), sslmode="require",
                            keepalives=1, keepalives_idle=30)


DDL = """
create table if not exists uk_listings (
  id bigint primary key,
  country text not null default 'GB',
  source text not null default 'rightmove',
  channel text not null,                       -- sale | rent
  search_location text,
  location_identifier text,
  url text,
  title text,                                  -- e.g. '3 bedroom flat for sale'
  summary text,
  display_address text,
  latitude double precision,
  longitude double precision,
  price_amount numeric,
  price_currency text,
  price_frequency text,                        -- null for sale; monthly for rent
  price_display text,
  price_qualifier text,
  bedrooms smallint,
  bathrooms smallint,
  property_sub_type text,
  tenure text,
  size_display text,
  size_value numeric,
  size_unit text,
  size_is_likely_plot boolean,
  status text,                                 -- live | sstc | under_offer | let_agreed
  key_features jsonb,
  image_urls jsonb,
  number_of_images int,
  number_of_floorplans int,
  first_visible_date timestamptz,
  listing_update_reason text,
  listing_update_date timestamptz,
  added_or_reduced text,
  is_commercial boolean,
  is_residential boolean,
  is_land boolean,
  is_development boolean,
  is_auction boolean,
  is_premium boolean,
  is_featured boolean,
  agent_name text,
  agent_branch text,
  agent_branch_id bigint,
  agent_phone text,
  search_raw jsonb,
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  -- details stage (listing page)
  description text,
  postcode text,
  pin_type text,                               -- ACCURATE_POINT etc.
  council_tax_band text,
  council_tax_exempt boolean,
  council_tax_included boolean,
  annual_service_charge numeric,
  annual_ground_rent numeric,
  ground_rent_review_years numeric,
  lease_years_remaining numeric,
  size_sqft_published numeric,
  size_sqm_published numeric,
  shared_ownership_pct numeric,
  nearest_stations jsonb,
  rooms jsonb,
  features jsonb,
  floorplan_urls jsonb,
  epc_urls jsonb,
  full_image_urls jsonb,
  details_status text,                         -- ok | removed | error
  details_fetched_at timestamptz,
  -- geo stage (postcodes.io, from lat/lng)
  nearest_postcode text,
  postcode_distance_m numeric,
  borough text, borough_code text,
  ward text, ward_code text,
  constituency text, constituency_code text,
  region text,
  lsoa text, lsoa_code text,
  msoa text, msoa_code text,
  geo_fetched_at timestamptz
);
create index if not exists uk_listings_loc_channel on uk_listings (search_location, channel);
create index if not exists uk_listings_status on uk_listings (status);
create index if not exists uk_listings_borough on uk_listings (borough_code);
create index if not exists uk_listings_details_todo on uk_listings (id) where details_fetched_at is null;
create index if not exists uk_listings_geo_todo on uk_listings (id) where geo_fetched_at is null;
alter table uk_listings enable row level security;   -- no public policy yet

create table if not exists uk_scrape_bands (
  job text not null,
  lo bigint not null,
  hi bigint,                                   -- null = open-ended top band
  expected int,
  status text not null default 'pending',      -- pending | done | truncated
  pages_done int not null default 0,
  rows_saved int not null default 0,
  updated_at timestamptz not null default now(),
  primary key (job, lo)
);
alter table uk_scrape_bands enable row level security;
"""


# ------------------------------------------------------------------------- http

class Blocked(RuntimeError):
    pass


def http_get(url: str, tries: int = 5) -> tuple[int, str]:
    """GET with gzip and backoff. Returns (status, body); 404/410 come back as-is."""
    delay = 15
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=40) as r:
                body = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
                return r.status, body.decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                return e.code, ""
            err = f"HTTP {e.code}"
        except Exception as e:  # timeouts, resets
            err = repr(e)[:120]
        log(f"  ! {err} (attempt {attempt + 1}/{tries}); waiting {delay}s")
        time.sleep(delay)
        delay = min(delay * 2, 300)
    raise Blocked(f"giving up after {tries} attempts: {url}")


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


# ----------------------------------------------------------------------- search

def resolve_location(name: str) -> tuple[str, str]:
    if "^" in name:
        return name, name
    q = urllib.parse.urlencode({"query": name, "limit": 5, "exclude": "STREET"})
    _, body = http_get(f"https://los.rightmove.co.uk/typeahead?{q}")
    m = json.loads(body)["matches"][0]
    return f"{m['type']}^{m['id']}", m["displayName"]


def search_page(channel: str, loc_id: str, include_off: bool, lo: int, hi: int | None, index: int,
                extra: dict | None = None) -> dict:
    path, off_param = CHANNELS[channel]
    params = {"locationIdentifier": loc_id, "index": index, "sortType": 2,
              "numberOfPropertiesPerPage": PAGE, **(extra or {})}
    if include_off:
        params[off_param] = "true"
    if lo > 0:
        params["minPrice"] = lo
    if hi is not None:
        params["maxPrice"] = hi
    url = f"https://www.rightmove.co.uk/{path}/find.html?" + urllib.parse.urlencode(params)
    for _ in range(3):
        status, html = http_get(url)
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
        if m:
            sr = json.loads(m.group(1))["props"]["pageProps"].get("searchResults")
            if sr is not None:
                return sr
        log(f"  ! page without search data (HTTP {status}); retrying in 60s")
        time.sleep(60)
    raise Blocked(f"search page never returned data: {url}")


def result_count(sr: dict) -> int:
    return int(str(sr.get("resultCount") or "0").replace(",", ""))


def parse_size(text: str | None) -> tuple[float | None, str | None]:
    if not text:
        return None, None
    m = re.search(r"([\d,.]+)\s*(sq\.?\s*ft|sq\.?\s*m|acres?|ac\b|hectares?|ha\b)", text, re.I)
    if not m:
        return None, None
    val = float(m.group(1).replace(",", ""))
    unit = m.group(2).lower()
    unit = ("sqft" if "ft" in unit else "sqm" if "m" in unit and "sq" in unit
            else "acres" if unit.startswith("ac") else "hectares")
    return val, unit


def map_search_row(p: dict, channel: str, loc_name: str, loc_id: str) -> tuple:
    price = p.get("price") or {}
    dp = (price.get("displayPrices") or [{}])[0]
    cust = p.get("customer") or {}
    upd = p.get("listingUpdate") or {}
    size_val, size_unit = parse_size(p.get("displaySize"))
    title = p.get("propertyTypeFullDescription") or ""
    is_land = title.lower().startswith("land") or (p.get("propertySubType") or "").lower() in ("land", "plot")
    plot = bool(is_land or (size_unit in ("acres", "hectares"))
                or (size_unit == "sqft" and size_val and size_val >= ACRE_SQFT and size_val % ACRE_SQFT == 0))
    freq = price.get("frequency")
    raw = {k: v for k, v in p.items() if k not in ("images", "customer", "lozengeModel")}
    return (
        int(p["id"]), channel, loc_name, loc_id,
        f"https://www.rightmove.co.uk/properties/{p['id']}",
        title or None, p.get("summary"), p.get("displayAddress"),
        (p.get("location") or {}).get("latitude"), (p.get("location") or {}).get("longitude"),
        price.get("amount"), price.get("currencyCode"),
        None if channel == "sale" or freq == "not specified" else freq,
        dp.get("displayPrice"), dp.get("displayPriceQualifier") or None,
        p.get("bedrooms"), p.get("bathrooms"), p.get("propertySubType"),
        (p.get("tenure") or {}).get("tenureType"),
        p.get("displaySize") or None, size_val, size_unit, plot,
        STATUS.get((p.get("displayStatus") or "").strip().lower(),
                   (p.get("displayStatus") or "").strip().lower().replace(" ", "_")),
        Json([f.get("description") for f in (p.get("keyFeatures") or [])]),
        Json([i.get("srcUrl") for i in (p.get("images") or []) if i.get("srcUrl")]),
        p.get("numberOfImages"), p.get("numberOfFloorplans"),
        p.get("firstVisibleDate"), upd.get("listingUpdateReason"), upd.get("listingUpdateDate"),
        p.get("addedOrReduced") or None,
        p.get("commercial"), p.get("residential"), is_land, p.get("development"),
        p.get("auction"), p.get("premiumListing"), p.get("featuredProperty"),
        cust.get("brandTradingName"), cust.get("branchDisplayName"), cust.get("branchId"),
        cust.get("contactTelephone"), Json(raw),
    )


SEARCH_COLS = (
    "id, channel, search_location, location_identifier, url, title, summary, display_address, "
    "latitude, longitude, price_amount, price_currency, price_frequency, price_display, "
    "price_qualifier, bedrooms, bathrooms, property_sub_type, tenure, size_display, size_value, "
    "size_unit, size_is_likely_plot, status, key_features, image_urls, number_of_images, "
    "number_of_floorplans, first_visible_date, listing_update_reason, listing_update_date, "
    "added_or_reduced, is_commercial, is_residential, is_land, is_development, is_auction, "
    "is_premium, is_featured, agent_name, agent_branch, agent_branch_id, agent_phone, search_raw"
)
_UPDATABLE = [c.strip() for c in SEARCH_COLS.split(",") if c.strip() != "id"]
# Only rewrite a row when something a buyer would notice changed. A weekly re-sweep sees ~120k
# London listings and most are unchanged; rewriting every one (with its big search_raw json) is
# the kind of bulk write that throttled the database on 2026-09-25. Sightings go to the narrow
# listing_seen table instead (tlrm-data-pipeline/43).
_CHANGE_COLS = ["price_amount", "price_qualifier", "status", "listing_update_reason",
                "listing_update_date", "added_or_reduced", "number_of_images", "title"]
UPSERT_SQL = (
    f"insert into uk_listings ({SEARCH_COLS}) values %s on conflict (id) do update set "
    + ", ".join(f"{c} = excluded.{c}" for c in _UPDATABLE)
    + ", last_seen_at = now() where ("
    + ", ".join(f"uk_listings.{c}" for c in _CHANGE_COLS) + ") is distinct from ("
    + ", ".join(f"excluded.{c}" for c in _CHANGE_COLS) + ")"
)

# Set by `refresh` while a sweep runs: every listing a search page returns is recorded as seen.
SWEEP: dict | None = None   # {"id": sweep_id, "scope": "REGION^87490|sale", "seen": set()}


def save_page(cur, props: list[dict], channel: str, loc_name: str, loc_id: str) -> int:
    rows = {}
    for p in props:  # a featured listing repeats on every page; dedupe within the batch
        rows[int(p["id"])] = map_search_row(p, channel, loc_name, loc_id)
    if rows:
        execute_values(cur, UPSERT_SQL, list(rows.values()))
        if SWEEP is not None:
            new_ids = [str(i) for i in rows if str(i) not in SWEEP["seen"]]
            SWEEP["seen"].update(new_ids)
            if new_ids:
                cur.execute(
                    "insert into listing_seen (source, scope, listing_id, last_sweep_id) "
                    "select 'rightmove', %s, unnest(%s::text[]), %s on conflict (source, listing_id) do update "
                    "set scope = excluded.scope, last_seen_at = now(), last_sweep_id = excluded.last_sweep_id, "
                    "missed_sweeps = 0", (SWEEP["scope"], new_ids, SWEEP["id"]))
    return len(rows)


def split_point(lo: int, hi: int | None, channel: str) -> int | None:
    if hi is None:
        return max(lo * 2, lo + (1_000_000 if channel == "sale" else 5_000))
    if hi - lo < 1:
        return None
    return (lo + hi) // 2


def run_search(conn, location: str, channel: str, include_off: bool, delay: float) -> None:
    loc_id, loc_name = resolve_location(location)
    job = f"{loc_id}|{channel}|{'all' if include_off else 'live'}"
    log(f"search {loc_name} ({loc_id}) {channel}, include sold/let-agreed={include_off}  job={job}")
    cur = conn.cursor()
    cur.execute("insert into uk_scrape_bands (job, lo, hi) values (%s, 0, null) on conflict do nothing", (job,))
    conn.commit()

    while True:
        cur.execute("select lo, hi, expected, pages_done from uk_scrape_bands "
                    "where job = %s and status = 'pending' order by lo limit 1", (job,))
        band = cur.fetchone()
        if not band:
            break
        lo, hi, expected, pages_done = band
        label = f"£{lo:,}–{'∞' if hi is None else f'£{hi:,}'}"

        if expected is None:  # probe: page 1 gives the count and, if it fits, real data
            sr = search_page(channel, loc_id, include_off, lo, hi, 0)
            n = result_count(sr)
            time.sleep(delay)
            if n > BAND_MAX:
                mid = split_point(lo, hi, channel)
                if mid is not None:
                    # The lower half shares the band's key (job, lo): shrink it in place,
                    # then add the upper half. One transaction, so a crash can't lose a range.
                    cur.execute("update uk_scrape_bands set hi=%s, expected=null, updated_at=now() "
                                "where job=%s and lo=%s", (mid, job, lo))
                    cur.execute("insert into uk_scrape_bands (job, lo, hi) values (%s,%s,%s) "
                                "on conflict do nothing", (job, mid + 1, hi))
                    conn.commit()
                    log(f"  split {label} ({n:,} listings) at £{mid:,}")
                    continue
                log(f"  ! {label} has {n:,} listings at one price; only the first 1,008 are reachable")
            saved = save_page(cur, sr["properties"], channel, loc_name, loc_id)
            cur.execute("update uk_scrape_bands set expected=%s, pages_done=1, rows_saved=rows_saved+%s, "
                        "updated_at=now() where job=%s and lo=%s", (n, saved, job, lo))
            conn.commit()
            expected, pages_done = n, 1

        pages = min(MAX_PAGES, math.ceil(expected / PAGE))
        for pg in range(pages_done, pages):
            sr = search_page(channel, loc_id, include_off, lo, hi, pg * PAGE)
            saved = save_page(cur, sr["properties"], channel, loc_name, loc_id)
            cur.execute("update uk_scrape_bands set pages_done=%s, rows_saved=rows_saved+%s, updated_at=now() "
                        "where job=%s and lo=%s", (pg + 1, saved, job, lo))
            conn.commit()
            time.sleep(delay)
        final = "truncated" if expected > MAX_PAGES * PAGE else "done"
        cur.execute("update uk_scrape_bands set status=%s, updated_at=now() where job=%s and lo=%s",
                    (final, job, lo))
        conn.commit()
        log(f"  band {label}: {expected:,} listings over {pages} pages — {final}")

    run_repair(conn, loc_id, loc_name, channel, include_off, delay)
    cur.execute("select coalesce(sum(expected),0) from uk_scrape_bands where job=%s and status in ('done','truncated','repaired')", (job,))
    banded = cur.fetchone()[0]
    cur.execute("select count(*) from uk_listings where location_identifier=%s and channel=%s", (loc_id, channel))
    have = cur.fetchone()[0]
    total = result_count(search_page(channel, loc_id, include_off, 0, None, 0))
    log(f"search finished: Rightmove total {total:,}, bands cover {banded:,}, rows in uk_listings {have:,}")


# ----------------------------------------------------------------------- repair

# Agents cluster on round prices: London has 2,075 listings at exactly £650,000,
# and a one-price band can't be bisected. Those bands are re-collected per
# bedroom count, and a still-oversized bedroom slice per property type.
BEDROOM_SLICES = [{"minBedrooms": b, "maxBedrooms": b} for b in range(5)] + [{"minBedrooms": 5}]
TYPE_SLICES = ["flat", "terraced", "semi-detached", "detached", "bungalow", "land", "park-home"]


def collect_slice(cur, conn, channel, loc_id, loc_name, include_off, lo, hi, extra, delay) -> tuple[int, int]:
    """Page through one filtered slice. Returns (upstream count, pages fetched)."""
    sr = search_page(channel, loc_id, include_off, lo, hi, 0, extra)
    n = result_count(sr)
    save_page(cur, sr["properties"], channel, loc_name, loc_id)
    conn.commit()
    pages = min(MAX_PAGES, math.ceil(n / PAGE))
    for pg in range(1, pages):
        time.sleep(delay)
        sr = search_page(channel, loc_id, include_off, lo, hi, pg * PAGE, extra)
        save_page(cur, sr["properties"], channel, loc_name, loc_id)
        conn.commit()
    time.sleep(delay)
    return n, pages


def run_repair(conn, loc_id: str, loc_name: str, channel: str, include_off: bool, delay: float) -> None:
    job = f"{loc_id}|{channel}|{'all' if include_off else 'live'}"
    cur = conn.cursor()
    cur.execute("select lo, hi, expected from uk_scrape_bands where job=%s and status='truncated' order by lo", (job,))
    for lo, hi, expected in cur.fetchall():
        covered, gaps = 0, []
        for bed in BEDROOM_SLICES:
            probe = search_page(channel, loc_id, include_off, lo, hi, 0, bed)
            n = result_count(probe)
            if n <= MAX_PAGES * PAGE:
                n, _ = collect_slice(cur, conn, channel, loc_id, loc_name, include_off, lo, hi, bed, delay)
                covered += n
                continue
            for t in TYPE_SLICES:
                sl = {**bed, "propertyTypes": t}
                m, _ = collect_slice(cur, conn, channel, loc_id, loc_name, include_off, lo, hi, sl, delay)
                if m > MAX_PAGES * PAGE:
                    # Same price, beds and type (e.g. 1-bed flats at £350k): read the
                    # list newest-first then oldest-first to reach both ends -- 2,016 max.
                    for sort in (6, 10):
                        collect_slice(cur, conn, channel, loc_id, loc_name, include_off, lo, hi,
                                      {**sl, "sortType": sort}, delay)
                cap = 2 * MAX_PAGES * PAGE
                covered += min(m, cap)
                if m > cap:
                    gaps.append(f"{bed} {t}: {m - cap} unreachable")
        cur.execute("update uk_scrape_bands set status=%s, rows_saved=%s, updated_at=now() where job=%s and lo=%s",
                    ("repaired", covered, job, lo))
        conn.commit()
        log(f"  repaired £{lo:,}: {covered:,} of {expected:,} reached via bedroom/type slices"
            + (f"; gaps: {gaps}" if gaps else ""))


# ---------------------------------------------------------------------- details

def decode_page_model(html: str) -> dict | None:
    i = html.find("window.__PAGE_MODEL")
    if i < 0:
        return None
    pm, _ = json.JSONDecoder().raw_decode(html, html.index("{", i))
    arr = json.loads(pm["data"])
    memo: dict[int, object] = {}

    def dec(ix):
        if type(ix) is not int:
            return ix
        if ix < 0:        # negative indices encode undefined/null/NaN
            return None
        if ix in memo:
            return memo[ix]
        v = arr[ix]
        if isinstance(v, dict):
            o: object = {}
            memo[ix] = o
            o.update({k: dec(x) for k, x in v.items()})
        elif isinstance(v, list):
            o = []
            memo[ix] = o
            o.extend(dec(x) for x in v)
        else:
            o = v
            memo[ix] = o
        return o

    return dec(0).get("propertyData")


def html_to_text(s: str | None) -> str | None:
    if not s:
        return None
    s = re.sub(r"<br\s*/?>|</p>|</li>", "\n", s.replace("\r", ""), flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = (s.replace("&amp;", "&").replace("&nbsp;", " ").replace("&#39;", "'")
          .replace("&quot;", '"').replace("&lt;", "<").replace("&gt;", ">"))
    return re.sub(r"\n{3,}", "\n\n", s).strip()


def map_details(pd: dict) -> dict:
    addr = pd.get("address") or {}
    lc = pd.get("livingCosts") or {}
    ten = pd.get("tenure") or {}
    so = pd.get("sharedOwnership") or {}
    sizes = {}
    for s in pd.get("sizings") or []:
        u = (s.get("unit") or "").lower()
        v = s.get("maximumSize") or s.get("minimumSize")
        if u and v:
            sizes[u] = v
    postcode = " ".join(x for x in (addr.get("outcode"), addr.get("incode")) if x) or None
    return {
        "description": html_to_text((pd.get("text") or {}).get("description")),
        "postcode": postcode,
        "pin_type": (pd.get("location") or {}).get("pinType"),
        "council_tax_band": lc.get("councilTaxBand"),
        "council_tax_exempt": lc.get("councilTaxExempt"),
        "council_tax_included": lc.get("councilTaxIncluded"),
        "annual_service_charge": lc.get("annualServiceCharge"),
        "annual_ground_rent": lc.get("annualGroundRent"),
        "ground_rent_review_years": lc.get("groundRentReviewPeriodInYears"),
        "lease_years_remaining": ten.get("yearsRemainingOnLease"),
        "size_sqft_published": sizes.get("sqft"),
        "size_sqm_published": sizes.get("sqm"),
        "shared_ownership_pct": so.get("ownershipPercentage") if so.get("sharedOwnershipFlag") else None,
        "nearest_stations": Json(pd.get("nearestStations") or []),
        "rooms": Json(pd.get("rooms") or []),
        "features": Json(pd.get("features") or {}),
        "floorplan_urls": Json([f.get("url") for f in pd.get("floorplans") or [] if f.get("url")]),
        "epc_urls": Json([f.get("url") for f in pd.get("epcGraphs") or [] if f.get("url")]),
        "full_image_urls": Json([f.get("url") for f in pd.get("images") or [] if f.get("url")]),
        "details_status": "ok",
    }


def safe_page_model(html: str | None) -> dict | None:
    """decode_page_model, but a page whose model is missing or in another layout is None, not a crash."""
    try:
        return decode_page_model(html or "")
    except (ValueError, KeyError, TypeError, IndexError, AttributeError):
        return None


def run_details(conn, delay: float, limit: int | None) -> None:
    cur = conn.cursor()
    done = 0
    # Most recent listing whose page decoded - the block check re-fetches it. Seeded from the
    # database so a restart that begins on odd pages (land/commercial queue last) still has one.
    cur.execute("select id from uk_listings where details_status = 'ok' order by details_fetched_at desc limit 1")
    row = cur.fetchone()
    last_good = row[0] if row else None
    while limit is None or done < limit:
        # live residential first; sold/let-agreed last since they are about to disappear
        cur.execute("""select id from uk_listings where details_fetched_at is null
                       order by (status = 'live') desc, is_commercial is true, id limit 100""")
        ids = [r[0] for r in cur.fetchall()]
        if not ids:
            break
        for pid in ids:
            if limit is not None and done >= limit:
                break
            status, html = http_get(f"https://www.rightmove.co.uk/properties/{pid}")
            if status in (404, 410):
                cur.execute("update uk_listings set details_status='removed', details_fetched_at=now() where id=%s", (pid,))
            else:
                pd = safe_page_model(html)
                if pd is None:
                    # Not every page without property data is a block: land/development-site
                    # listings (e.g. 730291421968304, "Land for sale in Residential Development
                    # Site") are served normally but in a different layout, and stopped the
                    # 2026-09-26 run for nothing. A real block hits every page, so re-fetch the
                    # last listing that worked: if that still decodes, only this page is odd -
                    # record it and move on; if not, it's a block, stop as before.
                    if last_good is not None and safe_page_model(http_get(f"https://www.rightmove.co.uk/properties/{last_good}")[1]) is not None:
                        cur.execute("update uk_listings set details_status='no_page_data', details_fetched_at=now() where id=%s", (pid,))
                        log(f"details: {pid} has no property data in its page (HTTP {status}) - skipped, not a block")
                    else:
                        raise Blocked(f"listing page {pid} had no page data (HTTP {status}) and a known-good page failed too — likely blocked")
                else:
                    d = map_details(pd)
                    cur.execute("update uk_listings set " + ", ".join(f"{k}=%s" for k in d)
                                + ", details_fetched_at=now() where id=%s", (*d.values(), pid))
                    last_good = pid
            done += 1
            if done % 25 == 0:  # commit in groups: a crash redoes at most 25 listings
                conn.commit()
            if done % 250 == 0:
                cur.execute("select count(*) filter (where details_fetched_at is null), count(*) from uk_listings")
                left, total = cur.fetchone()
                log(f"details: {done:,} this run, {total - left:,}/{total:,} overall")
            time.sleep(delay)
        conn.commit()
    log(f"details finished: {done:,} fetched this run")


# -------------------------------------------------------------------------- geo

def run_geo(conn) -> None:
    cur = conn.cursor()
    done = 0
    while True:
        cur.execute("select id, latitude, longitude from uk_listings where geo_fetched_at is null "
                    "and latitude is not null order by id limit 100")
        rows = cur.fetchall()
        if not rows:
            break
        body = json.dumps({"geolocations": [
            {"latitude": la, "longitude": lo, "limit": 1, "radius": 500} for _, la, lo in rows]}).encode()
        for attempt in range(5):
            try:
                req = urllib.request.Request("https://api.postcodes.io/postcodes", data=body,
                                             headers={"Content-Type": "application/json", "User-Agent": UA})
                res = json.load(urllib.request.urlopen(req, timeout=60))["result"]
                break
            except Exception as e:
                log(f"  ! postcodes.io {repr(e)[:80]}; retrying")
                time.sleep(10 * (attempt + 1))
        else:
            raise RuntimeError("postcodes.io unavailable")
        upd = []
        for (pid, _, _), r in zip(rows, res):
            p = (r.get("result") or [None])[0] or {}
            c = p.get("codes") or {}
            upd.append((pid, p.get("postcode"), p.get("distance"), p.get("admin_district"), c.get("admin_district"),
                        p.get("admin_ward"), c.get("admin_ward"), p.get("parliamentary_constituency"),
                        c.get("parliamentary_constituency"), p.get("region"), p.get("lsoa"), c.get("lsoa"),
                        p.get("msoa"), c.get("msoa")))
        execute_values(cur, """
            update uk_listings u set nearest_postcode=v.pc, postcode_distance_m=v.dist::numeric,
              borough=v.b, borough_code=v.bc, ward=v.w, ward_code=v.wc, constituency=v.pcon,
              constituency_code=v.pconc, region=v.reg, lsoa=v.l, lsoa_code=v.lc, msoa=v.m, msoa_code=v.mc,
              geo_fetched_at=now()
            from (values %s) as v(id, pc, dist, b, bc, w, wc, pcon, pconc, reg, l, lc, m, mc)
            where u.id = v.id""", upd)
        conn.commit()
        done += len(rows)
        if done % 5000 < 100:
            log(f"geo: {done:,} listings")
        time.sleep(0.2)
    log(f"geo finished: {done:,} listings")


# ---------------------------------------------------------------------- refresh

MISS_THRESHOLD = 2      # same rule as tlrm/listing-freshness.mjs
MIN_COVERAGE = 0.85


def db_healthy(conn, max_ms: int = 3000) -> tuple[bool, int]:
    """CPU probe: ~0.7s healthy, 38-72s when the instance was throttled on 2026-09-25."""
    cur = conn.cursor()
    t0 = time.time()
    cur.execute("select sum(i) from generate_series(1, 2000000) i")
    cur.fetchone()
    conn.commit()
    ms = int((time.time() - t0) * 1000)
    return ms <= max_ms, ms


def wait_for_healthy_db(conn, max_wait_min: int = 60) -> bool:
    deadline = time.time() + max_wait_min * 60
    while True:
        ok, ms = db_healthy(conn)
        if ok:
            return True
        if time.time() > deadline:
            log(f"database still slow ({ms} ms probe) after {max_wait_min} min - stopping")
            return False
        log(f"database slow ({ms} ms probe) - waiting 5 min")
        time.sleep(300)


def run_refresh(conn, location: str, delay: float, limit: int | None = None) -> None:
    """Weekly sweep: re-read every search band for sale and rent, record what's still listed,
    and mark listings two complete sweeps didn't see as 'withdrawn' (publish-uk-listings.mjs then
    takes them off the site). New listings get geo + details; nothing else is re-fetched."""
    global SWEEP
    if not wait_for_healthy_db(conn):
        sys.exit(4)
    loc_id, loc_name = resolve_location(location)
    cur = conn.cursor()
    for channel in ("sale", "rent"):
        scope = f"{loc_id}|{channel}"
        job = f"{loc_id}|{channel}|all"
        cur.execute("insert into listing_sweeps (source, scope) values ('rightmove', %s) returning id", (scope,))
        sweep_id = cur.fetchone()[0]
        # Keep last sweep's band boundaries (no re-bisecting from scratch) but re-read every band;
        # each re-probes its count, so a band that grew past the cap still splits.
        # (Skipped when bands are still pending: that's an interrupted refresh being resumed. Its
        # seen-set is lost, so coverage comes out low and nothing is marked missed - safe.)
        cur.execute("update uk_scrape_bands set status='pending', expected=null, pages_done=0, rows_saved=0, "
                    "updated_at=now() where job=%s and not exists "
                    "(select 1 from uk_scrape_bands b where b.job=%s and b.status='pending')", (job, job))
        conn.commit()
        SWEEP = {"id": sweep_id, "scope": scope, "seen": set()}
        log(f"refresh {loc_name} {channel}: sweep {sweep_id}")
        try:
            run_search(conn, location, channel, True, delay)
        finally:
            seen = SWEEP["seen"]
            SWEEP = None

        # Everything on file for this place: rows filed under this search, plus rows whose postcode
        # region is this place but which a smaller search (e.g. E1W) last re-filed - those are
        # published too, so they must be checked for withdrawal by the area-wide sweep.
        cur.execute("select id::text from uk_listings where (location_identifier=%s or region=%s) "
                    "and channel=%s and status not in ('withdrawn')", (loc_id, loc_name, channel))
        current = [r[0] for r in cur.fetchall()]
        overlap = sum(1 for i in current if i in seen)
        coverage = overlap / len(current) if current else 1.0
        missed, withdrawn = [], []
        if coverage >= MIN_COVERAGE:
            missed = [i for i in current if i not in seen]
            for k in range(0, len(missed), 2000):
                cur.execute(
                    "insert into listing_seen (source, scope, listing_id, last_sweep_id, missed_sweeps) "
                    "select 'rightmove', %s, unnest(%s::text[]), %s, 1 on conflict (source, listing_id) do update "
                    "set missed_sweeps = case when listing_seen.last_sweep_id = excluded.last_sweep_id "
                    "then listing_seen.missed_sweeps else listing_seen.missed_sweeps + 1 end, "
                    "last_sweep_id = excluded.last_sweep_id returning listing_id, missed_sweeps",
                    (scope, missed[k:k + 2000], sweep_id))
                withdrawn += [r[0] for r in cur.fetchall() if r[1] >= MISS_THRESHOLD]
            for k in range(0, len(withdrawn), 500):
                cur.execute("update uk_listings set status='withdrawn' where id = any(%s::bigint[])",
                            (withdrawn[k:k + 500],))
                conn.commit()
                time.sleep(0.4)
            status, note = "complete", None
        else:
            status, note = "partial", f"coverage {coverage:.1%} < {MIN_COVERAGE:.0%} - nothing marked missed"
        # A listing page that 404s during details is gone now, whatever the sweep saw.
        cur.execute("update uk_listings set status='withdrawn' where details_status='removed' "
                    "and status <> 'withdrawn' and (location_identifier=%s or region=%s) and channel=%s",
                    (loc_id, loc_name, channel))
        gone_404 = cur.rowcount
        cur.execute("update listing_sweeps set finished_at=now(), status=%s, seen=%s, missed_count=%s, "
                    "archived_count=%s, notes=%s where id=%s",
                    (status, len(seen), len(missed), len(withdrawn) + gone_404, note, sweep_id))
        conn.commit()
        log(f"refresh {channel}: seen {len(seen):,} of {len(current):,} on file ({coverage:.1%}), "
            f"missed {len(missed):,}, withdrawn {len(withdrawn):,} (+{gone_404} from 404s) - {status}")

    run_geo(conn)
    run_details(conn, delay, limit)


# ----------------------------------------------------------------------- status

def show_status(conn) -> None:
    cur = conn.cursor()
    cur.execute("""select search_location, channel, count(*),
                          count(*) filter (where status='live'),
                          count(*) filter (where details_fetched_at is not null),
                          count(*) filter (where geo_fetched_at is not null)
                   from uk_listings group by 1,2 order by 1,2""")
    print(f"{'location':20} {'channel':6} {'rows':>8} {'live':>8} {'details':>8} {'geo':>8}")
    for r in cur.fetchall():
        print(f"{r[0] or '':20} {r[1]:6} {r[2]:>8,} {r[3]:>8,} {r[4]:>8,} {r[5]:>8,}")
    cur.execute("""select job, count(*) filter (where status in ('done','truncated')),
                          count(*) filter (where status='pending'), coalesce(sum(rows_saved),0)
                   from uk_scrape_bands group by job order by job""")
    for job, done, pending, saved in cur.fetchall():
        print(f"  bands {job}: {done} done, {pending} pending, {saved:,} rows saved")


# ------------------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["setup", "search", "repair", "details", "geo", "all", "refresh", "status"])
    ap.add_argument("--location", default="London", help="place name or Rightmove id like REGION^87490")
    ap.add_argument("--channel", choices=["sale", "rent"], default="sale")
    ap.add_argument("--live-only", action="store_true", help="exclude sold STC / let agreed")
    ap.add_argument("--delay", type=float, default=0.5, help="seconds between requests")
    ap.add_argument("--limit", type=int, help="details: stop after this many listings")
    a = ap.parse_args()

    # Every stage resumes from what is already saved, so a dropped database
    # connection (laptop sleep, Wi-Fi blip, Supabase restart) is handled by
    # reconnecting and simply running the command again.
    for attempt in range(1, 51):
        try:
            conn = connect()
        except psycopg2.OperationalError as e:
            log(f"  ! database unreachable ({str(e).strip()[:80]}); retrying in 60s")
            time.sleep(60)
            continue
        try:
            run_command(a, conn)
            return
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
            log(f"  ! database connection lost ({str(e).strip()[:80]}); reconnecting in 30s (#{attempt})")
            time.sleep(30)
        except Blocked as e:
            log(f"STOPPED — Rightmove looks like it is blocking us: {e}. Progress is saved; re-run later to resume.")
            sys.exit(2)
        finally:
            try:
                conn.close()
            except Exception:
                pass
    log("STOPPED — database kept dropping; progress is saved, re-run to resume.")
    sys.exit(3)


def run_command(a, conn) -> None:
    if a.command == "setup":
        conn.cursor().execute(DDL)
        conn.commit()
        log("uk_listings and uk_scrape_bands are ready")
    elif a.command == "search":
        run_search(conn, a.location, a.channel, not a.live_only, a.delay)
    elif a.command == "repair":
        loc_id, loc_name = resolve_location(a.location)
        run_repair(conn, loc_id, loc_name, a.channel, not a.live_only, a.delay)
    elif a.command == "details":
        run_details(conn, a.delay, a.limit)
    elif a.command == "geo":
        run_geo(conn)
    elif a.command == "refresh":
        run_refresh(conn, a.location, a.delay, a.limit)
    elif a.command == "status":
        show_status(conn)
    elif a.command == "all":
        for ch in ("sale", "rent"):
            run_search(conn, a.location, ch, not a.live_only, a.delay)
        run_geo(conn)
        run_details(conn, a.delay, a.limit)


if __name__ == "__main__":
    main()
