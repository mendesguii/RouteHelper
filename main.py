import sys
import logging
import requests
import os
import re
import math
from bs4 import BeautifulSoup
from typing import Optional
from dotenv import load_dotenv
import json
from datetime import datetime


class RouteHelper:
    """Class to encapsulate route planning logic and state."""
    def __init__(self, env_path='.env'):
        # Basic logging (INFO by default so raw response shows up)
        logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(name)s: %(message)s')
        self._log = logging.getLogger(self.__class__.__name__)
        self.ensure_env(env_path)
        load_dotenv(env_path)
        self.data_path = os.getenv('DATA_PATH', '.')
        # AIRAC cycle for rfinder DB; default to 2501 if not set
        try:
            self.cycle = int(os.getenv('CYCLE', '2501'))
        except ValueError:
            self.cycle = 2501
        self.sids = []
        self.stars = []
        self.apps = []
        self.rwys = []
        self.plan = None
        self.route = None
        # Caches for map lookups
        self._fix_index = None
        self._airport_coords = None

    # -------- Non-mutating convenience APIs --------
    def fetch_loadsheet(self, origin: str, dest: str, plane: str) -> tuple[str, Optional[dict]]:
        """Return loadsheet text and parsed dict without mutating self.plan.

        Uses the same source as get_fuel.
        """
        headers = {
            'okstart': 1,
            'EQPT': plane.upper(),
            'ORIG': origin.upper(),
            'DEST': dest.upper(),
            'submit': 'LOADSHEET',
            'RULES': 'FARDOM',
            'UNITS': 'METRIC',
        }
        r = requests.post('http://fuelplanner.com/index.php', data=headers)
        soup = BeautifulSoup(r.text, 'html5lib')
        loadsheet = soup.pre.text.replace('fuelplanner.com | home', '').replace('Copyright 2008-2019 by Garen Evans', '')
        parsed = None
        try:
            parsed = self.parse_loadsheet(loadsheet)
        except Exception:
            parsed = None
        return loadsheet, parsed

    def fetch_route(self, origin: str, dest: str, minalt: str, maxalt: str, cycle: int) -> tuple[list, str]:
        """Return route list and full route text without mutating self.route/plan."""
        headers = {
            'id1': origin.upper(),
            'ic1': '',
            'id2': dest.upper(),
            'ic2': '',
            'minalt': f'FL{minalt}',
            'maxalt': f'FL{maxalt}',
            'lvl': 'B',
            'dbid': cycle,
            'usesid': 'Y',
            'usestar': 'Y',
            'easet': 'Y',
            'rnav': 'Y',
            'nats': 'R'
        }
        r = requests.post('http://rfinder.asalink.net/free/autoroute_rtx.php', data=headers)
        soup = BeautifulSoup(r.text, 'html5lib')
        genroute_tags = soup.find_all('tt')
        if len(genroute_tags) < 2:
            return [], 'No route generated.'
        genroute = genroute_tags[1].text
        route_list = genroute.split(' ')[2:-2]
        route_text = ' '.join(route_list) if route_list else 'No route generated.'
        return route_list, route_text

    def fetch_metar(self, icao: str) -> str:
        """Return METAR string without mutating self.plan."""
        r = requests.get(f'https://aviationweather.gov/api/data/metar?ids={icao}')
        soup = BeautifulSoup(r.text, 'html5lib')
        return soup.text

    # (map helpers moved to FastAPI layer)
    # Geometry helpers
    @staticmethod
    def haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Approximate great-circle distance between two points in nautical miles."""
        R_nm = 3440.065  # Earth radius in nautical miles
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlmb = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R_nm * c
    # Map data loading helpers (file I/O centralized here)
    def load_fix_index(self) -> dict:
        """Load and cache fix coordinates from earth_fix.dat under DATA_PATH.

        Returns a dict mapping FIXNAME -> (lat, lon)
        """
        if self._fix_index is not None:
            return self._fix_index
        index: dict = {}
        fix_path = os.path.join(self.data_path, 'earth_fix.dat')
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
                        name = parts[-1].upper()
                        if name and name not in index:
                            index[name] = (lat, lon)
                    except Exception:
                        continue
        except FileNotFoundError:
            index = {}
        self._fix_index = index
        return index

    def load_airport_coords(self) -> dict:
        """Load and cache airport coordinates from X-Plane metadata files.

        Tries DATA_PATH/earth_aptmeta.dat then DATA_PATH/earth_metadata.dat.
        Returns a dict mapping ICAO -> (lat, lon)
        """
        if self._airport_coords is not None:
            return self._airport_coords
        coords: dict = {}
        meta_candidates = [
            os.path.join(self.data_path, 'earth_aptmeta.dat'),
            os.path.join(self.data_path, 'earth_metadata.dat'),
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
                        # Expected: ICAO COUNTRY LAT LON ...
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
        self._airport_coords = coords
        return coords

    def get_route_fix_coords(self, items_text: str) -> list[tuple[float, float, str]]:
        """Return a list of (lat, lon, name) for items present in the fix index.

        The items_text is a space-separated route string. Unknown tokens are ignored.
        """
        index = self.load_fix_index()
        seq = [s for s in (items_text or '').split() if s.strip()]
        coords: list[tuple[float, float, str]] = []
        for it in seq:
            pos = index.get(it.upper())
            if pos:
                coords.append((pos[0], pos[1], it.upper()))
        return coords

    # -------- AIRAC helpers (cycle.json) --------
    def read_cycle_json(self) -> Optional[dict]:
        """Return parsed cycle.json from DATA_PATH if present, else None."""
        path = os.path.join(self.data_path, 'cycle.json')
        if not os.path.isfile(path):
            return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None

    def expected_cycle_str(self) -> str:
        """Return current cycle in YYMM format from system date."""
        now = datetime.now()
        return f"{now.year % 100:02d}{now.month:02d}"

    def is_cycle_current(self, cycle_str: str) -> bool:
        return (cycle_str or '').strip() == self.expected_cycle_str()

    def get_airac_info(self) -> dict:
        """Read-only AIRAC info from cycle.json; no writes.

        Returns: {
          'cycle': str|None,
          'name': str|None,
          'revision': str|None,
          'source': 'json'|'missing',
          'is_current': bool,
        }
        """
        data = self.read_cycle_json()
        if not data:
            return {'cycle': None, 'name': None, 'revision': None, 'source': 'missing', 'is_current': False}
        cycle = str(data.get('cycle', '')).strip() or None
        return {
            'cycle': cycle,
            'name': data.get('name'),
            'revision': str(data.get('revision')) if data.get('revision') is not None else None,
            'source': 'json',
            'is_current': self.is_cycle_current(cycle or ''),
        }

    def get_cycle(self) -> int:
        """Return AIRAC cycle from cycle.json; raise if missing or invalid.

        YYMM is used only for is_current comparison, not as a fallback.
        """
        data = self.read_cycle_json()
        if not data:
            raise FileNotFoundError("cycle.json not found under DATA_PATH")
        try:
            return int(str(data.get('cycle', '')).strip())
        except Exception as e:
            raise ValueError("Invalid cycle value in cycle.json") from e

    def list_cifp_icaos(self, prefix: str = "", limit: int = 20) -> list[str]:
        """List available ICAO codes from the CIFP directory based on a prefix.

        Looks under DATA_PATH/CIFP first; if not present, falls back to DATA_PATH.
        Returns up to `limit` codes, sorted, filtered by case-insensitive prefix.
        """
        base_cifp = os.path.join(self.data_path, 'CIFP')
        search_dir = base_cifp if os.path.isdir(base_cifp) else self.data_path
        codes: list[str] = []
        try:
            for name in os.listdir(search_dir):
                if name.lower().endswith('.dat'):
                    code = os.path.splitext(name)[0]
                    codes.append(code)
        except Exception:
            # In case DATA_PATH is invalid; return empty list gracefully
            return []
        p = (prefix or '').strip().upper()
        if p:
            codes = [c for c in codes if c.upper().startswith(p)]
        codes.sort()
        return codes[: max(0, int(limit))]

    def search_in_dict_text(self, obj_dict: dict, value: str) -> str:
        """Return search results as text (non-mutating)."""
        lines = [f"- Fix Search: {value}"]
        for k, v in obj_dict.items():
            if value in v or value in k:
                lines.append(f"* Chart: {k} || Route: {v}")
        return '\n'.join(lines).strip()

    def infer_sid_star(self, origin: str, dest: str, route_list: list[str]) -> tuple[str, str]:
        """Infer SID/STAR text based on first/last fixes of route_list."""
        sid_text = "No SID fix found."
        star_text = "No STAR fix found."
        try:
            self.get_file_data(origin)
            if route_list:
                sid_dict = self.structure_data(self.sids)
                self.plan = ''  # ensure previous state does not interfere
                self.search_in_dict(sid_dict, route_list[0])
                sid_text = self.plan or sid_text
        except Exception as e:
            sid_text = f"Error: {e}"
        try:
            self.get_file_data(dest)
            if route_list:
                star_dict = self.structure_data(self.stars)
                self.plan = ''
                self.search_in_dict(star_dict, route_list[-1])
                star_text = self.plan or star_text
        except Exception as e:
            star_text = f"Error: {e}"
        return sid_text, star_text

    @staticmethod
    def ensure_env(env_path):
        if not os.path.exists(env_path):
            # Create .env with default values
            with open(env_path, 'w', encoding='utf-8') as f:
                f.write('DATA_PATH=.' + '\n')
                f.write('CYCLE=2501' + '\n')
        else:
            # Ensure required keys exist
            with open(env_path, 'r', encoding='utf-8') as f:
                content = f.read()
            changed = False
            if 'DATA_PATH=' not in content:
                content += ('\n' if not content.endswith('\n') else '') + 'DATA_PATH=.' + '\n'
                changed = True
            if 'CYCLE=' not in content:
                content += ('\n' if not content.endswith('\n') else '') + 'CYCLE=2501' + '\n'
                changed = True
            if changed:
                with open(env_path, 'w', encoding='utf-8') as f:
                    f.write(content)
    
    def reset_procedure_lists(self):
        self.sids = []
        self.stars = []
        self.apps = []
        self.rwys = []

    def get_file_data(self, name_or_path: str):
        """Parse .dat file and populate procedure lists.

        Simple rules:
        - If name_or_path is an existing file, use it.
        - Else treat it as an ICAO code and try:
          1) DATA_PATH/CIFP/<ICAO>.dat
          2) DATA_PATH/<ICAO>.dat
        """
        self.reset_procedure_lists()
        # 1) Direct file path
        if os.path.isfile(name_or_path):
            resolved = name_or_path
        else:
            icao = os.path.basename(name_or_path).split('.')[0]
            candidate_cifp = os.path.join(self.data_path, 'CIFP', f'{icao}.dat')
            candidate_root = os.path.join(self.data_path, f'{icao}.dat')
            resolved = candidate_cifp if os.path.isfile(candidate_cifp) else candidate_root
        with open(resolved, 'r', encoding='utf-8') as f:
            for line in f:
                if 'SID:' in line:
                    self.sids.append(line)
                elif 'STAR' in line:
                    self.stars.append(line)
                elif 'APPCH' in line:
                    self.apps.append(line)
                elif 'RWY' in line:
                    self.rwys.append(line)

    def structure_data(self, rawdata):
        """Structure raw procedure data into a dictionary."""
        object_dict = {}
        proc_type = None
        for entry in rawdata:
            current = entry.split(',')
            proc_type = current[0].split(':')[0]
            num = current[0].split(':')[1]
            procedure = current[2]
            cur_pos_start = current[3]
            cur_pos_end = current[4]

            key = f"{procedure}-{cur_pos_start}"
            value = cur_pos_end.replace('  ', '')
            if num == "010":
                object_dict[key] = value
            else:
                object_dict[key] = object_dict.get(key, '')
                if object_dict[key]:
                    object_dict[key] += ' '
                object_dict[key] += value

        if rawdata:
            self.clean_dictionary(object_dict, proc_type)
        return object_dict

    # Utility used by legacy code to extract times from text
    @staticmethod
    def get_info_after(label: str, text: Optional[str]) -> str:
        if not text:
            return ''
        # Attempt generic HH:MM capture following the label
        try:
            m = re.search(fr'{re.escape(label)}\s+(\d{{2}}:\d{{2}})', text)
            return m.group(1) if m else ''
        except Exception:
            return ''

    @staticmethod
    def clean_dictionary(obj_dict, proc_type):
        """Clean up the procedure dictionary by merging RW entries."""
        list_to_delete = []
        for i in obj_dict:
            split_name = i.split('-')
            if len(split_name) > 1 and 'RW' in split_name[1]:
                for x in obj_dict:
                    if split_name[0] in x and 'RW' not in x:
                        list_to_delete.append(i)
                        if proc_type == "SID":
                            obj_dict[x] = f"[{split_name[1]}] {obj_dict[i].replace('  ', '')} | {obj_dict[x]}"
                        elif proc_type == "STAR":
                            obj_dict[x] = f"{obj_dict[x]} | {obj_dict[i]} [{split_name[1]}]"
        # Remove duplicates
        for item in set(list_to_delete):
            del obj_dict[item]

    def search_in_dict(self, obj_dict, value):
        """Search for a value in the procedure dictionary (delegates to search_in_dict_text)."""
        result = self.search_in_dict_text(obj_dict, value)
        if self.plan is not None:
            self.plan = result
        else:
            print(result)

    def get_metar(self, icao):
        """Fetch METAR for an airport (delegates to fetch_metar)."""
        metar = self.fetch_metar(icao)
        if self.plan is not None:
            self.plan += f'\n- Metar {icao}: {metar}'
        else:
            print(f'Metar: {metar}')

    def get_route(self, icao, icao_dest, minalt, maxalt, cycle):
        """Fetch route from rfinder (delegates to fetch_route)."""
        route_list, route_text = self.fetch_route(icao, icao_dest, minalt, maxalt, cycle)
        self.route = route_list
        if self.plan is not None:
            self.plan += f'- Route: {route_text}\n'
        else:
            print(f'Route: {route_text}')

    def get_fuel(self, icao, icao_dest, plane):
        """Fetch fuel/loadsheet info (delegates to fetch_loadsheet)."""
        loadsheet, parsed = self.fetch_loadsheet(icao, icao_dest, plane)
        self.plan = loadsheet
        self.parsed_loadsheet = parsed

    def parse_loadsheet(self, text: str) -> dict:
        # Backward-compatible delegation to shared service
        from app.services.loadsheets import parse_loadsheet as _parse
        return _parse(text)




    def run(self, argv):
        try:
            if len(argv) < 3:
                raise ValueError('Not enough arguments')
            icao = argv[1].upper()
            option = argv[2].upper()
            fix = argv[3].upper() if len(argv) > 3 else None

            if option == 'SID':
                self.get_file_data(icao)
                if fix is None:
                    print(self.structure_data(self.sids))
                else:
                    self.search_in_dict(self.structure_data(self.sids), fix)
            elif option == 'STAR':
                self.get_file_data(icao)
                if fix is None:
                    print(self.structure_data(self.stars))
                else:
                    self.search_in_dict(self.structure_data(self.stars), fix)
            elif option == 'METAR':
                self.get_metar(icao)
            elif option == 'ROUTE':
                icaos = icao.split('/')
                if len(argv) < 4:
                    raise ValueError('Plane type required for ROUTE')
                plane = argv[3]
                self.get_fuel(icaos[0], icaos[1], plane)
                self.get_route(icaos[0], icaos[1], '330', '330', self.get_cycle())
                self.get_metar(icaos[0])
                self.get_metar(icaos[1])
                self.get_file_data(icaos[0])
                if self.route:
                    self.search_in_dict(self.structure_data(self.sids), self.route[0])
                self.get_file_data(icaos[1])
                if self.route:
                    self.search_in_dict(self.structure_data(self.stars), self.route[-1])
                print(self.plan)
            else:
                raise ValueError('Unknown option')
        except Exception as e:
            print(
                """
                                                ~ UNKNOWN COMMAND ~
                                                
        ======================================= AVAILABLE COMMANDS =====================================
        
        - ICAO (SID/STAR) : Lists all available procedures and its routes
        - ICAO (SID/STAR) FIX: Search for a fix in all procedures (can also search by name of procedure)
        - ICAO METAR: Returns METAR of the airport
        - ICAO/ICAO ROUTE PLANE: List all info for a route (Route, Fuel, SIDS and STARS)
        """
            )
            print(f"Error: {e}")


def main():
    helper = RouteHelper()
    helper.run(sys.argv)


if __name__ == "__main__":
    main()
