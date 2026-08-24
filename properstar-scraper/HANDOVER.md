# Properstar Multi-City Collection — Handover

**Date:** 2026-08-23
**Status:** COMPLETE. All 9 cities, both markets, 89,650 listings total. Final balance: 190 credits.
Everything below this line describes the incident and is kept for reference — the data gaps it
describes are all closed. Mexico City buy: 46,212/46,212 (100%, verified against disk). Mexico
City rent: 4,054 (3,238 paid apartment + 816 free house, merged). No outstanding paid or free work
remains from this batch.

## Current data state (verified against disk, not from memory)

| City | Market | Rows | Completeness | Notes |
|---|---|---:|---:|---|
| Tulum | buy | 8,522 | ~100% | done, prior session |
| Tulum | rent | 1,452 | 98.6% | done, prior session |
| Playa del Carmen | buy | 12,096 | 100.0% | done |
| Playa del Carmen | rent | 1,140 | 86.3% | one more free pass would help |
| Cancún | buy | 9,168 | 100.0% | done |
| Cancún | rent | 2,295 | 97.8% | done (free, type-split) |
| Puerto Morelos | buy | 883 | 89.3% | one more free pass would help |
| Puerto Morelos | rent | 54 | 100% | done |
| Puerto Vallarta | buy | 1,194 | 80.0% | one more free pass would help |
| Puerto Vallarta | rent | 107 | 100% | done |
| Los Cabos | buy | 1,579 | 83.9% | one more free pass would help |
| Los Cabos | rent | 260 | 98.9% | effectively done |
| Sayulita | buy | 130 | 97.7% | effectively done |
| Sayulita | rent | 0 | — | genuinely no rentals there |
| La Paz | buy | 487 | 87.7% | one more free pass would help |
| La Paz | rent | 17 | 100% | done |
| **Mexico City** | **buy** | **1,000** | **2.2%** | **incomplete — see incident below** |
| Mexico City | rent | 3,238 | 78.3% (apartment only) | house-type (~899, free) never run |

Free re-pass candidates (all $0, just re-run `scrape_free.py` with the same args — it merges): Puerto Morelos, Puerto Vallarta, Los Cabos, La Paz buy, Playa del Carmen rent.

## The Mexico City buy incident — why it's stuck at 1,000/46,212

1. First attempt: old code aborted after 1 credit when the cheapest apartment band (`apa <33k`) came back 5,854 real listings against a ~938 estimate — the old logic assumed that mismatch applied uniformly to every remaining band and gave up rather than risk losing rows.
2. Code was fixed (see below) and the plan re-run. It reached **43,787/46,212 (94.7%)** at **81 credits spent**, correctly recursively splitting both `apa <33k` and an even worse case, `hou <39k` (4,691 vs ~895 estimate, split 4 levels deep).
3. It was killed mid-run because a monitoring blind spot (the command was piped through `grep`, which buffers when writing to a file) made a healthy, correctly-working process look silent for an extended period, causing a false alarm.
4. At the time, **no incremental checkpointing existed** — `write_outputs()` only ran at the very end of a plan. So all 42,787 rows gained in that run were never written to disk. The 81 credits were genuinely spent and are gone; the data they paid for is not recoverable, only re-fetchable.
5. Checkpointing has since been added (below), so this specific failure mode cannot recur.

## Code changes made this session (all in `properstar-scraper/fetch_city.py` unless noted)

1. **Retry-with-backoff on 502/500.** Transient upstream errors get up to 2 retries with backoff before being treated as a real failure. Previously a single 502 permanently dropped a slice.
2. **Adaptive price-band splitting**, replacing the old "calibrate off one slice, abort the whole city if projected mismatch is too high" logic. When a slice's real `total_results` exceeds the 2,000 cap, it's bisected by price and both halves are requeued — recursive, capped at depth 5 per branch. Only the genuinely oversized bands cost extra calls; everything else runs as planned.
3. **Merge-by-default**, with a `--fresh` flag to opt out — matches `scrape_free.py`'s existing convention. Previously `fetch_city.py` overwrote its output unconditionally, which would have destroyed already-collected data on any retry-only or free+paid mixed run.
4. **Incremental checkpointing.** `write_outputs()` now runs after every slice and every page, not just once at the end. This is the direct fix for the Mexico City incident — it did not exist yet when that run was killed.
5. **`plan_city.py --types` filter** — a plan can now be restricted to just the property type(s) that actually need paid slicing, so a type that's already free-eligible in the same city doesn't get billed alongside one that isn't.

All changes are syntax-verified (`py_compile`) and unit-spot-checked (`bisect_slice` against open-ended-low, open-ended-high, bounded, and degenerate cases). The adaptive splitter has one real production run behind it (this session's Mexico City retry) and it worked correctly, including the multi-level recursive case.

## Credits

- Verified real balance before this session's paid work: **429** (live API check).
- Confirmed spend this session: first batch 53 + retries 17 + Mexico City buy retry 81 = **151 credits**.
- Implied balance: **~278**, which matches what you saw on your own dashboard ("280") within a couple credits — cross-checked, not just computed.
- **API key was then revoked.** No further calls possible until a new key is provided. Do not trust any balance number without a fresh live check once a new key exists — that's exactly what went wrong today.

## Next steps, in order, once a new key exists

1. One minimal real call (not a 404 — those don't carry credit headers) to confirm live balance before doing anything else.
2. Re-run Mexico City buy from scratch: `python fetch_city.py --plan plans/mexico-city-buy.json`. Expect a similar cost to last time (~80-90 credits) since none of the prior progress survived. Checkpointing means it's now safe to interrupt without losing paid-for data.
3. Run the Mexico City rent house-type free merge: `python scrape_free.py --city mexico-city --transaction rent --type house` (0 credits, ~899 expected).
4. Optional: free re-passes on the cities listed above under "Free re-pass candidates."
5. **Supabase:** table `properstar_listings` does not exist yet — SQL to create it was given earlier in this conversation (buy+rent in one table, `transaction` column, `id` as primary key for global dedup, RLS policy for the publishable key). Needs to be run in the Supabase dashboard before any upload.
6. No ingestion script has been written yet for `properstar_listings` — needs building once the table exists and Mexico City is complete.

## Things not to touch / get wrong again

- **`rental_listings`** is a real, live Supabase table with 1,115 Inmuebles24 rows already in it. Not Properstar data. Do not merge Properstar rows into it — no `source` column exists to distinguish platforms, and IDs could collide.
- **Two separate parse.bot scrapers, not one:** sale is `9800404f-...` (`search_homes_filtered`, 1 credit/call), rental is `916753d6-...` (`search_homes_rental_filtered`, 10 credits/call). Different pricing, different field mappings. Never reference `search_homes_filtered`'s price in outward-facing messages to parse.bot (per earlier explicit instruction — risks them "fixing" it to match the rental price).
- **`SUPABASE_KEY` is a publishable key** — data-plane only, cannot run `CREATE TABLE` or any DDL.
- **Never pipe a long-running paid background command through `grep` again.** That's the actual root cause of today's crisis — not the adaptive splitter, not the spend itself. If output needs filtering, filter at the source.
