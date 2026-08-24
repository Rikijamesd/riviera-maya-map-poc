"""Shared helpers for the broker-listings scraper."""
from __future__ import annotations

import json
import re
import time
from urllib.parse import urljoin, urlparse

import truststore

truststore.inject_into_ssl()

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
}

DESCRIPTION_MAX_CHARS = 600  # keep descriptions short excerpts, not full page copy
MAX_IMAGES = 8

PRICE_RE = re.compile(r"(USD|MXN|US\$|\$|€|MX\$)\s?([\d][\d.,]{2,})", re.IGNORECASE)
BED_RE = re.compile(r"\b(\d+)\s*(bed(room)?s?|rec[aá]maras?|habitaciones?)\b", re.IGNORECASE)
BATH_RE = re.compile(r"\b(\d+(?:\.\d)?)\s*(bath(room)?s?|ba[nñ]os?)\b", re.IGNORECASE)
SIZE_RE = re.compile(r"(\d[\d,.]*)\s*(m2|m²|sq\s?ft|sqft|square\s+feet|metros)", re.IGNORECASE)

SALE_WORDS = [
    "venta", "en venta", "for sale", "compra", "se vende", "sale price",
    "vente", "à vendre", "a vendre", "acheter",  # French
]
RENT_WORDS = [
    "renta", "en renta", "for rent", "alquiler", "se renta", "rental", "arrendamiento",
    "location", "à louer", "a louer", "louer",  # French
]

PLATFORM_MARKERS = {
    "Tokko Broker": ["tokkobroker.com", "tokko"],
    "EasyBroker": ["easybroker.com", "eb-widget", "api.easybroker"],
    "Wiggot": ["wiggot.com", "wiggot"],
    "IDX Broker": ["idxbroker.com"],
    "Inmoenlace": ["inmoenlace.com"],
    "PropertyBase": ["propertybase.com"],
    "Resales Online": ["resales-online.com"],
}

PROPERTY_TYPE_PATTERNS = [
    ("Land/Lot", re.compile(r"\b(terreno|lote|land|lot|terrain)\b", re.IGNORECASE)),
    ("Villa", re.compile(r"\bvilla\b", re.IGNORECASE)),
    ("Penthouse", re.compile(r"\bpenthouse\b", re.IGNORECASE)),
    ("Condo/Apartment", re.compile(r"\b(condo|departamento|depto|apartment|apartamento|appartement)\b", re.IGNORECASE)),
    ("House", re.compile(r"\b(casa|house|home|maison)\b", re.IGNORECASE)),
    ("Commercial", re.compile(r"\b(local|oficina|office|commercial|comercial|bodega|bureau|entrepot)\b", re.IGNORECASE)),
]

LISTING_LINK_KEYWORDS = [
    "propert", "propiedad", "listing", "inmueble", "casa", "depto", "departamento",
    "villa", "condo", "condominio", "terreno", "lote", "venta", "renta", "mls",
    "for-sale", "for-rent",
    # French
    "immobilier", "annonce", "maison", "appartement", "terrain", "vente", "location", "achat",
]
LISTING_LINK_EXCLUDE = [
    "wp-content", "wp-admin", "wp-login", "facebook.com", "instagram.com",
    "linkedin.com", "twitter.com", "x.com", "youtube.com", "whatsapp.com",
    "mailto:", "tel:", "#", "privacy", "aviso-de-privacidad", "terms",
    "blog/", "/blog", "wp-json",
    "mentions-legales", "confidentialite", "cgu", "cgv",  # French legal/terms pages
]

REGION_CITY_STATE = {
    "tulum": ("Tulum", "Quintana Roo"),
    "playa del carmen": ("Playa del Carmen", "Quintana Roo"),
    "playa car": ("Playacar", "Quintana Roo"),
    "playacar": ("Playacar", "Quintana Roo"),
    "puerto morelos": ("Puerto Morelos", "Quintana Roo"),
    "puerto aventuras": ("Puerto Aventuras", "Quintana Roo"),
    "akumal": ("Akumal", "Quintana Roo"),
    "cancun": ("Cancún", "Quintana Roo"),
    "cancún": ("Cancún", "Quintana Roo"),
    "bacalar": ("Bacalar", "Quintana Roo"),
    "holbox": ("Holbox", "Quintana Roo"),
    "cozumel": ("Cozumel", "Quintana Roo"),
    "mahahual": ("Mahahual", "Quintana Roo"),
    "merida": ("Mérida", "Yucatán"),
    "mérida": ("Mérida", "Yucatán"),
    "progreso": ("Progreso", "Yucatán"),
    "puerto vallarta": ("Puerto Vallarta", "Jalisco"),
    "punta de mita": ("Punta de Mita", "Nayarit"),
    "punta mita": ("Punta de Mita", "Nayarit"),
    "nuevo vallarta": ("Nuevo Vallarta", "Nayarit"),
    "bucerias": ("Bucerías", "Nayarit"),
    "bucerías": ("Bucerías", "Nayarit"),
    "sayulita": ("Sayulita", "Nayarit"),
    "riviera nayarit": ("Riviera Nayarit", "Nayarit"),
    "los cabos": ("Los Cabos", "Baja California Sur"),
    "cabo san lucas": ("Cabo San Lucas", "Baja California Sur"),
    "san jose del cabo": ("San José del Cabo", "Baja California Sur"),
    "san josé del cabo": ("San José del Cabo", "Baja California Sur"),
    "la paz": ("La Paz", "Baja California Sur"),
    "todos santos": ("Todos Santos", "Baja California Sur"),
    "east cape": ("East Cape", "Baja California Sur"),
    "loreto": ("Loreto", "Baja California Sur"),
    "san felipe": ("San Felipe", "Baja California"),
}


def normalize_url(url: str) -> str:
    url = url.strip()
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "https://" + url
    return url


def fetch_html(url: str, browser=None) -> tuple[str | None, str | None]:
    """Fetch a page's HTML. Try a plain request first; fall back to a headless
    browser if the page looks too thin (client-side rendered)."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        if resp.status_code < 400 and len(resp.text) > 1500:
            return resp.text, resp.url
    except Exception:
        pass

    if browser is None:
        return None, None

    try:
        page = browser.new_page(user_agent=HEADERS["User-Agent"])
        page.set_default_timeout(20000)
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(2000)
        html = page.content()
        final_url = page.url
        page.close()
        return html, final_url
    except Exception:
        try:
            page.close()
        except Exception:
            pass
        return None, None


def _looks_like_individual_listing(parsed_path: str) -> bool:
    """Distinguish a specific property's detail page from a category/index
    page (e.g. '/Venta', '/Propiedades') that merely mentions a keyword.
    Individual listing URLs almost always carry either a numeric ID or a
    long descriptive slug; bare category pages don't."""
    segments = [s for s in parsed_path.split("/") if s]
    if not segments:
        return False
    last = segments[-1]
    if re.search(r"\d{3,}", last):  # property/MLS id
        return True
    if len(last) >= 25 and "-" in last:  # long descriptive slug
        return True
    return False


def find_candidate_links(html: str, base_url: str) -> tuple[list[str], list[str]]:
    """Split links on a page into (individual_listing_links, category_links).
    Category links are keyword-matching links that don't look like a specific
    property (no ID, no long slug) - candidates for a second-level crawl."""
    soup = BeautifulSoup(html, "html.parser")
    domain = urlparse(base_url).netloc
    seen = set()
    listing_links, category_links = [], []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith("javascript:"):
            continue
        full = urljoin(base_url, href)
        parsed = urlparse(full)
        if parsed.netloc != domain:
            continue
        lower = full.lower()
        if any(bad in lower for bad in LISTING_LINK_EXCLUDE):
            continue
        if not any(k in lower for k in LISTING_LINK_KEYWORDS):
            continue
        if full in seen or full == base_url:
            continue
        seen.add(full)
        if _looks_like_individual_listing(parsed.path):
            listing_links.append(full)
        else:
            category_links.append(full)
    return listing_links, category_links


def find_listing_links(html: str, base_url: str, limit: int) -> list[str]:
    listing_links, _ = find_candidate_links(html, base_url)
    return listing_links[:limit]


NEXT_PAGE_LABELS = {"siguiente", "next", "próxima", "proxima", "next »", "next page", "siguiente »"}


def find_next_page_link(html: str, base_url: str) -> str | None:
    """Find a 'next page' link on a category/search-results page, so a
    broker's full paginated inventory can be crawled instead of just page 1."""
    soup = BeautifulSoup(html, "html.parser")
    domain = urlparse(base_url).netloc

    rel_next = soup.find("a", rel="next")
    if rel_next and rel_next.get("href"):
        full = urljoin(base_url, rel_next["href"])
        if urlparse(full).netloc == domain and full != base_url:
            return full

    for a in soup.find_all("a", href=True):
        label = (a.get_text() or "").strip().lower()
        aria = (a.get("aria-label") or "").strip().lower()
        if label in NEXT_PAGE_LABELS or aria in NEXT_PAGE_LABELS:
            full = urljoin(base_url, a["href"])
            if urlparse(full).netloc == domain and full != base_url:
                return full

    return None


def parse_jsonld_blocks(soup: BeautifulSoup) -> list[dict]:
    blocks = []
    for tag in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            data = json.loads(tag.string or "")
        except Exception:
            continue
        if isinstance(data, list):
            blocks.extend(d for d in data if isinstance(d, dict))
        elif isinstance(data, dict):
            if "@graph" in data and isinstance(data["@graph"], list):
                blocks.extend(d for d in data["@graph"] if isinstance(d, dict))
            else:
                blocks.append(data)
    return blocks


def _first(*vals):
    for v in vals:
        if v:
            return v
    return None


def extract_from_jsonld(blocks: list[dict]) -> dict:
    out = {}
    for b in blocks:
        offers = b.get("offers")
        if isinstance(offers, list) and offers:
            offers = offers[0]
        if isinstance(offers, dict):
            price_spec = offers.get("priceSpecification")
            spec_price = price_spec.get("price") if isinstance(price_spec, dict) else None
            out.setdefault("price", offers.get("price") or spec_price)
            out.setdefault("currency", offers.get("priceCurrency"))

        out.setdefault("name", b.get("name"))
        out.setdefault("description", b.get("description"))

        addr = b.get("address")
        if isinstance(addr, dict):
            out.setdefault("city", addr.get("addressLocality"))
            out.setdefault("state", addr.get("addressRegion"))
            out.setdefault("country", addr.get("addressCountry") if isinstance(addr.get("addressCountry"), str)
                            else (addr.get("addressCountry") or {}).get("name"))

        geo = b.get("geo")
        if isinstance(geo, dict):
            out.setdefault("latitude", geo.get("latitude"))
            out.setdefault("longitude", geo.get("longitude"))

        out.setdefault("bedrooms", b.get("numberOfBedrooms") or b.get("numberOfRooms"))
        out.setdefault("bathrooms", b.get("numberOfBathroomsTotal") or b.get("numberOfBathrooms"))

        floor_size = b.get("floorSize")
        if isinstance(floor_size, dict):
            out.setdefault("size", floor_size.get("value"))
            out.setdefault("size_unit", (floor_size.get("unitText") or floor_size.get("unitCode")))

        image = b.get("image")
        if image:
            if isinstance(image, str):
                out.setdefault("images", [image])
            elif isinstance(image, list):
                urls = []
                for i in image:
                    if isinstance(i, str):
                        urls.append(i)
                    elif isinstance(i, dict) and i.get("url"):
                        urls.append(i["url"])
                if urls:
                    out.setdefault("images", urls)
            elif isinstance(image, dict) and image.get("url"):
                out.setdefault("images", [image["url"]])
    return out


def extract_from_opengraph(soup: BeautifulSoup, base_url: str) -> dict:
    def meta(prop):
        tag = soup.find("meta", {"property": prop}) or soup.find("meta", {"name": prop})
        return tag.get("content") if tag else None

    out = {
        "name": meta("og:title"),
        "description": meta("og:description"),
        "price": meta("product:price:amount") or meta("og:price:amount"),
        "currency": meta("product:price:currency") or meta("og:price:currency"),
    }
    images = []
    for tag in soup.find_all("meta", {"property": "og:image"}):
        content = tag.get("content")
        if content:
            images.append(urljoin(base_url, content))
    if images:
        out["images"] = images
    return {k: v for k, v in out.items() if v}


def detect_platform(html: str) -> str | None:
    """Identify which shared listing-management SaaS (Tokko Broker,
    EasyBroker, Wiggot, etc.) a broker's site is built on, if any. Several
    "independent" broker sites turn out to run on the same underlying
    platform, which usually has its own aggregated multi-broker search."""
    lower = html.lower()
    for platform, markers in PLATFORM_MARKERS.items():
        if any(m in lower for m in markers):
            return platform
    return None


def extract_property_type(name: str | None, text: str) -> str:
    haystack = f"{name or ''} {text[:2000]}"
    for label, pattern in PROPERTY_TYPE_PATTERNS:
        if pattern.search(haystack):
            return label
    return "Unknown"


def extract_images_from_dom(soup: BeautifulSoup, base_url: str, limit: int) -> list[str]:
    urls = []
    seen = set()
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
        if not src or src.startswith("data:"):
            continue
        full = urljoin(base_url, src)
        if full in seen:
            continue
        seen.add(full)
        urls.append(full)
        if len(urls) >= limit:
            break
    return urls


def extract_price_beds_baths_size(text: str) -> dict:
    out = {}
    m = PRICE_RE.search(text)
    if m:
        currency_raw = m.group(1).upper()
        out["price"] = m.group(2).replace(",", "")
        out["currency"] = "USD" if currency_raw in ("$", "US$") else currency_raw

    m = BED_RE.search(text)
    if m:
        out["bedrooms"] = m.group(1)

    m = BATH_RE.search(text)
    if m:
        out["bathrooms"] = m.group(1)

    m = SIZE_RE.search(text)
    if m:
        out["size"] = m.group(1).replace(",", "")
        out["size_unit"] = "m2" if "m" in m.group(2).lower() else "sqft"

    return out


def guess_location(text: str) -> dict:
    lower = text.lower()
    for key, (city, state) in REGION_CITY_STATE.items():
        if key in lower:
            return {"city": city, "state": state, "country": "Mexico"}
    return {}


def classify_sale_or_rent(text: str) -> str:
    lower = text.lower()
    sale_hits = sum(1 for w in SALE_WORDS if w in lower)
    rent_hits = sum(1 for w in RENT_WORDS if w in lower)
    if rent_hits > sale_hits:
        return "Rent"
    if sale_hits > 0:
        return "Sale"
    return "Unknown"


_geocode_cache: dict[str, tuple[float | None, float | None]] = {}


def geocode(city: str | None, state: str | None, country: str | None) -> tuple[float | None, float | None]:
    """Best-effort geocoding via OpenStreetMap Nominatim, cached per unique
    city/state/country combo and rate-limited to Nominatim's usage policy
    (max 1 request/second)."""
    if not city and not state:
        return None, None
    query = ", ".join(p for p in (city, state, country) if p)
    if query in _geocode_cache:
        return _geocode_cache[query]

    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": query, "format": "json", "limit": 1},
            headers={"User-Agent": "riviera-maya-broker-scraper/1.0 (research use)"},
            timeout=10,
        )
        time.sleep(1.1)  # respect Nominatim's 1 req/sec policy
        results = resp.json()
        if results:
            lat = float(results[0]["lat"])
            lon = float(results[0]["lon"])
            _geocode_cache[query] = (lat, lon)
            return lat, lon
    except Exception:
        pass

    _geocode_cache[query] = (None, None)
    return None, None


def build_record(html: str, url: str, broker_name: str, broker_url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator="\n")

    jsonld = extract_from_jsonld(parse_jsonld_blocks(soup))
    og = extract_from_opengraph(soup, url)
    heuristic = extract_price_beds_baths_size(text)
    loc = guess_location(text)

    name = _first(jsonld.get("name"), og.get("name"), soup.title.string if soup.title else None)
    description = _first(jsonld.get("description"), og.get("description"))
    if description:
        description = re.sub(r"\s+", " ", description).strip()[:DESCRIPTION_MAX_CHARS]

    price = _first(jsonld.get("price"), og.get("price"), heuristic.get("price"))
    currency = _first(jsonld.get("currency"), og.get("currency"), heuristic.get("currency"))
    bedrooms = _first(jsonld.get("bedrooms"), heuristic.get("bedrooms"))
    bathrooms = _first(jsonld.get("bathrooms"), heuristic.get("bathrooms"))
    size = _first(jsonld.get("size"), heuristic.get("size"))
    size_unit = _first(jsonld.get("size_unit"), heuristic.get("size_unit"))

    images = jsonld.get("images") or og.get("images") or extract_images_from_dom(soup, url, MAX_IMAGES)
    images = [urljoin(url, i) for i in images][:MAX_IMAGES]

    city = _first(jsonld.get("city"), loc.get("city"))
    state = _first(jsonld.get("state"), loc.get("state"))
    country = _first(jsonld.get("country"), loc.get("country"), "Mexico")
    lat = jsonld.get("latitude")
    lon = jsonld.get("longitude")

    sale_or_rent = classify_sale_or_rent(text + " " + url)
    property_type = extract_property_type(name, text)
    platform = detect_platform(html)

    return {
        "Broker": broker_name,
        "Broker URL": broker_url,
        "Platform": platform or "",
        "Listing URL": url,
        "Listing Name": name,
        "Property Type": property_type,
        "Price": price,
        "Currency": currency,
        "Bedrooms": bedrooms,
        "Bathrooms": bathrooms,
        "Size": size,
        "Size Unit": size_unit,
        "Description": description,
        "Images": "; ".join(images) if images else "",
        "Country": country,
        "State": state,
        "City": city,
        "Latitude": lat,
        "Longitude": lon,
        "Sale or Rent": sale_or_rent,
    }
