---
name: properstar-listings
description: Collect Properstar property listings for a city as two datasets, sale and rental, via parse.bot. Use when the user asks for listings, properties, or market data for a city (Tulum, Cancún, Playa del Carmen, Mérida, etc.), or says "scrape <city>", "get me <city> properties", "add <city> to the database", or asks for rentals vs sales for a location.
---

# Properstar city collection

Collects a city's listings into **two separate datasets** — sale and rental —
via parse.bot. **This is the only route in active use** — free scraping
(`scrape_free.py`) exists and still works, but is deliberately not the default;
see "Why not free scraping" below before reaching for it.

Scripts live in `properstar-scraper/`. Run them from that directory.

## Sale: the two commands

```bash
python calibrate_bands.py --city cancun --transaction buy --target 1900 \
  --types apartment,house --out plans/cancun-buy.json
python fetch_city.py --plan plans/cancun-buy.json --dry-run   # shows cost, bills nothing
python fetch_city.py --plan plans/cancun-buy.json
```

`calibrate_bands.py` binary-searches Properstar's own backend API for the
*exact* listing count in any price range — free (that API's search works fine
for counting; only its bulk-pagination is broken, see "Do not" below) — and
writes bands packed to ~1,900 with no slack. Measured on Cancún: **5 bands**,
9,213 listings, no gaps. `--types ""` bands price alone across every type
instead — don't use that for a normal buy pull, it pulls in land/commercial
listings the apartment+house counts never saw and overflows bands.

**Cost, measured live, not estimated:** `search_homes_filtered` on the correct
scraper (`PARSEBOT_FILTERED_URL` in `cancun-ingestion/.env` — verify it still
points here before trusting this number) bills **1 credit per 2,000 rows**
(both upstream pages in one call). Cancún's 9,213 listings: **5 credits
(~$0.15)**. `fetch_city.py --dry-run` always confirms the actual cost before
spending — run it and show the user the number regardless of how cheap this
now is; "cheap" isn't the same as "don't bother checking."

`plan_city.py` still works (sampled bands, ~20% error, must target lower to
leave margin) but is superseded for sale by `calibrate_bands.py` — no reason
to use it now.

## Rental: still the older, more expensive endpoint

```bash
python plan_city.py  --city cancun --transaction rent
python fetch_city.py --plan plans/cancun_rent.json --dry-run
python fetch_city.py --plan plans/cancun_rent.json
```

Rental sits on a different scraper (`916753d6-…`, `search_homes_rental_filtered`)
that has **not** been moved to the cheap 2,000-row endpoint — still **10
credits per call**, up to 1,000 rows each. `calibrate_bands.py` doesn't have a
rental-calibrated path built yet; `plan_city.py`'s sampled bands are what's
available today. Cost is real at this rate (Cancún's 2,347 rentals ≈ 24
credits, ~$0.72) — always `--dry-run` first and confirm with the user before
a rental run, same as any paid spend.

## Do not

- **Don't reach for `scrape_api.py`** (Properstar's backend search API, called
  directly for bulk collection) — **documented dead end**. Its `total` counts
  are exact and free (that's what `calibrate_bands.py` uses), but its
  pagination is broken: every `page`/`skip`/`offset` variant returns the
  identical first 25 rows. A real attempt collected 4/9,213 listings in 376
  requests before this was caught.
- **Don't default to free scraping** (`scrape_free.py`, `collect_city.py`'s
  free routing, `estimate_cities.py`'s "what free would save" framing) even
  though all of it still works and is documented below for reference. At
  today's parse.bot pricing a whole city is single-digit credits — the
  cost case that used to justify a multi-minute, non-deterministic free
  scrape just to save a few dollars mostly isn't there anymore. Use parse.bot.
- **Don't spend a credit on a scouting call.** `fetch_city.py` calibrates off
  its *first real slice* instead — same cost as a probe, except the rows are
  kept. If drift would push a later band past 2,000 it stops after 1 credit
  and prints the `--target` to re-plan with.
- **Never let a band exceed 2,000** — rows past the cap are silently dropped.
  `fetch_city.py` warns when a slice comes back over; the fix is re-planning
  with a lower `--target`.
- **Bad city slug → HTTP 404** (a clear error). Bad *property-type* slug fails
  silently by returning something else, so type filters are checked
  structurally. Slugs drop accents: Cancún → `cancun`, Mérida → `merida`.

Outputs, written to `properstar-scraper/`:

| File | Market |
|---|---|
| `properstar_<city>.csv` / `.json` | sale |
| `properstar_<city>_rent.csv` / `.json` | rental |

Keep them separate. Sale prices are totals and rental prices are monthly — a
merged price column is meaningless.

## Known API gaps (ask parse.bot to fix)

**The two scrapers behave differently — check which one you're on.**

| | sale scraper (2,000-row endpoint) | rental scraper `916753d6-…` |
|---|---|---|
| endpoint | `search_homes_filtered` | `search_homes_rental_filtered` |
| cost | 1 credit / 2,000 rows | **10 credits / 1,000 rows** |
| `date_listed` | always empty | populated on every row |
| `property_type` | `Condo` / `Home` | `Apartment` / `House` |
| incremental | none (`updated_since` ignored) | `min_date_listed=YYYY-MM-DD` |

- **The rental endpoint lives under a different scraper UUID** — not reachable
  by swapping the path on `PARSEBOT_SEARCH_URL`, that 404s. It's configured
  explicitly: `PARSEBOT_RENT_URL=https://api.parse.bot/scraper/916753d6-.../search_homes_rental_filtered`
  in `cancun-ingestion/.env`. `fetch_city.py` uses that verbatim.
- **parse.bot pricing is set per scraper at creation time and does not change
  on revision.** Confirmed: asking parse.bot to "lower the price" to match a
  cheaper sibling scraper changes the description text, never the actual
  `x-parse-price`. The only way to a cheaper price is a fresh scraper built
  from a cheap canonical, revised minimally (see the sale scraper's own
  history) — not a request to reprice an existing one.
- **Sale rows still lack `date_listed`** even though Properstar publishes
  `publicationDate`. Only the rental scraper and the free route return it.
- **Normalise `property_type` before joining sale and rental** — the two
  scrapers disagree, and rental happens to match the free route.
- **No sort control**, so a slice can't be read from both ends. Price banding
  is the only way past the cap.

## Why not free scraping (kept for reference, not the default)

Properstar hard-caps **any single search at 2,000 retrievable results**
(`totalRetrievable`). `scrape_free.py` scrapes the public site for free when a
market fits under that cap — but it's slow (one pass ~3 min, non-deterministic,
needs several merging passes to converge: measured 74% → 93% → 98.6% over
three passes on Tulum rentals) and doesn't help once a market exceeds the cap
in every type slice, at which point it's parse.bot regardless.

That trade only made sense when parse.bot was expensive. It mostly doesn't
anymore for sale (2,000 rows/credit). It's still a real trade-off for rental
specifically (10 credits/call, no free-tier discount) — if rental cost ever
becomes a real constraint again, this is where to look, not before:

- `scrape_free.py --type` slices by property type; output paths key on
  city+market, so successive type runs merge into one dataset automatically.
- `--fresh` discards instead of merging.
- Check type-slice totals before assuming a capped-looking market needs
  paying for — the cap is *per search*, so `/rent/apartment` and `/rent/house`
  are separate searches and can each be under 2,000 even when combined they
  look capped:

  ```bash
  python -c "from plan_city import Site; s=Site('mexico','cancun','rent'); s.bootstrap(); \
  [print(t, s.search(t).get('total'), s.search(t).get('totalRetrievable')) for t in ('apartment','house')]"
  ```
- Properstar's pagination overlaps, and a whole page can be duplicates while
  later pages still hold new listings — `scrape_free.py` only gives up after 5
  barren pages in a row. Stopping at the first one silently cost 45% of a
  rental market during development.

`collect_city.py` still auto-routes free-vs-paid per market by the aggregate
cap — don't rely on it without checking type slices yourself first, per above.

## Credits

`X-Credits-Charged` on each response is the source of truth; the run prints a
running total. Both a request ceiling and a credit ceiling are enforced in
code and cannot be exceeded.

Reference costs: Cancún sale 9,213 listings = 5 credits (~$0.15). Tulum sale
8,522 listings = 13 credits ($0.39, pre-2,000-row-endpoint figure — likely ~4
now, unverified). Cancún rental 2,347 = ~24 credits (~$0.72).
