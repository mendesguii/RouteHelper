from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from main import RouteHelper
from datetime import datetime
import os
import folium

app = FastAPI()

# Resolve absolute paths for robustness inside Docker
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

# Mount static only if directory exists (we use CDN for Bulma/htmx by default)
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

templates = Jinja2Templates(directory=TEMPLATES_DIR)

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
    origin_u = (origin or '').strip().upper()
    dest_u = (dest or '').strip().upper()
    # Loadsheet (non-mutating)
    try:
        loadsheet, parsed = helper.fetch_loadsheet(origin_u, dest_u, plane)
    except Exception as e:
        loadsheet, parsed = (f"Error: {e}", None)
    parsed = parsed or {}
    ttl = (parsed.get('weights', {}) or {}).get('total_traffic_load')
    tof = (parsed.get('weights', {}) or {}).get('takeoff_fuel')
    blk = (parsed.get('times', {}) or {}).get('block_time')
    endurance = (parsed.get('times', {}) or {}).get('time_to_empty')
    tc_val = (parsed.get('flight', {}) or {}).get('tc')
    # Route (non-mutating)
    try:
        cycle_val = helper.get_cycle()
        route_list, route_text = helper.fetch_route(origin_u, dest_u, fl_start, fl_end, cycle_val)
    except Exception as e:
        route_list, route_text = ([], f"Error: {e}")
    # SID/STAR (non-mutating inference)
    sid_text, star_text = helper.infer_sid_star(origin_u, dest_u, route_list)
    # Altitude suggestion based on semicircular IFR rule and requested FL range
    # Use TC (track/course) text from loadsheet when available, e.g., "123 (EAST)" or "278 (WEST)"
    tc_up = ((tc_val or "").strip()).upper()
    if "EAST" in tc_up:
        direction_label = "eastbound"
    elif "WEST" in tc_up:
        direction_label = "westbound"
    else:
        direction_label = "unknown"

    eastbound = True if direction_label == "eastbound" else (False if direction_label == "westbound" else None)
    rule_label = "IFR semicircular: eastbound odd FLs, westbound even FLs"
    # build candidate FLs within requested range
    try:
        fl_lo = int(fl_start)
        fl_hi = int(fl_end)
    except Exception:
        fl_lo, fl_hi = 100, 450
    if fl_lo > fl_hi:
        fl_lo, fl_hi = fl_hi, fl_lo
    rng = [fl for fl in range(max(100, fl_lo), min(450, fl_hi) + 1, 10)]
    def is_odd_fl(fl: int) -> bool:
        return ((fl // 10) % 2) == 1  # FL350 -> 35 -> odd
    if direction_label == "unknown":
        # Direction unknown: do not present any eligible levels
        filtered = []
    else:
        want_odd = bool(eastbound)
        filtered = [fl for fl in rng if is_odd_fl(fl) == want_odd]
        if not filtered:
            filtered = rng
    # Also prepare the list of eligible FLs to present to the user
    eligible_fls = [f"FL{fl}" for fl in filtered]
    # METARs (non-mutating)
    try:
        metar_origin = helper.fetch_metar(origin_u) or "No METAR found."
    except Exception as e:
        metar_origin = f"Error: {e}"
    try:
        metar_dest = helper.fetch_metar(dest_u) or "No METAR found."
    except Exception as e:
        metar_dest = f"Error: {e}"
    # ICAO FPL
    route_str = ' '.join(route_list) if route_list else ''
    si_block_time = (parsed.get('times', {}) or {}).get('block_time', '')
    endurance_time = (parsed.get('times', {}) or {}).get('time_to_empty', '')
    eet = si_block_time.replace(':', '') if si_block_time else ''
    endur = endurance_time.replace(':', '') if endurance_time else ''
    msg = RouteHelper.build_vatsim_icao_fpl(
        callsign="XXXXXX",
        actype=plane,
        wakecat="M",
        equipment="SDE3FGIJ1KRWXY/",
        surveillance="LB1",
        dep_icao=origin_u,
        dep_time="0000",
        speed="N0441",
        level=f"F{fl_start}",
        route=route_str,
        dest_icao=dest_u,
        eet=eet,
    endurance_hhmm='',
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
        "origin": origin_u,
        "dest": dest_u,
        "plane": plane,
        "fl_start": fl_start,
        "fl_end": fl_end,
        "airac": airac,
        "loadsheet": loadsheet,
        "ttl": ttl,
        "tof": tof,
        "blk": blk,
        "endurance": endurance,
    "tc": tc_val,
        "route_text": route_text,
        "sid_text": sid_text,
        "star_text": star_text,
        "metar_origin": metar_origin,
        "metar_dest": metar_dest,
        "icao_fpl": msg,
    "eligible_fls": eligible_fls,
    "altitude_rule": rule_label,
    "route_direction": direction_label,
        "route_map": "",
        "aircraft_options": AIRCRAFT_OPTIONS,
        "default_fl_start": DEFAULT_FL_START,
        "default_fl_end": DEFAULT_FL_END,
    })

@app.post("/route_map", response_class=HTMLResponse)
def route_map(request: Request, items: str = Form(""), origin: str = Form("") , dest: str = Form("")):
    helper = RouteHelper()
    # Get route fix coords via helper and airports via helper
    coords = helper.get_route_fix_coords(items)
    apt_coords = helper.load_airport_coords()
    # If route explicitly indicates none, ignore any fixes and render airport-to-airport only
    route_indicates_none = 'no route generated' in (items or '').lower()
    if route_indicates_none:
        coords = []

    points = []  # for bounds
    # Small helper to add a text label marker at given lat/lon (reduces duplication)
    def add_distance_label(lat: float, lon: float, text: str, color: str = '#cfd8dc'):
        folium.map.Marker(
            location=[lat, lon],
            icon=folium.DivIcon(html=(
                f'<div style="position: relative; left: 50%; transform: translate(-50%, -10px);'
                f' font-size: 11px; color: {color}; background: rgba(0,0,0,0.35); padding: 2px 4px; border-radius: 3px;'
                f' white-space: nowrap; text-shadow: 0 0 2px #000, 0 0 3px #000; pointer-events: none;">{text}</div>'
            ))
        ).add_to(m)

    def add_text_label(lat: float, lon: float, text: str, *, color: str = '#8bd9f8', dy_px: int = -14, size_px: int = 11, weight: int | str = 'normal'):
        folium.map.Marker(
            location=[lat, lon],
            icon=folium.DivIcon(html=(
                f'<div style="position: relative; left: 50%; transform: translate(-50%, {dy_px}px);'
                f' font-size: {size_px}px; font-weight: {weight}; color: {color}; white-space: nowrap;'
                f' text-shadow: 0 0 2px #000, 0 0 3px #000; pointer-events: none;">{text}</div>'
            ))
        ).add_to(m)

    total_distance_nm = 0.0
    # Build folium map
    m = folium.Map(location=[0, 0], zoom_start=2, tiles='CartoDB dark_matter')

    # Add route line (single polyline) if available
    if len(coords) >= 2:
        folium.PolyLine([(c[0], c[1]) for c in coords], color='#00c2ff', weight=3, opacity=0.85).add_to(m)
    # Plot fix markers (even if only 1), unknown fixes are already ignored by lookup
    for lat, lon, name in coords:
            folium.CircleMarker(location=[lat, lon], radius=4, color='#00c2ff', fill=True, fill_color='#ffffff', fill_opacity=0.9, popup=name, tooltip=name).add_to(m)
            add_text_label(lat, lon, name, color="#8bd9f8", dy_px=-14, size_px=11, weight='normal')
            points.append((lat, lon))

    # Add origin/dest airport markers if available
    o = (apt_coords.get((origin or '').upper()) if origin else None)
    d = (apt_coords.get((dest or '').upper()) if dest else None)
    if o:
        folium.Marker(location=[o[0], o[1]], icon=folium.Icon(color='lightgreen', icon='plane', prefix='fa'), popup=f"{origin.upper()} (Origin)", tooltip=f"{origin.upper()} (Origin)").add_to(m)
        add_text_label(o[0], o[1], origin.upper(), color="#a2f5bf", dy_px=-16, size_px=12, weight=700)
        points.append(o)
    if d:
        folium.Marker(location=[d[0], d[1]], icon=folium.Icon(color='orange', icon='flag', prefix='fa'), popup=f"{dest.upper()} (Destination)", tooltip=f"{dest.upper()} (Destination)").add_to(m)
        add_text_label(d[0], d[1], dest.upper(), color="#ffcc80", dy_px=-16, size_px=12, weight=700)
        points.append(d)

    # Build legs for distance labeling; draw connector lines dashed
    label_legs: list[tuple[float, float, float, float, str]] = []  # (lat1, lon1, lat2, lon2, color)
    if o and coords:
        first = coords[0]
        folium.PolyLine([[o[0], o[1]], [first[0], first[1]]], color='#90a4ae', weight=2, opacity=0.85, dash_array='4,6').add_to(m)
        label_legs.append((o[0], o[1], first[0], first[1], '#cfd8dc'))
    if len(coords) >= 2:
        for i in range(len(coords) - 1):
            lat1, lon1, _ = coords[i]
            lat2, lon2, _ = coords[i + 1]
            label_legs.append((lat1, lon1, lat2, lon2, '#ffd54f'))
    if d and coords:
        last = coords[-1]
        folium.PolyLine([[last[0], last[1]], [d[0], d[1]]], color='#90a4ae', weight=2, opacity=0.85, dash_array='4,6').add_to(m)
        label_legs.append((last[0], last[1], d[0], d[1], '#cfd8dc'))
    # Only draw airport-to-airport dashed when route explicitly says "No route generated."
    if (o and d) and route_indicates_none and not coords:
        folium.PolyLine([[o[0], o[1]], [d[0], d[1]]], color='#90a4ae', weight=2, opacity=0.85, dash_array='4,6').add_to(m)
        label_legs.append((o[0], o[1], d[0], d[1], '#cfd8dc'))

    # Compute total and place labels for all legs
    for (lat1, lon1, lat2, lon2, color) in label_legs:
        leg_nm = helper.haversine_nm(lat1, lon1, lat2, lon2)
        total_distance_nm += leg_nm
        mid_lat = (lat1 + lat2) / 2
        mid_lon = (lon1 + lon2) / 2
        add_distance_label(mid_lat, mid_lon, f"{leg_nm:.1f} nm", color=color)

    # Fit map to all points if we have at least one
    if points:
        min_lat = min(p[0] for p in points)
        max_lat = max(p[0] for p in points)
        min_lon = min(p[1] for p in points)
        max_lon = max(p[1] for p in points)
        m.fit_bounds([[min_lat, min_lon], [max_lat, max_lon]], padding=(20, 20))

    html = m.get_root().render()
    return templates.TemplateResponse("partials/route_map.html", {"request": request, "html": html, "total_distance_nm": f"{total_distance_nm:.1f}"})

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
        icao_u = (icao or '').strip().upper()
        metar = helper.fetch_metar(icao_u) or "No METAR found."
    except Exception as e:
        metar = f"Error: {e}"
    return templates.TemplateResponse("partials/metar_block.html", {
        "request": request,
        "icao": icao_u,
        "metar": metar,
    })

@app.post("/search_sid", response_class=HTMLResponse)
def search_sid(request: Request, origin: str = Form(...), fix: str = Form("")):
    helper = RouteHelper()
    sid_text = ""
    try:
        origin_u = (origin or '').strip().upper()
        helper.get_file_data(origin_u)
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
        "origin": origin_u,
        "sid_text": sid_text,
    })

@app.post("/search_star", response_class=HTMLResponse)
def search_star(request: Request, dest: str = Form(...), fix: str = Form("")):
    helper = RouteHelper()
    star_text = ""
    try:
        dest_u = (dest or '').strip().upper()
        helper.get_file_data(dest_u)
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
        "dest": dest_u,
        "star_text": star_text,
    })
@app.get("/health")
def health():
    return {"status": "ok"}
