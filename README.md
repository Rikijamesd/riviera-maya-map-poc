# Yucatán Peninsula Developments — Map Prototype

A proof-of-concept: an interactive map of Quintana Roo & Yucatán residential
developments, with search, filtering by unit type/city, and a detail panel
showing price/size/availability per unit type — similar in spirit to
[mayaocean.com](https://mayaocean.com/).

## What this is

- Plain HTML/CSS/JS, no build step. [Leaflet](https://leafletjs.com/) (via CDN)
  renders the map over OpenStreetMap tiles.
- `data.js` holds 12 **real** projects (ALTRA, TIERRA MADRE, THE LANDMARK,
  MACONDO PLAYACAR, BAGÁ RIVIERA, SAMSARA, XUNIK, PARAMAR BLACK, SEREMONIA
  HÁBITAT, HAMA, ALBA, ALUX 33), pulled from the "BROKERS - iMexico 2026"
  Google Drive folder — real names, real delivery dates, real photos
  (hotlinked from Drive file IDs via `https://lh3.googleusercontent.com/d/{id}`).
  Developer names are only filled in where a source doc explicitly named one
  (DOMA, GR4, Macondo, Algi); the rest say "Developer not confirmed" rather
  than guessing. **Unit numbers, prices, and sizes are now real** — pulled
  from each project's actual "Prices and Availability" PDF in the Drive,
  filtered to units marked available (not sold/reserved). MXN prices were
  converted to USD at a fixed ~18:1 rate, not a live exchange rate.
  **Bathroom counts and amenities are still estimates** where the source PDF
  didn't include that detail. TIERRA MADRE's real data is for raw land lots
  (no bedrooms apply), not a built house. This is a point-in-time snapshot,
  not a live sync — if a unit sells or a price changes in the Drive, this
  site won't know until someone re-pulls it.
- Search bar filters by developer/project/city name. Dropdowns filter by
  unit type (Studio/1BR/2BR/3BR) and city. Clicking a marker, a result card,
  or "View all" navigates to a dedicated detail page for that development
  (`detail.html?id=N`).

## Running it locally

Any static file server works. Example using the included PowerShell server
(no Python/Node required):

```
powershell -File serve.ps1
```

Then open `http://localhost:8843/`.

## What real data ingestion would take (not built yet)

The original idea — auto-pulling from a Google Drive/SharePoint folder that
developers update monthly with new PDFs — is a separate, larger effort:

1. **Auth**: a Google Drive API (service account or OAuth) and/or Microsoft
   Graph API (for SharePoint) connection with read access to the shared
   folders.
2. **Change detection**: poll or subscribe to folder changes to detect new/
   updated PDFs each month.
3. **Extraction**: parse unit type, price, size, and availability out of each
   PDF. Developer PDFs are unlikely to share one layout, so this probably
   needs either per-developer templates or an LLM-based extraction step,
   with a human review pass before publishing.
4. **Storage**: a small database (rather than in-memory `data.js`) so the
   site reads current data instead of redeploying on every update.
5. **Geocoding**: turning development addresses into map coordinates
   (Google/Mapbox geocoding API, or manual entry per project).

This prototype only proves out the front-end interaction model (map + filters
+ detail panel) against sample data, to validate that part before investing
in the ingestion pipeline above.
