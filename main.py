import sys
import requests
import html5lib
import os
import re
from bs4 import BeautifulSoup
from typing import Optional, List
from datetime import datetime
from dotenv import load_dotenv, set_key


class RouteHelper:
    """Class to encapsulate route planning logic and state."""
    def __init__(self, env_path='.env'):
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

    # --- VATSIM / ICAO FPL helpers ---
    def format_icao_fpl(self,
                        callsign: str,
                        dep_icao: str,
                        dest_icao: str,
                        dep_time_utc: str = "0000",
                        speed: str = "N0430",
                        level: str = "F330",
                        route: Optional[str] = None,
                        eet_hhmm: Optional[str] = None,
                        alt1: Optional[str] = None,
                        alt2: Optional[str] = None,
                        actype: str = "B738",
                        wakecat: str = "M",
                        equipment: str = "SDFGIRY",
                        surveillance: str = "S",
                        other: Optional[List[str]] = None) -> str:
        """Build an ICAO flight plan message string suitable for VATSIM.

        Produces a standard ATS FPL message in the form:
        (FPL-<CS>-IS
        -<TYPE>/<WAKE>-<EQUIP>
        -<DEP><TIME>
        -<SPEED><LEVEL> <ROUTE>
        -<DEST><EET>
        -<ALT1> <ALT2>
        -<OTHER>)

        Only a subset is filled using available data; placeholders are used where
        data is unavailable so users can edit before submitting to VATSIM.
        """
        # Defaults and sanitization
        cs = (callsign or "XXXXXX").upper()
        dep = (dep_icao or "XXXX").upper()
        dest = (dest_icao or "XXXX").upper()
        time_utc = (dep_time_utc or "0000").rjust(4, '0')[:4]
        lvl = level if level else "F330"
        spd = speed if speed else "N0430"
        rte = (route or (" ".join(self.route) if isinstance(self.route, list) else (self.route or ""))).strip()
        # EET should be HHMM
        eet = (eet_hhmm or "").replace(":", "")
        if eet and len(eet) == 3:
            eet = eet.zfill(4)
        if not eet:
            # Try to derive from loadsheet if available
            try:
                eet_guess = self.get_info_after('SI BLOCK TIME', self.plan).replace(':', '') if self.plan else ''
            except Exception:
                eet_guess = ''
            eet = (eet_guess or "0000")
        # Alternates line (can be empty)
        alt_line = ""
        if alt1:
            alt_line += alt1.upper()
        if alt2:
            alt_line += (" " if alt_line else "") + alt2.upper()
        # Other information
        dof = 'DOF/' + datetime.today().strftime('%y%m%d')
        other_items = [dof]
        # Keep equipment/surveillance simple; advanced PBN not handled here.
        other_line = " ".join([*other_items, *(other or [])]).strip()
        # Assemble message
        lines = [
            f"(FPL-{cs}-IS",
            f"-{actype.upper()}/{wakecat.upper()}-{equipment}",
            f"-{dep}{time_utc}",
            f"-{spd}{lvl} {rte}".rstrip(),
            f"-{dest}{eet}",
            f"-{alt_line}" if alt_line else "-",
            f"-{other_line}" if other_line else "-",
            ")"
        ]
        return "\n".join(lines)


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

    def get_file_data(self, file_path):
        """Parse .dat file and populate procedure lists."""
        self.reset_procedure_lists()
        with open(file_path, 'r', encoding='utf-8') as f:
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
        """Search for a value in the procedure dictionary."""
        # Always overwrite self.plan for clean output (no leading blank lines)
        lines = [f"- Fix Search: {value}"]
        for k, v in obj_dict.items():
            if value in v or value in k:
                lines.append(f"* Chart: {k} || Route: {v}")
        result = '\n'.join(lines).strip()  # Remove leading/trailing blank lines
        if self.plan is not None:
            self.plan = result
        else:
            print(result)

    def get_metar(self, icao):
        """Fetch METAR for an airport."""
        r = requests.get(f'https://aviationweather.gov/api/data/metar?ids={icao}')
        soup = BeautifulSoup(r.text, 'html5lib')
        metar = soup.text
        if self.plan is not None:
            self.plan += f'\n- Metar {icao}: {metar}'
        else:
            print(f'Metar: {metar}')

    def get_route(self, icao, icao_dest, minalt, maxalt, cycle):
        """Fetch route from rfinder."""
        headers = {
            'id1': icao.upper(),
            'ic1': '',
            'id2': icao_dest.upper(),
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
            self.route = []
            return
        genroute = genroute_tags[1].text
        self.route = genroute.split(' ')[2:-2]
        if self.plan is not None:
            self.plan += f'- Route: {genroute}\n'
        else:
            print(f'Route: {genroute}')

    def get_fuel(self, icao, icao_dest, plane):
        """Fetch fuel/loadsheet info."""
        headers = {
            'okstart': 1,
            'EQPT': plane.upper(),
            'ORIG': icao.upper(),
            'DEST': icao_dest.upper(),
            'submit': 'LOADSHEET',
            'RULES': 'FARDOM',
            'UNITS': 'METRIC',
        }
        r = requests.post('http://fuelplanner.com/index.php', data=headers)
        soup = BeautifulSoup(r.text, 'html5lib')
        loadsheet = soup.pre.text.replace('fuelplanner.com | home', '').replace('Copyright 2008-2019 by Garen Evans', '')
        self.plan = loadsheet
        # Parse and store structured loadsheet data for reuse
        try:
            self.parsed_loadsheet = self.parse_loadsheet(loadsheet)
        except Exception:
            self.parsed_loadsheet = None

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



    def gen_flight_plan(self, icao, icao_dest, plane, output_dir='flights'):
        # Use parsed loadsheet for SI BLOCK TIME and TIME TO EMPTY
        eet = ''
        endu = ''
        if hasattr(self, 'parsed_loadsheet') and self.parsed_loadsheet:
            eet = (self.parsed_loadsheet.get('times', {}) or {}).get('block_time', '')
            endu = (self.parsed_loadsheet.get('times', {}) or {}).get('time_to_empty', '')
            if eet:
                eet = eet.replace(':', '')
            if endu:
                endu = endu.replace(':', '')
        dof = 'DOF/' + datetime.today().strftime('%y%m%d')
        base = f"""[FLIGHTPLAN]
ID=XXXXXX
RULES=I
FLIGHTTYPE=S
NUMBER=1
ACTYPE={plane}
WAKECAT=M
EQUIPMENT=SDFGIRY
TRANSPONDER=S
DEPICAO={icao}
DEPTIME=
SPEEDTYPE=N
SPEED=
LEVELTYPE=F
LEVEL=330
ROUTE={' '.join(self.route) if self.route else ''}
DESTICAO={icao_dest}
EET={eet}
ALTICAO=
ALTICAO2=
OTHER={dof}
ENDURANCE={endu}
POB=
"""
        os.makedirs(output_dir, exist_ok=True)
        out_path = os.path.join(output_dir, f'{icao}{icao_dest}.fpl')
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(base)

    def run(self, argv):
        try:
            if len(argv) < 3:
                raise ValueError('Not enough arguments')
            icao = argv[1].upper()
            option = argv[2].upper()
            fix = argv[3].upper() if len(argv) > 3 else None

            if option == 'SID':
                self.get_file_data(f'{self.data_path}/{icao}.dat')
                if fix is None:
                    print(self.structure_data(self.sids))
                else:
                    self.search_in_dict(self.structure_data(self.sids), fix)
            elif option == 'STAR':
                self.get_file_data(f'{self.data_path}/{icao}.dat')
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
                self.gen_flight_plan(icaos[0], icaos[1], plane)
                self.get_metar(icaos[0])
                self.get_metar(icaos[1])
                self.get_file_data(f'{self.data_path}/{icaos[0]}.dat')
                if self.route:
                    self.search_in_dict(self.structure_data(self.sids), self.route[0])
                self.get_file_data(f'{self.data_path}/{icaos[1]}.dat')
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
        and generate an IVAO FlightPlan.
        """
            )
            print(f"Error: {e}")


def main():
    helper = RouteHelper()
    helper.run(sys.argv)


if __name__ == "__main__":
    main()
