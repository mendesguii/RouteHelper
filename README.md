# RouteHelper
CLI and GUI tools to get SID/STARs, plan routes, and fetch METARs. Now includes a Streamlit web UI.

## Features
- Procedures: list/search SIDs and STARs from local .dat files
- METAR fetch for any ICAO
- Route planning via rfinder
- Loadsheet via fuelplanner (parsed into structured data)
- Export IVAO FPL (.fpl) and VATSIM (ICAO FPL text)

## Run (CLI)
Use `main.py` as before.

## Run (Desktop GUI)
Launch `gui.py` for the ttkbootstrap desktop UI.

## Run (Streamlit Web UI)
1. Install deps
2. Run Streamlit app

```powershell
pip install -r requirements.txt
streamlit run .\streamlit_app.py
```

Configure the data folder and AIRAC in the left sidebar. The Streamlit app mirrors the GUI features:
- Procedures + METAR tab
- Route Planner with loadsheet, route, SID/STAR fix searches, METARs
- Export IVAO FPL and VATSIM ICAO FPL text

