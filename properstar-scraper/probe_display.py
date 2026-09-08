"""Does any single domain DISPLAY the Original price for every listing?

Matters for parse.bot specifically: it extracts what the page presents, so it can
only get the true uploaded price if that price is the one rendered on screen.

Tests two listings with different Original currencies:
  119293941 -> Original MXN 145,000,000
  109194519 -> Original USD 7,000,000
across .co.uk and .com.mx, comparing the values array to the rendered price text.
"""
from __future__ import annotations

import json
import re

from scrapling.fetchers import Fetcher, StealthyFetcher

LISTINGS = {"119293941": "MXN original", "109194519": "USD original"}
DOMAINS = ["https://www.properstar.co.uk", "https://www.properstar.com.mx"]


def extract_state(html):
    i = html.find("window.__INITIAL_STATE__")
    if i == -1:
        return None
    start = html.find("{", i)
    depth, j, in_str, esc = 0, start, False, False
    while j < len(html):
        c = html[j]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(html[start:j + 1])
                    except Exception:
                        return None
        j += 1
    return None


for base in DOMAINS:
    print(f"\n########## {base} ##########")
    boot = StealthyFetcher.fetch(f"{base}/listing/119293941", headless=True,
                                 network_idle=True, wait=8000)
    cookies = {c["name"]: c["value"] for c in boot.cookies}
    for lid, label in LISTINGS.items():
        url = f"{base}/listing/{lid}"
        r = Fetcher.get(url, stealthy_headers=True, cookies=cookies)
        html = r.body.decode("utf-8", "ignore") if isinstance(r.body, bytes) else r.body
        print(f"\n--- {lid} ({label}) status={r.status} ---")
        st = extract_state(html)
        node = ((st or {}).get("entities", {}).get("listing") or {}).get(lid) if st else None
        if node:
            pv = (node.get("price") or {}).get("values") or []
            print(f"  values: {json.dumps(pv, ensure_ascii=False)}")
        # What price does the page actually SHOW? og:title / meta description / price markup
        og = re.search(r'property="og:title" content="([^"]{0,200})"', html)
        if og:
            print(f"  og:title: {og.group(1)[:160]}")
        # visible price element
        for pat in [r'class="[^"]*price[^"]*"[^>]*>([^<]{2,40})<',
                    r'itemprop="price"[^>]*content="([^"]+)"']:
            m = re.search(pat, html)
            if m:
                print(f"  rendered price-ish: {m.group(1).strip()[:60]}")
                break
