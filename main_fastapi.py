from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from main import RouteHelper
from datetime import datetime

app = FastAPI()

# Mount static files for Bulma and htmx
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

AIRCRAFT_OPTIONS = ["A319", "A320", "A321", "B738_ZIBO", "B738", "B737"]
DEFAULT_FL_START = "250"
DEFAULT_FL_END = "350"

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "aircraft_options": AIRCRAFT_OPTIONS,
            "default_fl_start": DEFAULT_FL_START,
            "default_fl_end": DEFAULT_FL_END,
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
        route_list, route_text = helper.fetch_route(origin, dest, fl_start, fl_end, helper.cycle)
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
        "aircraft_options": AIRCRAFT_OPTIONS,
        "default_fl_start": DEFAULT_FL_START,
        "default_fl_end": DEFAULT_FL_END,
    })

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
        if fix:
            sid_text = helper.search_in_dict_text(sid_dict, fix)
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
        if fix:
            star_text = helper.search_in_dict_text(star_dict, fix)
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
