const params = new URLSearchParams(window.location.search);
const devId = Number(params.get("id"));
const dev = DEVELOPMENTS.find((d) => d.id === devId);

let favorites = loadFavorites();
let unitTypeFilter = null; // null = "All" tab

if (!dev) {
  document.querySelector(".detail-page").innerHTML =
    '<p style="padding:24px;">Development not found. <a href="index.html">Back to map</a></p>';
} else {
  init();
}

async function init() {
  document.title = `${dev.project} — Yucatán Peninsula Developments`;

  const [city, state] = dev.city.split(",").map((s) => s.trim());
  document.getElementById("breadcrumbState").textContent = state || dev.city;
  document.getElementById("breadcrumbCity").textContent = city;

  document.getElementById("devTitle").textContent = dev.project;
  document.getElementById("devStatusLine").textContent = `Available · Earliest Delivery: ${dev.deliveryDate}`;

  renderFavButton();
  document.getElementById("favBtn").addEventListener("click", () => {
    if (favorites.has(dev.id)) {
      favorites.delete(dev.id);
    } else {
      favorites.add(dev.id);
    }
    saveFavorites(favorites);
    renderFavButton();
  });

  renderGallery();
  renderPriceBlock();
  document.getElementById("viewPricesLink").addEventListener("click", () => activateTab("prices"));
  renderFactList();
  renderPhases();
  renderAmenities();
  renderDeveloperInfo();
  renderMap();

  renderUnitTabs();
  renderUnitTable();

  setupTabs();
  setupContactForm();

  await fetchLiveExchangeRate();
  document.getElementById("exchangeRateLabel").textContent = exchangeRateLabel();
  renderPriceBlock(); // re-render with the live rate now that it's resolved
}

function renderFavButton() {
  const isFav = favorites.has(dev.id);
  const btn = document.getElementById("favBtn");
  btn.className = "gallery-fav-btn" + (isFav ? " active" : "");
  btn.innerHTML = isFav
    ? '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 21s-7.5-4.6-10-9.3C.4 8.2 2 4.5 5.6 4.5c2 0 3.6 1.2 4.4 2.8.8-1.6 2.4-2.8 4.4-2.8 3.6 0 5.2 3.7 3.6 7.2C19.5 16.4 12 21 12 21z"/></svg>'
    : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 21s-7.5-4.6-10-9.3C.4 8.2 2 4.5 5.6 4.5c2 0 3.6 1.2 4.4 2.8.8-1.6 2.4-2.8 4.4-2.8 3.6 0 5.2 3.7 3.6 7.2C19.5 16.4 12 21 12 21z"/></svg>';
  btn.title = isFav ? "Remove from favorites" : "Save to favorites";
}

function renderGallery() {
  const main = document.getElementById("galleryMainContent");
  const wrap = document.getElementById("galleryMain");
  const photos = dev.photos || [];

  if (photos[0]) {
    wrap.style.cssText = "";
    main.innerHTML = `<img src="${driveImageUrl(photos[0], 1200)}" alt="${dev.project}" onerror="this.replaceWith(Object.assign(document.createElement('div'), {className: 'gallery-initials', textContent: '${initials(dev.project)}'})); this.parentElement.style.cssText = '${bannerStyle(dev)}';">`;
    document.getElementById("galleryCounter").textContent = `1 / ${photos.length}`;
  } else {
    wrap.style.cssText = bannerStyle(dev);
    main.innerHTML = `<div class="gallery-initials">${initials(dev.project)}</div><div class="gallery-caption">No photos available</div>`;
    document.getElementById("galleryCounter").textContent = "";
  }

  const thumbs = document.getElementById("galleryThumbs");
  const thumbPhotos = photos.slice(1, 4);
  if (thumbPhotos.length) {
    thumbs.innerHTML = thumbPhotos
      .map((id) => `<div class="gallery-thumb"><img src="${driveImageUrl(id, 500)}" alt="${dev.project}" onerror="this.parentElement.style.display='none'"></div>`)
      .join("");
  } else {
    const captions = ["Exterior", "Interior", "Amenities"];
    thumbs.innerHTML = captions
      .map(
        (cap, i) => `
        <div class="gallery-thumb" style="${bannerStyle({ id: dev.id + i + 1 })}">
          <div class="gallery-thumb-caption">${cap}</div>
        </div>`
      )
      .join("");
  }
}

function renderPriceBlock() {
  document.getElementById("priceMXN").textContent = `From: ${formatMXN(devMinPrice(dev))}`;
  document.getElementById("priceUSD").textContent = formatPrice(devMinPrice(dev));
}

function renderFactList() {
  const avail = totalAvailable(dev);
  const totalUnits = avail + Math.round(avail * 0.25); // placeholder "some already sold" ratio, not real data
  const counts = unitTypeCounts(dev);
  const presentTypes = UNIT_TYPE_ORDER.filter((t) => counts[t] !== undefined);
  const bedSummary = presentTypes.map((t) => UNIT_TYPE_LABEL[t]).join(", ").replace(/,([^,]*)$/, " &$1");

  document.getElementById("factList").innerHTML = `
    <div class="fact-row">${uiIconSVG("pin")} <span>${dev.city}, Mexico</span></div>
    <div class="fact-row">${uiIconSVG("home")} <span>${avail} units available / ${totalUnits} total units</span></div>
    <div class="fact-row">${uiIconSVG("building")} <span>Property type: ${dev.propertyType}</span></div>
    <div class="fact-row">${uiIconSVG("bed")} <span>${bedSummary} units available</span></div>
    <div class="fact-row"><strong>Earliest Delivery:</strong> <span>${dev.deliveryDate}</span></div>
  `;
}

function renderPhases() {
  document.getElementById("phasesBody").innerHTML = `
    <div class="phase-row">✓ Phase 1: Delivery ${dev.deliveryDate}</div>
  `;
}

function renderAmenities() {
  document.getElementById("amenitiesBody").innerHTML = `
    <div class="amenities-grid">${dev.amenities.map(amenityPillHTML).join("")}</div>
  `;
}

function renderDeveloperInfo() {
  document.getElementById("developerBody").innerHTML = `
    <p><strong>${dev.developer}</strong></p>
    <p>${dev.description}</p>
  `;
}

function renderMap() {
  const detailMap = L.map("detailMap", { zoomControl: true }).setView([dev.lat, dev.lng], 13);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 18,
  }).addTo(detailMap);
  L.marker([dev.lat, dev.lng]).addTo(detailMap).bindPopup(`<b>${dev.project}</b>`);
}

function renderUnitTabs() {
  const counts = unitTypeCounts(dev);
  const presentTypes = UNIT_TYPE_ORDER.filter((t) => counts[t] !== undefined);

  document.getElementById("unitTabs").innerHTML = `
    <button class="unit-tab${unitTypeFilter === null ? " active" : ""}" data-type="">All · ${totalAvailable(dev)}</button>
    ${presentTypes
      .map(
        (t) =>
          `<button class="unit-tab${unitTypeFilter === t ? " active" : ""}" data-type="${t}">${UNIT_TYPE_LABEL[t]} · ${counts[t]}</button>`
      )
      .join("")}
  `;

  document.querySelectorAll(".unit-tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      unitTypeFilter = btn.dataset.type || null;
      renderUnitTabs();
      renderUnitTable();
    });
  });
}

function expandUnits() {
  // Each entry in dev.units is already one specific real unit (unitLabel is the
  // real unit/lot number from the project's price list PDF).
  return dev.units.map((u) => ({
    label: u.unitLabel || u.type,
    type: u.type,
    bedrooms: u.bedrooms,
    bathrooms: u.bathrooms,
    size: u.size,
    price: u.price,
  }));
}

function renderUnitTable() {
  const avail = totalAvailable(dev);
  document.getElementById("unitsAvailableLine").textContent = `${avail} matching units available`;

  const rows = expandUnits().filter((r) => !unitTypeFilter || r.type === unitTypeFilter);
  document.getElementById("unitTableBody").innerHTML = rows
    .map(
      (r) => `
      <tr>
        <td>${r.label}</td>
        <td>${r.bedrooms === 0 ? "Studio" : r.bedrooms}</td>
        <td>${r.bathrooms}</td>
        <td>${r.size} m²</td>
        <td>${formatPrice(r.price)}</td>
        <td>Available</td>
      </tr>`
    )
    .join("");
}

function activateTab(tab) {
  document.querySelectorAll(".detail-tab").forEach((btn) => btn.classList.toggle("active", btn.dataset.tab === tab));
  document.getElementById("tabDetails").classList.toggle("active", tab === "details");
  document.getElementById("tabPrices").classList.toggle("active", tab === "prices");
}

function setupTabs() {
  document.querySelectorAll(".detail-tab").forEach((btn) => {
    btn.addEventListener("click", () => activateTab(btn.dataset.tab));
  });
}

function setupContactForm() {
  document.getElementById("contactHeading").textContent = `Any questions about ${dev.project}?`;
  document.getElementById("contactForm").addEventListener("submit", (e) => {
    e.preventDefault();
    document.getElementById("contactResult").textContent =
      "Thanks! (This is a prototype — nothing was actually sent.)";
  });
}
