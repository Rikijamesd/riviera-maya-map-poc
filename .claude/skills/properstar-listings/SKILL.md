---
name: properstar-listings
description: Collect Properstar property listings for a city as two datasets, sale and rental. Use when the user asks for listings, properties, or market data for a city (Tulum, Cancún, Playa del Carmen, Mérida, etc.), or says "scrape <city>", "get me <city> properties", "add <city> to the database", or asks for rentals vs sales for a location.
---

# Properstar city collection

Collects a city's listings into **two separate datasets** — sale and rental —
choosing the cheapest route that still reaches 100% coverage.

Scripts live in `properstar-scraper/`. Run them from that directory.

## Update (2026-09-08): use calibrate_bands.py, not plan_city.py, for sale

`plan_city.py` still works but is superseded for the sale/buy side by
`calibrate_bands.py`, which is strictly better and costs nothing extra:

```bash
python calibrate_bands.py --city cancun --transaction buy --target 1900 \
  --types apartment,house --out plans/cancun-buy.json
python fetch_city.py --plan plans/cancun-buy.json --dry-run   # shows cost, bills nothing
python fetch_city.py --plan plans/cancun-buy.json
```

Why: `plan_city.py` sizes bands from *sampled* public-site prices (~20% error on
Tulum), so it must target ~1,650/band to leave safety margin, and it cuts each
property type separately — both waste retrievable capacity. `calibrate_bands.py`
binary-searches Properstar's own backend API for the *exact* count in any price
range (free — that API's search works fine for counting, only its pagination is
broken, see "Known API gaps" below), so bands pack to ~1,900 with zero slack.
Measured on Cancún: 7 bands (plan_city.py) → **5 bands** (calibrate_bands.py),
same 9,213 listings covered, no gaps. `--types ""` bands price alone across
every type instead — don't use that for a normal buy pull, it pulls in land/
commercial listings the apartment+house counts never saw and overflows bands.

**The real cost, measured live, not estimated:** `search_homes_filtered` was
long assumed to bill 1 credit per call for up to 1,000 rows. It actually bills
1 credit for up to **2,000** rows (both upstream pages in one call) on the
correct scraper — `PARSEBOT_FILTERED_URL` in `cancun-ingestion/.env` already
points at it. Cancún's 9,213 listings: **5 credits (~$0.15)**, not ~10. Verify
whichever scraper `PARSEBOT_FILTERED_URL` points at is still the 2,000-row one
before trusting this number blindly — parse.bot pricing is set per scraper at
creation time and does not change on revision (confirmed: asking parse.bot to
"lower the price" changes the description, never the actual `x-parse-price`).

`scrape_api.py` (Properstar's own backend search API, called directly) is a
**documented dead end for bulk collection** — don't try to build on it again.
Its `total` counts are exact and free (that's what `calibrate_bands.py` uses),
but its pagination is broken: every `page`/`skip`/`offset` variant returns the
identical first 25 rows. A real attempt collected 4/9,213 listings in 376
requests before this was caught.

## Always cost it first

```bash
python estimate_cities.py --cities tulum,cancun,merida
```

Free and fast (~2 requests per city, no price sampling, no credits). Prints a
per-city table of listings, parse.bot credits, dollar cost, and what free
scraping would miss. **Show the user this table and get approval before any
paid run.**

**Sale and rental are separate parse.bot scrapers on separate pricing:
sale is 1 credit/call, rental is 10.** The estimator accounts for this; don't
reason about rental cost using sale figures. Reference: Cancún sale 9,170
listings = 10 cr ($0.30); Cancún rental 2,347 = 30 cr ($0.90).

## The one command

```bash
python collect_city.py --city tulum --plan-only   # free, always safe
python collect_city.py --city tulum --yes         # collect (may spend credits)
```

`--plan-only` never spends credits. Run it first, show the user the projected
cost, and **only pass `--yes` once they approve the spend**. The user paid for
these credits and wants them used deliberately.

Outputs, written to `properstar-scraper/`:

| File | Market |
|---|---|
| `properstar_<city>.csv` / `.json` | sale |
| `properstar_<city>_rent.csv` / `.json` | rental |

Keep them separate. Sale prices are totals and rental prices are monthly — a
merged price column is meaningless.

## Why two routes

Properstar hard-caps **any single search at 2,000 retrievable results**, and
reports this itself as `totalRetrievable` next to `total`. So:

- **City under 2,000 listings → free.** `scrape_free.py` scrapes the public site.
  No credits. Also recovers `date_listed`, which parse.bot returns empty.
  One pass gets only ~75% — Properstar re-serves listings across pages, and is
  **non-deterministic**, returning a different subset each run (1,154 then 1,092
  on identical commands). Exploit that: `scrape_free.py` **merges into existing
  output by default**, so re-running the same command converges toward complete
  coverage. Measured on Tulum rentals: **74% → 93% → 98.6%** over three passes.
  `--fresh` discards instead of merging. Each pass costs ~3 minutes and 0
  credits, so free is viable for completeness — it trades time for money, not
  completeness for money. Run passes until the "+N new this pass" line
  approaches zero.
- **Over 2,000 → check the type slices before paying.** The cap applies *per
  search*, and `/rent/apartment` and `/rent/house` are separate searches. A
  market that looks capped in aggregate is often two uncapped halves. Cancún
  rentals: 2,347 combined (capped, 2,000 retrievable) but apartment 1,605 and
  house 742 each return `totalRetrievable == total` — so the whole market is
  free, not the 30 credits the aggregate figure implies. Always check:

  ```bash
  python -c "from plan_city import Site; s=Site('mexico','cancun','rent'); s.bootstrap(); \
  [print(t, s.search(t).get('total'), s.search(t).get('totalRetrievable')) for t in ('apartment','house')]"
  ```

  `scrape_free.py --type` takes the slice, and output paths key on city+market
  only — so successive `--type apartment` / `--type house` runs merge into one
  dataset automatically.
- **Still over 2,000 within a single type → parse.bot.** `plan_city.py` cuts the
  market into GBP price bands under the cap; `fetch_city.py` runs them. ~1 credit
  per 1,000 listings for sale, ~10 for rental.

`collect_city.py` applies this rule automatically per market, but it only tests
the aggregate — it will route a type-splittable market to parse.bot. Check the
type totals yourself before approving any rental spend.

## Running the steps individually

```bash
python plan_city.py  --city cancun --transaction buy    # free; writes plans/cancun.json
python fetch_city.py --plan plans/cancun.json --dry-run # shows cost, bills nothing
python fetch_city.py --plan plans/cancun.json           # runs it
python scrape_free.py --city tulum --transaction rent   # free route
```

## Things that will bite you

- **Slicing is a correctness requirement, not an optimisation.** An unsliced
  search over a big city returns ~2,000 rows and looks perfectly successful.
  Always check the reported total against `city_total`.
- **Don't spend a credit on a scouting call.** `fetch_city.py` calibrates off its
  *first real slice* instead: bands are sized from public-site counts but run
  against parse.bot, so if its inventory differs, the first slice's
  `total_results` reveals it. If the drift would push a later band past 2,000 it
  stops after 1 credit and prints the `--target` to re-plan with. Same cost as a
  probe, except the rows are kept.
- **Never let a band exceed 2,000** — rows past the cap are silently dropped.
  `fetch_city.py` warns when a slice comes back over; the fix is re-planning with
  a lower `--target`.
- **Slice by price, not bedrooms.** Bedroom filters work but leave a hole: some
  listings carry no bedroom value, and `max_bedrooms=0` matches nothing. Every
  listing has a price, and bands are open-ended at both ends, so nothing escapes.
- **Price bands don't transfer between cities.** Cancún's median apartment is
  ~GBP 360k vs Tulum's ~195k. Always re-plan per city; that's what the free
  sampling step is for.
- **Properstar's pagination overlaps, and a whole page can be duplicates while
  later pages still hold new listings.** `scrape_free.py` therefore only gives up
  after 5 barren pages in a row. Stopping at the first one silently cost 45% of a
  rental market during development. If a free pull lands well under the stated
  total, suspect the stop condition before believing the site ran out — check a
  deep page directly (`site.search("apartment-house", 70)`) for unseen ids.
  Expect a few percent shortfall regardless, from genuine duplicate overlap.
- **Bad city slug → HTTP 404** (a clear error). Bad *property-type* slug fails
  silently by returning something else, so type filters are checked structurally.
  Slugs drop accents: Cancún → `cancun`, Mérida → `merida`.

## Known API gaps (ask parse.bot to fix)

**The two scrapers behave differently — check which one you're on.**

| | sale scraper `9800404f-…` | rental scraper `916753d6-…` |
|---|---|---|
| endpoint | `search_homes_filtered` | `search_homes_rental_filtered` |
| cost | 1 credit/call | **10 credits/call** |
| `date_listed` | always empty | populated on every row |
| `property_type` | `Condo` / `Home` | `Apartment` / `House` |
| incremental | none (`updated_since` ignored) | `min_date_listed=YYYY-MM-DD` |

- **The rental endpoint lives under a different scraper UUID**, so it is *not*
  reachable by swapping the path on `PARSEBOT_SEARCH_URL` — that 404s, which is
  what made it look unshipped for weeks. It is configured explicitly:
  `PARSEBOT_RENT_URL=https://api.parse.bot/scraper/916753d6-.../search_homes_rental_filtered`
  in `cancun-ingestion/.env`. `fetch_city.py` uses that verbatim.
- **Sale rows still lack `date_listed`** even though Properstar publishes
  `publicationDate`. Only the rental scraper and the free route return it.
- **Normalise `property_type` before joining sale and rental** — the two
  scrapers disagree, and rental happens to match the free route.
- **No sort control**, so a slice can't be read from both ends. Price banding is
  the only way past the cap.

## Credits

`X-Credits-Charged` on each response is the source of truth; the run prints a
running total. Measured at **1 credit per sale call, 10 per rental call**, each
returning up to 1,000 rows. Both a request ceiling and a credit ceiling are
enforced in code and cannot be exceeded.

Reference costs: Tulum sale 8,522 listings = 13 credits ($0.39). Cancún sale
~9,170 = ~10 credits. Cancún rental 2,347 = ~30 credits ($0.90).

**The 10x rental price changes the free-vs-paid call.** For sales, paying is
almost always right. For rentals, prefer free scraping whenever the market fits
under the 2,000 cap — Tulum's 1,475 rentals cost 20 credits paid, versus 0 and
~3 minutes per merging pass free (98.6% measured). Pay for rentals only when the
market is genuinely over the cap, as Cancún's 2,347 is.
