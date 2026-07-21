# Yucatán Peninsula Developments — Map Prototype

A proof-of-concept: an interactive map of Quintana Roo & Yucatán residential
developments, with search, filtering by unit type/city, and a detail panel
showing price/size/availability per unit type — similar in spirit to
[mayaocean.com](https://mayaocean.com/).

## What this is

- Plain HTML/CSS/JS, no build step. [Leaflet](https://leafletjs.com/) (via CDN)
  renders the map over OpenStreetMap tiles.
- `data.js` holds 14 sample developments. Developer names, project names, and
  cities are pulled from the real developer directories in
  `../1. Quintana Roo` and `../2. Yucatan`. **Unit types, prices, sizes, and
  availability counts are fabricated placeholder data** — there's no live
  data source wired up yet.
- Search bar filters by developer/project/city name. Dropdowns filter by
  unit type (Studio/1BR/2BR/3BR) and city. Clicking a marker or a result
  card opens full details in the right-hand panel.

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
