# RouteHelper
Plan IFR routes, fetch loadsheets and METARs, and search SIDs/STARs.

Now a FastAPI + HTMX + Bulma web app, with a small CLI for power users.

## Features
- Procedures: list/search SIDs and STARs from local CIFP `.dat` files
- METAR fetch for any ICAO
- Route planning via rfinder (with FL range and aircraft type)
- Loadsheet via fuelplanner (parsed into structured data)
- VATSIM ICAO FPL text builder
- Route map rendering via Folium from `earth_fix.dat`

## Configuration
Create a `.env` file (auto-created on first run) and set:

```
DATA_PATH=./Custom Data
CYCLE=2501
```

`DATA_PATH` should point to the root containing `CIFP/` and `earth_fix.dat` (or place `.dat` files directly under `DATA_PATH`).

## Run (Web UI)

Install and start the FastAPI app:

```powershell
pip install -r requirements.txt
uvicorn main_fastapi:app --host 0.0.0.0 --port 8000
```

Then open http://localhost:8000 in your browser.

### Run with Docker

```powershell
docker compose up --build
```

The app will be available on http://localhost:8000.

## Run (CLI)

Legacy CLI is still available:

```powershell
python .\main.py EHAM METAR
python .\main.py EHAM SID VUREP
python .\main.py EHAM/LEBL ROUTE A320
```

## Notes

- ICAO suggestions are based on listing `.dat` files under `DATA_PATH/CIFP` (fallback to `DATA_PATH`).
- The route map uses fixes from `earth_fix.dat` if present.

## Database and Indexing

This project stores navdata and generated flights in a database (default: SQLite).

When running with Docker Compose, a named volume `routehelper_db` persists the SQLite file at `/var/lib/routehelper/routehelper.db`.

API endpoints:

- `POST /admin/init` — create tables.
- `POST /admin/index?force=false` — parse navdata files from `DATA_PATH` and index Fixes, Airports, Airways, and AIRAC info. Run this after AIRAC updates.
- `GET /admin/status` — show counts and the last indexed AIRAC.

You can override the database with `DATABASE_URL` (e.g., Postgres) or set `DB_DIR` when using SQLite.

