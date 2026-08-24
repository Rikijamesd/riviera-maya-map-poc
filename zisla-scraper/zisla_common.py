"""Shared helpers for the Zisla (zisla.com) scraper scripts."""
from __future__ import annotations

import html
import re
import time
from datetime import date

import truststore

truststore.inject_into_ssl()  # trust the Windows cert store, matching PowerShell's Invoke-RestMethod

import requests
from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

API_BASE = "https://www.zisla.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://www.zisla.com/",
    "Accept": "application/json",
}

HEADER_FILL = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
HEADER_FONT = Font(bold=True, color="FFFFFF")

SNAPSHOT_DATE = date.today().isoformat()


def _get(url: str, params: dict) -> dict:
    resp = requests.get(url, headers=HEADERS, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _paginate(url: str, base_params: dict, page_size: int, delay: float = 0.25) -> list[dict]:
    all_items: list[dict] = []
    offset = 0
    while True:
        params = {**base_params, "offset": offset, "limit": page_size}
        data = _get(url, params)
        items = data.get("items") or []
        if not items:
            break
        all_items.extend(items)
        if len(items) < page_size:
            break
        offset += page_size
        time.sleep(delay)
    return all_items


def fetch_developments() -> list[dict]:
    published_filter = '[{"id":"published","type":"boolean","value":true}]'
    return _paginate(
        f"{API_BASE}/api/v1/properties/listing",
        {"filters": published_filter, "lang": "en"},
        page_size=200,
    )


def fetch_units(property_id: str) -> list[dict]:
    filters = f'[{{"id":"propertyId","type":"_id","value":"{property_id}"}}]'
    return _paginate(
        f"{API_BASE}/api/v1/units/listing",
        {"filters": filters, "lang": "en", "browser": "true"},
        page_size=1000,
        delay=0.2,
    )


def fetch_blog_articles() -> list[dict]:
    filters = (
        '[{"type":"string","id":"type","value":"ARTICLE"},'
        '{"type":"boolean","id":"localized.en.published","value":true}]'
    )
    return _paginate(f"{API_BASE}/api/v1/pages", {"filters": filters}, page_size=100)


def to_plain_text(html_str: str | None) -> str:
    if not html_str:
        return ""
    text = re.sub(r"<[^>]+>", " ", html_str)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def join_true_keys(obj: dict | None) -> str:
    if not obj:
        return ""
    return ", ".join(k for k, v in obj.items() if v is True)


def style_header(ws, col_count: int) -> None:
    for c in range(1, col_count + 1):
        cell = ws.cell(row=1, column=c)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
    ws.row_dimensions[1].height = 20
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(col_count)}1"


def autofit_columns(ws, max_width: int = 60) -> None:
    widths: dict[str, int] = {}
    for row in ws.iter_rows():
        for cell in row:
            if cell.value is None:
                continue
            length = len(str(cell.value))
            col = cell.column_letter
            widths[col] = min(max(widths.get(col, 0), length + 2), max_width)
    for col, width in widths.items():
        ws.column_dimensions[col].width = width


def _sanitize(value):
    """Strips control characters Excel/XML can't hold - e.g. mojibake'd dashes
    that occasionally survive in Zisla's listing copy."""
    if isinstance(value, str):
        return ILLEGAL_CHARACTERS_RE.sub("", value)
    return value


def write_new_workbook(path, sheet_name: str, rows: list[dict]) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name
    headers = list(rows[0].keys())
    ws.append(headers)
    for row in rows:
        ws.append([_sanitize(row.get(h)) for h in headers])
    style_header(ws, len(headers))
    autofit_columns(ws)
    wb.save(path)


def get_or_create_sheet(wb, name: str, headers: list[str]):
    """Returns the sheet, creating it with a styled header row if it doesn't exist yet.

    ID-like columns get a text number format so leading zeros / long numeric
    IDs survive round-tripping through Excel unmangled.
    """
    if name in wb.sheetnames:
        return wb[name]
    ws = wb.create_sheet(name)
    ws.append(headers)
    for idx, header in enumerate(headers, start=1):
        if header == "Unit" or "ID" in header:
            ws.column_dimensions[get_column_letter(idx)].number_format = "@"
    style_header(ws, len(headers))
    return ws


def append_rows(ws, rows: list[dict]) -> None:
    if not rows:
        return
    headers = list(rows[0].keys())
    for row in rows:
        ws.append([_sanitize(row.get(h)) for h in headers])
