import sys
import requests
import html5lib
import os
from bs4 import BeautifulSoup
from datetime import datetime
from dotenv import load_dotenv, set_key



class RouteHelper:
    """Class to encapsulate route planning logic and state."""
    def __init__(self, env_path='.env'):
        self.ensure_env(env_path)
        load_dotenv(env_path)
        self.data_path = os.getenv('DATA_PATH', '.')
        self.sids = []
        self.stars = []
        self.apps = []
        self.rwys = []
        self.plan = None
        self.route = None


    @staticmethod
    def ensure_env(env_path):
        if not os.path.exists(env_path):
            # Create .env with a default DATA_PATH
            with open(env_path, 'w', encoding='utf-8') as f:
                f.write('DATA_PATH=.' + '\n')
    
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
        if self.plan is not None:
            self.plan += f'\n\n- Fix Search: {value}'
        for k, v in obj_dict.items():
            if value in v or value in k:
                if self.plan is not None:
                    self.plan += f'\n* Chart: {k} || Route: {v}'
                else:
                    print(f' * Chart: {k} || Route: {v}')

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

    @staticmethod
    def get_info_after(word, string):
        start = string.find(word)
        end = start + len(word)
        return string[end + 1:end + 6]

    def gen_flight_plan(self, icao, icao_dest, plane):
        eet = self.get_info_after('SI BLOCK TIME', self.plan).replace(':', '')
        endu = self.get_info_after('TIME TO EMPTY', self.plan).replace(':', '')
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
        with open(f'{icao}{icao_dest}.fpl', 'w', encoding='utf-8') as f:
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
                self.get_route(icaos[0], icaos[1], '330', '330', 2501)
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
