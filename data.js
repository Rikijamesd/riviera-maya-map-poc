// Real project names, delivery dates, photos, and per-unit prices/sizes pulled from the
// "BROKERS - iMexico 2026" Google Drive folder shared for this project (organized by
// city > sales stage > project > "Prices and Availability" PDF).
//
// Each entry in `units` below is ONE specific real unit from that project's price list
// PDF, filtered to units marked DISPONIBLE/AVAILABLE (not sold/reserved) as of when the
// PDF was pulled — `unitLabel` is the real unit/lot number from the document. Prices and
// sizes are real; MXN prices were converted to USD at an approximate fixed rate (18
// MXN = 1 USD), not a live exchange rate. Bathroom counts are real only where the source
// PDF had an explicit baños column (ALTRA, ALBA); elsewhere they're a reasonable estimate
// from bedroom count. Amenities are still illustrative, not from a verified amenities
// list document. TIERRA MADRE's PDF only covers raw land lots (no bedrooms apply), not
// built houses — its prices reflect lot cost, not a finished home.
//
// Developer names are only filled in where a source doc explicitly named one (DOMA, GR4,
// Macondo, Algi); the rest say "Developer not confirmed" rather than guessing.

function driveImageUrl(fileId, width) {
  return `https://lh3.googleusercontent.com/d/${fileId}=w${width || 800}`;
}

const DEVELOPMENTS = [
  {
    id: 1,
    project: "ALTRA",
    developer: "Developer not confirmed",
    city: "Playa del Carmen, Quintana Roo",
    lat: 20.6296, lng: -87.0739,
    deliveryDate: "Ready to move in",
    propertyType: "Condo",
    description: "Pre-sale condo development in Playa del Carmen, delivered and ready to move in.",
    amenities: ["Pool", "Gym", "Rooftop Terrace", "Coworking", "Security 24/7"],
    photos: ["1o8tIW6i7o0AoEGZrca4NwA2NHDOvw_aN", "1axpTi0rEyxMKkw4KBuQiBnRhNzuJ1qU4", "19vbXNSAbEmH0T-sPJftI_JpmN9CiGuZZ", "1MNKWbSficPTfRO3BWQLLAOJ0QdzNnzqN"],
    units: [
      { unitLabel: "208A", type: "1BR", bedrooms: 1, bathrooms: 1, price: 229108, size: 37.53, available: 1 },
    ],
  },
  {
    id: 2,
    project: "TIERRA MADRE",
    developer: "Developer not confirmed",
    city: "Playa del Carmen, Quintana Roo",
    lat: 20.6450, lng: -87.0850,
    deliveryDate: "Dec 2026",
    propertyType: "Land",
    description: "Raw land lots (not built houses) south of Playa del Carmen. Prices below reflect lot cost only, from the project's lot price list.",
    amenities: ["Security 24/7", "Beach Club", "BBQ Area"],
    photos: ["1zR7RP1CmSeXbHofYixYxy1lf7fikOkEa", "1hy02ChvolB7xKrYdB7fU0Z29dTXlC8t5", "1KklwjOVPzwH0Pybgup6DoIgIzf5Pho3Z", "1yR8X3JezjQEqC3X_eYgXVpn2BFMjdKBi"],
    units: [
      { unitLabel: "Lote 2", type: "Land", bedrooms: 0, bathrooms: 0, price: 134919, size: 300, available: 1 },
      { unitLabel: "Lote 25", type: "Land", bedrooms: 0, bathrooms: 0, price: 80951, size: 180, available: 1 },
    ],
  },
  {
    id: 3,
    project: "THE LANDMARK",
    developer: "GR4",
    city: "Playa del Carmen, Quintana Roo",
    lat: 20.6244, lng: -87.0750,
    deliveryDate: "Dec 2028",
    propertyType: "Condo",
    description: "Pre-sale condo tower in Playa del Carmen by developer GR4.",
    amenities: ["Pool", "Coworking", "Gym", "Rooftop Terrace", "Concierge"],
    photos: ["1_2fNNLqmk2uKKPJuCnLojwiQ6Xa_rCiP", "1UE1DAsynM5lpzqUYGGd-2B7BcZVDeCYz", "1Wely0d7Pv4ltOeghk9Jebk70F-n2enFb", "1e8QGEzi9v8g5h3QrJCZy6weilDcJrk-v"],
    units: [
      { unitLabel: "108", type: "Studio", bedrooms: 0, bathrooms: 1, price: 177241, size: 26.60, available: 1 },
      { unitLabel: "113", type: "1BR", bedrooms: 1, bathrooms: 1, price: 242143, size: 43.60, available: 1 },
      { unitLabel: "202", type: "2BR", bedrooms: 2, bathrooms: 2, price: 446600, size: 86.56, available: 1 },
      { unitLabel: "223", type: "2BR", bedrooms: 2, bathrooms: 2, price: 459395, size: 89.04, available: 1 },
    ],
  },
  {
    id: 4,
    project: "MACONDO PLAYACAR",
    developer: "Macondo",
    city: "Playa del Carmen, Quintana Roo",
    lat: 20.6080, lng: -87.0913,
    deliveryDate: "Dec 2027",
    propertyType: "Villa",
    description: "Pre-sale condo development in Playacar by developer Macondo, which also has projects in Tulum and elsewhere in Playa del Carmen (Corazón, Mayakoba, PDC Fase 2/3, Punta Esmeralda).",
    amenities: ["Pool", "Gym", "Kids Club", "Security 24/7", "Parking"],
    photos: ["1mIoqOnJlowUSljcBCI0VJJ0X6oBYqL4v", "1sskaHeRAJcwadDZlzcb0Z7kx02YjClY9", "1zAXoJVdL3pIUuekPvE2PqlwLTHpfxLav", "1nkIkIWQFQ1Jd6y_LXyi7K936bN3xZA15"],
    units: [
      { unitLabel: "GH-01A", type: "1BR", bedrooms: 1, bathrooms: 1.5, price: 434394, size: 201.21, available: 1 },
      { unitLabel: "GH-04", type: "2BR", bedrooms: 2, bathrooms: 2, price: 695852, size: 237.03, available: 1 },
      { unitLabel: "GH-02", type: "3BR", bedrooms: 3, bathrooms: 2.5, price: 708815, size: 255.43, available: 1 },
    ],
  },
  {
    id: 5,
    project: "BAGÁ RIVIERA",
    developer: "DOMA",
    city: "Playa del Carmen, Quintana Roo",
    lat: 20.6350, lng: -87.0780,
    deliveryDate: "Ready to move in",
    propertyType: "Condo",
    description: "Condo development in Playa del Carmen by developer DOMA (Desarrollos Doma), delivered and ready to move in. Nearly sold out — only 2 units remain listed as available.",
    amenities: ["Pool", "Coworking", "Parking"],
    photos: ["1JsXr1C4nSn3AK-wkWMW2gU8d2mEmBP4P", "1qwVBaNpiCo25Dh6kAclnzNL0EWww7LvY", "1PB21AYrbWUodm4oN2byZE_0iarT8qEfx", "1ymHS_QUh2DPZQYnp4NasHDmhlL0FCHdp"],
    units: [
      { unitLabel: "PB01", type: "1BR", bedrooms: 1, bathrooms: 1, price: 217000, size: 58.25, available: 1 },
      { unitLabel: "PB03", type: "1BR", bedrooms: 1, bathrooms: 1, price: 220000, size: 63.45, available: 1 },
    ],
  },
  {
    id: 6,
    project: "SAMSARA",
    developer: "GR4",
    city: "Tulum, Quintana Roo",
    lat: 20.2114, lng: -87.4654,
    deliveryDate: "Ready to move in",
    propertyType: "Condo",
    description: "Condo development in Tulum by developer GR4 (also behind The Landmark in Playa del Carmen), delivered and ready to move in.",
    amenities: ["Pool", "Spa", "Beach Club", "Security 24/7"],
    photos: ["1G9FJiPtp_SEyByhedcM494dVHBrDrVTK", "1tfQeOV1qrfk1C6u876ArHTv_qke6USiC", "1aIzGTQV2CYbBIjq-sD_59NyQskTJRLSr", "1gfP0MvLlUhi9dASUDe79CvN4DAF6NFLe"],
    units: [
      { unitLabel: "114TC", type: "2BR", bedrooms: 2, bathrooms: 2, price: 353668, size: 126.31, available: 1 },
      { unitLabel: "127TC", type: "2BR", bedrooms: 2, bathrooms: 2, price: 383940, size: 127.98, available: 1 },
      { unitLabel: "208TC", type: "2BR", bedrooms: 2, bathrooms: 2, price: 283247, size: 91.37, available: 1 },
    ],
  },
  {
    id: 7,
    project: "XUNIK",
    developer: "Algi",
    city: "Tulum, Quintana Roo",
    lat: 20.2200, lng: -87.4700,
    deliveryDate: "Ready to move in",
    propertyType: "Condo",
    description: "Condo development in Tulum by Desarrolladora Inmobiliaria Algi, built by Constructora Impala and designed by SER Arquitectura. Delivered and ready to move in.",
    amenities: ["Pool", "Gym", "Beach Club", "Concierge"],
    photos: ["1nqz5Z6tfMzqj9OWSz6IbJ7319VpPPSKV", "1rX9Z7Ef33L3a0-LTtvZLsES3L_Ld3uiJ", "1N0kMilvhh2SGQy9fpFm98hWhjfC2W-zS", "1U4GSdSGHT_G8AffxD4IhcNSngCTje1xU"],
    units: [
      { unitLabel: "PB102", type: "Studio", bedrooms: 0, bathrooms: 1, price: 122422, size: 43.46, available: 1 },
      { unitLabel: "PB104", type: "1BR", bedrooms: 1, bathrooms: 1, price: 130688, size: 57.21, available: 1 },
      { unitLabel: "PB105", type: "2BR", bedrooms: 2, bathrooms: 2, price: 204557, size: 115.98, available: 1 },
    ],
  },
  {
    id: 8,
    project: "PARAMAR BLACK",
    developer: "Developer not confirmed",
    city: "Tulum, Quintana Roo",
    lat: 20.2050, lng: -87.4600,
    deliveryDate: "Ready to move in",
    propertyType: "Condo",
    description: "Condo development in Tulum, delivered and ready to move in.",
    amenities: ["Pool", "Rooftop Terrace", "Security 24/7"],
    photos: ["1bXMBMhCgGF7yRZLzPBGl8S5JEADMU9Ok", "19ajzndKDpXzcjpS0pgJTnlL2CeS3f4pJ", "1Lq9f-3lhkGjuovR4PO4tWOiYRTbU4auO", "12d2G8XPoJvCQrZVNzSe_jPrN5m55Vrvj"],
    units: [
      { unitLabel: "101", type: "2BR", bedrooms: 2, bathrooms: 2, price: 251005, size: 80.35, available: 1 },
      { unitLabel: "107", type: "2BR", bedrooms: 2, bathrooms: 2, price: 232096, size: 82.80, available: 1 },
      { unitLabel: "211", type: "2BR", bedrooms: 2, bathrooms: 2, price: 275400, size: 92.50, available: 1 },
    ],
  },
  {
    id: 9,
    project: "SEREMONIA HÁBITAT",
    developer: "Developer not confirmed",
    city: "Tulum, Quintana Roo",
    lat: 20.1950, lng: -87.4550,
    deliveryDate: "Dec 2027",
    propertyType: "Villa",
    description: "Pre-sale villa development in Tulum, includes a dedicated beach club. Units are lock-off villas, not condo apartments.",
    amenities: ["Pool", "Beach Club", "Gym"],
    photos: ["14b0A1yndmehJIACjPgXGpBRjqRc1AVe4", "1AMr9PZVjJIpQrJnFTuraCsZvFrwMoDVA", "14PJMgIAhBY1czY8TVUigQ_z0MibaN4pb", "1Ta4JVbX8ZzB2cZ5L2yVqHRguq6sDkNAv"],
    units: [
      { unitLabel: "4.9", type: "3BR", bedrooms: 3, bathrooms: 3, price: 352778, size: 225, available: 1 },
      { unitLabel: "4.10", type: "2BR", bedrooms: 2, bathrooms: 2, price: 288000, size: 225, available: 1 },
    ],
  },
  {
    id: 10,
    project: "HAMA",
    developer: "Developer not confirmed",
    city: "Mahahual, Quintana Roo",
    lat: 18.7216, lng: -87.7042,
    deliveryDate: "Ready to move in",
    propertyType: "Condo",
    description: "Condo development in Mahahual, delivered and ready to move in. Nearly sold out — only 2 units remain listed as available.",
    amenities: ["Pool", "Beach Club", "Parking"],
    photos: ["1qkiWEmUVeYHIxiFJmQrLvqqdcoZ_hLFG", "1XAevYTMt_7iNvFJpOhkx5zCDH8jJOj8x", "1ZxKa4HYRcmYdljLPTFQgBJmzAZQZrV99", "1VZTDZWHHmFTaYqga5rcS-M1g2IbPrliA"],
    units: [
      { unitLabel: "201A", type: "Studio", bedrooms: 0, bathrooms: 1, price: 235000, size: 46.48, available: 1 },
      { unitLabel: "204A", type: "Studio", bedrooms: 0, bathrooms: 1, price: 235000, size: 46.48, available: 1 },
    ],
  },
  {
    id: 11,
    project: "ALBA",
    developer: "Developer not confirmed",
    city: "Cancún, Quintana Roo",
    lat: 21.1619, lng: -86.8515,
    deliveryDate: "Ready to move in",
    propertyType: "Condo",
    description: "Luxury condo development in Cancún, delivered and ready to move in. Mostly sold out — only a few high-end units remain listed as available.",
    amenities: ["Pool", "Gym", "Security 24/7", "Parking"],
    photos: ["16r44gMFYYqXayNN62tRuglk28mfPf5bN", "1tQxZ1S_-BtdtMrARdOgnWhab1U7i0bj0", "1SQ8IL-LeGvvioZAFo_wwvCDfYm1IrD7A", "1sZBLgDJweeW9WBkHbcPuLa81ZDPL2aoC"],
    units: [
      { unitLabel: "106", type: "3BR", bedrooms: 3, bathrooms: 3.5, price: 1084444, size: 236.80, available: 1 },
      { unitLabel: "304", type: "3BR", bedrooms: 3, bathrooms: 3.5, price: 1269444, size: 244.00, available: 1 },
    ],
  },
  {
    id: 12,
    project: "ALUX 33",
    developer: "Developer not confirmed",
    city: "Puerto Morelos, Quintana Roo",
    lat: 20.8477, lng: -86.8766,
    deliveryDate: "Sept 2026",
    propertyType: "Condo",
    description: "Pre-sale condo tower in Puerto Morelos with a rooftop lounge, across two towers (Agua and Fuego).",
    amenities: ["Pool", "Rooftop Terrace", "Gym"],
    photos: ["1ZO_th26VKfiHgumLftQQCggaJuFNo2jR", "1xNmSsiaxdNVQyciNLHEEcqAgiMzB_-OX", "14u7eGnej-MGrlLAu0oFaaFgKuCLGZX1e", "1OFJAD746wd0CffO7-a91pVvvCpUfUsx1"],
    units: [
      { unitLabel: "Agua 101", type: "2BR", bedrooms: 2, bathrooms: 2, price: 252281, size: 48.48, available: 1 },
      { unitLabel: "Agua 201", type: "2BR", bedrooms: 2, bathrooms: 2, price: 267901, size: 53.53, available: 1 },
      { unitLabel: "Fuego 602", type: "3BR", bedrooms: 3, bathrooms: 2.5, price: 662613, size: 107.08, available: 1 },
    ],
  },
];
