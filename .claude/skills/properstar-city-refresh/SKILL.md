---
name: properstar-city-refresh
description: End-to-end refresh of one city's Properstar resale listings — collect via parse.bot, upload new listings, fix existing GBP-priced ones with the same fresh data, reclassify, verify the live site, and (separately) remove delisted rows. Use when the user asks to scrape, add, refresh, sync, or update a city's properties/listings (Tulum, Cancún, Playa del Carmen, Mérida, etc.), or "do <city> the same way we did Cancún".
---

# Properstar city refresh

Three stages. The first two are commands; the third is a deliberate manual
step because it deletes data.

| # | What | Where | Automatic? |
|---|---|---|---|
| 1 | Collect via parse.bot | `properstar-scraper/` | Two commands, cost shown before spend |
| 2 | Upload + fix existing + reclassify + verify | `tlrm/` | **One command**, six sub-stages |
| 3 | Remove delisted/priceless rows | `tlrm/` | Separate, run yourself after reading the dry run |

## Stage 1 — Collect

```bash
cd properstar-scraper
python calibrate_bands.py --city <city> --transaction buy --target 1900 \
  --types apartment,house --out plans/<city>-buy.json
python fetch_city.py --plan plans/<city>-buy.json --dry-run   # confirm cost, bills nothing
python fetch_city.py --plan plans/<city>-buy.json             # spend, writes properstar_<city>.json
```

`calibrate_bands.py` binary-searches Properstar's own backend API for the
*exact* listing count in any price range — free — and packs bands to ~1,900
with no slack. `--types ""` bands price alone across every type instead —
don't use that for a normal pull, it drags in land/commercial listings the
apartment+house counts never saw and overflows bands. `plan_city.py` (sampled
bands, ~20% error) still works but is superseded for sale.

**Cost, measured live:** `search_homes_filtered` on the correct scraper
(`PARSEBOT_FILTERED_URL` in `cancun-ingestion/.env` — verify it still points
here) bills **1 credit per 2,000 rows**. A whole city is typically
single-digit credits (Cancún's 9,213 listings = 5, ~$0.15). `--dry-run`
always confirms the actual number before spending — run it and show the user
regardless of how cheap this now is.

**Rental** sits on a different, unfixed scraper (`916753d6-…`,
`search_homes_rental_filtered`) — still **10 credits per call**, up to 1,000
rows each, no cheap-tier equivalent shipped. Use `plan_city.py --transaction
rent` + `fetch_city.py`; always `--dry-run` and confirm with the user first,
this one is real money.

**This is the collection route in active use.** Free scraping
(`scrape_free.py`, `collect_city.py`'s free routing) still works but isn't
the default — see "Why not free scraping" below.

## Stage 2 — Upload, backfill, reclassify, verify (one command)

```bash
cd ../tlrm
node upload-and-verify-resale-city.mjs \
  ../riviera-maya-map-poc/properstar-scraper/properstar_<city>.json "<City>" "<Province>"
```

City and province must match the site's existing tag exactly (`"Cancún"`
with the accent). Check first if unsure:

```bash
node -e "
import('pg').then(async ({default: pg}) => {
  const fs = await import('fs');
  const cs = fs.readFileSync('.env.local','utf-8').split('\n').find(l=>l.startsWith('DATABASE_URL=')).slice(13).trim();
  const c = new pg.Client({connectionString: cs, ssl:{rejectUnauthorized:false}});
  await c.connect();
  console.log((await c.query('SELECT DISTINCT city, province FROM resale_listings ORDER BY city')).rows);
  await c.end();
});"
```

Runs six sub-stages, **each its own process** (never bundled into one script
or transaction — see "Why separate processes" below), stopping immediately if
a fatal one fails:

| # | Script | What it does | Time |
|---|---|---|---|
| 1a | `import-resale-from-properstar-json.mjs` (dry run) | Prints insert count + skip breakdown | seconds |
| 1b | same, `--apply` | Inserts **new** rows, fills `nb_colonia`/`geo_level`/`quality_flags` | seconds |
| 1c | `backfill-resale-original-prices.mjs --apply` | Fixes **existing** GBP-tagged rows using this same fresh JSON | seconds–min |
| 2 | `reprocess-resale-dedup-and-channel.mjs` | Full-table dedup + `listing_channel` classification + VACUUM ANALYZE | **~7 min** |
| 3 | `check-resale-currency-integrity.mjs` | Table-wide currency/price sanity (informational, non-fatal) | seconds |
| 4 | `verify-resale-site.mjs <city>` | Hits the real DB functions + API routes the site uses | seconds |

**Stage 1c is the one that's easy to forget, and forgetting it is why it's
now automatic.** 1a/1b only ever touch listings not already in the table —
re-scraping a whole city and stopping at 1a/1b fixes nothing for listings
already there, even though the fresh JSON has their correct price sitting in
it. First real run (Cancún) shipped without 1c and left 9,158 existing rows
on the old GBP price; 1c alone then fixed 8,797 of them in one pass. No flag
to skip it — there's no useful "upload but don't fix what's already wrong"
mode.

## Stage 3 — Remove dead listings (manual, on purpose)

```bash
node prune-dead-listings.mjs "<City>" \
  ../riviera-maya-map-poc/properstar-scraper/properstar_<city>.json
```

Dry run by default (`--apply` to delete). Removes three groups, scoped to one
city: rows still `price_currency = 'GBP'` that the fresh pull *also* couldn't
fix, rows with no price recorded at all, and rows absent from the fresh pull
despite being an in-scope type (apartment/house family) — likely delisted.

**Before applying on a city pruned for the first time**, spot-check a handful
of the GBP-only rows directly against Properstar (fetch
`https://www.properstar.co.uk/listing/<id>`, or read `__INITIAL_STATE__` —
see `probe_display.py`'s pattern in `properstar-scraper/`). Cancún, Tulum, and
Puerto Morelos each came back 5/5 or 10/10 HTTP 404 — genuinely delisted, not
just price-hidden — which is what justified deleting all of that group.

**Playa del Carmen didn't** — a 5-sample came back 4 delisted, 1 still live
with a real recoverable price. That's not "mostly live" (the don't-delete
case below), but it's not the clean 100% the other three cities gave either —
worth resolving properly rather than guessing from a small sample either way.
Audited **every** GBP row individually (499 listings, ~5 min, free): 370
confirmed HTTP 404 (deleted), 129 still live — and every one of those 129 had
a real Original price sitting on its own detail page that the search-results
pass had simply missed. Recovered 104 of those (25 hit the sanity ceiling —
see below); deleted only the confirmed-404 370, not the whole group-of-499.
**This is a real outcome, not a hypothetical** — check whether the group-1
rate is clean before trusting a blanket delete on a new city, and do the
full per-row audit instead of a delete when it isn't.

If a new city's sample comes back mostly HTTP 200 (still live, price
genuinely just hidden/POA), don't delete that city's group 1 at all.

Kept out of the automatic stage-2 command on purpose — it's a `DELETE`, and
that spot-check judgment call shouldn't happen silently. `upload-and-verify-
resale-city.mjs` prints the exact command to run this, every time, at the end
of its own run.

Backs up every deleted row to a local JSON file first, runs VACUUM ANALYZE
after.

## The price rule — why stage 1c and stage 3's group-1 both exist

The scraped JSON carries **two price pairs** per listing:

| field | what it is | used? |
|---|---|---|
| `price` / `price_amount` / `price_currency` | Properstar's **GBP display conversion** — drifts day to day independent of the real price | **never** |
| `original_price_currency` / `original_price_amount` | the advertiser's **real listed price**, read from the source's own `type:"Original"` entry | **always** |

Every script in this pipeline reads only the `original_*` pair,
unconditionally, and skips/leaves-GBP rather than falling back to the
converted value when Original is missing. A listing whose Original currency
genuinely is GBP is used normally — the rule is *never treat the display
conversion as the price*, not *never allow GBP*. `price_usd` is always
computed from a live exchange rate fetched at write time (frankfurter.app,
same source every resale script uses) — never from parse.bot's own converted
`price_amount`. This is the exact bug class the 2026-09-06 GBP-price incident
was about (see `properstar-scraper/HANDOVER-parsebot.md` and the
`tlrm-resale-currency-check` skill) — do not weaken it to "fall back to GBP
if Original is missing" even if it recovers more rows; those rows are exactly
what the incident was about.

**93% of the table predates this fix** (falling as backfills land). The
site's "Originally listed in {currency}" note (`ResaleDetailBody.tsx`) is
gated to never fire for `price_currency = 'GBP'` for exactly this reason —
don't remove that gate without backfilling first, or the site asserts a false
currency on most listings.

## Why separate processes, not one script

`reprocess-resale-dedup-and-channel.mjs` (stage 2) is a **full-table**
operation by design — dedup ranking and neighbourhood price norms are both
relative to the whole table, not just new rows, so there's no way to scope it
to "just this upload." An earlier attempt to bundle the equivalent SQL into
one auto-triggered function was tried and caused a real incident: a run was
left going against the live database and starved it for several minutes,
causing production timeouts on unrelated site queries, before it was caught.
Every stage here — collection, each upload sub-stage, dedup, prune — runs as
its own process/transaction, releasing before the next starts. Don't
"optimise" this into one script or transaction.

## A real incident this pipeline caused, and how it's handled now

First real end-to-end run (Cancún, 380 new + 8,797 backfilled rows): the
Market Analysis page 500'd right after stage 2 — a genuine Postgres
`statement timeout`, not hypothetical. Stage 2's full-table `UPDATE`s left
15,349 dead tuples (653MB table growth — Postgres never overwrites a row in
place; every `UPDATE`/`DELETE` leaves the old version behind until vacuumed),
which pushed a query over the tight timeout the site's `anon` role gets on
this small instance. `VACUUM ANALYZE` (36s, non-blocking) fixed it
immediately.

**Fixed, permanently:** every script in this pipeline that does a bulk write
(`reprocess-resale-dedup-and-channel.mjs`, `backfill-resale-original-prices.mjs`,
`prune-dead-listings.mjs`) runs `VACUUM ANALYZE resale_listings` as its own
last step, always.

**Second issue, same run:** stage 3 (`check-resale-currency-integrity.mjs`)
failed on real pre-existing problems unrelated to that upload. Since it's
table-wide and most of the table currently trips it regardless of any given
upload, it's `{ fatal: false }` in the orchestrator — reported loudly, never
blocks stage 4. Stage 4 itself stays fatal.

## What the auction tag depends on

`listing_channel = 'auction_repossession'` (stage 2) is assigned two ways:
(1) the title literally contains "auction"/"remate"/"subasta"/"adjudicaci-",
or (2) the title matches Properstar's auto-generated `"<Type> for sale in
<place>"` template **and** the price scores ≤ -1.6 on a robust z-score
against the median price/m² for that type/city/colonia. New uploads aren't
more likely to get flagged than existing rows — if anything less, since their
price comes from the real Original value rather than the GBP-conversion bug
that produced most of the historical false "suspiciously cheap" signals this
classifier exists to catch.

## Known parse.bot API gaps (ask parse.bot to fix)

| | sale scraper (2,000-row endpoint) | rental scraper `916753d6-…` |
|---|---|---|
| endpoint | `search_homes_filtered` | `search_homes_rental_filtered` |
| cost | 1 credit / 2,000 rows | **10 credits / 1,000 rows** |
| `date_listed` | always empty | populated on every row |
| `property_type` | `Condo` / `Home` | `Apartment` / `House` |
| incremental | none (`updated_since` ignored) | `min_date_listed=YYYY-MM-DD` |

- **parse.bot pricing is set per scraper at creation time and does not change
  on revision.** Confirmed: asking it to "lower the price" to match a cheaper
  sibling changes the description text, never the actual `x-parse-price`. The
  only way to a cheaper price is a fresh scraper cloned from a cheap
  canonical, revised minimally — not a request to reprice an existing one.
- **Sale rows lack `date_listed`** even though Properstar publishes
  `publicationDate`. Only the rental scraper and free scraping return it.
- **No sort control**, so a slice can't be read from both ends. Price banding
  is the only way past the 2,000-retrievable cap.

## Do not

- Point the upload stage at a `*_rent.json` file — it refuses. Rentals go to
  a different table (`rental_listings`, Inmuebles24-sourced, no `source`
  column to tell platforms apart).
- Reach for `scrape_api.py` (Properstar's backend search API, called directly
  for bulk collection) — **documented dead end**. `total` counts are exact
  and free (what `calibrate_bands.py` uses), but pagination is broken: every
  `page`/`skip`/`offset` variant returns the identical first 25 rows. A real
  attempt collected 4/9,213 listings in 376 requests before this was caught.
- Re-run `resale_process_new_listings()` (inside stage 1b) expecting it to
  reprocess existing rows — scoped to `geo_level IS NULL`, only ever touches
  genuinely new rows. By design, not a bug.
- Never let a collection band exceed 2,000 — rows past the cap are silently
  dropped. `fetch_city.py` warns; the fix is re-planning with a lower
  `--target`.
- Skip stage 2 to save time on one small upload, then forget to come back —
  new rows stay invisible to Market Analysis stats and unclassified between
  auction/open-market until it runs. Uploading several cities in one sitting?
  Run each city's 1a/1b/1c, then stage 2 once at the end standalone.

## Why not free scraping (kept for reference, not the default)

`scrape_free.py` scrapes the public site for free when a market fits under
the 2,000-retrievable cap — but it's slow (~3 min/pass, non-deterministic,
needs several merging passes to converge: measured 74% → 93% → 98.6% over
three on Tulum rentals) and doesn't help once a market exceeds the cap in
every type slice, at which point it's parse.bot regardless. That trade only
made sense when parse.bot was expensive; it mostly isn't anymore for sale.
Still a live trade-off for rental specifically (10 credits/call, no
cheap-tier fix) — if rental cost becomes a real constraint, this is where to
look:

- `--type` slices by property type; output paths key on city+market, so
  successive type runs merge into one dataset automatically.
- `--fresh` discards instead of merging.
- Check type-slice totals before assuming a capped-looking market needs
  paying for — the cap is *per search*, so `/rent/apartment` and
  `/rent/house` can each be under 2,000 even when combined they look capped.
- Pagination overlaps, and a whole page can be duplicates while later pages
  still hold new listings — `scrape_free.py` only gives up after 5 barren
  pages in a row. Stopping at the first one silently cost 45% of a rental
  market during development.

## Columns the upload stage does NOT set from source data

`price_per_m2` is a **generated column** (`price_usd / size_m2`) — never
write it directly. `highlights` isn't in the flattened JSON at all — always
`null`. `description` is stored as `{"es": text}` — the fetch endpoint
doesn't return `description_language`, and every sample checked has been
Spanish; the frontend falls back to whichever key is present regardless
(`ResaleDetailBody.tsx`).

## Verify (stage 4) — what it checks, and its one real gap

Calls `resale_market_stats()` (Market Analysis card + "Median price for
similar properties") and `resale_city_counts()` (province-level map rollup),
checks row-level sanity for rows *this run touched* (last 24h — not the
whole city, which would fail on every run given the legacy backlog above),
and — if a dev server is reachable — hits the real
`/api/market-analysis/resale-summary` and `/api/resale-map` routes.

Deliberately does **not** call `resale_neighbourhood_counts()` directly — its
first argument is a denoised eligible-colonia list computed in TypeScript
(`resale_colonia_centroids()` + `isExcludedColoniaName()` in
`resaleQueries.ts`), kept out of SQL so it isn't duplicated a third time;
re-deriving it here would be exactly that duplication. Neighbourhood-level
clustering is verified via the live `/api/resale-map` route instead.

## Credits reference

Cancún sale 9,213 listings = 5 credits (~$0.15). Tulum sale 8,522 listings =
13 credits ($0.39, pre-2,000-row-endpoint figure — likely ~4 now,
unverified). Cancún rental 2,347 = ~24 credits (~$0.72).
