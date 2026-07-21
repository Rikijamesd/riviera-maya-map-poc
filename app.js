const map = L.map("map").setView([20.9, -87.6], 8);

const streetLayer = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  maxZoom: 18,
}).addTo(map);

const satelliteLayer = L.tileLayer(
  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
  { attribution: "Tiles &copy; Esri", maxZoom: 18 }
);

L.control.layers({ Street: streetLayer, Satellite: satelliteLayer }).addTo(map);

const markers = new Map(); // id -> L.Marker
let favoritesOnly = false;
const expandedAmenities = new Set(); // dev ids showing all amenities instead of the first 4
let favorites = loadFavorites();

const searchInput = document.getElementById("searchInput");
const propertyTypeFilter = document.getElementById("propertyTypeFilter");
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

function detailUrl(id) {
  return `detail.html?id=${id}`;
}

function goToDetail(id) {
  window.location.href = detailUrl(id);
}

function toggleFavorite(id) {
  if (favorites.has(id)) {
    favorites.delete(id);
  } else {
    favorites.add(id);
  }
  saveFavorites(favorites);
  renderResults();
}

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

function shortDeliveryLabel(dev) {
  if (/ready/i.test(dev.deliveryDate)) return "Now";
  const m = dev.deliveryDate.match(/([A-Za-z]+)\.?\s+(\d{4})/);
  if (!m) return dev.deliveryDate;
  return `${m[1].slice(0, 3)} ${m[2].slice(2)}`;
}

function dateBubbleIcon(dev) {
  return L.divIcon({
    className: "date-marker",
    html: `<div class="date-bubble">${shortDeliveryLabel(dev)}</div>`,
    iconSize: [56, 24],
    iconAnchor: [28, 30],
  });
}

function createMarkers() {
  for (const dev of DEVELOPMENTS) {
    const marker = L.marker([dev.lat, dev.lng], { icon: dateBubbleIcon(dev) }).addTo(map);
    marker.bindPopup(
      `<b>${dev.project}</b>${dev.developer}<br>${priceRangeLabel(dev)}<br><a href="${detailUrl(dev.id)}">View details →</a>`
    );
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
    if (bathrooms !== null && u.bathrooms < bathrooms) return false;
    if (minPrice !== null && u.price < minPrice) return false;
    if (maxPrice !== null && u.price > maxPrice) return false;
    return true;
  });

  const city = cityFilter.value;
  const matchesCity = !city || dev.city === city;

  const propertyType = propertyTypeFilter.value;
  const matchesPropertyType = !propertyType || dev.propertyType === propertyType;

  const matchesFavorite = !favoritesOnly || favorites.has(dev.id);

  return matchesSearch && matchesUnitAndPrice && matchesCity && matchesPropertyType && matchesFavorite;
}

function resetFilters() {
  searchInput.value = "";
  propertyTypeFilter.value = "";
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

    const pillsHTML = shownAmenities.map(amenityPillHTML).join("");
    const moreBtnHTML =
      remaining > 0
        ? `<button class="amenities-more" data-id="${dev.id}">+${remaining} more amenities</button>`
        : isExpanded && dev.amenities.length > 4
          ? `<button class="amenities-more" data-id="${dev.id}">Show less</button>`
          : "";

    const item = document.createElement("div");
    item.className = "result-item";
    item.innerHTML = `
      <div class="card-header-row">
        <span>${totalAvailable(dev)} units available</span>
        <button class="view-all-link">View all →</button>
      </div>
      <div class="card-banner" style="${bannerStyle(dev)}">
        <div class="banner-initials">${initials(dev.project)}</div>
        ${dev.photos && dev.photos[0] ? `<img src="${driveImageUrl(dev.photos[0], 500)}" alt="${dev.project}" loading="lazy" onerror="this.style.display='none'">` : ""}
        <span class="type-badge">${dev.propertyType}</span>
        <button class="fav-btn${isFav ? " active" : ""}" title="${isFav ? "Remove from favorites" : "Save to favorites"}" aria-label="Toggle favorite">${isFav ? "★" : "♡"}</button>
        <div class="banner-address">${dev.deliveryDate}</div>
      </div>
      <div class="card-body">
        <div class="rname">${dev.project}</div>
        <div class="price-row">From ${formatMoney(devMinPrice(dev))}</div>
        <div class="card-stats">
          <span>${bedRangeLabel(dev)}</span>
          <span>${sizeFromLabel(dev)}</span>
        </div>
        <div class="rlocation">${dev.city}, Mexico</div>
        <div class="amenity-pills">${pillsHTML}${moreBtnHTML}</div>
      </div>
    `;
    item.addEventListener("click", () => goToDetail(dev.id));
    item.querySelector(".fav-btn").addEventListener("click", (e) => {
      e.stopPropagation();
      toggleFavorite(dev.id);
    });
    item.querySelector(".view-all-link").addEventListener("click", (e) => {
      e.stopPropagation();
      goToDetail(dev.id);
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
    marker.setPopupContent(
      `<b>${dev.project}</b>${dev.developer}<br>${priceRangeLabel(dev)}<br><a href="${detailUrl(dev.id)}">View details →</a>`
    );
  }
}

searchInput.addEventListener("input", renderResults);
propertyTypeFilter.addEventListener("change", renderResults);
unitFilter.addEventListener("change", renderResults);
cityFilter.addEventListener("change", renderResults);
bathroomFilter.addEventListener("change", renderResults);
minPriceInput.addEventListener("input", renderResults);
maxPriceInput.addEventListener("input", renderResults);
sortBySelect.addEventListener("change", renderResults);

resetFiltersBtn.addEventListener("click", resetFilters);

// Close an open Price/More dropdown when clicking anywhere outside it — <details>
// has no built-in "close on outside click" behavior.
document.addEventListener("click", (e) => {
  document.querySelectorAll(".filter-dropdown[open]").forEach((dropdown) => {
    if (!dropdown.contains(e.target)) dropdown.removeAttribute("open");
  });
});

favoritesToggleBtn.addEventListener("click", () => {
  favoritesOnly = !favoritesOnly;
  favoritesToggleBtn.classList.toggle("active", favoritesOnly);
  favoritesToggleBtn.querySelector(".star").textContent = favoritesOnly ? "★" : "♡";
  renderResults();
});

viewListBtn.addEventListener("click", () => {
  viewListBtn.classList.add("active");
  viewMapBtn.classList.remove("active");
  layoutEl.classList.add("list-only");
  map.invalidateSize();
});

viewMapBtn.addEventListener("click", () => {
  viewMapBtn.classList.add("active");
  viewListBtn.classList.remove("active");
  layoutEl.classList.remove("list-only");
  map.invalidateSize();
});

async function init() {
  populateCityFilter();
  createMarkers();
  setupCurrencyToggle(renderResults);
  renderResults();

  await fetchLiveExchangeRate();
  document.getElementById("exchangeRateLabel").textContent = exchangeRateLabel();
  renderResults(); // re-render with the live rate now that it's resolved
}

init();
