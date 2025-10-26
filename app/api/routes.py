from fastapi import APIRouter, Request, Form
from typing import Optional
from fastapi.responses import HTMLResponse
from datetime import datetime
import logging
from app.utils.airac import is_cycle_current
from app.utils.dbnav import get_route_fix_coords_db as nav_get_route_fix_coords_db, get_airport_coords_db as nav_get_airport_coords_db, list_icaos_db as list_icaos_db
from app.services.fpl_builder import build_vatsim_icao_fpl
from app.services.ops import fetch_loadsheet as svc_fetch_loadsheet, fetch_route as svc_fetch_route, fetch_metar as svc_fetch_metar
from app.services.planner import plan_standards_route, PlannerOptions
from app.services.maps import build_route_map_html
from app.services.procedures import infer_sid_star
from app.services.procedures import structure_data as proc_structure_data
from app.services.procedures import search_in_dict_text as proc_search_text
from app.utils.dbnav import get_procedure_texts_db as proc_get_texts_db
from app.db.session import get_db
from app.db.models import FlightPlan, AiracCycle
from fastapi import Depends
from sqlalchemy.orm import Session

router = APIRouter()
log = logging.getLogger(__name__)


def templates(request: Request):
    return request.app.state.templates


def _airac_from_db(db: Session) -> dict:
    rec = db.query(AiracCycle).order_by(AiracCycle.id.desc()).first()
    if not rec:
        return {"cycle": None, "name": None, "revision": None, "source": "missing", "is_current": False}
    cyc = (rec.cycle or '').strip()
    return {
        "cycle": cyc or None,
        "name": rec.name,
        "revision": rec.revision,
        "source": "db",
        "is_current": is_cycle_current(cyc) if cyc else False,
    }


# Local constants (avoid importing side-effectful modules)
AIRCRAFT_OPTIONS = ["A319", "A320", "A321", "B738_ZIBO", "B738", "B737"]
DEFAULT_FL_START = "250"
DEFAULT_FL_END = "350"


@router.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    log.info("Page opened: / (planner)")
    airac = _airac_from_db(db)
    return templates(request).TemplateResponse(
        "index.html",
        {
            "request": request,
            "aircraft_options": AIRCRAFT_OPTIONS,
            "default_fl_start": DEFAULT_FL_START,
            "default_fl_end": DEFAULT_FL_END,
            "airac": airac,
        },
    )


@router.post("/plan", response_class=HTMLResponse)
def plan_route(request: Request,
               origin: str = Form(...),
               dest: str = Form(...),
               plane: str = Form(...),
               fl_start: str = Form(DEFAULT_FL_START),
               fl_end: str = Form(DEFAULT_FL_END),
               use_internal_planner: Optional[str] = Form(None),
               db: Session = Depends(get_db)):
    log.info("Action: plan route origin=%s dest=%s plane=%s fl=[%s,%s]", origin, dest, plane, fl_start, fl_end)
    airac = _airac_from_db(db)
    origin_u = (origin or '').strip().upper()
    dest_u = (dest or '').strip().upper()
    try:
        loadsheet, parsed = svc_fetch_loadsheet(origin_u, dest_u, plane)
    except Exception as e:
        loadsheet, parsed = (f"Error: {e}", None)
    parsed = parsed or {}
    ttl = (parsed.get('weights', {}) or {}).get('total_traffic_load')
    tof = (parsed.get('weights', {}) or {}).get('takeoff_fuel')
    blk = (parsed.get('times', {}) or {}).get('block_time')
    endurance = (parsed.get('times', {}) or {}).get('time_to_empty')
    tc_val = (parsed.get('flight', {}) or {}).get('tc')
    try:
        cyc = (airac.get('cycle') or '').strip()
        cycle_val = int(cyc) if cyc.isdigit() else 2501
        if use_internal_planner:
            # Use DB-backed internal planner
            try:
                fl_lo = int(fl_start)
                fl_hi = int(fl_end)
            except Exception:
                fl_lo, fl_hi = 250, 350
            if fl_lo > fl_hi:
                fl_lo, fl_hi = fl_hi, fl_lo
            opts = PlannerOptions(origin=origin_u, dest=dest_u, fl_start=fl_lo, fl_end=fl_hi)
            route_list, route_text = plan_standards_route(db, opts)
        else:
            route_list, route_text = svc_fetch_route(origin_u, dest_u, fl_start, fl_end, cycle_val)
    except Exception as e:
        route_list, route_text = ([], f"Error: {e}")
    sid_text, star_text = infer_sid_star(db, origin_u, dest_u, route_list)
    tc_up = ((tc_val or "").strip()).upper()
    if "EAST" in tc_up:
        direction_label = "eastbound"
    elif "WEST" in tc_up:
        direction_label = "westbound"
    else:
        direction_label = "unknown"
    eastbound = True if direction_label == "eastbound" else (False if direction_label == "westbound" else None)
    rule_label = "IFR semicircular: eastbound odd FLs, westbound even FLs"
    try:
        fl_lo = int(fl_start)
        fl_hi = int(fl_end)
    except Exception:
        fl_lo, fl_hi = 100, 450
    if fl_lo > fl_hi:
        fl_lo, fl_hi = fl_hi, fl_lo
    rng = [fl for fl in range(max(100, fl_lo), min(450, fl_hi) + 1, 10)]
    def is_odd_fl(fl: int) -> bool:
        return ((fl // 10) % 2) == 1
    if direction_label == "unknown":
        filtered = []
    else:
        want_odd = bool(eastbound)
        filtered = [fl for fl in rng if is_odd_fl(fl) == want_odd]
        if not filtered:
            filtered = rng
    eligible_fls = [f"FL{fl}" for fl in filtered]
    try:
        metar_origin = svc_fetch_metar(origin_u) or "No METAR found."
    except Exception as e:
        metar_origin = f"Error: {e}"
    try:
        metar_dest = svc_fetch_metar(dest_u) or "No METAR found."
    except Exception as e:
        metar_dest = f"Error: {e}"
    route_str = ' '.join(route_list) if route_list else ''
    si_block_time = (parsed.get('times', {}) or {}).get('block_time', '')
    eet = si_block_time.replace(':', '') if si_block_time else ''
    msg = build_vatsim_icao_fpl(
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
    # Persist flight plan (best-effort)
    try:
        fp = FlightPlan(
            origin=origin_u,
            dest=dest_u,
            aircraft=plane,
            fl_start=int(fl_start) if str(fl_start).isdigit() else None,
            fl_end=int(fl_end) if str(fl_end).isdigit() else None,
            cycle=str(cycle_val) if 'cycle_val' in locals() else None,
            route_text=route_text,
            route_list=route_str,
            sid_text=sid_text,
            star_text=star_text,
        )
        db.add(fp)
        db.commit()
    except Exception:
        # ignore DB errors
        pass

    return templates(request).TemplateResponse("result.html", {
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


@router.post("/route_map", response_class=HTMLResponse)
def route_map(request: Request, items: str = Form(""), origin: str = Form(""), dest: str = Form(""), theme: str = Form("auto"), db: Session = Depends(get_db)):
    log.info("Action: build route map origin=%s dest=%s items_len=%d theme=%s", origin, dest, len(items or ''), theme)
    items = (items or "").strip()
    origin_u = (origin or '').strip().upper()
    dest_u = (dest or '').strip().upper()
    coords = nav_get_route_fix_coords_db(db, items)
    apt_coords = nav_get_airport_coords_db(db)
    route_indicates_none = 'no route generated' in items.lower()
    html, total_distance_nm = build_route_map_html(coords, apt_coords, origin_u, dest_u, route_indicates_none, theme)
    return templates(request).TemplateResponse("partials/route_map.html", {"request": request, "html": html, "total_distance_nm": f"{total_distance_nm:.1f}"})


@router.post("/route_map_close", response_class=HTMLResponse)
def route_map_close():
    return ""


@router.get("/icao_suggest", response_class=HTMLResponse)
def icao_suggest(request: Request, q: str = "", origin: str = "", dest: str = "", limit: int = 20, mode: str = "options", input_id: str = "", target_id: str = "", db: Session = Depends(get_db)):
    # No helper needed here
    query = (q or origin or dest or "").strip()
    # If query is empty, return empty menus/options depending on mode
    if not query:
        if mode == "menu":
            return templates(request).TemplateResponse("partials/icao_menu.html", {
                "request": request,
                "codes": [],
                "q": query,
                "input_id": input_id,
                "target_id": target_id,
            })
        else:
            return templates(request).TemplateResponse("partials/icao_options.html", {
                "request": request,
                "codes": [],
            })

    # Non-empty query: list codes and render appropriate partial
    codes = list_icaos_db(db, query, limit)
    if mode == "menu":
        return templates(request).TemplateResponse("partials/icao_menu.html", {
            "request": request,
            "codes": codes,
            "q": query,
            "input_id": input_id,
            "target_id": target_id,
        })
    else:
        return templates(request).TemplateResponse("partials/icao_options.html", {
            "request": request,
            "codes": codes,
        })


@router.get("/metar", response_class=HTMLResponse)
def get_metar(request: Request, icao: str):
    log.info("Action: get METAR %s", icao)
    try:
        icao_u = (icao or '').strip().upper()
        metar = svc_fetch_metar(icao_u) or "No METAR found."
    except Exception as e:
        metar = f"Error: {e}"
    return templates(request).TemplateResponse("partials/metar_block.html", {
        "request": request,
        "icao": icao_u,
        "metar": metar,
    })


@router.post("/search_sid", response_class=HTMLResponse)
def search_sid(request: Request, origin: str = Form(...), fix: str = Form(""), db: Session = Depends(get_db)):
    origin_u = (origin or '').strip().upper()
    try:
        sid_dict = proc_get_texts_db(db, origin_u, kind='SID')
        q = (fix or '').strip().upper()
        sid_text = proc_search_text(sid_dict, q)
    except Exception as e:
        sid_text = f"Error: {e}"
    return templates(request).TemplateResponse("partials/sid_block.html", {
        "request": request,
        "origin": origin_u,
        "sid_text": sid_text,
    })


@router.post("/search_star", response_class=HTMLResponse)
def search_star(request: Request, dest: str = Form(...), fix: str = Form(""), db: Session = Depends(get_db)):
    dest_u = (dest or '').strip().upper()
    try:
        star_dict = proc_get_texts_db(db, dest_u, kind='STAR')
        q = (fix or '').strip().upper()
        star_text = proc_search_text(star_dict, q)
    except Exception as e:
        star_text = f"Error: {e}"
    return templates(request).TemplateResponse("partials/star_block.html", {
        "request": request,
        "dest": dest_u,
        "star_text": star_text,
    })


@router.get("/health")
def health():
    return {"status": "ok"}
