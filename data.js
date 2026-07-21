// Sample/placeholder data for the proof-of-concept.
//
// Developer names, project names, and cities are drawn from the real developer
// directories in "1. Quintana Roo" and "2. Yucatan". Unit types, prices, sizes,
// and availability counts are FABRICATED for demo purposes only — real per-unit
// data would come from parsing the monthly developer PDFs (see README "Next steps").

const DEVELOPMENTS = [
  {
    id: 1,
    project: "Vía Montejo",
    developer: "Inmobilia",
    city: "Mérida, Yucatán",
    lat: 21.0500, lng: -89.6200,
    description: "Large mixed-use master-planned development along the Vía Montejo corridor. Winner of \"Best Mixed-Use Development in Mexico\" (Americas Property Awards).",
    units: [
      { type: "Studio", price: 118000, size: 40, available: 4 },
      { type: "1BR", price: 168000, size: 58, available: 6 },
      { type: "2BR", price: 245000, size: 88, available: 3 },
    ],
  },
  {
    id: 2,
    project: "Yucalpetén Resort Marina",
    developer: "Desarrollos SIMCA",
    city: "Progreso, Yucatán",
    lat: 21.2833, lng: -89.6667,
    description: "Yucatán's first oceanfront residential community — three towers on the marina, 20+ years of the developer active in the region.",
    units: [
      { type: "1BR", price: 195000, size: 60, available: 2 },
      { type: "2BR", price: 289000, size: 95, available: 5 },
      { type: "3BR", price: 410000, size: 140, available: 1 },
    ],
  },
  {
    id: 3,
    project: "Las Américas",
    developer: "Grupo Sadasi",
    city: "Mérida, Yucatán",
    lat: 20.9500, lng: -89.5500,
    description: "National developer active since 1975. Las Américas has 14,000+ homes built with 5,300 under construction.",
    units: [
      { type: "Studio", price: 95000, size: 38, available: 8 },
      { type: "1BR", price: 132000, size: 52, available: 10 },
      { type: "2BR", price: 189000, size: 78, available: 6 },
    ],
  },
  {
    id: 4,
    project: "Aldea Balbhá",
    developer: "Teca Desarrollos",
    city: "Mérida, Yucatán",
    lat: 21.0100, lng: -89.5800,
    description: "100% Yucatecan developer, 15+ years active with 20+ developments delivered.",
    units: [
      { type: "1BR", price: 145000, size: 55, available: 3 },
      { type: "2BR", price: 210000, size: 84, available: 4 },
    ],
  },
  {
    id: 5,
    project: "Way'uum",
    developer: "Grupo GEA",
    city: "Telchac Puerto, Yucatán",
    lat: 21.3417, lng: -89.2667,
    description: "Coastal development from a 100% Yucatecan developer founded 2016; 11 developments delivered to date.",
    units: [
      { type: "Studio", price: 105000, size: 36, available: 5 },
      { type: "2BR", price: 265000, size: 92, available: 2 },
    ],
  },
  {
    id: 6,
    project: "Cumbres Towers",
    developer: "Eleva Capital Group",
    city: "Cancún, Quintana Roo",
    lat: 21.1619, lng: -86.8515,
    description: "Founded 2016 by pioneer Cancún families. High-rise residential towers in the Cumbres corridor.",
    units: [
      { type: "Studio", price: 155000, size: 42, available: 6 },
      { type: "1BR", price: 225000, size: 64, available: 7 },
      { type: "2BR", price: 340000, size: 98, available: 3 },
    ],
  },
  {
    id: 7,
    project: "Sole Blu",
    developer: "Eleva Capital Group",
    city: "Puerto Morelos, Quintana Roo",
    lat: 20.8460, lng: -86.8756,
    description: "Low-density residential project close to the Puerto Morelos reef and marina.",
    units: [
      { type: "1BR", price: 210000, size: 60, available: 4 },
      { type: "2BR", price: 315000, size: 90, available: 2 },
    ],
  },
  {
    id: 8,
    project: "B10 Luxury Condos",
    developer: "DIG Desarrollos Inmobiliarios",
    city: "Cancún, Quintana Roo",
    lat: 21.1300, lng: -86.8100,
    description: "High-design architecture focus; 13+ years of the developer active in Cancún and Playa del Carmen.",
    units: [
      { type: "2BR", price: 385000, size: 110, available: 2 },
      { type: "3BR", price: 560000, size: 155, available: 1 },
    ],
  },
  {
    id: 9,
    project: "Xikal",
    developer: "Grupo Makech",
    city: "Tulum, Quintana Roo",
    lat: 20.2114, lng: -87.4654,
    description: "15+ years building luxury Tulum residences, alongside Itzá I & II and Casa Veleta.",
    units: [
      { type: "Studio", price: 175000, size: 45, available: 3 },
      { type: "1BR", price: 260000, size: 68, available: 5 },
      { type: "2BR", price: 420000, size: 105, available: 2 },
    ],
  },
  {
    id: 10,
    project: "Paravian",
    developer: "Grupo Emérita",
    city: "Playa del Carmen, Quintana Roo",
    lat: 20.6296, lng: -87.0739,
    description: "One of five active Grupo Emérita projects in the region (alongside Tierra Madre, Constelada, Trébola).",
    units: [
      { type: "Studio", price: 148000, size: 41, available: 5 },
      { type: "1BR", price: 205000, size: 59, available: 6 },
      { type: "3BR", price: 495000, size: 148, available: 1 },
    ],
  },
  {
    id: 11,
    project: "Aldea Valladolid",
    developer: "Grupo Emérita",
    city: "Valladolid, Yucatán",
    lat: 20.6896, lng: -88.2019,
    description: "Grupo Emérita's inland project, closer to Chichén Itzá and the colonial center of Valladolid.",
    units: [
      { type: "Studio", price: 78000, size: 36, available: 7 },
      { type: "1BR", price: 110000, size: 50, available: 8 },
    ],
  },
  {
    id: 12,
    project: "The Fives Downtown",
    developer: "The Fives Hotels & Residences",
    city: "Playa del Carmen, Quintana Roo",
    lat: 20.6400, lng: -87.0800,
    description: "Hotel-condo investment model with shared rental income; developer has 25,000+ homes delivered nationwide.",
    units: [
      { type: "1BR", price: 240000, size: 62, available: 4 },
      { type: "2BR", price: 365000, size: 96, available: 3 },
    ],
  },
  {
    id: 13,
    project: "Vivo Cozumel",
    developer: "Vivo Grupo Inmobiliario",
    city: "Cozumel, Quintana Roo",
    lat: 20.4230, lng: -86.9223,
    description: "ESR-certified 13 years running; mid-market housing with financing options for qualified buyers.",
    units: [
      { type: "Studio", price: 98000, size: 38, available: 6 },
      { type: "2BR", price: 220000, size: 82, available: 3 },
    ],
  },
  {
    id: 14,
    project: "Urban Homes Puerto Cancún",
    developer: "Urban Homes",
    city: "Cancún, Quintana Roo",
    lat: 21.1200, lng: -86.8000,
    description: "Publicly traded on the BMV; 24+ completed projects and 2,500+ units sold region-wide.",
    units: [
      { type: "1BR", price: 230000, size: 63, available: 5 },
      { type: "2BR", price: 355000, size: 97, available: 4 },
      { type: "3BR", price: 520000, size: 145, available: 2 },
    ],
  },
];
