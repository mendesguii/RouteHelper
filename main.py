import sys
import requests
import html5lib
import yaml
from bs4 import BeautifulSoup as bs 
from datetime import datetime


plan = None
route = None
sids = []
stars = []
apps = []
rwys = []
path = None

def getConfig():
    global path
    configFile = open('config.yaml','r')
    config = yaml.load(configFile,Loader=yaml.FullLoader)
    path = config['path']

def getFileData(path):
    global sids
    global starts
    global apps
    global rwys

    f = open(path,'r',encoding='utf-8')
    lines = f.readlines()
    f.close()
    for line in lines:
        if 'SID:' in line:
            sids.append(line)
        elif 'STAR' in line:
            stars.append(line)
        elif 'APPCH' in line:
            apps.append(line)
        elif 'RWY' in line:
            rwys.append(line)

def structureData(rawdata):
    objectDict = {}
    for i in range(len(rawdata)):
        current = rawdata[i].split(',')
        type = current[0].split(':')[0] 
        num = current[0].split(':')[1]
        procedure = current[2]
        cur_pos_start = current[3]
        cur_pos_end = current[4]

        if num == "010":
            objectDict[procedure+'-'+cur_pos_start] = cur_pos_end.replace('  ','') 
        else:
            try:
                objectDict[procedure+'-'+cur_pos_start] += ' ' + cur_pos_end.replace('  ','')
            except:
                objectDict[procedure+'-'+cur_pos_start] = cur_pos_end.replace('  ','')

    if len(rawdata) >= 1:
       cleanDictionary(objectDict,type)
    return objectDict


def cleanDictionary(dict,type):
    listToDelete = []
    for i in dict:
        splitName = i.split('-')
        if len(splitName) > 1:
            if 'RW' in splitName[1]:
                for x in dict:
                    if splitName[0] in x and 'RW' not in x:
                        listToDelete.append(i)
                        if type == "SID":
                            dict[x] = '['+splitName[1] +'] '+dict[i].replace('  ','')  +' | '+ dict[x]
                        elif type == "STAR":
                            dict[x] = dict[x] +' | '+ dict[i] + ' ['+splitName[1] +']'

    #Cleaning final Dictionary
    listToDelete = list(dict.fromkeys(listToDelete)) #removing duplicates
    for item in listToDelete:
        del dict[item]


def searchInDict(dict,value):
    global plan
    if plan is not None:
        plan += '\n\n' + '- Fix Search: '+value
    for i in dict:
        if value in dict[i] or value in i:
            if plan is not None:
                plan += '\n' + '* Chart: '+ i +' || Route: '+dict[i] 
            else:
                print(' * Chart: '+ i +' || Route: '+dict[i])


def getMetar(icao):
    global plan
    r = requests.get('https://metar-taf.com/pt/'+icao)
    soup = bs(r.text,'html5lib')
    metar = soup.code.text
    if plan is not None:
         plan += '\n' + '- Metar '+ icao + ': '+ metar
    else:
        print('Metar: '+ metar)

def getRoute(icao,icaoDest,minalt,maxalt,cycle):
    global route
    global plan

    headers = {
   'id1': icao.upper(),
   'ic1': '',
   'id2': icaoDest.upper(),
   'ic2': '',
   'minalt': 'FL'+minalt,
   'maxalt': 'FL'+maxalt,
   'lvl': 'B',
   'dbid': cycle,
   'usesid': 'Y',
   'usestar': 'Y',
   'easet': 'Y',
   'rnav': 'Y',
   'nats': 'R'} 
    r = requests.post('http://rfinder.asalink.net/free/autoroute_rtx.php',data = headers)
    soup = bs(r.text,'html5lib')
    genroute = soup.findAll('tt')[1].text
    route = genroute.split(' ')[2:-2]
    plan += '- Route: '+genroute + '\n'


def getFuel(icao,icaoDest,plane):
    global plan
    headers = {
   'okstart': 1,
   'EQPT': plane.upper(),
   'ORIG': icao.upper(),
   'DEST': icaoDest.upper(),
   'submit': 'LOADSHEET',
   'RULES': 'FARDOM',
   'UNITS': 'METRIC',
            }
    r = requests.post('http://fuelplanner.com/index.php',data = headers)
    soup = bs(r.text,'html5lib')
    loadsheet = soup.pre.text.replace('fuelplanner.com | home','').replace('Copyright 2008-2019 by Garen Evans','')
    plan = loadsheet


def getInfoAfter(word,string):
    start = string.find(word)
    end = start+len(word)
    return string[end+1:end+6]


def genFlightPlan(icao,icaodest,plane):
    f = open(icao+icaodest+'.fpl', "w")
    eet = getInfoAfter('SI BLOCK TIME',plan).replace(':','')
    endu = getInfoAfter('TIME TO EMPTY',plan).replace(':','')
    dof = 'DOF/'+datetime.today().strftime('%y%m%d')
    base = """[FLIGHTPLAN]
ID=XXXXXX
RULES=I
FLIGHTTYPE=S
NUMBER=1
ACTYPE={0}
WAKECAT=M
EQUIPMENT=SDFGIRY
TRANSPONDER=S
DEPICAO={1}
DEPTIME=
SPEEDTYPE=N
SPEED=
LEVELTYPE=F
LEVEL=330
ROUTE={2}
DESTICAO={3}
EET={4}
ALTICAO=
ALTICAO2=
OTHER={5}
ENDURANCE={6}
POB=
""".format(plane,icao,' '.join(route),icaodest,eet,dof,endu)
    f.write(base)
    f.close()


def main():
    try:
        getConfig()
        icao = sys.argv[1].upper()
        option = sys.argv[2].upper()
        try:
            fix = sys.argv[3].upper()
        except:
            fix = None

       #SID
        if option == 'SID':
            getFileData(path+'/'+icao+'.dat')
            if fix is None:
                print(structureData(sids))
            else:
                searchInDict(structureData(sids),fix)
       #STAR 
        elif option == 'STAR':
            getFileData(path+'/'+icao+'.dat')
            if fix is None:
                print(structureData(stars))
            else:
                searchInDict(structureData(stars),fix)
        #METAR
        elif option == 'METAR':
            getMetar(icao)

        #ROUTE
        elif option == 'ROUTE':
            icaos = icao.split('/')
            getFuel(icaos[0],icaos[1],sys.argv[3])
            getRoute(icaos[0],icaos[1],'330','330',2205)
            genFlightPlan(icaos[0],icaos[1],sys.argv[3])

            #Metar Both Airports
            getMetar(icaos[0])
            getMetar(icaos[1])
            
            #Search first ICAO SID
            getFileData(path+'/'+icaos[0]+'.dat')
            searchInDict(structureData(sids),route[0])
            
            #Search Dest ICAO STAR
            getFileData(path+'/'+icaos[1]+'.dat')
            searchInDict(structureData(stars),route[len(route) - 1])
            
            print(plan)
    except:
        print("""
                                                ~ UNKNOWN COMMAND ~
                                                
        ======================================= AVALIABLE COMMANDS =====================================
        
        - ICAO (SID/STAR) : Lists all avaliable procedures and its routes
        - ICAO (SID/STAR) FIX: Search for a fix in all procedures (can also search by name of procedure)
        - ICAO METAR: Returns METAR of the airport
        - ICAO/ICAO ROUTE PLANE: List all info for a route (Route,Fuel,SIDS and STARS)
        and generate a IVAO FlightPlan.""")

if __name__ == "__main__":
    main()
