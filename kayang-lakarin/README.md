# 🌿 Lakad MNL — Metro Manila Outdoor Commute Finder

A Streamlit webapp that helps Metro Manila residents find the nearest outdoor activity areas with good air quality, along with **real road-based commute estimates** powered by OSRM.

## What's New in v3.0

- **OSRM Integration** — Real road distances and turn-by-turn routes via the Open Source Routing Machine
- **Actual route polylines** drawn on the interactive map (driving + optional walking)
- **Traffic-adjusted times** — OSRM free-flow times multiplied by Metro Manila traffic factors
- **Dynamic fare calculation** — Jeepney fare uses LTFRB formula; Grab uses distance-based estimate with surge range
- **Fallback mode** — Gracefully degrades to straight-line estimates if OSRM is unavailable

## Quick Start

```bash
pip install -r requirements.txt
streamlit run app.py
```

Then open http://localhost:8501 in your browser.

## How Routing Works

### OSRM (Open Source Routing Machine)
The app queries the free public OSRM server (`router.project-osrm.org`) for:
- **Driving routes** — used for Grab/taxi and jeepney estimates
- **Walking routes** — for destinations within 5 km

OSRM returns free-flow travel times based on OpenStreetMap road data. Since Metro Manila traffic is far heavier than free-flow, the app applies multipliers:

| Mode | Profile | Multiplier | Why |
|------|---------|-----------|-----|
| Grab/Taxi | `driving` | ×1.6 | Traffic + pickup wait |
| Jeepney | `driving` | ×2.2 | Stops, loading, indirection |
| Walking | `foot` | ×1.0 | Unaffected by traffic |

### Fare Calculation
- **Jeepney**: ₱13 base (first 4 km) + ₱1.80/km — LTFRB 2024 rates
- **Grab**: ₱45 base + ₱14/km, with ×0.85–1.35 surge factor

### Fallback
If OSRM is unavailable, the app uses haversine (straight-line) distance × 1.35 (typical road detour ratio for Metro Manila).

## Features

- 16 curated outdoor spaces across Metro Manila
- Air quality scoring (1–5) based on green cover and traffic proximity
- Interactive Folium map with route polylines
- Sidebar filters: air quality, activity type, max commute
- 20+ starting locations across all Metro Manila cities
- Toggle between OSRM routes and straight-line estimates
- Results cached for 1 hour to be polite to the public OSRM server

## Self-Hosting OSRM

For production use, you can run your own OSRM instance with Philippines data:

```bash
# Download Philippines OSM extract
wget https://download.geofabrik.de/asia/philippines-latest.osm.pbf

# Process with OSRM
docker run -t -v $(pwd):/data ghcr.io/project-osrm/osrm-backend osrm-extract -p /opt/car.lua /data/philippines-latest.osm.pbf
docker run -t -v $(pwd):/data ghcr.io/project-osrm/osrm-backend osrm-partition /data/philippines-latest.osrm
docker run -t -v $(pwd):/data ghcr.io/project-osrm/osrm-backend osrm-customize /data/philippines-latest.osrm

# Run server
docker run -t -p 5000:5000 -v $(pwd):/data ghcr.io/project-osrm/osrm-backend osrm-routed --algorithm mld /data/philippines-latest.osrm
```

Then change `OSRM_BASE` in `app.py` to `http://localhost:5000/route/v1`.

## License

MIT
