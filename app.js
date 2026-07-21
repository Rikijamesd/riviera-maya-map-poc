const map = L.map("map").setView([20.9, -87.6], 8);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  maxZoom: 18,
}).addTo(map);

const markers = new Map(); // id -> L.Marker
let activeId = null;

const searchInput = document.getElementById("searchInput");
const unitFilter = document.getElementById("unitFilter");
const cityFilter = document.getElementById("cityFilter");
const bathroomFilter = document.getElementById("bathroomFilter");
const minPriceInput = document.getElementById("minPrice");
const maxPriceInput = document.getElementById("maxPrice");
const sortBySelect = document.getElementById("sortBy");
const resultsList = document.getElementById("resultsList");
const resultsCount = document.getElementById("resultsCount");
const detailPanel = document.getElementById("detailPanel");

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

  return matchesSearch && matchesUnitAndPrice && matchesCity;
}

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
    const item = document.createElement("div");
    item.className = "result-item" + (dev.id === activeId ? " active" : "");
    item.innerHTML = `
      <div class="rname">${dev.project}</div>
      <div class="rmeta">${dev.developer} · ${dev.city}</div>
      <div class="rmeta">${priceRangeLabel(dev)}</div>
    `;
    item.addEventListener("click", () => selectDevelopment(dev.id));
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
  activeId = id;
  const dev = DEVELOPMENTS.find((d) => d.id === id);
  if (!dev) return;

  map.panTo([dev.lat, dev.lng]);
  markers.get(id).openPopup();

  const rows = dev.units
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
    <h2>${dev.project}</h2>
    <div class="developer">${dev.developer}</div>
    <div class="city">${dev.city}</div>
    <div class="description">${dev.description}</div>
    <table class="unit-table">
      <thead>
        <tr><th>Unit</th><th>Baths</th><th>Price</th><th>Size</th><th>Available</th></tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;

  renderResults();
}

searchInput.addEventListener("input", renderResults);
unitFilter.addEventListener("change", renderResults);
cityFilter.addEventListener("change", renderResults);
bathroomFilter.addEventListener("change", renderResults);
minPriceInput.addEventListener("input", renderResults);
maxPriceInput.addEventListener("input", renderResults);
sortBySelect.addEventListener("change", renderResults);

populateCityFilter();
createMarkers();
renderResults();
