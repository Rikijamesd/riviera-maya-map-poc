r"""
One-call "regenerate + check + diff" round-trip for iterating a live Excel-export
generator against a reference workbook, instead of the 4-5 separate tool calls
(curl the export, convert with LibreOffice, check formula errors, run the diff
tool, read the output) that took each round of the tlrm "Greater of Both" work.

Usage:
    python verify_export.py \
        --api-url http://localhost:3000/api/cash-flow/export \
        --payload debug_payload.json \
        --reference "TLRM-CashFlow-irr+emx.xlsx" --reference-sheet "Equity Returns" \
        --rows 15:127 --cols B,C,D,E,F,G,H,I,J \
        [--checked-sheet "Equity Returns"] [--out generated.xlsx] \
        [--skip-formula-check] [--soffice "C:\Program Files\LibreOffice\program\soffice.exe"]

Exit code 0 only when BOTH the formula-error check passes AND the diff is clean -
use it as a loop-until-clean gate: fix generator code for whatever it prints,
re-run, repeat. Everything printed is the same output extract_model.py's
--diff-against would give you directly - this script just chains the steps that
normally sit in front of it (getting a fresh, real export to diff against).

This automates the MECHANICAL round-trip only. It does not, and should not,
decide whether a reported mismatch is a bug to fix, a deliberate divergence, or
an error in the reference file itself - that judgment call stays manual every
time (see this skill's SKILL.md, Step 1b, on why a mismatch is not automatically
"copy the reference file's cell").
"""
import argparse
import json
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from extract_model import diff_against  # noqa: E402
from openpyxl.utils import column_index_from_string  # noqa: E402

DEFAULT_SOFFICE = r"C:\Program Files\LibreOffice\program\soffice.exe"


def fetch_export(api_url: str, payload_path: str, out_path: Path) -> None:
    payload = json.loads(Path(payload_path).read_text())
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(api_url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        if resp.status != 200:
            raise RuntimeError(f"Export API returned HTTP {resp.status}")
        out_path.write_bytes(resp.read())


def check_formula_errors(path: Path, soffice: str) -> int:
    """Round-trips the file through LibreOffice (which computes real values for any
    formula lacking a cache - true of anything openpyxl/ExcelJS just wrote) and counts
    cells whose computed value is an Excel error token (#REF!, #VALUE!, #NUM!, ...).
    Returns the error count; 0 means clean."""
    import openpyxl

    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            [soffice, "--headless", "--convert-to", "xlsx", "--outdir", tmp, str(path)],
            capture_output=True, timeout=90, check=True,
        )
        recalced = Path(tmp) / path.name
        wb = openpyxl.load_workbook(recalced, data_only=True)
        errors = 0
        for ws in wb.worksheets:
            for row in ws.iter_rows():
                for cell in row:
                    if isinstance(cell.value, str) and cell.value.startswith("#"):
                        errors += 1
        return errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-url", required=True)
    ap.add_argument("--payload", required=True, help="JSON file with the export API's request body")
    ap.add_argument("--reference", required=True)
    ap.add_argument("--reference-sheet", required=True)
    ap.add_argument("--checked-sheet", help="defaults to --reference-sheet")
    ap.add_argument("--rows", required=True, help="start:end, 1-indexed inclusive")
    ap.add_argument("--cols", required=True, help="comma-separated column letters")
    ap.add_argument("--row-offset", type=int, default=0)
    ap.add_argument("--out", help="where to save the fetched export (default: a temp file)")
    ap.add_argument("--skip-formula-check", action="store_true",
                     help="skip the LibreOffice recalc pass - faster, but only checks layout/formulas, not that they actually evaluate")
    ap.add_argument("--soffice", default=DEFAULT_SOFFICE)
    args = ap.parse_args()

    out_path = Path(args.out) if args.out else Path(tempfile.mktemp(suffix=".xlsx"))
    print(f"Fetching export -> {out_path}")
    fetch_export(args.api_url, args.payload, out_path)

    ok = True
    if not args.skip_formula_check:
        print("Checking for formula errors (LibreOffice recalc)...")
        try:
            n = check_formula_errors(out_path, args.soffice)
        except Exception as e:
            print(f"  Could not run the formula-error check: {e}", file=sys.stderr)
            n = None
        if n is None:
            pass
        elif n == 0:
            print("  0 formula errors.")
        else:
            print(f"  {n} formula error(s) found - this needs fixing before the diff below matters.")
            ok = False

    r1, r2 = (int(x) for x in args.rows.split(":"))
    col_letters = [c.strip() for c in args.cols.split(",")]
    c1 = min(column_index_from_string(c) for c in col_letters)
    c2 = max(column_index_from_string(c) for c in col_letters)

    print(f"\nDiffing {args.reference}[{args.reference_sheet}] rows {args.rows} against {out_path.name}...")
    n_mismatch = diff_against(
        args.reference, args.reference_sheet, str(out_path), args.checked_sheet or args.reference_sheet,
        r1, r2, c1, c2, args.row_offset,
    )
    if n_mismatch:
        ok = False

    print(f"\n{'PASS' if ok else 'FAIL'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
