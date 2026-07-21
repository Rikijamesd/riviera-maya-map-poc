const map = L.map("map").setView([20.9, -87.6], 8);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  maxZoom: 18,
}).addTo(map);

const markers = new Map(); // id -> L.Marker
let activeId = null;
let detailUnitFilter = null; // null = "All" tab in the detail panel
let favoritesOnly = false;
let listOnly = false;
const expandedAmenities = new Set(); // dev ids showing all amenities instead of the first 4

const AMENITY_ICONS = {
  Pool: "🏊",
  Gym: "🏋️",
  "Rooftop Terrace": "🌇",
  "Security 24/7": "🛡️",
  Elevator: "🛗",
  Parking: "🅿️",
  Coworking: "💼",
  "Kids Club": "🧒",
  "BBQ Area": "🔥",
  Concierge: "🛎️",
  "Pet Friendly": "🐾",
  "Beach Club": "🏖️",
  Spa: "💆",
  "EV Charging": "🔌",
};

// Cosmetic only: not a real exchange rate feed, just for dual-currency display like the reference site.
const USD_TO_MXN = 18;
const SQM_TO_SQFT = 10.7639;

const searchInput = document.getElementById("searchInput");
const unitFilter = document.getElementById("unitFilter");
const cityFilter = document.getElementById("cityFilter");
const bathroomFilter = document.getElementById("bathroomFilter");
const minPriceInput = document.getElementById("minPrice");
const maxPriceInput = document.getElementById("maxPrice");
const sortBySelect = document.getElementById("sortBy");
const favoritesToggleBtn = document.getElementById("favoritesToggleBtn");
const resetFiltersBtn = document.getElementById("resetFiltersBtn");
const viewListBtn = document.getElementById("viewListBtn");
const viewMapBtn = document.getElementById("viewMapBtn");
const layoutEl = document.querySelector(".layout");
const resultsList = document.getElementById("resultsList");
const resultsCount = document.getElementById("resultsCount");
const detailPanel = document.getElementById("detailPanel");
const sidebar = document.querySelector(".sidebar");

const FAVORITES_KEY = "riviera-maya-map-poc:favorites";
let favorites = new Set();
try {
  favorites = new Set(JSON.parse(localStorage.getItem(FAVORITES_KEY) || "[]"));
} catch (e) {
  favorites = new Set();
}

function saveFavorites() {
  localStorage.setItem(FAVORITES_KEY, JSON.stringify([...favorites]));
}

function toggleFavorite(id) {
  if (favorites.has(id)) {
    favorites.delete(id);
  } else {
    favorites.add(id);
  }
  saveFavorites();
  if (activeId === id) {
    renderDetailPanel(DEVELOPMENTS.find((d) => d.id === id));
  }
  renderResults();
}

// ---------- formatting helpers ----------

function formatPrice(usd) {
  return "US $" + usd.toLocaleString("en-US");
}

function formatMXN(usd) {
  return "MX $" + Math.round(usd * USD_TO_MXN).toLocaleString("en-US");
}

function devMinPrice(dev) {
  return Math.min(...dev.units.map((u) => u.price));
}

function priceRangeLabel(dev) {
  const prices = dev.units.map((u) => u.price);
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  return min === max ? formatPrice(min) : `${formatPrice(min)} – ${formatPrice(max)}`;
}

function bedRangeLabel(dev) {
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

const UNIT_TYPE_ORDER = ["Studio", "1BR", "2BR", "3BR"];
const UNIT_TYPE_LABEL = { Studio: "Studio", "1BR": "1 Bed", "2BR": "2 Bed", "3BR": "3 Bed" };

// ---------- filters ----------

function populateCityFilter() {
  const cities = [...new Set(DEVELOPMENTS.map((d) => d.city))].sort();
  for (const city of cities) {
    const opt = document.createElement("option");
    opt.value = city;
    opt.textContent = city;
    cityFilter.appendChild(opt);
  }
}

function createMarkers() {
  for (const dev of DEVELOPMENTS) {
    const marker = L.marker([dev.lat, dev.lng]).addTo(map);
    marker.bindPopup(`<b>${dev.project}</b>${dev.developer}<br>${priceRangeLabel(dev)}`);
    marker.on("click", () => selectDevelopment(dev.id));
    markers.set(dev.id, marker);
  }
}

function matchesFilters(dev) {
  const q = searchInput.value.trim().toLowerCase();
  const matchesSearch =
    !q ||
    dev.project.toLowerCase().includes(q) ||
    dev.developer.toLowerCase().includes(q) ||
    dev.city.toLowerCase().includes(q);

  const unitType = unitFilter.value;
  const bathrooms = bathroomFilter.value === "" ? null : Number(bathroomFilter.value);
  const minPrice = minPriceInput.value === "" ? null : Number(minPriceInput.value);
  const maxPrice = maxPriceInput.value === "" ? null : Number(maxPriceInput.value);

  const matchesUnitAndPrice = dev.units.some((u) => {
    if (unitType && u.type !== unitType) return false;
    if (bathrooms !== null && u.bathrooms !== bathrooms) return false;
    if (minPrice !== null && u.price < minPrice) return false;
    if (maxPrice !== null && u.price > maxPrice) return false;
    return true;
  });

  const city = cityFilter.value;
  const matchesCity = !city || dev.city === city;

  const matchesFavorite = !favoritesOnly || favorites.has(dev.id);

  return matchesSearch && matchesUnitAndPrice && matchesCity && matchesFavorite;
}

function resetFilters() {
  searchInput.value = "";
  unitFilter.value = "";
  bathroomFilter.value = "";
  cityFilter.value = "";
  minPriceInput.value = "";
  maxPriceInput.value = "";
  sortBySelect.value = "";
  favoritesOnly = false;
  favoritesToggleBtn.classList.remove("active");
  favoritesToggleBtn.querySelector(".star").textContent = "♡";
  renderResults();
}

// ---------- rendering ----------

function renderResults() {
  const filtered = DEVELOPMENTS.filter(matchesFilters);

  const sortBy = sortBySelect.value;
  if (sortBy === "price-asc") {
    filtered.sort((a, b) => devMinPrice(a) - devMinPrice(b));
  } else if (sortBy === "price-desc") {
    filtered.sort((a, b) => devMinPrice(b) - devMinPrice(a));
  }

  const unitsSum = filtered.reduce((sum, d) => sum + totalAvailable(d), 0);
  resultsCount.textContent = `${filtered.length} Listing${filtered.length === 1 ? "" : "s"} / ${unitsSum} Units matching your search`;
  resultsList.innerHTML = "";

  for (const dev of filtered) {
    const isFav = favorites.has(dev.id);
    const isExpanded = expandedAmenities.has(dev.id);
    const shownAmenities = isExpanded ? dev.amenities : dev.amenities.slice(0, 4);
    const remaining = dev.amenities.length - shownAmenities.length;

    const pillsHTML = shownAmenities
      .map((a) => `<span class="amenity-pill">${AMENITY_ICONS[a] || "•"} ${a}</span>`)
      .join("");
    const moreBtnHTML =
      remaining > 0
        ? `<button class="amenities-more" data-id="${dev.id}">+${remaining} more amenities</button>`
        : isExpanded && dev.amenities.length > 4
          ? `<button class="amenities-more" data-id="${dev.id}">Show less</button>`
          : "";

    const item = document.createElement("div");
    item.className = "result-item" + (dev.id === activeId ? " active" : "");
    item.innerHTML = `
      <div class="card-header-row">
        <span>${totalAvailable(dev)} units available</span>
        <button class="view-all-link">View all →</button>
      </div>
      <div class="card-banner" style="${bannerStyle(dev)}">
        <div class="banner-initials">${initials(dev.project)}</div>
        <span class="type-badge">Condo</span>
        <button class="fav-btn${isFav ? " active" : ""}" title="${isFav ? "Remove from favorites" : "Save to favorites"}" aria-label="Toggle favorite">${isFav ? "★" : "♡"}</button>
        <div class="banner-address">${dev.deliveryDate}</div>
      </div>
      <div class="card-body">
        <div class="rname">${dev.project}</div>
        <div class="rprice-mxn">From ${formatMXN(devMinPrice(dev))}*</div>
        <div class="card-stats">
          <span>${bedRangeLabel(dev)}</span>
          <span>${sizeFromLabel(dev)}</span>
        </div>
        <div class="rlocation">${dev.city}, Mexico</div>
        <div class="rprice-usd-row">From <span class="price-box">${formatPrice(devMinPrice(dev))}</span></div>
        <div class="amenity-pills">${pillsHTML}${moreBtnHTML}</div>
      </div>
    `;
    item.addEventListener("click", () => selectDevelopment(dev.id));
    item.querySelector(".fav-btn").addEventListener("click", (e) => {
      e.stopPropagation();
      toggleFavorite(dev.id);
    });
    item.querySelector(".view-all-link").addEventListener("click", (e) => {
      e.stopPropagation();
      selectDevelopment(dev.id);
    });
    const moreBtn = item.querySelector(".amenities-more");
    if (moreBtn) {
      moreBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        if (expandedAmenities.has(dev.id)) {
          expandedAmenities.delete(dev.id);
        } else {
          expandedAmenities.add(dev.id);
        }
        renderResults();
      });
    }
    resultsList.appendChild(item);
  }

  for (const [id, marker] of markers) {
    const dev = DEVELOPMENTS.find((d) => d.id === id);
    const visible = filtered.includes(dev);
    const el = marker.getElement();
    if (el) el.style.display = visible ? "" : "none";
  }
}

function selectDevelopment(id) {
  if (activeId !== id) detailUnitFilter = null;
  activeId = id;
  const dev = DEVELOPMENTS.find((d) => d.id === id);
  if (!dev) return;

  map.panTo([dev.lat, dev.lng]);
  markers.get(id).openPopup();

  sidebar.classList.add("detail-open");
  renderDetailPanel(dev);
  renderResults();
}

function closeDetail() {
  activeId = null;
  detailUnitFilter = null;
  sidebar.classList.remove("detail-open");
  map.closePopup();
  detailPanel.innerHTML = `<p class="detail-placeholder">Click a pin on the map, or a listing above, to see full development details here.</p>`;
  renderResults();
}

function renderDetailPanel(dev) {
  const isFav = favorites.has(dev.id);
  const counts = unitTypeCounts(dev);
  const presentTypes = UNIT_TYPE_ORDER.filter((t) => counts[t] !== undefined);

  const tabsHTML = `
    <button class="unit-tab${detailUnitFilter === null ? " active" : ""}" data-type="">All · ${totalAvailable(dev)}</button>
    ${presentTypes
      .map(
        (t) =>
          `<button class="unit-tab${detailUnitFilter === t ? " active" : ""}" data-type="${t}">${UNIT_TYPE_LABEL[t]} · ${counts[t]}</button>`
      )
      .join("")}
  `;

  const visibleUnits = detailUnitFilter ? dev.units.filter((u) => u.type === detailUnitFilter) : dev.units;

  const rows = visibleUnits
    .map(
      (u) => `
      <tr>
        <td>${u.type}</td>
        <td>${u.bathrooms}</td>
        <td>${formatPrice(u.price)}</td>
        <td>${u.size} m²</td>
        <td>${u.available}</td>
      </tr>`
    )
    .join("");

  detailPanel.innerHTML = `
    <div class="detail-banner" style="${bannerStyle(dev)}">
      <div class="detail-actions">
        <button class="detail-fav-btn${isFav ? " active" : ""}" title="${isFav ? "Remove from favorites" : "Save to favorites"}" aria-label="Toggle favorite">${isFav ? "★" : "♡"}</button>
        <button class="detail-close-btn" title="Close" aria-label="Close details">✕</button>
      </div>
      <h2>${dev.project}</h2>
    </div>
    <div class="detail-body">
      <div class="developer">${dev.developer}</div>
      <div class="city">${dev.city} · Delivery: ${dev.deliveryDate}</div>
      <div class="description">${dev.description}</div>
      <div class="unit-tabs">${tabsHTML}</div>
      <table class="unit-table">
        <thead>
          <tr><th>Unit</th><th>Baths</th><th>Price</th><th>Size</th><th>Available</th></tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;

  detailPanel.querySelector(".detail-fav-btn").addEventListener("click", () => toggleFavorite(dev.id));
  detailPanel.querySelector(".detail-close-btn").addEventListener("click", closeDetail);
  detailPanel.querySelectorAll(".unit-tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      detailUnitFilter = btn.dataset.type || null;
      renderDetailPanel(dev);
    });
  });
}

searchInput.addEventListener("input", renderResults);
unitFilter.addEventListener("change", renderResults);
cityFilter.addEventListener("change", renderResults);
bathroomFilter.addEventListener("change", renderResults);
minPriceInput.addEventListener("input", renderResults);
maxPriceInput.addEventListener("input", renderResults);
sortBySelect.addEventListener("change", renderResults);

resetFiltersBtn.addEventListener("click", resetFilters);

favoritesToggleBtn.addEventListener("click", () => {
  favoritesOnly = !favoritesOnly;
  favoritesToggleBtn.classList.toggle("active", favoritesOnly);
  favoritesToggleBtn.querySelector(".star").textContent = favoritesOnly ? "★" : "♡";
  renderResults();
});

viewListBtn.addEventListener("click", () => {
  listOnly = true;
  viewListBtn.classList.add("active");
  viewMapBtn.classList.remove("active");
  layoutEl.classList.add("list-only");
  map.invalidateSize();
});

viewMapBtn.addEventListener("click", () => {
  listOnly = false;
  viewMapBtn.classList.add("active");
  viewListBtn.classList.remove("active");
  layoutEl.classList.remove("list-only");
  map.invalidateSize();
});

populateCityFilter();
createMarkers();
renderResults();
