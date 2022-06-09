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
        before = []
        bef_pos_start = []
        current = rawdata[i].split(',')
        type = current[0].split(':')[0]
        num = current[0].split(':')[1]
        procedure = current[2]
        cur_pos_start = current[3]
        cur_pos_end = current[4]

        if i > 0:
            before = rawdata[i-1].split(',')
            bef_pos_start = before[3] 
            bef_pos_end = before[4]

        if type == 'SID':
            if 'RW' in cur_pos_start:
                if num == "010":
                    objectDict[procedure] = cur_pos_start+' '+cur_pos_end
                else:
                    objectDict[procedure] += ' ' + cur_pos_end 

            else:
                if num == "010":
                    objectDict[procedure] = objectDict[procedure].replace('  ','')
                    objectDict[procedure+'-'+cur_pos_start] = objectDict[procedure]
                else:
                    objectDict[procedure+'-'+cur_pos_start] += ' ' + cur_pos_end  
        elif type == 'STAR':
            print(current)

    return objectDict

def searchInDict(dict,value):
    for i in dict:
        if value in dict[i]:
            print('Chart: '+ i +' || Route: '+dict[i])

def getMetar(icao):
    r = requests.get('https://metar-taf.com/pt/'+icao)
    soup = bs(r.text,'html5lib')
    soup = soup.code.text
    print('Metar: '+ soup)


def main():
    icao = sys.argv[2].upper()
    getFileData('CIFP/'+icao+'.dat')
    try:
        fix = sys.argv[3].upper()
    except:
        print()
    if sys.argv[1].upper() == 'SID':
        searchInDict(structureData(sids),fix)
    
    elif sys.argv[1].upper() == 'STAR':
        for item in structureData(stars):
            print(item)
    elif sys.argv[1].upper() == 'METAR':
        getMetar(icao)

if __name__ == "__main__":
    main()
