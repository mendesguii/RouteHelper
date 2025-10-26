import os
from typing import Dict, List, Tuple
from dotenv import load_dotenv

load_dotenv()


def _data_path() -> str:
    return os.getenv('DATA_PATH', '.')


def load_fix_index() -> Dict[str, Tuple[float, float]]:
    index: dict = {}
    fix_path = os.path.join(_data_path(), 'earth_fix.dat')
    try:
        with open(fix_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith(';'):
                    continue
                parts = line.split()
                if len(parts) < 3:
                    continue
                try:
                    lat = float(parts[0])
                    lon = float(parts[1])
                    ident = parts[2].upper()
                    if ident and ident not in index:
                        index[ident] = (lat, lon)
                except Exception:
                    continue
    except FileNotFoundError:
        index = {}
    return index


def load_airport_coords() -> Dict[str, Tuple[float, float]]:
    coords: dict = {}
    meta_candidates = [
        os.path.join(_data_path(), 'earth_aptmeta.dat'),
        os.path.join(_data_path(), 'earth_metadata.dat'),
    ]
    meta_path = next((p for p in meta_candidates if os.path.isfile(p)), None)
    if meta_path:
        try:
            with open(meta_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith(';'):
                        continue
                    parts = line.split()
                    if len(parts) >= 4:
                        code = parts[0].upper()
                        try:
                            lat = float(parts[2])
                            lon = float(parts[3])
                            coords[code] = (lat, lon)
                        except Exception:
                            continue
        except Exception:
            coords = {}
    return coords


def get_route_fix_coords(items_text: str) -> List[Tuple[float, float, str]]:
    index = load_fix_index()
    seq = [s for s in (items_text or '').split() if s.strip()]
    coords: list[tuple[float, float, str]] = []
    for it in seq:
        pos = index.get(it.upper())
        if pos:
            coords.append((pos[0], pos[1], it.upper()))
    return coords
