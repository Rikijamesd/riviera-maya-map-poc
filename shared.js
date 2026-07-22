// Shared formatting/data helpers used by both index.html (map + list) and detail.html (single development page).

// Fallback only, used if the live rate fetch (below) fails or hasn't resolved yet.
let USD_TO_MXN = 18;
let exchangeRateInfo = { rate: USD_TO_MXN, updatedUtc: null, isLive: false };
const SQM_TO_SQFT = 10.7639;

// Fetches a live USD->MXN rate from a free, keyless API (open.er-api.com, backed by
// exchangerate-api.com's open dataset). Falls back to the fixed rate above on any
// failure (offline, API down, blocked) so the page still renders usable prices.
async function fetchLiveExchangeRate() {
  try {
    const res = await fetch("https://open.er-api.com/v6/latest/USD");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (data.result === "success" && data.rates && data.rates.MXN) {
      USD_TO_MXN = data.rates.MXN;
      exchangeRateInfo = { rate: data.rates.MXN, updatedUtc: data.time_last_update_utc, isLive: true };
    }
  } catch (e) {
    // Keep the fallback rate; exchangeRateInfo.isLive stays false.
  }
  return exchangeRateInfo;
}

function formatPrice(usd) {
  return "US $" + usd.toLocaleString("en-US");
}

function formatMXN(usd) {
  return "MX $" + Math.round(usd * USD_TO_MXN).toLocaleString("en-US");
}

function exchangeRateLabel() {
  const rateText = `1 USD = ${exchangeRateInfo.rate.toFixed(2)} MXN`;
  return exchangeRateInfo.isLive ? `${rateText} (live)` : `${rateText} (offline estimate)`;
}

// ---------- currency toggle (shared USD/MXN display preference) ----------

const CURRENCY_KEY = "riviera-maya-map-poc:currency";
let currentCurrency = localStorage.getItem(CURRENCY_KEY) === "MXN" ? "MXN" : "USD";

function formatMoney(usd) {
  return currentCurrency === "MXN" ? formatMXN(usd) : formatPrice(usd);
}

// Wires up the #currencyUsdBtn / #currencyMxnBtn pill (present on both index.html
// and detail.html) and calls onChange() whenever the selected currency changes,
// so the caller can re-render whatever prices it's showing.
function setupCurrencyToggle(onChange) {
  const usdBtn = document.getElementById("currencyUsdBtn");
  const mxnBtn = document.getElementById("currencyMxnBtn");
  if (!usdBtn || !mxnBtn) return;

  function refreshButtons() {
    usdBtn.classList.toggle("active", currentCurrency === "USD");
    mxnBtn.classList.toggle("active", currentCurrency === "MXN");
  }
  refreshButtons();

  function select(currency) {
    if (currentCurrency === currency) return;
    currentCurrency = currency;
    localStorage.setItem(CURRENCY_KEY, currency);
    refreshButtons();
    onChange();
  }

  usdBtn.addEventListener("click", () => select("USD"));
  mxnBtn.addEventListener("click", () => select("MXN"));
}

function devMinPrice(dev) {
  return Math.min(...dev.units.map((u) => u.price));
}

function priceRangeLabel(dev) {
  const prices = dev.units.map((u) => u.price);
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  return min === max ? formatMoney(min) : `${formatMoney(min)} – ${formatMoney(max)}`;
}

function bedRangeLabel(dev) {
  if (dev.propertyType === "Land") return "Land";
  const beds = dev.units.map((u) => u.bedrooms);
  const min = Math.min(...beds);
  const max = Math.max(...beds);
  if (min === 0 && max === 0) return "Studio";
  const minLabel = min === 0 ? "Studio" : `${min} Bed`;
  return min === max ? `${max} Bed` : `${minLabel} - ${max} Bed`;
}

function sizeFromLabel(dev) {
  const min = Math.min(...dev.units.map((u) => u.size));
  const ft2 = Math.round(min * SQM_TO_SQFT * 100) / 100;
  return `From ${min}m² / ${ft2}ft²`;
}

function driveImageUrl(fileId, width) {
  return `https://lh3.googleusercontent.com/d/${fileId}=w${width || 800}`;
}

function initials(project) {
  return project
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0])
    .join("")
    .toUpperCase();
}

const BANNER_PALETTE = [
  ["#0e7c86", "#0b5f68"],
  ["#2472a8", "#173f63"],
  ["#1c8c6b", "#0f5c46"],
  ["#3f6e9c", "#24466b"],
  ["#0f9aa0", "#0a6970"],
  ["#4a7fae", "#2a4f7c"],
];

function bannerStyle(dev) {
  const pal = BANNER_PALETTE[dev.id % BANNER_PALETTE.length];
  return `background: linear-gradient(135deg, ${pal[0]}, ${pal[1]});`;
}

function unitTypeCounts(dev) {
  const counts = {};
  for (const u of dev.units) counts[u.type] = (counts[u.type] || 0) + u.available;
  return counts;
}

function totalAvailable(dev) {
  return dev.units.reduce((sum, u) => sum + u.available, 0);
}

const UNIT_TYPE_ORDER = ["Studio", "1BR", "2BR", "3BR", "Land"];
const UNIT_TYPE_LABEL = { Studio: "Studio", "1BR": "1 Bed", "2BR": "2 Bed", "3BR": "3 Bed", Land: "Land" };

// ---------- favorites (shared localStorage-backed set) ----------

const FAVORITES_KEY = "riviera-maya-map-poc:favorites";

function loadFavorites() {
  try {
    return new Set(JSON.parse(localStorage.getItem(FAVORITES_KEY) || "[]"));
  } catch (e) {
    return new Set();
  }
}

function saveFavorites(favorites) {
  localStorage.setItem(FAVORITES_KEY, JSON.stringify([...favorites]));
}

// ---------- monochrome amenity icons (single accent color, like the Maya Ocean reference) ----------

const AMENITY_ICON_PATHS = {
  Pool: '<path d="M3 17c1.2 1 2.4 1 3.6 0s2.4-1 3.6 0 2.4 1 3.6 0 2.4-1 3.6 0 2.4 1 3.6 0" stroke-linecap="round"/><path d="M6 13V6a2 2 0 0 1 2-2h2M6 13h12M6 13a2 2 0 0 0-2 2"/>',
  Gym: '<path d="M4 12h2M18 12h2M6 12h2v-3a1 1 0 0 1 1-1h0a1 1 0 0 1 1 1v6a1 1 0 0 1-1 1h0a1 1 0 0 1-1-1v-3zM16 12h-2v-3a1 1 0 0 0-1-1h0a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h0a1 1 0 0 0 1-1v-3z"/>',
  "Rooftop Terrace": '<path d="M4 20V9l8-5 8 5v11"/><path d="M9 20v-6h6v6M4 9l8 5 8-5"/>',
  "Security 24/7": '<path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6l7-3z"/><path d="m9.5 12 1.8 1.8L14.5 10"/>',
  Elevator: '<rect x="6" y="3" width="12" height="18" rx="1.5"/><path d="M10 8l2-2 2 2M10 15l2 2 2-2"/>',
  Parking: '<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M10 16V8h2.5a2.5 2.5 0 0 1 0 5H10"/>',
  Coworking: '<rect x="3" y="6" width="18" height="12" rx="1.5"/><path d="M3 12h18M9 6V4.5A1.5 1.5 0 0 1 10.5 3h3A1.5 1.5 0 0 1 15 4.5V6"/>',
  "Kids Club": '<circle cx="12" cy="9" r="3"/><path d="M6 20c0-3.3 2.7-6 6-6s6 2.7 6 6"/>',
  "BBQ Area": '<path d="M9 3c0 2-2 2-2 4a2 2 0 0 0 4 0c0-2-2-2-2-4zM15 3c0 2-2 2-2 4a2 2 0 0 0 4 0c0-2-2-2-2-4z"/><path d="M5 12h14l-1.5 7a2 2 0 0 1-2 1.7H8.5a2 2 0 0 1-2-1.7L5 12z"/>',
  Concierge: '<path d="M4 18a8 8 0 0 1 16 0"/><path d="M2 18h20M12 6V3M9 3h6"/>',
  "Pet Friendly": '<circle cx="7" cy="8" r="1.6"/><circle cx="12" cy="6" r="1.6"/><circle cx="17" cy="8" r="1.6"/><circle cx="19" cy="12.5" r="1.6"/><path d="M12 12c-3 0-6 2-6 5.2 0 1.5 1.2 2.3 2.6 1.7l1-.5a5 5 0 0 1 4.8 0l1 .5c1.4.6 2.6-.2 2.6-1.7C18 14 15 12 12 12z"/>',
  "Beach Club": '<path d="M12 3c5 2 9 6 9 9H3c0-3 4-7 9-9z"/><path d="M12 3v18M4.5 20l15-3"/>',
  Spa: '<path d="M12 21c-3.3 0-6-2.5-6-5.8C6 11 12 3 12 3s6 8 6 12.2c0 3.3-2.7 5.8-6 5.8z"/>',
  "EV Charging": '<path d="M13 3 5 13h5l-1 8 8-10h-5l1-8z"/>',
  Restaurant: '<path d="M3 2v7c0 1.1.9 2 2 2h4a2 2 0 0 0 2-2V2M7 2v20M21 15V2a5 5 0 0 0-5 5v6c0 1.1.9 2 2 2h3Zm0 0v7"/>',
  Golf: '<path d="M6 21V3"/><path d="M6 4c1.6 0 1.6 2 3.2 2s1.6-2 3.2-2 1.6 2 3.2 2v6c-1.6 0-1.6-2-3.2-2s-1.6 2-3.2 2-1.6-2-3.2-2"/>',
  Jacuzzi: '<path d="M3 20a2 2 0 0 1-2-2v-3h22v3a2 2 0 0 1-2 2z"/><path d="M3 15V8a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v7"/><circle cx="8" cy="9" r="1.1"/><circle cx="12" cy="6.5" r="1.1"/><circle cx="16" cy="9" r="1.1"/>',
  Yoga: '<circle cx="12" cy="5" r="2"/><path d="M12 7v4M6 20c0-3 2-5 3-6l3-3 3 3c1 1 3 3 3 6M9 14l-3 3M15 14l3 3"/>',
  "Tennis Court": '<circle cx="9" cy="9" r="6"/><path d="M4.5 6h9M4.5 12h9M9 3a6 6 0 0 1 0 12M9 3a6 6 0 0 0 0 12"/><path d="m13.2 13.2 7.8 7.8"/>',
  Marina: '<circle cx="12" cy="5" r="2"/><path d="M12 7v13M7 12H2a10 10 0 0 0 10 9 10 10 0 0 0 10-9h-5M8 9h8"/>',
};

function amenityIconSVG(name) {
  const path = AMENITY_ICON_PATHS[name];
  if (!path) return "";
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round">${path}</svg>`;
}

function amenityPillHTML(name) {
  return `<span class="amenity-pill"><span class="amenity-icon-badge">${amenityIconSVG(name)}</span>${name}</span>`;
}

// ---------- generic monochrome UI icons (inline, currentColor — no emoji) ----------

const UI_ICON_PATHS = {
  phone: '<path d="M6.6 10.8c1.4 2.8 3.8 5.1 6.6 6.6l2.2-2.2c.3-.3.7-.4 1-.2 1.1.4 2.3.6 3.6.6.6 0 1 .4 1 1V20c0 .6-.4 1-1 1C10.6 21 3 13.4 3 4c0-.6.4-1 1-1h3.2c.6 0 1 .4 1 1 0 1.3.2 2.5.6 3.6.1.4 0 .8-.2 1L6.6 10.8z"/>',
  home: '<path d="M4 20V10l8-6 8 6v10a1 1 0 0 1-1 1h-4v-6H9v6H5a1 1 0 0 1-1-1z"/>',
  pin: '<path d="M12 22s7-7.4 7-12.5A7 7 0 0 0 5 9.5C5 14.6 12 22 12 22z"/><circle cx="12" cy="9.5" r="2.5" fill="var(--panel,#fff)"/>',
  bed: '<path d="M3 18v-7a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2h2v-2a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v7M3 18h18M3 15h18"/>',
  building: '<rect x="5" y="3" width="14" height="18" rx="1"/><path d="M9 7h1M14 7h1M9 11h1M14 11h1M9 15h1M14 15h1M10 21v-3h4v3"/>',
  key: '<circle cx="8" cy="15" r="4"/><path d="M11 12l9-9M17 6l2 2M14 9l2 2"/>',
  wrench: '<path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L4 17l3 3 5.3-5.3a4 4 0 0 0 5.4-5.4l-2.6 2.6-2-2 2.6-2.6z"/>',
  tag: '<path d="M20.5 12.5 12 21l-9-9V4h8l9.5 9z"/><circle cx="7.5" cy="7.5" r="1.5"/>',
  chevronRight: '<path d="M9 6l6 6-6 6"/>',
  x: '<path d="M6 6l12 12M18 6L6 18"/>',
};

function uiIconSVG(name, strokeWidth) {
  const path = UI_ICON_PATHS[name];
  if (!path) return "";
  const isFilled = name === "home" || name === "pin" || name === "building" || name === "tag";
  return `<svg viewBox="0 0 24 24" fill="${isFilled ? "currentColor" : "none"}" stroke="currentColor" stroke-width="${strokeWidth || 1.8}" stroke-linecap="round" stroke-linejoin="round">${path}</svg>`;
}
