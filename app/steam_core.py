#!/usr/bin/env python3
"""Steam Auto Sync: Windows standalone games -> non-Steam shortcuts and SteamGridDB artwork.
Only standard library. Original game directories are never modified.
"""
import binascii
import difflib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request

ROOT = Path(r'C:\Gaming\Games')
STEAM = Path(r'C:\Program Files (x86)\Steam')
APP = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'SteamAutoSync'
CONF = APP / 'settings.json'
LOG = APP / 'last_report.txt'

KNOWN = {
 '7 days to die': ('7 Days to Die', r'7.Days.To.Die-SteamRIP.com\7 Days To Die\7DaysToDie.exe'),
 'buckshot roulette': ('Buckshot Roulette', r'Buckshot Roulette\Buckshot.Roulette.v2.2.0a\Buckshot.Roulette.v2.2.0a\Buckshot Roulette.exe'),
 'control': ('Control', r'Control-UE-SteamRIP.com\Control\Control.exe'),
 'keep talking and nobody explodes': ('Keep Talking and Nobody Explodes', r'Keep Talking and Nobody Explodes\KTANE.v1.9.24\ktane.exe'),
 'outer wilds': ('Outer Wilds', r'Outer Wilds\Outer Wilds\OuterWilds.exe'),
 'sekiro': ('Sekiro: Shadows Die Twice', r'Sekiro-Shadows-Die-Twice-SteamRIP.com\Sekiro\sekiro.exe'),
 'silent hill 2': ('Silent Hill 2', r'Silent-Hill-2-SteamRIP.com\SILENT HILL 2\SHProto.exe'),
 'jackbox 7': ('The Jackbox Party Pack 7', r'The Jackbox Party Pack 7\The Jackbox Party Pack 7\The Jackbox Party Pack 7.exe'),
}
IGNORE_PARTS = ('_commonredist', '_redist', 'redist', 'easyanticheat', 'artwork_minisoundtrack', 'engine\\binaries', 'crash', 'unins', 'setup', 'install', 'launcher', 'benchmark', 'unitycrashhandler', 'vcredist', 'dxwebsetup', 'dotnet', 'oalinst', 'eac', 'report', 'updater', 'prereq')

def log(s=''):
 print(s, flush=True)
 with LOG.open('a', encoding='utf-8') as f: f.write(s+'\n')

def normalized(s):
 s = re.sub(r'(?i)steamrip\.com|elamigos|repack|gog-games|fitgirl|dodi|\.v\d+(?:\.\d+)*|[-_]multi\d+|[-_]win64', ' ', s)
 s = re.sub(r'[^a-z0-9]+', ' ', s.lower())
 return ' '.join(s.split())

def clean_name(folder):
 s = re.sub(r'(?i)[-_ ]*steamrip\.com', '', folder)
 s = re.sub(r'(?i)\.v\d+(?:\.\d+)*[a-z]?', '', s)
 return re.sub(r'[._-]+', ' ', s).strip() or folder

def get_games():
 out = []
 if not ROOT.exists(): raise RuntimeError('Game directory does not exist: '+str(ROOT))
 for folder in sorted(ROOT.iterdir(), key=lambda x:x.name.lower()):
  if not folder.is_dir() or folder.is_symlink(): continue
  matched = None
  for display, rel in KNOWN.values():
   p = ROOT / rel
   if p.is_file() and (p == folder or folder in p.parents):
    matched = (display, p, 'verified'); break
  if not matched:
   choices = []
   for base, dirs, files in os.walk(folder):
    depth = len(Path(base).relative_to(folder).parts)
    dirs[:] = [d for d in dirs if depth < 5 and not any(x in d.lower() for x in ('_redist','_commonredist','easyanticheat','prereq','crashreport'))]
    for file in files:
     if not file.lower().endswith('.exe'): continue
     path = Path(base) / file
     low = str(path.relative_to(folder)).lower().replace('/', '\\')
     if any(x in low for x in IGNORE_PARTS): continue
     stem = normalized(path.stem)
     target = normalized(clean_name(folder.name))
     score = difflib.SequenceMatcher(None, stem, target).ratio()
     if stem and (stem in target or target in stem): score += .18
     try: size = path.stat().st_size
     except OSError: continue
     if size < 60_000: continue
     score += min(size/(40*1024*1024), 1)*.10
     score -= depth*.015
     choices.append((score, path))
   choices.sort(key=lambda a:a[0], reverse=True)
   if len(choices)==1 or (choices and choices[0][0] >= .68 and (len(choices)==1 or choices[0][0]-choices[1][0] > .14)):
    matched = (clean_name(folder.name), choices[0][1], 'detected')
   elif choices:
    log('[REVIEW] '+folder.name+' : multiple possible EXEs. No import; add one to overrides.json.')
    for _,p in choices[:5]: log('         '+str(p))
   else:
    log('[SKIP]   '+folder.name+' : no likely game executable')
  if matched: out.append(matched)
 return out

# Conservative binary Valve KeyValues parser. Unknown formats halt before any modification.
def read_cstr(data, off):
 end=data.find(b'\0',off)
 if end<0: raise ValueError('Unterminated VDF string')
 return data[off:end].decode('utf-8', 'replace'), end+1

def parse_obj(data, off):
 obj={}
 while off<len(data):
  typ=data[off];off+=1
  if typ==8:return obj,off
  key,off=read_cstr(data,off)
  if typ==0: value,off=parse_obj(data,off)
  elif typ==1: value,off=read_cstr(data,off)
  elif typ==2:
   if off+4>len(data):raise ValueError('Truncated int')
   value=struct.unpack_from('<i',data,off)[0];off+=4
  elif typ==7:
   if off+8>len(data):raise ValueError('Truncated uint64')
   value=struct.unpack_from('<Q',data,off)[0];off+=8
  else:raise ValueError('Unsupported VDF type '+str(typ)+'; no changes written')
  obj[key]=value
 raise ValueError('Missing VDF object terminator')

def load_vdf(path):
 if not path.exists():return {'shortcuts':{}}
 data=path.read_bytes()
 if not data:return {'shortcuts':{}}
 result,off=parse_obj(data,0)
 if off!=len(data):raise ValueError('Extra data in VDF; refusing write')
 if not isinstance(result.get('shortcuts'),dict):raise ValueError('shortcuts root missing')
 return result

def pack_obj(obj):
 out=bytearray()
 for key,value in obj.items():
  if isinstance(value,dict): typ=0;payload=pack_obj(value)
  elif isinstance(value,str):typ=1;payload=value.encode('utf-8')+b'\0'
  elif isinstance(value,int):
   if -2147483648<=value<=2147483647:typ=2;payload=struct.pack('<i',value)
   elif 0<=value<2**64:typ=7;payload=struct.pack('<Q',value)
   else:raise ValueError('Invalid integer size')
  else:raise ValueError('Invalid VDF value type')
  out.append(typ);out.extend(str(key).encode('utf-8')+b'\0');out.extend(payload)
 out.append(8)
 return bytes(out)

def app_ids(exe, name):
 # exe is quoted string exactly as written into Steam's file
 appid=(binascii.crc32((exe+name).encode('utf-8')) | 0x80000000) & 0xffffffff
 return (appid - 2**32 if appid >= 2**31 else appid), (appid << 32) | 0x02000000

def steam_running():
 try:
  r=subprocess.run(['tasklist','/FI','IMAGENAME eq steam.exe','/FO','CSV','/NH'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,timeout=10)
  return 'steam.exe' in r.stdout.lower()
 except Exception:return True

def pick_user(config):
 users=STEAM/'userdata'
 found=sorted([p for p in users.iterdir() if p.is_dir() and p.name.isdigit() and p.name!='0'],key=lambda x:x.name) if users.exists() else []
 if not found:raise RuntimeError('Steam user profile not found in '+str(users))
 saved=str(config.get('steam_user',''))
 if saved and any(p.name==saved for p in found):return users/saved
 if len(found)==1: config['steam_user']=found[0].name;return found[0]
 print('\nSelect Steam account (once):')
 for i,p in enumerate(found,1):print(f' {i}. {p.name}  (shortcuts: {"yes" if (p/"config"/"shortcuts.vdf").exists() else "no"})')
 answer=input('Number [Enter cancels]: ').strip()
 if not answer.isdigit() or not 1<=int(answer)<=len(found):raise RuntimeError('No Steam account selected')
 chosen=found[int(answer)-1];config['steam_user']=chosen.name;return chosen

def get_json(url,key):
 req=urllib.request.Request(url,headers={'Authorization':'Bearer '+key,'User-Agent':'SteamAutoSync/1.0'})
 with urllib.request.urlopen(req,timeout=12) as res:return json.load(res)

def get_art(name,key,grid,launchid,appid):
 search=get_json('https://www.steamgriddb.com/api/v2/search/autocomplete/'+urllib.parse.quote(name,safe=''),key)
 results=search.get('data',[])
 if not results:log('  No SteamGridDB match for '+name);return 0
 exact=[g for g in results if normalized(g.get('name',''))==normalized(name)]
 if exact:g=exact[0]
 else:
  g=max(results,key=lambda a:difflib.SequenceMatcher(None,normalized(a.get('name','')),normalized(name)).ratio())
  score=difflib.SequenceMatcher(None,normalized(g.get('name','')),normalized(name)).ratio()
  if score<.86:
   log('  Artwork match uncertain: '+name+' -> '+g.get('name','')+'; skipped');return 0
 gid=g['id'];count=0
 targets=[('grids','?dimensions=600x900',str(launchid)+'p'),('grids','?dimensions=920x430',str(launchid)),('heroes','',str(launchid)+'_hero'),('logos','',str(launchid)+'_logo'),('icons','',str(launchid)+'_icon')]
 for typ,params,basename in targets:
  try:
   resp=get_json(f'https://www.steamgriddb.com/api/v2/{typ}/game/{gid}{params}',key)
   options=[a for a in resp.get('data',[]) if a.get('url') and not str(a.get('url','')).lower().endswith(('.webm','.webp','.gif','.mp4'))]
   if not options:continue
   url=options[0]['url'];ext=Path(urllib.parse.urlparse(url).path).suffix.lower()
   if ext not in ('.png','.jpg','.jpeg'):continue
   filename=grid/(basename+ext)
   if filename.exists():continue
   req=urllib.request.Request(url,headers={'User-Agent':'SteamAutoSync/1.0'})
   with urllib.request.urlopen(req,timeout=18) as res: data=res.read(7_000_001)
   if not data or len(data)>7_000_000:continue
   grid.mkdir(parents=True,exist_ok=True);filename.write_bytes(data);count+=1
  except Exception as e:log('  Artwork '+typ+' skipped: '+str(e)[:120])
 return count

def run():
 APP.mkdir(parents=True,exist_ok=True)
 LOG.write_text('STEAM AUTO SYNC REPORT\n\n',encoding='utf-8')
 config=json.loads(CONF.read_text(encoding='utf-8')) if CONF.exists() else {}
 if not STEAM.exists():raise RuntimeError('Steam not found at '+str(STEAM))
 if steam_running():
  log('Steam is open. Exit Steam completely (Steam tray icon -> Exit), then run this again.')
  return False
 profile=pick_user(config)
 vpath=profile/'config'/'shortcuts.vdf'
 grid=profile/'config'/'grid'
 current=load_vdf(vpath)
 shortcuts=current['shortcuts']
 # Preserve shortcut IDs and all fields for all pre-existing entries.
 existing_paths={}
 for obj in shortcuts.values():
  if isinstance(obj,dict):
   val=str(obj.get('exe','')).strip('"').lower()
   if val:existing_paths[val]=obj
 games=get_games()
 log(f'\nFound {len(games)} games ready for Steam.')
 new=0;art_jobs=[]
 for name,exe,source in games:
  exestr='"'+str(exe)+'"'
  obj=existing_paths.get(str(exe).lower())
  if obj:
   _,launchid=app_ids(str(obj.get('exe',exestr)),str(obj.get('AppName',name)))
   log('[EXISTS] '+name)
  else:
   signed,launchid=app_ids(exestr,name)
   obj={'appid':signed,'AppName':name,'exe':exestr,'StartDir':'"'+str(exe.parent)+'"','icon':str(exe),'ShortcutPath':'','LaunchOptions':'','IsHidden':0,'AllowDesktopConfig':1,'AllowOverlay':1,'OpenVR':0,'Devkit':0,'DevkitGameID':'','DevkitOverrideAppID':0,'LastPlayTime':0,'FlatpakAppID':'','tags':{}}
   key=str(max([int(k) for k in shortcuts.keys() if k.isdigit()]+[-1])+1)
   shortcuts[key]=obj;existing_paths[str(exe).lower()]=obj;new+=1
   log('[ADD]    '+name+' -> '+str(exe))
  art_jobs.append((name,launchid))
 if new:
  vpath.parent.mkdir(parents=True,exist_ok=True)
  if vpath.exists():
   backup=APP/('shortcuts-'+time.strftime('%Y%m%d-%H%M%S')+'.vdf.bak')
   shutil.copy2(vpath,backup);log('BACKUP: '+str(backup))
  payload=pack_obj(current)
  # Decode our own output before writing; then atomic replace.
  check,offset=parse_obj(payload,0)
  if offset != len(payload) or check!=current:raise RuntimeError('VDF verification failed; nothing written')
  with tempfile.NamedTemporaryFile(dir=vpath.parent,delete=False) as tmp:
   tmp.write(payload);tmp.flush();os.fsync(tmp.fileno());tmpname=tmp.name
  os.replace(tmpname,vpath)
  log('STEAM SHORTCUTS UPDATED: '+str(new)+' new games')
 else:log('No new Steam shortcuts needed.')
 key=config.get('steamgrid_key','').strip()
 if not key:
  log('\nArtwork is optional. Paste your SteamGridDB API key once, or Enter to skip.')
  log('Get it from: https://www.steamgriddb.com/profile/preferences/api')
  key=input('SteamGridDB API key (Enter to skip): ').strip()
  if key:config['steamgrid_key']=key
 config['steam_user']=profile.name
 CONF.write_text(json.dumps(config,indent=2),encoding='utf-8')
 count=0
 if key:
  for name,launchid in art_jobs:
   try:count+=get_art(name,key,grid,launchid,0)
   except Exception as e:log('[ART FAILED] '+name+': '+str(e)[:140])
  log(f'Artwork files downloaded: {count}')
 else:log('Artwork skipped. Re-run later to enable it.')
 log('\nFinished. Originals remain in C:\\Gaming\\Games.')
 log('Report: '+str(LOG))
 return True

if __name__=='__main__':
 success=False
 try:success=run()
 except Exception as exc:
  log('ERROR: '+str(exc));success=False
 if success:
  try:
   answer=input('\nOpen Steam now? [Y/n]: ').strip().lower()
   if answer in ('','y','yes'):subprocess.Popen([str(STEAM/'steam.exe')],cwd=str(STEAM))
  except EOFError:pass
 else:input('\nPress Enter to close...')
