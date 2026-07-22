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
// from bedroom count. TIERRA MADRE's PDF only covers raw land lots (no bedrooms apply), not
// built houses — its prices reflect lot cost, not a finished home.
//
// Developer names are only filled in where a source doc explicitly named one (DOMA, GR4,
// Macondo, Algi); the rest say "Developer not confirmed" rather than guessing.
//
// `description` and `amenities` were researched per-project (developer sites, Maya Ocean,
// and third-party listing pages) rather than invented; a couple of internal-document-only
// details (e.g. ALUX 33's "Agua"/"Fuego" tower names, from its real unit labels below)
// aren't published anywhere externally but are trusted since they come from the source
// price-list PDF. `pointsOfInterest` distances are straight-line (great-circle) km computed
// from each project's coordinates to a real, sourced landmark location (airport, nearest
// Tren Maya station, ADO bus terminal, hospital, and a named public beach) — not driving
// distances, and not pulled from a single authoritative per-project source.

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
    description: "Luxury 6-floor condo tower in downtown Playa del Carmen, a block from the beach, with a design concept inspired by the bioluminescence of Isla Holbox. Offers 70 studio–2BR units aimed at investors and buyers wanting a walkable, central location. Delivered and ready to move in.",
    amenities: ["Pool", "Jacuzzi", "Spa", "Gym", "Rooftop Terrace", "Coworking", "Security 24/7", "Parking"],
    pointsOfInterest: [
      { label: "Airport", name: "Cancún International Airport (CUN)", distanceKm: 49.7 },
      { label: "Train Station", name: "Tren Maya – Playa del Carmen", distanceKm: 7.0 },
      { label: "Bus Station", name: "ADO Playa del Carmen", distanceKm: 1.1 },
      { label: "Hospital", name: "Hospiten Riviera Maya", distanceKm: 2.6 },
      { label: "Public Beach", name: "Playa Centro (Parque Fundadores)", distanceKm: 0.2 },
    ],
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
    description: "A 15+ hectare raw-land community south of Playa del Carmen, offering 403 custom-build lots (238 still available) inside a jungle sanctuary with shared wellness and recreation grounds. About 12 minutes from Playa Esmeralda and Xcalacoco beaches. Prices below reflect lot cost only, from the project's lot price list.",
    amenities: ["Pool", "Spa", "Gym", "Kids Club", "Tennis Court", "Beach Club", "BBQ Area", "Security 24/7"],
    pointsOfInterest: [
      { label: "Airport", name: "Cancún International Airport (CUN)", distanceKm: 48.6 },
      { label: "Train Station", name: "Tren Maya – Playa del Carmen", distanceKm: 5.0 },
      { label: "Bus Station", name: "ADO Playa del Carmen", distanceKm: 1.9 },
      { label: "Hospital", name: "Hospiten Riviera Maya", distanceKm: 3.3 },
      { label: "Public Beach", name: "Playa Centro (Parque Fundadores)", distanceKm: 2.3 },
    ],
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
    description: "Pre-sale condo tower in Playa del Carmen Centro, steps from Fifth Avenue and the beach. Its standout feature is the \"Sky Club,\" a half-acre rooftop amenity deck.",
    amenities: ["Pool", "Rooftop Terrace", "Restaurant", "Yoga", "Spa", "Gym", "Coworking", "Concierge", "Security 24/7"],
    pointsOfInterest: [
      { label: "Airport", name: "Cancún International Airport (CUN)", distanceKm: 50.2 },
      { label: "Train Station", name: "Tren Maya – Playa del Carmen", distanceKm: 7.4 },
      { label: "Bus Station", name: "ADO Playa del Carmen", distanceKm: 1.1 },
      { label: "Hospital", name: "Hospiten Riviera Maya", distanceKm: 2.3 },
      { label: "Public Beach", name: "Playa Centro (Parque Fundadores)", distanceKm: 0.5 },
    ],
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
    description: "Luxury villa-style residences within the gated, golf-course community of Playacar, positioned as a private, resort-style enclave near Fifth Avenue. Includes a golf practice range, beach club, and full-service spa.",
    amenities: ["Pool", "Golf", "Beach Club", "Spa", "Gym", "Kids Club", "Tennis Court", "Concierge", "Security 24/7", "Parking"],
    pointsOfInterest: [
      { label: "Airport", name: "Cancún International Airport (CUN)", distanceKm: 52.6 },
      { label: "Train Station", name: "Tren Maya – Playa del Carmen", distanceKm: 8.3 },
      { label: "Bus Station", name: "ADO Playa del Carmen", distanceKm: 2.3 },
      { label: "Hospital", name: "Hospiten Riviera Maya", distanceKm: 1.0 },
      { label: "Public Beach", name: "Playa Centro (Parque Fundadores)", distanceKm: 3.0 },
    ],
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
    description: "Boutique 5-floor condo tower in central Playa del Carmen, a few blocks from the main shopping and dining district. Design-forward with natural materials and a wellness focus, including a full spa and rooftop lounge. Delivered and ready to move in. Nearly sold out — only 2 units remain listed as available.",
    amenities: ["Pool", "Spa", "Beach Club", "Rooftop Terrace", "Coworking", "Concierge", "Parking"],
    pointsOfInterest: [
      { label: "Airport", name: "Cancún International Airport (CUN)", distanceKm: 49.3 },
      { label: "Train Station", name: "Tren Maya – Playa del Carmen", distanceKm: 6.3 },
      { label: "Bus Station", name: "ADO Playa del Carmen", distanceKm: 1.0 },
      { label: "Hospital", name: "Hospiten Riviera Maya", distanceKm: 2.7 },
      { label: "Public Beach", name: "Playa Centro (Parque Fundadores)", distanceKm: 0.9 },
    ],
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
    description: "Boutique, jungle-immersed condo community in Tulum, marketed as a secluded private enclave fronting a protected national park. Includes a rooftop infinity pool, two ground-level stone pools, a yoga/meditation deck, and a private shuttle plus VIP membership to Ikal Beach Club. Delivered and ready to move in.",
    amenities: ["Pool", "Beach Club", "Yoga", "Gym", "Spa", "Coworking", "BBQ Area", "Security 24/7"],
    pointsOfInterest: [
      { label: "Airport", name: "Aeropuerto Internacional de Tulum Felipe Carrillo Puerto (TQO)", distanceKm: 20.8 },
      { label: "Train Station", name: "Mayan Train – Tulum", distanceKm: 4.1 },
      { label: "Bus Station", name: "ADO Tulum", distanceKm: 0.1 },
      { label: "Hospital", name: "Hospital Comunitario de Tulum", distanceKm: 0.2 },
      { label: "Public Beach", name: "Playa Paraíso", distanceKm: 2.2 },
    ],
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
    description: "Feng-shui-influenced condo community in downtown Tulum, spanning five 3-level towers (76 units total). Just two blocks from Avenida Kukulcán with direct beach access. Delivered and ready to move in.",
    amenities: ["Pool", "Beach Club", "Gym", "Yoga", "BBQ Area", "Parking", "Security 24/7", "Concierge"],
    pointsOfInterest: [
      { label: "Airport", name: "Aeropuerto Internacional de Tulum Felipe Carrillo Puerto (TQO)", distanceKm: 20.6 },
      { label: "Train Station", name: "Mayan Train – Tulum", distanceKm: 3.4 },
      { label: "Bus Station", name: "ADO Tulum", distanceKm: 1.2 },
      { label: "Hospital", name: "Hospital Comunitario de Tulum", distanceKm: 1.2 },
      { label: "Public Beach", name: "Playa Paraíso", distanceKm: 3.3 },
    ],
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
    description: "Moody, dark-toned boutique condo in Tulum's established Aldea Zamá district. Features a rooftop adults-only pool, a separate ground-floor family pool, a full spa with massage cabins, and a sky bar. Delivered and ready to move in.",
    amenities: ["Pool", "Rooftop Terrace", "Restaurant", "Spa", "Jacuzzi", "Gym", "Coworking", "Security 24/7"],
    pointsOfInterest: [
      { label: "Airport", name: "Aeropuerto Internacional de Tulum Felipe Carrillo Puerto (TQO)", distanceKm: 21.3 },
      { label: "Train Station", name: "Mayan Train – Tulum", distanceKm: 4.7 },
      { label: "Bus Station", name: "ADO Tulum", distanceKm: 0.8 },
      { label: "Hospital", name: "Hospital Comunitario de Tulum", distanceKm: 0.8 },
      { label: "Public Beach", name: "Playa Paraíso", distanceKm: 1.4 },
    ],
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
    description: "Pre-sale community of 54 lock-off villas in Tulum, each with its own private garden and pool — letting owners split a residence into separately rentable units for income flexibility. Includes a dedicated beach club, palapa clubhouse, and zen garden. Units are lock-off villas, not condo apartments.",
    amenities: ["Pool", "Beach Club", "Yoga", "Jacuzzi", "Gym", "Kids Club", "Pet Friendly", "Security 24/7", "Parking"],
    pointsOfInterest: [
      { label: "Airport", name: "Aeropuerto Internacional de Tulum Felipe Carrillo Puerto (TQO)", distanceKm: 21.6 },
      { label: "Train Station", name: "Mayan Train – Tulum", distanceKm: 5.8 },
      { label: "Bus Station", name: "ADO Tulum", distanceKm: 2.0 },
      { label: "Hospital", name: "Hospital Comunitario de Tulum", distanceKm: 2.0 },
      { label: "Public Beach", name: "Playa Paraíso", distanceKm: 0.4 },
    ],
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
    description: "Boutique 5-floor condo on Mahahual's pedestrian boardwalk, blending Japanese-inspired zen design with Mexican natural materials. Most units include a private rooftop-terrace pool, with a shared sky bar, spa, and beach club membership. Delivered and ready to move in. Nearly sold out — only 2 units remain listed as available.",
    amenities: ["Pool", "Beach Club", "Restaurant", "Spa", "Gym", "Yoga", "Security 24/7", "Parking"],
    pointsOfInterest: [
      { label: "Airport", name: "Chetumal International Airport (CTM)", distanceKm: 69.9 },
      { label: "Train Station", name: "Tren Maya – Chetumal", distanceKm: 69.9 },
      { label: "Bus Station", name: "ADO Mahahual", distanceKm: 0.6 },
      { label: "Hospital", name: "Hospital Costamed Mahahual", distanceKm: 2.3 },
      { label: "Public Beach", name: "Playa Mahahual (Malecón)", distanceKm: 0.1 },
    ],
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
    lat: 21.1637, lng: -86.8060,
    deliveryDate: "Ready to move in",
    propertyType: "Condo",
    description: "Luxury 5-level condo building in the heart of Puerto Cancún, designed by Italian architecture firm Archea Associati with full marble cladding and a monumental pergola. Residents get community access to a Tom Weiskopf-designed golf course, a private marina, and a beach club. Delivered and ready to move in. Mostly sold out — only a few high-end units remain listed as available.",
    amenities: ["Pool", "Marina", "Golf", "Beach Club", "Jacuzzi", "Gym", "Tennis Court", "Coworking", "Security 24/7", "Parking"],
    pointsOfInterest: [
      { label: "Airport", name: "Cancún International Airport (CUN)", distanceKm: 16.0 },
      { label: "Train Station", name: "Tren Maya – Cancún Airport", distanceKm: 16.6 },
      { label: "Bus Station", name: "ADO Cancún Centro", distanceKm: 2.3 },
      { label: "Hospital", name: "Hospital Galenia", distanceKm: 7.8 },
      { label: "Public Beach", name: "Playa Langosta", distanceKm: 3.4 },
    ],
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
    description: "Pre-sale beachfront condo in Puerto Morelos' Pier District, about 200m from the Caribbean Sea and two blocks from downtown. Spans two towers (Agua and Fuego) with a rooftop garden and infinity pool, plus community access to golf and polo clubs.",
    amenities: ["Pool", "Rooftop Terrace", "Beach Club", "Golf", "Yoga", "Gym", "Kids Club", "Pet Friendly", "Security 24/7"],
    pointsOfInterest: [
      { label: "Airport", name: "Cancún International Airport (CUN)", distanceKm: 21.0 },
      { label: "Train Station", name: "Tren Maya – Puerto Morelos", distanceKm: 7.6 },
      { label: "Bus Station", name: "ADO Puerto Morelos", distanceKm: 0.6 },
      { label: "Hospital", name: "Hospital Costamed Puerto Morelos", distanceKm: 2.4 },
      { label: "Public Beach", name: "Playa Puerto Morelos", distanceKm: 0.7 },
    ],
    photos: ["1ZO_th26VKfiHgumLftQQCggaJuFNo2jR", "1xNmSsiaxdNVQyciNLHEEcqAgiMzB_-OX", "14u7eGnej-MGrlLAu0oFaaFgKuCLGZX1e", "1OFJAD746wd0CffO7-a91pVvvCpUfUsx1"],
    units: [
      { unitLabel: "Agua 101", type: "2BR", bedrooms: 2, bathrooms: 2, price: 252281, size: 48.48, available: 1 },
      { unitLabel: "Agua 201", type: "2BR", bedrooms: 2, bathrooms: 2, price: 267901, size: 53.53, available: 1 },
      { unitLabel: "Fuego 602", type: "3BR", bedrooms: 3, bathrooms: 2.5, price: 662613, size: 107.08, available: 1 },
    ],
  },
];
