import json
import csv
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DESKTOP = Path(r"C:\Users\rikij\Desktop")
OUT_DIR = Path(__file__).parent

REGION_FILES = {
    "Cancun": ["cancun agents 1.txt", "Cancun agents 2.json"],
    "Playa del Carmen": ["playa del carmen agents 1.json", "playa del carmen agents 2.json"],
    "Puerto Morelos": ["Puerto Morelos agents 1.json"],
    "Puerto Vallarta": ["puerto vallarta agents 1.txt"],
    "Baja California Sur": ["baja california sur agents 1.txt", "baja california sur agents 2.json"],
}

EXCLUDE_DOMAIN_SUBSTRINGS = [
    "facebook.com", "instagram.com", "linkedin.com", "twitter.com", "x.com",
    "youtube.com", "wa.me", "whatsapp.com", "tiktok.com",
    "jamesedition.com", "nocnok.com", "icasas.mx", "point2homes.com",
    "properstar.", "zillow.com", "realtor.com", "trulia.com",
]

# generic chain homepages with no office/agent-specific path -- not scrapeable per-broker
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
    for fname in ["sites.csv", "new_sites_only.csv"]:
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
    print(f"Already-scraped domains (Tulum pipeline): {len(existing_domains)}")

    seen_domains_new = {}  # domain -> record (first-seen wins, regions tracked)
    region_membership = {}  # domain -> set of regions

    for region, files in REGION_FILES.items():
        for fname in files:
            path = DESKTOP / fname
            agents = load_agents(path)
            print(f"{region} / {fname}: {len(agents)} agents")
            for a in agents:
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
                region_membership.setdefault(d, set()).add(region)
                if d not in seen_domains_new:
                    seen_domains_new[d] = {
                        "broker_name": a.get("broker_name") or "",
                        "brokerage": a.get("brokerage") or "",
                        "url": url,
                        "listings_for_sale": a.get("listings_for_sale") or "",
                        "properstar_profile_url": a.get("properstar_profile_url") or "",
                    }

    print(f"Unique new-region broker domains (pre-exclusion): {len(seen_domains_new)}")

    truly_new = {
        d: rec for d, rec in seen_domains_new.items() if d not in existing_domains
    }
    print(f"Truly new domains not already scraped for Tulum: {len(truly_new)}")

    # Write combined new-sites CSV for the scraper (Broker Name, URL)
    combined_path = OUT_DIR / "new_sites_5regions.csv"
    with open(combined_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Broker Name", "URL"])
        for d, rec in sorted(truly_new.items()):
            writer.writerow([rec["broker_name"] or rec["brokerage"] or d, rec["url"]])
    print(f"Wrote {combined_path} ({len(truly_new)} rows)")

    # Write a region-mapping CSV (domain -> regions, for post-scrape tagging)
    mapping_path = OUT_DIR / "new_sites_5regions_region_map.csv"
    with open(mapping_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Domain", "URL", "Broker Name", "Brokerage", "Regions", "Properstar Listings"])
        for d, rec in sorted(seen_domains_new.items()):
            writer.writerow([
                d, rec["url"], rec["broker_name"], rec["brokerage"],
                "; ".join(sorted(region_membership.get(d, []))),
                rec["listings_for_sale"],
            ])
    print(f"Wrote {mapping_path} ({len(seen_domains_new)} rows, all new-region domains incl. already-scraped)")

    already_covered = len(seen_domains_new) - len(truly_new)
    print(f"\nAlready covered by existing Tulum scrape: {already_covered}")


if __name__ == "__main__":
    main()
