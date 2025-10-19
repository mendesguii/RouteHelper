import sys
import logging
import requests
import os
import re
from bs4 import BeautifulSoup
from typing import Optional
from dotenv import load_dotenv


class RouteHelper:
    @staticmethod
    def build_vatsim_icao_fpl(
        callsign: str,
        actype: str,
        wakecat: str,
        equipment: str,
        surveillance: str,
        dep_icao: str,
        dep_time: str,
        speed: str,
        level: str,
        route: str,
        dest_icao: str,
        eet: str,
        alt1: str = '',
        alt2: str = '',
        pbn: str = '',
        nav: str = '',
        rnp: str = '',
        dof: str = '',
        reg: str = '',
        sel: str = '',
        code: str = '',
        rvr: str = '',
        opr: str = '',
        per: str = '',
        rmk: str = ''
    ) -> str:
        # Compose the ICAO FPL message as a single line, as per user request
        # Only include fields that are not empty, in the correct order
        parts = [
            f"(FPL-{callsign}-IS",
            f"-{actype}/{wakecat}-{equipment}{surveillance}",
            f"-{dep_icao}{dep_time}",
            f"-{speed}{level} {route}".strip(),
            f"-{dest_icao}{eet} {alt1} {alt2}".strip(),
        ]
        # Optional fields, only if not empty
        if pbn: parts.append(f"-PBN/{pbn}")
        if nav: parts.append(f"NAV/{nav}")
        if rnp: parts.append(f"RNP{rnp}")
        if dof: parts.append(f"DOF/{dof}")
        if reg: parts.append(f"REG/{reg}")
        if eet: parts.append(f"EET/{eet}")
        if sel: parts.append(f"SEL/{sel}")
        if code: parts.append(f"CODE/{code}")
        if rvr: parts.append(f"RVR/{rvr}")
        if opr: parts.append(f"OPR/{opr}")
        if per: parts.append(f"PER/{per}")
        if rmk: parts.append(f"RMK/{rmk}")
        # Join all with spaces, close with )
        return ' '.join([p for p in parts if p.strip()]) + ")"
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
        """Parse the fuelplanner loadsheet text into a structured dictionary.

        Returns a dict with top-level keys: database, flight, routing, weights, times, end.
        Values are numbers where applicable; missing values will be None.
        """
        lines = [ln.rstrip() for ln in (text or '').splitlines()]
        data: dict = {
            'database': None,
            'flight': {
                'from': None,
                'to': None,
                'flight': None,
                'ac_reg': None,
                'version': None,
                'crew': None,
                'date': None,
                'time': None,
                'tc': None,
            },
            'weights': {
                'load_compartments': None,
                'load_compartments_dist': None,
                'passenger_cabin_bag': None,
                'passenger_cabin_bag_dist': None,
                'efu': None,
                'reserve_fuel': None,
                'total_traffic_load': None,
                'dry_operating_weight': None,
                'zfw_actual': None,
                'zfw_max': None,
                'takeoff_fuel': None,
                'tow_actual': None,
                'tow_max': None,
                'trip_fuel': None,
                'ldw_actual': None,
                'ldw_max': None,
                'underload_before_lmc': None,
                'lmc_total': None,
            },
            'times': {
                'block_time': None,
                'reserve': None,
                'time_to_empty': None,
                'ci': None,
            },
            'end': {
                'aircraft': None,
                'route': None,
                'date': None,
            }
        }

        def to_int(s):
            try:
                return int(s)
            except Exception:
                return None

        # database line
        for ln in lines:
            m = re.search(r'^DATABASE\s+(.+)$', ln)
            if m:
                data['database'] = m.group(1).strip()
                break

        # Find FROM/TO header and parse next significant line
        for idx, ln in enumerate(lines):
            if re.search(r'^FROM/TO\s+FLIGHT\s+A/C-REG\s+VERSION\s+CREW\s+DATE\s+TIME', ln):
                # Next non-empty line should have values
                for j in range(idx+1, min(idx+4, len(lines))):
                    vals = lines[j].strip()
                    if not vals:
                        continue
                    m = re.match(r'^(?P<from>[A-Z0-9]{4})/(?P<to>[A-Z0-9]{4})\s+' \
                                 r'(?P<flight>\S+)\s+' \
                                 r'(?P<ac_reg>\S+)\s+' \
                                 r'(?P<version>\S+)\s+' \
                                 r'(?P<crew>\S+)\s+' \
                                 r'(?P<date>\S+)\s+' \
                                 r'(?P<time>\S+)$', vals)
                    if m:
                        data['flight'].update({k: m.group(k) for k in m.groupdict()})
                        break
                # Optional TC line follows
                if idx+2 < len(lines):
                    tc_line = lines[idx+2].strip()
                    m_tc = re.match(r'^TC\s+(.+)$', tc_line)
                    if m_tc:
                        data['flight']['tc'] = m_tc.group(1).strip()
                break

        # Weights and distributions
        for ln in lines:
            m = re.match(r'^LOAD IN COMPARTMENTS\s+(\d+)\s+(\S+)$', ln)
            if m:
                data['weights']['load_compartments'] = to_int(m.group(1))
                data['weights']['load_compartments_dist'] = m.group(2)
            m = re.match(r'^PASSENGER/CABIN BAG\s+(\d+)\s+(\S+)$', ln)
            if m:
                data['weights']['passenger_cabin_bag'] = to_int(m.group(1))
                data['weights']['passenger_cabin_bag_dist'] = m.group(2)
            # EFU/RSV may be on same line or separate; search generically
            if 'EFU' in ln or 'RSV' in ln:
                m_efu = re.search(r'EFU\.?\s*(\d+)', ln)
                m_rsv = re.search(r'RSV\.?\s*(\d+)', ln)
                if m_efu:
                    data['weights']['efu'] = to_int(m_efu.group(1))
                if m_rsv:
                    data['weights']['reserve_fuel'] = to_int(m_rsv.group(1))
            # TOTAL TRAFFIC LOAD
            m = re.search(r'TOTAL\s+TRAFFIC\s+LOAD\s+(\d+)', ln)
            if m:
                data['weights']['total_traffic_load'] = to_int(m.group(1))
            m = re.match(r'^DRY OPERATING WEIGHT\s+(\d+)', ln)
            if m:
                data['weights']['dry_operating_weight'] = to_int(m.group(1))
            m = re.match(r'^ZERO FUEL WEIGHT ACTUAL\s+(\d+)\s+MAX\s+(\d+)', ln)
            if m:
                data['weights']['zfw_actual'] = to_int(m.group(1))
                data['weights']['zfw_max'] = to_int(m.group(2))
            # TAKE OFF FUEL (allow variations of spacing or hyphen)
            m = re.search(r'TAKE\s*OFF\s*FUEL\s*(\d+)', ln)
            if m:
                data['weights']['takeoff_fuel'] = to_int(m.group(1))
            m = re.match(r'^TAKE OFF WEIGHT ACTUAL\s+(\d+)\s+MAX\s+(\d+)', ln)
            if m:
                data['weights']['tow_actual'] = to_int(m.group(1))
                data['weights']['tow_max'] = to_int(m.group(2))
            m = re.match(r'^TRIP FUEL\s+(\d+)', ln)
            if m:
                data['weights']['trip_fuel'] = to_int(m.group(1))
            m = re.match(r'^LANDING WEIGHT ACTUAL\s+(\d+)\s+MAX\s+(\d+)', ln)
            if m:
                data['weights']['ldw_actual'] = to_int(m.group(1))
                data['weights']['ldw_max'] = to_int(m.group(2))
            m = re.match(r'^UNDERLOAD BEFORE LMC\s+(\d+)(.*)$', ln)
            if m:
                data['weights']['underload_before_lmc'] = to_int(m.group(1))
                # attempt to get LMC TOTAL if present in tail
                tail = m.group(2)
                m_lmc = re.search(r'LMC TOTAL\s*([+\-]?)\s*(\d+)', tail)
                if m_lmc:
                    sign = -1 if m_lmc.group(1) == '-' else 1
                    data['weights']['lmc_total'] = sign * to_int(m_lmc.group(2))

        # Times and CI
        for ln in lines:
            m = re.search(r'SI\s+BLOCK\s+TIME\s+(\d{2}:\d{2}).*?RESERVE\s+(\d{2}:\d{2}).*?TIME\s+TO\s+EMPTY\s+(\d{2}:\d{2}).*?CI\s+(\d+)', ln)
            if m:
                data['times']['block_time'] = m.group(1)
                data['times']['reserve'] = m.group(2)
                data['times']['time_to_empty'] = m.group(3)
                data['times']['ci'] = to_int(m.group(4))
                break

        # End line with brackets
        for ln in lines:
            if 'END LOADSHEET' in ln:
                # subsequent line might contain brackets; search entire text
                m_all = re.search(r'\[\s*([^\]]+?)\s*\]\s*\[\s*([^\]]+?)\s*\]\s*\[\s*([^\]]+?)\s*\]', text)
                if m_all:
                    data['end']['aircraft'] = m_all.group(1).strip()
                    data['end']['route'] = m_all.group(2).strip()
                    data['end']['date'] = m_all.group(3).strip()
                break

        return data




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
                self.get_route(icaos[0], icaos[1], '330', '330', self.cycle)
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
