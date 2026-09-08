---
name: properstar-resale-upload
description: Upload a properstar-scraper JSON (properstar_<city>.json, sale only) into resale_listings on Supabase and verify the live site — one command covers price import, dedup/channel classification, and error-checking Resale Properties + Market Analysis. Use after the properstar-listings skill has collected a city, or when the user asks to "upload", "push", "add to the database/website", or "sync" Cancún/Tulum/etc. property data.
---

# Properstar resale upload + verify

Takes the JSON `properstar-listings` collected (`properstar-scraper/properstar_<city>.json`),
gets it onto the live site, reclassifies the table, and checks nothing broke — **one
command**, not four manual steps. **Sale only** — resale_listings is a sale-only table;
rentals live in a different table this never touches.

All scripts live in the sibling `tlrm` repo, not this one (paths below are relative to
`riviera-maya-map-poc`).

## Run it

```bash
cd ../tlrm
node upload-and-verify-resale-city.mjs \
  ../riviera-maya-map-poc/properstar-scraper/properstar_cancun.json \
  "Cancún" "Quintana Roo"
```

City and province must match the site's existing tag for that city exactly (`"Cancún"`
with the accent, not `"Cancun"`) — check first if unsure:

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

That one command runs six stages, **each its own process** (never bundled into one script
or one transaction — see "Why separate processes" below), stopping immediately if a fatal
stage fails:

| # | Script | What it does | Typical time |
|---|---|---|---|
| 1a | `import-resale-from-properstar-json.mjs` (dry run) | Prints insert count + skip-reason breakdown | seconds |
| 1b | same, `--apply` | Inserts **new** rows + fills `nb_colonia`/`geo_level`/`quality_flags` | seconds |
| 1c | `backfill-resale-original-prices.mjs --apply` | Fixes **existing** GBP-tagged rows using this same fresh JSON | seconds–minutes |
| 2 | `reprocess-resale-dedup-and-channel.mjs` | Full-table dedup + `listing_channel` classification + VACUUM ANALYZE | **~7 min** |
| 3 | `check-resale-currency-integrity.mjs` | Table-wide currency/price sanity (informational, non-fatal) | seconds |
| 4 | `verify-resale-site.mjs <city>` | Hits the actual DB functions + API routes Resale Properties and Market Analysis use | seconds |

**Stage 1c is the one that's easy to forget, and forgetting it is the whole reason it's
now automatic.** 1a/1b only ever touch listings that aren't in the table yet — re-scraping
a whole city and running just 1a/1b fixes *nothing* for the ~9,000 listings already there,
even though the fresh JSON has their correct price sitting right in it. First real run of
this pipeline (Cancún) shipped without 1c and left 9,158 existing listings on the old GBP
price; 1c alone then fixed 8,797 of them in one pass. Don't skip it, and don't add a flag
to skip it — there's no version of "upload but don't fix what's already there" worth having.

**Not run automatically:** `prune-dead-listings.mjs` (removes listings absent from the
fresh scrape, or with no price at all — see its own section below). That's a `DELETE`, and
deciding whether "not in this scrape" really means "gone" is a judgment call the first
time you run it against a new city — so it stays a separate, explicit command, printed at
the end of every orchestrator run for convenience.

You can also run any stage on its own — see each script's own header comment. Stage 2 in
particular is worth running standalone if you've just done several uploads in a row and
want to reclassify once at the end rather than once per city (see its cost below).

## The price rule — the reason this pipeline exists

The JSON carries **two price pairs** per listing. Stage 1 uses only one of them:

| field | what it is | used? |
|---|---|---|
| `price` / `price_amount` / `price_currency` | Properstar's **GBP display conversion**, drifts day to day independent of the real price | **never** |
| `original_price_currency` / `original_price_amount` | the advertiser's **real listed price**, read from the source's own `type:"Original"` entry | **always** |

The import script enforces this itself — reads only `original_*`, unconditionally, and
skips a listing rather than falling back to the GBP pair if `original_*` is null (price
hidden). If a listing's Original currency genuinely is GBP, that's used normally — the
rule is *never treat the display conversion as the price*, not *never allow GBP*.

`price_usd` is computed from a **live exchange rate fetched at import time**
(frankfurter.app, same source/fallback table as every other resale import script) — never
from parse.bot's own converted `price_amount`. This is the exact bug class the 2026-09-06
GBP-price incident was about (see `properstar-scraper/HANDOVER-parsebot.md` and the
`tlrm-resale-currency-check` skill) — do not weaken this to "fall back to GBP if Original
is missing" even if it recovers more rows; those rows are exactly the ones the incident
was about.

**93% of the table predates this fix** and still carries the old GBP display value in
`price_currency`. The site's "Originally listed in {currency}" note
(`ResaleDetailBody.tsx`) is gated to never show for `price_currency = 'GBP'` for exactly
this reason — don't remove that gate without backfilling those rows first, or the site
will assert a false currency on ~80,000 listings.

## Why separate processes, not one script

`reprocess-resale-dedup-and-channel.mjs` (stage 2) is a **full-table** operation by
design — dedup ranking and neighbourhood price norms are both relative to the whole
table, not just new rows, so there's no way to scope it to "just this upload." An earlier
attempt to bundle the equivalent SQL into one auto-triggered function was tried and
caused a real incident: a run was left going against the live database and starved it for
several minutes, causing production timeouts on unrelated site queries, before it was
caught (see the script's own header). What fixed it was keeping every stage a separate
top-level statement/process, each releasing before the next starts — the orchestrator
script mirrors that at the pipeline level with `spawnSync`, one child process per stage.
Do not "optimise" this into a single script or transaction.

## Why stage 2 takes ~7 minutes

Measured directly (`EXPLAIN`, not estimated) against the live table: two of stage 2's nine
SQL statements account for 88% of the time.

- **Dedup (~217s):** three separate duplicate-detection rules, each a full-table
  `Incremental Sort` + window function over all ~86,000 rows, then a single `UPDATE`
  rewriting every row — not just changed ones, because a newly-arrived row can supersede
  an *existing* row's canonical status, so the whole table has to be re-ranked every time.
- **Channel classification (~153s):** a four-level hierarchy of medians (colonia → city+type
  → type → global, each blended by sample size) computed fresh, then joined onto every
  qualifying listing to score it against the right level of "what's normal here."

Both are inherent to the full-table design above, not something to optimise away without
changing what the pipeline does. Running on Supabase's small instance makes this worse
than it would be on a bigger one — a real lever if this becomes a bottleneck, not
something to fix in code.

## A real incident this pipeline caused, and how it's now handled

First real end-to-end run (2026-09-08, Cancún, 380 rows): stages 1–2 succeeded, but the
**Market Analysis page 500'd immediately afterward** — a genuine `statement timeout`
(Postgres error 57014) live in the browser, not a hypothetical. Root cause: stage 2's
three full-table `UPDATE`s (dedup ranking + two classification passes) left the table
with 15,349 dead tuples (MVCC — an `UPDATE` writes a new row version even when the value
didn't change) and grew it to 653MB. That bloat pushed at least one query over the tight
`statement_timeout` the site's `anon` role gets on this small instance (see
`reference_tlrm_anon_statement_timeout`) — a pre-existing fragility that stage 2's own
writes made worse. A plain `VACUUM ANALYZE` (36s, non-blocking) fixed it immediately,
confirmed live by reloading the page.

**Fix, now permanent:** `reprocess-resale-dedup-and-channel.mjs` runs `VACUUM ANALYZE
resale_listings` as its own last step, always — not optional, not something to skip to
save a few seconds. If stage 2 is ever run standalone (not through the orchestrator),
this still happens automatically.

**Second issue found the same run:** stage 3 (`check-resale-currency-integrity.mjs`)
failed — correctly, on real pre-existing problems (a stale-rate EUR row from Tulum, 11
corrupted size-less listings from an August scrape, a duplicate-price cluster count one
over its baseline). All three predate this upload and are separately tracked; none were
caused by the 380 new rows. But since that check is table-wide and ~93% of the table
currently trips it regardless of what any given upload does, treating it as fatal would
mean the orchestrator could **never** reach stage 4 — the one that actually answers "did
this run break anything" — until that whole separate backlog is cleared.

**Fix:** stage 3 is `{ fatal: false }` in the orchestrator. It still runs, still prints
its failure loudly (real, worth fixing on its own), but stage 4 runs regardless, and the
final summary says so explicitly (`STAGES 1, 2 AND 4 PASSED ... stage 3 ... failed`) with
a non-zero exit code so a caller can still tell. Stage 4 itself stays fatal — a failure
there is the real, immediate, this-upload-specific signal.

`verify-resale-site.mjs`'s row-level sanity section is scoped to rows fetched in the last
24 hours for exactly the same reason — checking the whole city for legacy GBP tags would
fail on every run regardless of what it did, since 95%+ of most cities predate the fix.
The whole-city legacy count is still printed, as `[INFO]`, never as a failure.

## What the auction tag depends on — so you know what NOT to expect from new uploads

`listing_channel = 'auction_repossession'` is assigned by stage 2, two ways: (1) the
title literally contains "auction"/"remate"/"subasta"/"adjudicaci-", or (2) the title
matches Properstar's auto-generated `"<Type> for sale in <place>"` template **and** the
price scores ≤ -1.6 on a robust z-score against the median price/m² for that type/city/
colonia. New uploads aren't more or less likely to get flagged than existing rows by
virtue of being new — if anything less likely, since their price comes from the real
Original value rather than the GBP-conversion bug that produced most of the historical
false "suspiciously cheap" signals this classifier exists to catch.

## What verify (stage 4) actually checks, and its one real gap

`verify-resale-site.mjs` calls `resale_market_stats()` (powers the Market Analysis Resale
card and the listing page's "Median price for similar properties") and
`resale_city_counts()` (the province-level map rollup), checks row-level sanity for the
city (no bad prices, no leftover GBP tags, everything geocoded), and — if a dev server is
reachable at `--base-url` (default `http://localhost:3000`) — hits the real
`/api/market-analysis/resale-summary` and `/api/resale-map` routes.

It deliberately does **not** call `resale_neighbourhood_counts()` directly: that RPC's
first argument is a denoised eligible-colonia list computed in TypeScript
(`resale_colonia_centroids()` + `isExcludedColoniaName()` in `resaleQueries.ts`),
deliberately kept out of SQL so it isn't duplicated a third time — re-deriving it in a
Node script would be exactly that duplication. Neighbourhood-level clustering is verified
via the live `/api/resale-map` route instead, which exercises the real TS+SQL path
together. If no dev server is running, that route check is skipped and reported as such —
it does not count as a pass.

`listing_channel IS NULL` on freshly-uploaded rows is reported as a **warning**, not a
failure, immediately after upload — it's expected until stage 2 runs, and stage 2 always
runs before stage 4 in the pipeline, so seeing it there means something is actually wrong,
not just pending.

## Removing dead listings — separate, manual, run after the pipeline

```bash
node prune-dead-listings.mjs "Cancún" \
  ../riviera-maya-map-poc/properstar-scraper/properstar_cancun.json
```

Dry run by default (`--apply` to actually delete). Removes three groups, all
scoped to one city:

1. **`price_currency = 'GBP'`** — rows `scrape_free.py` could never resolve an Original
   price for (distinct from the historical bulk-GBP debt stage 1c fixes — these are ones
   the fresh pull *also* couldn't fix).
2. **`price_currency IS NULL`** — never had a price recorded at all.
3. **Not present in the fresh pull**, despite being an in-scope type — likely delisted.

**Before trusting group 1 on a city you haven't pruned before**, spot-check a handful
directly against Properstar (fetch `https://www.properstar.co.uk/listing/<id>` — see
`probe_display.py`'s pattern in `properstar-scraper/`, or `state.entities.listing[id]`
in the page's `__INITIAL_STATE__`). On Cancún, 10/10 sampled GBP rows came back HTTP 404
— genuinely delisted, not just price-hidden — which is what justified deleting all 361.
That confirmed rate is evidence for Cancún, not a law for every city; if a new city's
sample comes back mostly HTTP 200 (still live, price genuinely just hidden/POA), don't
delete that city's group 1 — leave those rows alone rather than deleting real listings.

Backs up every deleted row to a local JSON file first, runs `VACUUM ANALYZE` after —
same reasoning as stage 2's, just smaller.

## Columns this does NOT set from source data

`price_per_m2` is a **generated column** (`price_usd / size_m2`) — never write it directly.
`highlights` isn't in the flattened JSON at all (the fetch endpoints this reads don't
return it) — always inserted `null`. `description` is stored as `{"es": text}` — the
fetch endpoint doesn't return `description_language`, and every sample checked has been
Spanish, so `"es"` is used rather than an honestly-unknown key; the frontend falls back to
whichever key is present regardless (`ResaleDetailBody.tsx`).

## Don't

- Point this at a `*_rent.json` file — the import script refuses, but don't try to work
  around that. Rentals go to a different table (`rental_listings`), currently
  Inmuebles24-sourced with no `source` column to tell platforms apart.
- Re-run `resale_process_new_listings()` (called inside stage 1b) expecting it to
  reprocess existing rows — it's scoped to `geo_level IS NULL`, so it only ever touches
  genuinely new rows. That's by design (idempotent, cheap to call after every import), not
  a bug.
- Skip stage 2 to save time on a single small upload, then forget to come back to it —
  new rows stay invisible to Market Analysis stats (not wrong, just uncounted) and
  unclassified between auction/open-market until it runs. If uploading several cities in
  one sitting, it's fine to run each city's stages 1a/1b, then run stage 2 once at the end
  standalone rather than once per city.
