from __future__ import annotations

import os
import logging
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import AiracCycle, Airport, Fix, Airway, Procedure
from app.utils.airac import read_cycle_json
from app.utils.navdata import load_airport_coords, load_fix_index

log = logging.getLogger(__name__)


def _info(msg: str, *args) -> None:
    try:
        text = msg % args if args else msg
    except Exception:
        text = f"{msg} {args}"
    print(f"[INFO] {text}", flush=True)


def upsert_airac(db: Session) -> Optional[AiracCycle]:
    data = read_cycle_json()
    if not data:
        _info("AIRAC: cycle.json not found; skipping upsert")
        return None
    cycle = str(data.get("cycle", "")).strip()
    name = data.get("name")
    revision = str(data.get("revision")) if data.get("revision") is not None else None
    cur = db.query(AiracCycle).filter(AiracCycle.cycle == cycle).one_or_none()
    if cur:
        cur.name = name
        cur.revision = revision
        _info("AIRAC: existing cycle %s updated", cycle)
        return cur
    db.query(AiracCycle).update({AiracCycle.current: False})
    cur = AiracCycle(cycle=cycle, name=name, revision=revision, current=True)
    db.add(cur)
    _info("AIRAC: inserted cycle %s", cycle)
    return cur


def index_airports(db: Session) -> int:
    coords = load_airport_coords() or {}
    _info("Airports: %d entries loaded from files", len(coords))
    added = 0
    for icao, (lat, lon) in coords.items():
        rec = db.query(Airport).filter(Airport.icao == icao).one_or_none()
        if rec:
            rec.lat = lat
            rec.lon = lon
        else:
            db.add(Airport(icao=icao, lat=lat, lon=lon))
            added += 1
    _info("Airports: %d added (others updated)", added)
    return added


def index_fixes(db: Session) -> int:
    # Full parse of earth_fix.dat to ensure multiple (ident, country) variants are captured
    path = os.path.join(_data_path(), "earth_fix.dat")
    added = 0
    seen: set[tuple[str, Optional[str], float, float]] = set()
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith(';'):
                    continue
                parts = line.split()
                if len(parts) < 3:
                    continue
                try:
                    lat = float(parts[0]); lon = float(parts[1])
                    ident = parts[2].upper()
                except Exception:
                    continue
                usage = (parts[3].strip().upper() if len(parts) > 3 else None)
                country = (parts[4].strip().upper() if len(parts) > 4 else None)
                dbid = (parts[5].strip() if len(parts) > 5 else None)
                name = (parts[6].strip() if len(parts) > 6 else None)
                key = (ident, country, lat, lon)
                if key in seen:
                    continue
                # avoid duplicates in DB
                exists = (
                    db.query(Fix)
                    .filter(
                        Fix.ident == ident,
                        Fix.country == country,
                        Fix.lat == lat,
                        Fix.lon == lon,
                    )
                    .one_or_none()
                )
                if exists:
                    # Optionally refresh metadata
                    exists.usage = usage
                    exists.dbid = dbid
                    exists.name = name
                    continue
                try:
                    db.add(Fix(ident=ident, usage=usage, country=country, lat=lat, lon=lon, dbid=dbid, name=name))
                    db.flush()
                    added += 1
                    seen.add(key)
                except IntegrityError:
                    db.rollback()
                    continue
    except FileNotFoundError:
        _info("Fixes: file not found: %s", path)
    _info("Fixes: %d added", added)
    return added


def run_full_index(db: Session, *, force: bool = False) -> dict:
    _info("Index pipeline start (force=%s)", force)

    data = read_cycle_json()
    json_cycle = str(data.get("cycle", "")).strip() if data else None
    existing = db.query(AiracCycle).filter(AiracCycle.cycle == (json_cycle or "")).one_or_none() if json_cycle else None
    if existing and not force:
        _info("Index skipped: AIRAC unchanged (cycle=%s).", json_cycle)
        return {
            "airac": 0,
            "airports": db.query(Airport).count(),
            "fixes": db.query(Fix).count(),
            "airways": 0,
            "procedures": {"sids": 0, "stars": 0},
            "skipped": True,
            "reason": "AIRAC unchanged",
        }

    if force:
        _info("Force reindex: clearing airports/fixes/airways/procedures")
        db.query(Airway).delete()
        db.query(Procedure).delete()
        db.query(Fix).delete()
        db.query(Airport).delete()

    upsert_airac(db)
    airports_added = index_airports(db)
    fixes_added = index_fixes(db)
    # Ensure Fixes are visible to subsequent queries
    try:
        db.flush()
    except Exception:
        pass
    airways_added = index_airways(db)
    procs_counts = index_procedures(db)

    out = {
        "airac": 1 if json_cycle else 0,
        "airports": airports_added,
        "fixes": fixes_added,
        "airways": airways_added,
        "procedures": procs_counts,
        "skipped": False,
    }
    _info("Index done: %s", out)
    return out


def _data_path() -> str:
    return os.getenv("DATA_PATH", ".")


def index_airways(db: Session) -> int:
    path = os.path.join(_data_path(), "earth_awy.dat")
    if not os.path.isfile(path):
        _info("Airways: file not found: %s", path)
        return 0
    _info("Airways: reading %s", path)

    def parse_line(raw: str):
        raw = raw.strip()
        if not raw or raw.startswith(";"):
            return None
        parts = raw.split()
        if len(parts) < 11:
            return None
        try:
            if len(parts) >= 13:
                fix1 = parts[0].upper(); fix1_cc = parts[1].upper()
                fix2 = parts[4].upper(); fix2_cc = parts[5].upper()
                direction = parts[8].upper()
                route_class = int(parts[9]); lower_fl = int(parts[10]); upper_fl = int(parts[11])
                airway_name = parts[12].upper()
            else:
                fix1 = parts[0].upper(); fix1_cc = parts[1].upper()
                fix2 = parts[3].upper(); fix2_cc = parts[4].upper()
                direction = parts[6].upper()
                route_class = int(parts[7]); lower_fl = int(parts[8]); upper_fl = int(parts[9])
                airway_name = parts[10].upper()
        except Exception:
            return None
        if direction not in ("N", "P", "M"):
            return None
        return (fix1, fix1_cc, fix2, fix2_cc, direction, route_class, lower_fl, upper_fl, airway_name)

    def find_fix(ident: str, country: Optional[str]):
        rows = db.query(Fix).filter(Fix.ident == ident).all()
        if not rows:
            return None
        # prefer exact country
        if country:
            for r in rows:
                if (r.country or '').upper() == country:
                    return r
        # fallback ENRT usage
        for r in rows:
            if (r.usage or '').upper() == 'ENRT':
                return r
        # last resort: first row
        return rows[0]

    added = 0
    total = 0
    resolved = 0
    miss_samples: list[tuple[str, str]] = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for raw in f:
            parsed = parse_line(raw)
            if not parsed:
                continue
            total += 1
            fix1, fix1_cc, fix2, fix2_cc, direction, route_class, lower_fl, upper_fl, airway_name = parsed
            f1 = find_fix(fix1, fix1_cc)
            f2 = find_fix(fix2, fix2_cc)
            if not f1 or not f2:
                if len(miss_samples) < 5:
                    miss_samples.append((f"{fix1}@{fix1_cc}", f"{fix2}@{fix2_cc}"))
                continue
            resolved += 1
            # avoid duplicates across runs
            exists = (
                db.query(Airway)
                .filter(
                    Airway.name == airway_name,
                    Airway.fix1_id == f1.id,
                    Airway.fix2_id == f2.id,
                    Airway.direction == direction,
                    Airway.route_class == route_class,
                    Airway.lower_fl == lower_fl,
                    Airway.upper_fl == upper_fl,
                )
                .one_or_none()
            )
            if exists:
                continue
            try:
                db.add(
                    Airway(
                        name=airway_name,
                        fix1_id=f1.id,
                        fix2_id=f2.id,
                        direction=direction,
                        route_class=route_class,
                        lower_fl=lower_fl,
                        upper_fl=upper_fl,
                    )
                )
                db.flush()
                added += 1
            except IntegrityError:
                db.rollback()
                continue
    _info("Airways: parsed=%d resolved=%d added segments=%d", total, resolved, added)
    if added == 0 and miss_samples:
        _info("Airways: sample unresolved pairs: %s", miss_samples)
    return added


def index_procedures(db: Session, *, limit_icaos: Optional[int] = None) -> dict:
    base = os.path.join(_data_path(), "CIFP")
    root = base if os.path.isdir(base) else _data_path()
    try:
        files = [f for f in os.listdir(root) if f.lower().endswith('.dat')]
    except Exception:
        files = []
    files.sort()
    if limit_icaos:
        try:
            files = files[: max(1, int(limit_icaos))]
        except Exception:
            pass
    _info("Procedures: root=%s total_files=%d limit=%s", root, len(files), limit_icaos)

    cnt_sid = 0
    cnt_star = 0

    for fname in files:
        icao = os.path.splitext(fname)[0].upper()
        path = os.path.join(root, fname)
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                buckets: dict[tuple[str, str, str], list[str]] = {}
                for line in f:
                    if ('SID:' in line) or ('STAR' in line):
                        parts = line.split(',')
                        try:
                            proc_tag = parts[0]
                            proc_type, num = proc_tag.split(':', 1)
                            proc_type = proc_type.strip().upper()
                            name = parts[2].strip()
                            start = parts[3].strip()
                            seg = parts[4].replace('  ', ' ').strip()
                        except Exception:
                            continue
                        key = (proc_type, name, start)
                        if num.strip() == '010':
                            buckets[key] = [seg]
                        else:
                            buckets.setdefault(key, []).append(seg)
                for (proc_type, name, start), segments in buckets.items():
                    route = ' '.join(s for s in segments if s).strip()
                    existing = (
                        db.query(Procedure)
                        .filter(
                            Procedure.icao == icao,
                            Procedure.proc_type == proc_type,
                            Procedure.name == name,
                            Procedure.start == start,
                        )
                        .one_or_none()
                    )
                    if existing:
                        existing.route = route
                    else:
                        db.add(Procedure(icao=icao, proc_type=proc_type, name=name, start=start, route=route))
                        if proc_type == 'SID':
                            cnt_sid += 1
                        elif proc_type == 'STAR':
                            cnt_star += 1
        except Exception as e:
            _info("Procedures: failed to read %s: %s", path, e)
            continue
    _info("Procedures: added SIDs=%d STARs=%d", cnt_sid, cnt_star)
    return {"sids": cnt_sid, "stars": cnt_star}
