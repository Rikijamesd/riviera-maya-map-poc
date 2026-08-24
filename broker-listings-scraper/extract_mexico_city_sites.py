import json
import csv
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DESKTOP = Path(r"C:\Users\rikij\Desktop")
OUT_DIR = Path(__file__).parent

FILES = [
    "Mexico City Agents 1.txt",  # page 2 (dup of file 2)
    "Mexico City Agents 2.txt",  # page 2
    "Mexico City Agents 3.txt",  # page 3
    "Mexico City Agents 4.txt",  # page 4
    "Mexico City Agents 5.txt",  # page 5
    "Mexico City Agents 6.txt",  # page 6
]

EXCLUDE_DOMAIN_SUBSTRINGS = [
    "facebook.com", "instagram.com", "linkedin.com", "twitter.com", "x.com",
    "youtube.com", "wa.me", "whatsapp.com", "tiktok.com",
    "jamesedition.com", "nocnok.com", "icasas.mx", "point2homes.com",
    "properstar.", "zillow.com", "realtor.com", "trulia.com",
]

EXACT_EXCLUDE_URLS = {
    "https://www.theagencyre.com/",
    "https://www.theagencyre.com",
}


def normalize_url(url: str) -> str:
    url = url.strip()
    if not url:
        return ""
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "https://" + url
    return url


def domain_of(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().lstrip("www.")
    except Exception:
        return ""


def load_existing_scraped_domains() -> set[str]:
    domains = set()
    for fname in ["sites.csv", "new_sites_only.csv", "new_sites_5regions.csv"]:
        path = OUT_DIR / fname
        if not path.exists():
            continue
        with open(path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                url = row.get("URL") or row.get("url") or ""
                url = normalize_url(url)
                d = domain_of(url)
                if d:
                    domains.add(d)
    return domains


def load_agents(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig") as f:
        data = json.load(f)
    return data.get("data", {}).get("agents", [])


def main():
    existing_domains = load_existing_scraped_domains()
    print(f"Already-scraped domains (Tulum + 5-region pipelines): {len(existing_domains)}")

    seen_pages = set()
    all_agents = []
    for fname in FILES:
        path = DESKTOP / fname
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
        page = data["data"]["page"]
        if page in seen_pages:
            print(f"{fname}: page {page} -- duplicate, skipping")
            continue
        seen_pages.add(page)
        agents = data["data"]["agents"]
        print(f"{fname}: page {page}, {len(agents)} agents")
        all_agents.extend(agents)

    print(f"\nTotal unique agents loaded: {len(all_agents)} (pages: {sorted(seen_pages)})")
    if 1 not in seen_pages:
        print("NOTE: page 1 was not provided -- top ~100 agents by listing volume are missing.")

    seen_domains_new = {}
    for a in all_agents:
        raw_url = a.get("website_url")
        if not raw_url:
            continue
        url = normalize_url(raw_url)
        if url in EXACT_EXCLUDE_URLS:
            continue
        d = domain_of(url)
        if not d:
            continue
        if any(sub in d for sub in EXCLUDE_DOMAIN_SUBSTRINGS):
            continue
        if d not in seen_domains_new:
            seen_domains_new[d] = {
                "broker_name": a.get("broker_name") or "",
                "brokerage": a.get("brokerage") or "",
                "url": url,
                "listings_for_sale": a.get("listings_for_sale") or "",
            }

    print(f"Unique broker domains found (pre-exclusion): {len(seen_domains_new)}")

    truly_new = {d: rec for d, rec in seen_domains_new.items() if d not in existing_domains}
    print(f"Truly new domains not already scraped: {len(truly_new)}")

    out_path = OUT_DIR / "new_sites_mexico_city.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Broker Name", "URL"])
        for d, rec in sorted(truly_new.items()):
            writer.writerow([rec["broker_name"] or rec["brokerage"] or d, rec["url"]])
    print(f"Wrote {out_path} ({len(truly_new)} rows)")


if __name__ == "__main__":
    main()
