---
name: style_vocabulary
description: Named hex color / border / number-format roles from the tlrm project's own Excel builder (src/lib/cashFlowExcel.ts) and the reference "IRR V1" workbook it was built to match.
---

# Style vocabulary (tlrm house style)

Pulled directly from `tlrm/src/lib/cashFlowExcel.ts` (the actual generator that
produces the site's downloadable equity waterfall workbook) and cross-checked
against `Desktop/Equity Waterfall/IRR/IRR V1 - full - Copy.xlsx`, the
hand-built reference model that section of the code was written to replicate
cell-by-cell. When a model you're reading uses one of these hex values, name
it by role, not just by hex — that's what makes the breakdown legible as a
build spec instead of a color dump.

## Fills

| Hex | Role | Used for |
|---|---|---|
| `FF1F3864` | NAVY | Section banner (darker navy variant) |
| `FF002060` | PARTNERSHIP_TITLE_FILL / DIST_SECTION_FILL | Top-level title banner, deep navy |
| `FF0070C0` | PARTNERSHIP_SECTION_FILL | Sub-banner under the title, mid blue |
| `FFDCE6F1` | SECTION_FILL | Pale blue-gray band behind a section header row |
| `FFD9D9D9` | SECTION_BAND_FILL / REF_SUBHEAD_FILL | Light gray band (tier/hurdle header rows) |
| `FF737373` | REF_BANNER_FILL | Dark gray banner |
| `FFC6EFCE` | conditional-format PASS | Green fill on a check cell that reads TRUE |
| `FFFFC7CE` | conditional-format FAIL | Red fill on a check cell that reads FALSE |

Note: in the actual xlsx, a "gray band" fill is frequently written as a
**theme color** (`theme:0 tint:-0.15`) rather than a literal RGB hex — theme 0
is the workbook's background color and a negative tint darkens it. openpyxl
throws on `.rgb` for a theme color; read `.type`/`.theme`/`.tint` instead (see
`scripts/extract_model.py`'s `color_repr`). Report it as "theme 0, tint -0.15
(~ SECTION_BAND_FILL gray)" rather than guessing a literal hex.

## Font colors

| Hex | Role |
|---|---|
| `FF0000FF` | INPUT_FONT — blue = hardcoded input, per the xlsx skill's own financial-model convention |
| `FF000000` | FORMULA_FONT — black = formula |
| `FF00B050` | CROSS_SHEET_FONT — green = link to another sheet |
| `FFFFFFFF` | white (paired with a dark fill) |
| `FF374151` | SUBSECTION_TEXT — dark slate |
| `FF808080` | muted gray — helper/check-row label |
| `FF6B7280` | muted gray-blue — helper label |
| `FF9CA3AF` | light gray — dotted-divider color |
| `FFB45309` | amber — warning/flag text |
| `FF006100` / `FF9C0006` | dark green / dark red — PASS / FAIL text pair |

## Borders

| Hex | Role |
|---|---|
| `FF000000` (indexed 64 = "automatic") | Solid black — section-header bottom rule |
| `FFB7C3D9` | TOTAL_BORDER / BOTTOM_DIVIDER_BORDER — steel-blue thin top rule above a subtotal |
| `FF9CA3AF` | DOTTED_BORDER — light gray, dotted, used between adjacent period columns in some tables |

Border style values seen: `thin` (the default rule weight throughout),
`dotted` (divider use only). No thick/double/medium borders in this style.

## Number formats

| Format string | Role | Renders as |
|---|---|---|
| `#,##0;[Red](#,##0);-` | CURRENCY_FMT | `1,234` / red `(1,234)` / `-` for zero |
| `#,##0;[Red](#,##0);""` | CURRENCY_FMT_BLANK_ZERO | same, but zero renders blank not `-` |
| `#,##0;[Red](#,##0);#,##0` | CURRENCY_FMT_ZERO_PLAIN | zero renders as `0`, no dash |
| `0.0%` | PERCENT_FMT | one decimal |
| `0.00%` | PERCENT_FMT_2DP / REF_PERCENT_FMT | two decimals |
| `0.00"x"` | MULTIPLE_FMT | equity-multiple style, e.g. `1.43x` |
| `d-mmm-yy` | DATE_FMT | `30-Sep-26` |
| `0" Mths";(0" Mths");0" Mths"` | MONTHS_FMT | |
| `_(* #,##0_);_(* \(#,##0\);_(* "-"_);_(@_)` | REF_ACCOUNTING_FMT | classic accounting column alignment |
| `#,##0;(#,##0);-` | CASH_ON_CASH_CF_FMT | negatives in plain parens, no red |
| custom text formats, e.g. `"LP Check -" 0.0% "IRR"` | check-row labels | turns a bare percentage into a labeled sentence in the cell itself |

## Fonts

Calibri throughout. Section banners run larger (20pt title, 11–14pt
sub-banner); tier/hurdle header rows are 10pt bold italic; ordinary data rows
are 11pt regular; "Ending Balance" / total rows are 11pt **bold**, same size
as the data around them — weight carries the emphasis, not size.

## Layout convention

`LABEL_COL = 3` (column C) / `VALUE_COL = 5` (column E) with a blank gap
column (D) between label and value is the convention for **single-value
assumption tables**. Monthly waterfall grids instead start their period-0
column at **G** (per the reference-exact partnership banner block), with
labels in B/C to their left.
