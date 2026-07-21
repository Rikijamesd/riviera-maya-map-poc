const map = L.map("map").setView([20.9, -87.6], 8);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  maxZoom: 18,
}).addTo(map);

const markers = new Map(); // id -> L.Marker
let activeId = null;
let detailUnitFilter = null; // null = "All" tab in the detail panel

const searchInput = document.getElementById("searchInput");
const unitFilter = document.getElementById("unitFilter");
const cityFilter = document.getElementById("cityFilter");
const bathroomFilter = document.getElementById("bathroomFilter");
const minPriceInput = document.getElementById("minPrice");
const maxPriceInput = document.getElementById("maxPrice");
const sortBySelect = document.getElementById("sortBy");
const favoritesOnlyFilter = document.getElementById("favoritesOnlyFilter");
const resultsList = document.getElementById("resultsList");
const resultsCount = document.getElementById("resultsCount");
const detailPanel = document.getElementById("detailPanel");

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
  return "$" + usd.toLocaleString("en-US") + " USD";
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
  if (min === max) return `${min} bed`;
  return `${min}–${max} bed`;
}

function bathRangeLabel(dev) {
  const baths = dev.units.map((u) => u.bathrooms);
  const min = Math.min(...baths);
  const max = Math.max(...baths);
  return min === max ? `${min} bath` : `${min}–${max} bath`;
}

function sizeRangeLabel(dev) {
  const sizes = dev.units.map((u) => u.size);
  const min = Math.min(...sizes);
  const max = Math.max(...sizes);
  return min === max ? `${min} m²` : `${min}–${max} m²`;
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

  const matchesFavorite = !favoritesOnlyFilter.checked || favorites.has(dev.id);

  return matchesSearch && matchesUnitAndPrice && matchesCity && matchesFavorite;
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

  resultsCount.textContent = `${filtered.length} development${filtered.length === 1 ? "" : "s"} match your filters`;
  resultsList.innerHTML = "";

  for (const dev of filtered) {
    const isFav = favorites.has(dev.id);
    const item = document.createElement("div");
    item.className = "result-item" + (dev.id === activeId ? " active" : "");
    item.innerHTML = `
      <div class="card-banner" style="${bannerStyle(dev)}">
        ${initials(dev.project)}
        <button class="fav-btn${isFav ? " active" : ""}" title="${isFav ? "Remove from favorites" : "Save to favorites"}" aria-label="Toggle favorite">${isFav ? "★" : "☆"}</button>
      </div>
      <div class="card-body">
        <div class="rname">${dev.project}</div>
        <div class="rmeta">${dev.developer} · ${dev.city}</div>
        <div class="rprice">${priceRangeLabel(dev)}</div>
        <div class="card-stats">
          <span>${bedRangeLabel(dev)}</span>
          <span>${bathRangeLabel(dev)}</span>
          <span>${sizeRangeLabel(dev)}</span>
        </div>
      </div>
    `;
    item.addEventListener("click", () => selectDevelopment(dev.id));
    item.querySelector(".fav-btn").addEventListener("click", (e) => {
      e.stopPropagation();
      toggleFavorite(dev.id);
    });
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

  renderDetailPanel(dev);
  renderResults();
}

function renderDetailPanel(dev) {
  const isFav = favorites.has(dev.id);
  const counts = unitTypeCounts(dev);
  const presentTypes = UNIT_TYPE_ORDER.filter((t) => counts[t] !== undefined);
  const totalAvailable = dev.units.reduce((sum, u) => sum + u.available, 0);

  const tabsHTML = `
    <button class="unit-tab${detailUnitFilter === null ? " active" : ""}" data-type="">All · ${totalAvailable}</button>
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
      <button class="detail-fav-btn${isFav ? " active" : ""}" title="${isFav ? "Remove from favorites" : "Save to favorites"}" aria-label="Toggle favorite">${isFav ? "★" : "☆"}</button>
      <h2>${dev.project}</h2>
    </div>
    <div class="detail-body">
      <div class="developer">${dev.developer}</div>
      <div class="city">${dev.city}</div>
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
favoritesOnlyFilter.addEventListener("change", renderResults);

populateCityFilter();
createMarkers();
renderResults();
