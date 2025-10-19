from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from main import RouteHelper
from datetime import datetime
import os
import folium

app = FastAPI()

# Mount static files for Bulma and htmx
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

AIRCRAFT_OPTIONS = ["A319", "A320", "A321", "B738_ZIBO", "B738", "B737"]
DEFAULT_FL_START = "250"
DEFAULT_FL_END = "350"

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    helper = RouteHelper()
    airac = helper.get_airac_info()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "aircraft_options": AIRCRAFT_OPTIONS,
            "default_fl_start": DEFAULT_FL_START,
            "default_fl_end": DEFAULT_FL_END,
            "airac": airac,
        },
    )

@app.post("/plan", response_class=HTMLResponse)
def plan_route(request: Request,
               origin: str = Form(...),
               dest: str = Form(...),
               plane: str = Form(...),
               fl_start: str = Form(DEFAULT_FL_START),
               fl_end: str = Form(DEFAULT_FL_END)):
    helper = RouteHelper()
    airac = helper.get_airac_info()
    # Loadsheet (non-mutating)
    try:
        loadsheet, parsed = helper.fetch_loadsheet(origin, dest, plane)
    except Exception as e:
        loadsheet, parsed = (f"Error: {e}", None)
    parsed = parsed or {}
    ttl = (parsed.get('weights', {}) or {}).get('total_traffic_load')
    tof = (parsed.get('weights', {}) or {}).get('takeoff_fuel')
    blk = (parsed.get('times', {}) or {}).get('block_time')
    endurance = (parsed.get('times', {}) or {}).get('time_to_empty')
    # Route (non-mutating)
    try:
        cycle_val = helper.get_cycle()
        route_list, route_text = helper.fetch_route(origin, dest, fl_start, fl_end, cycle_val)
    except Exception as e:
        route_list, route_text = ([], f"Error: {e}")
    # SID/STAR (non-mutating inference)
    sid_text, star_text = helper.infer_sid_star(origin, dest, route_list)
    # METARs (non-mutating)
    try:
        metar_origin = helper.fetch_metar(origin) or "No METAR found."
    except Exception as e:
        metar_origin = f"Error: {e}"
    try:
        metar_dest = helper.fetch_metar(dest) or "No METAR found."
    except Exception as e:
        metar_dest = f"Error: {e}"
    # ICAO FPL
    route_str = ' '.join(route_list) if route_list else ''
    si_block_time = (parsed.get('times', {}) or {}).get('block_time', '')
    eet = si_block_time.replace(':', '') if si_block_time else ''
    msg = RouteHelper.build_vatsim_icao_fpl(
        callsign="XXXXXX",
        actype=plane,
        wakecat="M",
        equipment="SDE3FGIJ1KRWXY/",
        surveillance="LB1",
        dep_icao=origin,
        dep_time="0000",
        speed="N0441",
        level=f"F{fl_start}",
        route=route_str,
        dest_icao=dest,
        eet=eet,
        alt1="",
        alt2="",
        pbn="A1B1D1O1S2",
        nav="RNVD1E2A1",
        rnp="2",
        dof=datetime.today().strftime('%y%m%d'),
        reg="",
        sel="",
        code="",
        rvr="",
        opr="",
        per="C",
        rmk="",
    )
    return templates.TemplateResponse("result.html", {
        "request": request,
        "origin": origin,
        "dest": dest,
        "plane": plane,
        "fl_start": fl_start,
        "fl_end": fl_end,
        "airac": airac,
        "loadsheet": loadsheet,
        "ttl": ttl,
        "tof": tof,
        "blk": blk,
        "endurance": endurance,
        "route_text": route_text,
        "sid_text": sid_text,
        "star_text": star_text,
        "metar_origin": metar_origin,
        "metar_dest": metar_dest,
        "icao_fpl": msg,
        "route_map": "",
        "aircraft_options": AIRCRAFT_OPTIONS,
        "default_fl_start": DEFAULT_FL_START,
        "default_fl_end": DEFAULT_FL_END,
    })

@app.post("/route_map", response_class=HTMLResponse)
def route_map(request: Request, items: str = Form(""), origin: str = Form("") , dest: str = Form("")):
    helper = RouteHelper()
    seq = [s for s in (items or '').split() if s.strip()]
    # Get route fix coords via helper and airports via helper
    coords = helper.get_route_fix_coords(items)
    apt_coords = helper.load_airport_coords()
    # If route explicitly indicates none, ignore any fixes and render airport-to-airport only
    route_indicates_none = 'no route generated' in (items or '').lower()
    if route_indicates_none:
        coords = []

    points = []  # for bounds
    # Build folium map
    m = folium.Map(location=[0, 0], zoom_start=2, tiles='CartoDB dark_matter')

    # Add route line and fix markers if available
    if len(coords) >= 2:
        folium.PolyLine([(c[0], c[1]) for c in coords], color='#00c2ff', weight=3, opacity=0.85).add_to(m)
    # Plot fix markers (even if only 1), unknown fixes are already ignored by lookup
    for lat, lon, name in coords:
            folium.CircleMarker(location=[lat, lon], radius=4, color='#00c2ff', fill=True, fill_color='#ffffff', fill_opacity=0.9, popup=name, tooltip=name).add_to(m)
            # Add a text label centered above the fix marker
            folium.map.Marker(
                location=[lat, lon],
                icon=folium.DivIcon(html=(
                    f'<div style="position: relative; left: 50%; transform: translate(-50%, -14px);'
                    f' font-size: 11px; color: #8bd9f8; white-space: nowrap;'
                    f' text-shadow: 0 0 2px #000, 0 0 3px #000; pointer-events: none;">{name}</div>'
                ))
            ).add_to(m)
            points.append((lat, lon))

    # Add origin/dest airport markers if available
    o = (apt_coords.get((origin or '').upper()) if origin else None)
    d = (apt_coords.get((dest or '').upper()) if dest else None)
    if o:
        folium.Marker(location=[o[0], o[1]], icon=folium.Icon(color='lightgreen', icon='plane', prefix='fa'), popup=f"{origin.upper()} (Origin)", tooltip=f"{origin.upper()} (Origin)").add_to(m)
        folium.map.Marker(
            location=[o[0], o[1]],
            icon=folium.DivIcon(html=(
                f'<div style="position: relative; left: 50%; transform: translate(-50%, -16px);'
                f' font-size: 12px; font-weight: 700; color: #a2f5bf; white-space: nowrap;'
                f' text-shadow: 0 0 2px #000, 0 0 3px #000; pointer-events: none;">{origin.upper()}</div>'
            ))
        ).add_to(m)
        points.append(o)
    if d:
        folium.Marker(location=[d[0], d[1]], icon=folium.Icon(color='orange', icon='flag', prefix='fa'), popup=f"{dest.upper()} (Destination)", tooltip=f"{dest.upper()} (Destination)").add_to(m)
        folium.map.Marker(
            location=[d[0], d[1]],
            icon=folium.DivIcon(html=(
                f'<div style="position: relative; left: 50%; transform: translate(-50%, -16px);'
                f' font-size: 12px; font-weight: 700; color: #ffcc80; white-space: nowrap;'
                f' text-shadow: 0 0 2px #000, 0 0 3px #000; pointer-events: none;">{dest.upper()}</div>'
            ))
        ).add_to(m)
        points.append(d)

    # Connect airports to the route using dashed lines
    if o and coords:
        first = coords[0]
        folium.PolyLine([[o[0], o[1]], [first[0], first[1]]], color='#90a4ae', weight=2, opacity=0.85, dash_array='4,6').add_to(m)
    if d and coords:
        last = coords[-1]
        folium.PolyLine([[last[0], last[1]], [d[0], d[1]]], color='#90a4ae', weight=2, opacity=0.85, dash_array='4,6').add_to(m)
    # Only draw airport-to-airport dashed when route explicitly says "No route generated."
    if (o and d) and route_indicates_none:
        folium.PolyLine([[o[0], o[1]], [d[0], d[1]]], color='#90a4ae', weight=2, opacity=0.85, dash_array='4,6').add_to(m)

    # Fit map to all points if we have at least one
    if points:
        min_lat = min(p[0] for p in points)
        max_lat = max(p[0] for p in points)
        min_lon = min(p[1] for p in points)
        max_lon = max(p[1] for p in points)
        m.fit_bounds([[min_lat, min_lon], [max_lat, max_lon]], padding=(20, 20))

    html = m.get_root().render()
    return templates.TemplateResponse("partials/route_map.html", {"request": request, "html": html})

@app.post("/route_map_close", response_class=HTMLResponse)
def route_map_close():
    # Returning an empty string clears the container
    return ""

@app.get("/icao_suggest", response_class=HTMLResponse)
def icao_suggest(request: Request, q: str = "", origin: str = "", dest: str = "", limit: int = 20, mode: str = "options", input_id: str = "", target_id: str = ""):
    helper = RouteHelper()
    query = (q or origin or dest or "").strip()
    if not query:
        # No query: return empty for both modes to hide UI
        if mode == "menu":
            return templates.TemplateResponse("partials/icao_menu.html", {
                "request": request,
                "codes": [],
                "q": query,
                "input_id": input_id,
                "target_id": target_id,
            })
        return templates.TemplateResponse("partials/icao_options.html", {
            "request": request,
            "codes": [],
        })
    codes = helper.list_cifp_icaos(query, limit)
    if mode == "menu":
        # For nicer dropdown UI; if no query or codes, return empty to hide menu
        return templates.TemplateResponse("partials/icao_menu.html", {
            "request": request,
            "codes": codes,
            "q": query,
            "input_id": input_id,
            "target_id": target_id,
        })
    # Default datalist options
    return templates.TemplateResponse("partials/icao_options.html", {
        "request": request,
        "codes": codes,
    })

@app.get("/metar", response_class=HTMLResponse)
def get_metar(request: Request, icao: str):
    helper = RouteHelper()
    try:
        metar = helper.fetch_metar(icao) or "No METAR found."
    except Exception as e:
        metar = f"Error: {e}"
    return templates.TemplateResponse("partials/metar_block.html", {
        "request": request,
        "icao": icao,
        "metar": metar,
    })

@app.post("/search_sid", response_class=HTMLResponse)
def search_sid(request: Request, origin: str = Form(...), fix: str = Form("")):
    helper = RouteHelper()
    sid_text = ""
    try:
        helper.get_file_data(origin)
        sid_dict = helper.structure_data(helper.sids)
        q = (fix or "").upper()
        if q:
            sid_text = helper.search_in_dict_text(sid_dict, q)
        else:
            # default to listing or last inferred route-based search
            sid_text = helper.search_in_dict_text(sid_dict, "")
    except Exception as e:
        sid_text = f"Error: {e}"
    return templates.TemplateResponse("partials/sid_block.html", {
        "request": request,
        "origin": origin,
        "sid_text": sid_text,
    })

@app.post("/search_star", response_class=HTMLResponse)
def search_star(request: Request, dest: str = Form(...), fix: str = Form("")):
    helper = RouteHelper()
    star_text = ""
    try:
        helper.get_file_data(dest)
        star_dict = helper.structure_data(helper.stars)
        q = (fix or "").upper()
        if q:
            star_text = helper.search_in_dict_text(star_dict, q)
        else:
            star_text = helper.search_in_dict_text(star_dict, "")
    except Exception as e:
        star_text = f"Error: {e}"
    return templates.TemplateResponse("partials/star_block.html", {
        "request": request,
        "dest": dest,
        "star_text": star_text,
    })
@app.get("/health")
def health():
    return {"status": "ok"}
