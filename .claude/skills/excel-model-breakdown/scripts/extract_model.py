"""
Dump formulas + exact formatting for a row range of an Excel sheet, in a form
suited to writing a formula-pair / structure / formatting breakdown of a
financial model (waterfall tabs, equity returns tabs, etc).

Usage:
    python extract_model.py "<path>.xlsx" "<Sheet Name>" --rows 64:81 --cols B,C,D,E,F,G,H
    python extract_model.py "<path>.xlsx" "<Sheet Name>" --rows 1:120          # labels only, no --cols
    python extract_model.py "<path>.xlsx" "<Sheet Name>" --find-hurdle-rows   # locate every section-header-styled row

Two openpyxl passes are unavoidable here: data_only=True gives cached values
(needed to sanity-check a formula's real output) but destroys the formula
strings; the default load keeps formulas but every value reads back as the
formula text. Never save from either loaded object.
"""
import argparse
import re
import sys
import openpyxl
from openpyxl.utils import column_index_from_string, get_column_letter

_SAME_ROW_RANGE = re.compile(r"\$?([A-Z]{1,3})\$?(\d+):\$?([A-Z]{1,3})\$?\2\b")


def normalize_formula(value):
    """A same-row range like G73:EI73 (or $G$29:$EI$29) is almost always "period 0 through the
    last period" - its end column legitimately varies with deal length (hold period, periodicity)
    and isn't a real structural difference between two files built from different test deals.
    Collapse both ends to a placeholder so --diff-against compares formula SHAPE, not a
    deal-length artifact that will never match between two arbitrarily-configured exports."""
    if not isinstance(value, str) or not value.startswith("="):
        return value
    return _SAME_ROW_RANGE.sub(r"\1\2:LASTCOL\2", value)

# Known style constants, pulled directly from the tlrm codebase's own Excel
# builder (src/lib/cashFlowExcel.ts) plus the "reference-exact" partnership
# banner block (usesReferenceCascade). Used to name a color/border by its role
# instead of just printing a hex code, and to flag anything that doesn't match
# any known role (which usually means either a new convention or a mistake).
KNOWN_FILLS = {
    "FF1F3864": "NAVY (section banner, darker variant)",
    "FF002060": "PARTNERSHIP_TITLE_FILL / DIST_SECTION_FILL (top banner, deep navy)",
    "FF0070C0": "PARTNERSHIP_SECTION_FILL (sub-banner, mid blue)",
    "FFDCE6F1": "SECTION_FILL (pale blue-gray section band)",
    "FFD9D9D9": "SECTION_BAND_FILL / REF_SUBHEAD_FILL (light gray band)",
    "FF737373": "REF_BANNER_FILL (dark gray banner)",
    "FFC6EFCE": "conditional-format PASS fill (green)",
    "FFFFC7CE": "conditional-format FAIL fill (red)",
}
KNOWN_FONT_COLORS = {
    "FF0000FF": "INPUT_FONT — blue = hardcoded input",
    "FF000000": "FORMULA_FONT — black = formula",
    "FF00B050": "CROSS_SHEET_FONT — green = link to another sheet",
    "FFFFFFFF": "white (on a dark fill)",
    "FF374151": "SUBSECTION_TEXT (dark slate)",
    "FF808080": "muted gray (helper/check-row label)",
    "FF6B7280": "muted gray-blue (helper label)",
    "FF9CA3AF": "light gray (dotted-divider color)",
    "FFB45309": "amber (warning/flag text)",
    "FF006100": "dark green (PASS text)",
    "FF9C0006": "dark red (FAIL text)",
}
KNOWN_BORDER_COLORS = {
    "FF000000": "solid black",
    "FFB7C3D9": "TOTAL_BORDER / BOTTOM_DIVIDER_BORDER (steel-blue, subtotal rule)",
    "FF9CA3AF": "DOTTED_BORDER (light gray, dotted)",
}
KNOWN_NUMFMTS = {
    "#,##0;[Red](#,##0);-": "CURRENCY_FMT",
    '#,##0;[Red](#,##0);""': "CURRENCY_FMT_BLANK_ZERO",
    "#,##0;[Red](#,##0);#,##0": "CURRENCY_FMT_ZERO_PLAIN",
    "0.0%": "PERCENT_FMT",
    "0.00%": "PERCENT_FMT_2DP / REF_PERCENT_FMT",
    '0.00"x"': "MULTIPLE_FMT",
    "d-mmm-yy": "DATE_FMT",
    '_(* #,##0_);_(* \\(#,##0\\);_(* "-"_);_(@_)': "REF_ACCOUNTING_FMT",
    "#,##0;(#,##0);-": "CASH_ON_CASH_CF_FMT",
}


def color_repr(c, known_map):
    if c is None:
        return "none"
    try:
        if c.type == "rgb":
            hexval = c.rgb
            role = known_map.get(hexval)
            return f"{hexval}" + (f" [{role}]" if role else " [unrecognized — no matching known role]")
        elif c.type == "theme":
            return f"theme:{c.theme} tint:{round(c.tint, 4)}"
        elif c.type == "indexed":
            # 64 is Excel's "automatic" (usually black) indexed color
            return "automatic (black)" if c.indexed == 64 else f"indexed:{c.indexed}"
        return str(c)
    except Exception as e:
        return f"<unreadable: {e}>"


def numfmt_repr(fmt):
    role = KNOWN_NUMFMTS.get(fmt)
    return f'"{fmt}"' + (f" [{role}]" if role else "")


def describe_cell(cell):
    f = cell.font
    fill = cell.fill
    b = cell.border
    a = cell.alignment

    parts = [f"font={f.name} {f.sz}pt" + (" BOLD" if f.b else "") + (" ITALIC" if f.i else "")]
    parts.append(f"color={color_repr(f.color, KNOWN_FONT_COLORS)}")
    if fill.fill_type:
        parts.append(f"fill={fill.fill_type}:{color_repr(fill.fgColor, KNOWN_FILLS)}")
    borders = []
    for side_name, side in (("top", b.top), ("bottom", b.bottom), ("left", b.left), ("right", b.right)):
        if side and side.style:
            borders.append(f"{side_name}={side.style}/{color_repr(side.color, KNOWN_BORDER_COLORS)}")
    if borders:
        parts.append("border[" + ", ".join(borders) + "]")
    # Alignment is easy to miss by eye but is exactly the kind of thing a "looks the same"
    # comparison needs explicit — default (None) means Excel's type-based default (text=left,
    # numbers=right), which is NOT the same as an explicit 'general'/'left'/'center'.
    align_bits = []
    if a.horizontal:
        align_bits.append(f"h={a.horizontal}")
    if a.vertical:
        align_bits.append(f"v={a.vertical}")
    parts.append("align=" + (",".join(align_bits) if align_bits else "default"))
    parts.append(f"numfmt={numfmt_repr(cell.number_format)}")
    return " | ".join(parts)


def safe_color_key(c):
    """A comparable key for a Color object that never raises (openpyxl's .rgb throws on a
    theme/indexed color instead of returning None) and treats "automatic black" (indexed 64,
    Excel's default when no color is set) as equal to an explicit FF000000 - both render
    identically, so a diff between them is noise, not a real style mismatch."""
    if c is None:
        return None
    try:
        if c.type == "rgb":
            rgb = c.rgb
            return "BLACK" if rgb in ("FF000000", "00000000") else rgb
        if c.type == "theme":
            return ("THEME", c.theme, round(c.tint, 4) if c.tint else 0)
        if c.type == "indexed":
            return "BLACK" if c.indexed == 64 else ("INDEXED", c.indexed)
    except Exception:
        pass
    return ("RAW", str(c))


def normalize_numfmt(fmt):
    """Excel formats can serialize the same pattern with different escaping (backslash-escaped
    literal vs quoted, e.g. 0.00\\x vs 0.00"x") - normalize before comparing so that doesn't
    read as a mismatch."""
    return fmt.replace('"', "").replace("\\", "") if fmt else fmt


def cell_signature(cell):
    """A comparable tuple of everything that makes two cells 'look the same' - formula/value
    text plus every style axis extract_model.py otherwise prints as free text. Used by --diff-
    against so a mismatch anywhere (including alignment, which is easy to eyeball past) is
    caught mechanically instead of relying on a human re-reading two dumps side by side."""
    f = cell.font
    fill = cell.fill
    b = cell.border
    a = cell.alignment
    borders = tuple(
        (side_name, side.style, safe_color_key(side.color) if side.color else None)
        for side_name, side in (("top", b.top), ("bottom", b.bottom), ("left", b.left), ("right", b.right))
        if side and side.style
    )
    # A cell with no font set at all inherits the workbook default (Calibri 11 throughout this
    # entire model family) - openpyxl reports that as None rather than resolving it, which reads
    # as a false mismatch against a cell that sets it explicitly. Normalize both to the known
    # default so only a REAL font override shows up as a difference.
    font_name = f.name if f.name else "Calibri"
    font_size = f.sz if f.sz else 11.0
    return (
        normalize_formula(cell.value),
        font_name, font_size, bool(f.b), bool(f.i),
        safe_color_key(f.color),
        fill.fill_type,
        safe_color_key(fill.fgColor) if fill.fgColor else None,
        borders,
        a.horizontal, a.vertical,
        normalize_numfmt(cell.number_format),
    )


def diff_against(path_a, sheet_a, path_b, sheet_b, r1, r2, c1, c2, row_offset):
    """Cell-by-cell diff of path_a[sheet_a] (the reference / "should look like this" file)
    against path_b[sheet_b] (the file to check), over rows r1..r2 and columns c1..c2 of path_a
    - path_b's row is (row + row_offset). Prints ONLY mismatches, each showing exactly what
    changed (value/formula, or which specific style axis)."""
    wb_a = openpyxl.load_workbook(path_a, data_only=False)
    wb_b = openpyxl.load_workbook(path_b, data_only=False)
    ws_a = wb_a[sheet_a]
    ws_b = wb_b[sheet_b]

    axis_names = ["value", "font_name", "font_size", "bold", "italic", "font_color",
                  "fill_type", "fill_color", "borders", "align_h", "align_v", "numfmt"]

    mismatches = 0
    for row in range(r1, r2 + 1):
        brow = row + row_offset
        for col in range(c1, c2 + 1):
            ca = ws_a.cell(row=row, column=col)
            cb = ws_b.cell(row=row, column=col)
            sig_a = cell_signature(ca)
            sig_b = cell_signature(cb)
            if sig_a == sig_b:
                continue
            if sig_a[0] is None and sig_b[0] is None:
                # Both blank except for a stray style difference on an empty cell - not worth
                # reporting; "looks the same" is about visible content.
                continue
            mismatches += 1
            letter = get_column_letter(col)
            print(f"\n{letter}{row} (reference) vs {letter}{brow} (checked file) — MISMATCH")
            for name, va, vb in zip(axis_names, sig_a, sig_b):
                if va != vb:
                    print(f"    {name}: {va!r}  ->  {vb!r}")
    print(f"\n{'='*60}\n{mismatches} mismatching cell(s) found." if mismatches else f"\n{'='*60}\nNo mismatches — identical over this range.")
    return mismatches


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("sheet")
    ap.add_argument("--rows", help="start:end, 1-indexed, inclusive")
    ap.add_argument("--cols", help="comma-separated column letters to show formulas for, e.g. B,C,G,H")
    ap.add_argument("--find-hurdle-rows", action="store_true",
                     help="scan column B/C for bold+filled rows (typical section/tier headers) and list them")
    ap.add_argument("--diff-against", metavar="PATH",
                     help="cell-by-cell diff: this file/sheet/--rows/--cols range (as the reference) against "
                          "PATH (the file to check) - prints only mismatches, one line per differing style/value axis")
    ap.add_argument("--diff-sheet", help="sheet name in --diff-against's file, if different from `sheet`")
    ap.add_argument("--diff-row-offset", type=int, default=0,
                     help="row N in the reference file corresponds to row N+OFFSET in the checked file (default 0)")
    args = ap.parse_args()

    if args.diff_against:
        if not args.rows or not args.cols:
            print("Need --rows and --cols for --diff-against", file=sys.stderr)
            sys.exit(1)
        r1, r2 = (int(x) for x in args.rows.split(":"))
        col_letters = [c.strip() for c in args.cols.split(",")]
        c1 = min(column_index_from_string(c) for c in col_letters)
        c2 = max(column_index_from_string(c) for c in col_letters)
        n = diff_against(
            args.path, args.sheet, args.diff_against, args.diff_sheet or args.sheet,
            r1, r2, c1, c2, args.diff_row_offset
        )
        sys.exit(1 if n else 0)

    wb_f = openpyxl.load_workbook(args.path, data_only=False)
    wb_v = openpyxl.load_workbook(args.path, data_only=True)
    ws_f = wb_f[args.sheet]
    ws_v = wb_v[args.sheet]

    if args.find_hurdle_rows:
        for row in range(1, ws_f.max_row + 1):
            for col in (2, 3):
                cell = ws_f.cell(row=row, column=col)
                if cell.value and cell.font.b and cell.fill.fill_type:
                    print(f"row {row:>4}  col {get_column_letter(col)}  {cell.value!r:60s}  {describe_cell(cell)}")
                    break
        return

    if not args.rows:
        print("Need --rows start:end (or use --find-hurdle-rows)", file=sys.stderr)
        sys.exit(1)
    r1, r2 = (int(x) for x in args.rows.split(":"))
    cols = [column_index_from_string(c.strip()) for c in args.cols.split(",")] if args.cols else [2, 3]

    for row in range(r1, r2 + 1):
        label_b = ws_f.cell(row=row, column=2).value
        label_c = ws_f.cell(row=row, column=3).value
        if label_b is None and label_c is None and not args.cols:
            continue
        print(f"\n=== Row {row} ===  B={label_b!r}  C={label_c!r}")
        for col in cols:
            letter = get_column_letter(col)
            fcell = ws_f.cell(row=row, column=col)
            vcell = ws_v.cell(row=row, column=col)
            if fcell.value is None:
                continue
            print(f"  {letter}{row}: {fcell.value!r}")
            print(f"       value={vcell.value!r}")
            print(f"       style: {describe_cell(fcell)}")


if __name__ == "__main__":
    main()
