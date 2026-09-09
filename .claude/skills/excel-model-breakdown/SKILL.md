---
name: excel-model-breakdown
description: Read an Excel financial model tab (equity waterfall, cash flow, returns) and produce a rigorous, section-by-section breakdown — every formula as an Excel-formula/plain-English pair, the tier/section structure, and the exact visual spec (font, fill hex, border style+color, number format) for each row — at the level of detail Riki uses when auditing or documenting a model. Use when asked to explain, break down, document, or audit an Excel model/tab, or to prep a model for replication as code (e.g. into tlrm's cashFlowExcel.ts).
---

# Excel model breakdown

Two things this produces, always together — never formulas without formatting, never formatting without formulas:

1. **Formula breakdown** — every formula as a pair: the Excel formula, then a
   plain-English translation with the cell references swapped for the row
   labels they represent.
2. **Format spec** — font (name/size/bold/italic/color), fill, border
   (per-side style + color), number format — named by role against
   [reference/style_vocabulary.md](reference/style_vocabulary.md), not just
   dumped as raw hex.

Both together are what make the output usable as a build spec, not just a
description — this is literally how `tlrm/src/lib/cashFlowExcel.ts`'s
`usesReferenceCascade` branch got written: someone (Riki) described a
reference workbook to this level of detail, and it got implemented cell-by-
cell from that description. Producing that same level of spec, reliably, is
the point of this skill.

## Step 1 — Extract raw formulas + styles

Don't hand-read cells one at a time. Use the extraction script — it resolves
theme colors correctly (openpyxl throws on `.rgb` for a theme-indexed color;
the script handles `.type`/`.theme`/`.tint` instead) and cross-references
known hex values against their named role.

```bash
python .claude/skills/excel-model-breakdown/scripts/extract_model.py "<path>.xlsx" "<Sheet Name>" --find-hurdle-rows
```

Run this first, always — it scans column B/C for bold+filled rows, which in
every model seen so far marks section/tier headers (`Preferred Return`,
`Tier 1`, `Hurdle 2`, …). That gives you the row map before pulling detail.

Then pull formulas + styles for each section, across a few representative
columns (first data column, second data column, and — critically — a column
from **late in the schedule**, near or after any reversion/sale event, so you
can see whether balances actually clear rather than assuming from period 1–2
alone):

```bash
python .claude/skills/excel-model-breakdown/scripts/extract_model.py "<path>.xlsx" "<Sheet Name>" --rows 64:81 --cols B,C,D,G,H
```

To find the reversion/exit column and confirm balances clear by the end of
the schedule (don't skip this — a tier that never zeroes out by the final
period is a real finding, not a formatting detail), open a second Python pass
with `data_only=True` and scan the reversion-cash-flow row for its nonzero
column, then check the tier's Ending Balance rows from there to the last
column. This is exactly how the last EMx-hurdle discrepancy in this project
got resolved — it wasn't a formula bug, it was a check-row cell referencing
the wrong hurdle cell, findable only by tracing real values through to the
end of the schedule, not by reading the first few columns.

## Step 1b — Verifying a generated file against a reference file exactly

When the task is "does the website's output look/function the same as this
reference workbook" (not just "explain this model"), don't eyeball two dumps
side by side — that misses things (alignment, borders, a column that moved).
Use `--diff-against` instead:

```bash
python .claude/skills/excel-model-breakdown/scripts/extract_model.py \
  "<reference>.xlsx" "<Sheet>" --rows 60:130 --cols B,C,D,E,F,G,H,I,J \
  --diff-against "<generated-file-to-check>.xlsx" --diff-sheet "<Sheet>"
```

Reads the reference file as ground truth, compares every cell in the range
against the checked file cell-by-cell (value/formula, font, fill, border,
alignment, number format — everything `describe_cell` prints, plus
alignment, which is easy to miss by eye), and prints ONLY mismatches with
the exact axis that differs. It exits 0 on a clean match, 1 otherwise, so
it's usable as a loop-until-clean check: fix the generator code for what it
reports, regenerate, re-diff, repeat.

Two normalizations are already built in so the tool doesn't cry wolf:
- A same-row range (`G73:EI73`) collapses both endpoints before comparing,
  since its actual end column is deal-length-dependent (hold period,
  periodicity) and will never match between two arbitrarily-configured test
  exports — that's not a real structural difference.
- A cell with no font explicitly set reads back as `None` from openpyxl
  even though it inherits the workbook's real default (Calibri 11 across
  this whole model family) — normalized to that default so it doesn't read
  as a false mismatch against a cell that sets it explicitly.
- Theme-based colors (`theme:0 tint:-0.5`) and their literal-hex visual
  equivalent (`FF808080`) are NOT normalized to each other, since they can
  drift apart depending on the workbook's actual theme palette — these
  still show up as reported mismatches. Treat a `THEME` vs literal-hex
  mismatch as almost always cosmetic noise (verify by eye once, don't chase
  it every round), but don't blanket-suppress it in the tool itself.

If you don't have a way to generate a fresh export to check (e.g. no local
dev server), ask for one, or use the API route/generator function directly
(`curl` against a running `next dev` server's export endpoint is usually
fastest — see cashFlowExcel.ts's own `buildCashFlowWorkbook` entry point
and its API route for the request shape).

**A mismatch is not automatically a bug to fix by copying the reference
file's cell.** Read what actually changed before reacting - twice in one
session, a "the generator doesn't match" mismatch turned out to be the
*reference file itself* having an unfixed error (a stale cross-tier cell
reference, a distribution formula missing a term) that the generator had
already independently gotten right. Replicating that would have "matched"
the file while reintroducing a real financial-calculation bug. When a
mismatch traces back to something in the reference file that looks like an
error rather than a deliberate choice, say so explicitly and ask before
either changing the generator to match it or leaving the generator as the
(correct) source of truth.

## Step 2 — Write the breakdown, in this structure

Match this shape regardless of how many tiers the model has:

### Assumptions area
Promote structure method / mode switch, equity contribution split, the
hurdle grid (one row per tier: IRR hurdle / EMx hurdle / promote % / GP
catch-up formula / LP % / plain-English band description), sponsor fees.
Note any formula that derives a label or percentage from a dropdown cell
(`=IF(D7="IRR",...)`) — these drive presentation only; confirm whether they
also gate which formulas actually run, or are purely cosmetic.

### First hurdle tier (Preferred Return / Hurdle 1)
Walk every row top to bottom as a numbered formula pair:
```
1. <Row label>
   a. <Excel formula, exact, e.g. =MAX(0,G65+G67+G69-G70)>
   b. <Plain English, e.g. =MAX(0, Beginning Balance (IRR) + Required
      Return by LP (IRR) + Contributions from LP - Distributions to LP)>
```
Then the format spec for that row's data cells and its header/label cell,
using the vocabulary doc's role names. End the section with the tier's own
check row (if present) and confirm what it actually compares — check rows
are exactly where the two bug patterns below hide.

### Tier 1 (second hurdle) — and note what's genuinely new
Don't re-derive the whole skeleton from scratch — say explicitly which rows
are structurally identical to the first tier (same formula shape, own
hurdle cells) and call out only the real additions: a `Prior Distributions
from LP` row (summing every earlier tier's distribution that period, since
it nets against this tier's target too), a distribution cap sourced from the
prior tier's `Remaining Cash Flow` instead of gross cash, and any asymmetry
worth flagging (e.g. a missing `MAX(0, …)` floor present on one balance row
but not its sibling).

### How further tiers follow
One short paragraph, not a repeat of the full walkthrough: each additional
tier repeats Tier 1's shape exactly — own hurdle row, `Prior Distributions`
extended to sum every tier before it, distribution cap sourced from the
immediately preceding tier's `Remaining Cash Flow`. Say this once, plainly,
rather than re-listing 15 identical-shaped rows three more times.

### Final tier
Usually no hurdle, no balance tracking — a straight residual split of
whatever `Remaining Cash Flow` survived every prior tier, at the final
promote percentages. Confirm there's no hurdle test here (a blank hurdle
cell, "N/A", or similar) before describing it as a plain split.

## Step 3 — Actively hunt for these two bug patterns while writing it

Don't just transcribe formulas — audit them as you go, the same way you would
if asked directly "why doesn't this add up." Two patterns have shown up
repeatedly in this exact model family and are worth checking every time:

1. **Copy-paste absolute-reference drift in check rows.** A check cell copied
   across tiers/columns (`=ROUND(F73,4)=ROUND($D$64,4)`) that should track
   its *own* tier's hurdle cell but still points at the first tier's
   (`$D$64`/`$E$64`) instead of its own (`$D$83`/`$E$83`, `$D$103`/`$E$103`,
   …). These are silent — they don't feed the waterfall math, so the model's
   real numbers are fine, but the check display lies. Grep every check row's
   formula against the hurdle-row cells it's *supposed* to reference (same
   row block, i.e. row 83's checks should reference row 83's own `D83`/`E83`
   or whatever the tier's local hurdle cells are — not another tier's).
2. **Timing lag in a decomposed "required return" row.** When a return/bonus
   row is split out for display (e.g. `Required Return by LP (EMx)` broken
   out from an inline `Contributions × hurdle` term), confirm it's driven by
   the **current period's** own inputs, not a prior column's — a lagged
   reference (`=F69*$hurdle-F69` instead of `=G69*($hurdle-1)`) produces a
   value that looks plausible in isolation but is one period out of step with
   the balance it's meant to explain, and usually turns out to be
   disconnected from the actual balance formula entirely (cosmetic only).

Report anything you find plainly, with the exact cell references and the
fix — the way you'd report any other finding — rather than folding it
quietly into the "normal" breakdown.

## Step 4 — If this is prep for replicating the model as code

Say so explicitly in the output, and point at
`tlrm/src/lib/cashFlowExcel.ts`'s `usesReferenceCascade` branch as the
precedent — that section was built exactly this way, from a spec at this
level of detail, cell-by-cell. But flag the gap plainly: a spec this
thorough is enough to *write* the generator code, not enough to *trust* it.
Before treating generated code as correct, run it against the source
workbook's own real numbers (extract a handful of cached values from the
original file the same way this skill's script does with `data_only=True`)
and diff them against what the generated code produces — an XIRR
implementation, a day-count convention, or a `MAX(0, …)` floor is exactly
the kind of thing that translates almost-but-not-quite-right and won't show
up any other way.
