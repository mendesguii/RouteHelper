import sys
import requests
from bs4 import BeautifulSoup as bs 
import html5lib

sids = []
stars = []
apps = []
rwys = []

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
            objectDict[procedure+'-'+cur_pos_start] += ' ' + cur_pos_end.replace('  ','')

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
    for i in dict:
        if value in dict[i] or value in i:
            print('Chart: '+ i +' || Route: '+dict[i])

def getMetar(icao):
    r = requests.get('https://metar-taf.com/pt/'+icao)
    soup = bs(r.text,'html5lib')
    soup = soup.code.text
    print('Metar: '+ soup)

def getRoute(icao,icaoDest,minalt,maxalt,cycle):
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
    route = soup.findAll('tt')[1].text
    print('Route: '+route)

def getFuel(icao,icaoDest,plane):
    headers = {
   'okstart': 1,
   'EQPT': plane.uppper(),
   'ORIG': icao.upper(),
   'DEST': icaoDest.upper,
   'submit': 'LOADSHEET',
   'RULES': 'FARDOM',
   'UNITS': 'METRIC',
            }
    r = requests.post('http://fuelplanner.com/index.php',data = headers)
    soup = bs(r.text,'html5lib')
    loadsheet = soup.pre.text.replace('fuelplanner.com | home','').replace('Copyright 2008-2019 by Garen Evans','')
    print(loadsheet)


def main():
    icao = sys.argv[1].upper()
    try:
        fix = sys.argv[3].upper()
    except:
        fix = None
    if sys.argv[2].upper() == 'SID':
        getFileData('CIFP/'+icao+'.dat')
        if fix is None:
            print(structureData(sids))
        else:
            searchInDict(structureData(sids),fix)
    
    elif sys.argv[2].upper() == 'STAR':
        getFileData('CIFP/'+icao+'.dat')
        if fix is None:
            print(structureData(stars))
        else:
            searchInDict(structureData(stars),fix)

    elif sys.argv[2].upper() == 'METAR':
        getMetar(icao)

    elif sys.argv[2].upper() == 'ROUTE':
        icaos = icao.split('/')
        getRoute(icaos[0],icaos[1],'330','330',2205)
    
    elif sys.argv[2].upper() == 'FUEL':
        getFuel()


    else:
        print('Command not found!')

if __name__ == "__main__":
    main()
