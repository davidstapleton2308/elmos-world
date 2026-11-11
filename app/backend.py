"""SteamMatch Arcade — local Windows game library. Standard library only.
Steam mutations: explicit opt-in, Steam closed, atomic backups, never touch game files.
"""
import os, re, json, time, secrets, random, shutil, tempfile, hashlib, difflib, threading, subprocess, urllib.request, urllib.parse, pathlib, sys
from pathlib import Path
from game_discovery import detect as detect_pc_game, blocked_exe, JUNK_ROOT, clean_game_title
import steam_core as vdf

_active_game_lock=threading.RLock()
_active_game=None
_active_game_type="pc"
_active_game_id=None
_active_game_name=None

# The existing native application window is the ONLY launch shield.
# Never create an extra always-on-top overlay window (v1.5 regression).
_shield_lock=threading.RLock()
_shield_hwnd=0
_shield_on=False


def _launcher_window():
 if sys.platform!='win32':return 0
 try:
  import ctypes
  from ctypes import wintypes
  u=ctypes.windll.user32; k=ctypes.windll.kernel32
  u.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
  u.GetWindowThreadProcessId.restype=wintypes.DWORD
  u.IsWindowVisible.argtypes=[wintypes.HWND]
  u.IsWindowVisible.restype=wintypes.BOOL
  u.GetWindowRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
  u.GetWindowRect.restype=wintypes.BOOL
  pid=k.GetCurrentProcessId(); found=[]
  CALLBACK=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
  def visit(hwnd,_):
   owner=wintypes.DWORD()
   u.GetWindowThreadProcessId(hwnd,ctypes.byref(owner))
   if owner.value!=pid or not u.IsWindowVisible(hwnd):return True
   rect=wintypes.RECT()
   if u.GetWindowRect(hwnd,ctypes.byref(rect)):
    w=rect.right-rect.left;h=rect.bottom-rect.top
    if w>=750 and h>=500:found.append((w*h,int(hwnd)))
   return True
  u.EnumWindows.argtypes=[CALLBACK,wintypes.LPARAM]
  u.EnumWindows.restype=wintypes.BOOL
  u.EnumWindows(CALLBACK(visit),0)
  return max(found)[1] if found else 0
 except Exception:return 0


def set_launch_shield(enabled):
 """Pin the EXISTING Elmos window only while a game is starting.

 This avoids a desktop flash when the game opens on top of the launcher.
 It does not work in browser fallback mode and cannot mask exclusive fullscreen.
 """
 global _shield_hwnd,_shield_on
 if sys.platform!='win32':return {'enabled':False,'supported':False}
 import ctypes
 from ctypes import wintypes
 u=ctypes.windll.user32
 u.SetWindowPos.argtypes=[wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.UINT]
 u.SetWindowPos.restype=wintypes.BOOL
 with _shield_lock:
  if enabled:
   hwnd=_launcher_window()
   if not hwnd:return {'enabled':False,'supported':False}
   flags=0x0001|0x0002|0x0010 # NOSIZE|NOMOVE|NOACTIVATE
   ok=u.SetWindowPos(hwnd,-1,0,0,0,0,flags)
   if ok:_shield_hwnd=hwnd;_shield_on=True
   return {'enabled':bool(ok),'supported':True}
  if _shield_on and _shield_hwnd:
   u.SetWindowPos(_shield_hwnd,-2,0,0,0,0,0x0001|0x0002|0x0010)
  _shield_hwnd=0;_shield_on=False
  return {'enabled':False,'supported':True}

def active_game_process():
 with _active_game_lock:
  global _active_game
  if _active_game is not None and _active_game.poll() is not None:_active_game=None
  return _active_game

def close_active_game():
 """Explicit user-requested exit for the exact game process Elmos World launched.
 First attempt WM_CLOSE and wait briefly; if still alive, terminate only that tracked
 process tree. The game/emulator and its files are never deleted.
 """
 process=active_game_process()
 if process is None:
  return {'closed':True,'alreadyStopped':True,'message':'The tracked game is already closed.'}
 if sys.platform!='win32':
  return {'closed':False,'message':'This exit action requires Windows.'}
 import ctypes
 from ctypes import wintypes
 user32=ctypes.windll.user32
 CALLBACK=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
 pid=process.pid
 def visit(hwnd,_):
  owner=wintypes.DWORD()
  user32.GetWindowThreadProcessId(hwnd,ctypes.byref(owner))
  if owner.value==pid and user32.IsWindowVisible(hwnd):
   user32.PostMessageW(hwnd,0x0010,0,0)
  return True
 user32.EnumWindows(CALLBACK(visit),0)
 method='normal'
 try:process.wait(timeout=2.0)
 except subprocess.TimeoutExpired:
  method='forced'
  # Only the launched PID (and its descendants), never a process-name wildcard.
  try:
   result=subprocess.run(['taskkill','/PID',str(pid),'/T','/F'],capture_output=True,text=True,timeout=10,check=False)
  except (OSError,subprocess.TimeoutExpired) as exc:
   return {'closed':False,'message':'Unable to close game: '+str(exc)}
  try:process.wait(timeout=2.0)
  except subprocess.TimeoutExpired:
   return {'closed':False,'message':'The game is still running. '+(result.stderr or result.stdout)[:170]}
 global _active_game,_session_window,_session_window_since
 with _active_game_lock:
  if _active_game is process:_active_game=None
 _session_window=0;_session_window_since=0
 return {'closed':True,'method':method,'message':'Game closed and returned to Elmos World.'}


# Session window detection does not send Esc/Alt+Enter or change emulator settings.
def find_game_window(pid,include_minimized=False):
 if sys.platform!='win32' or not pid:return 0
 try:
  import ctypes
  from ctypes import wintypes
  u=ctypes.windll.user32
  u.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
  CALLBACK=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
  found=[]
  def visit(hwnd,_):
   owner=wintypes.DWORD();u.GetWindowThreadProcessId(hwnd,ctypes.byref(owner))
   if owner.value!=pid or not u.IsWindowVisible(hwnd):return True
   iconic=bool(u.IsIconic(hwnd))
   if iconic and not include_minimized:return True
   if u.GetWindowTextLengthW(hwnd)<=0:return True
   if iconic:
    # Windows may minimize an exclusive-fullscreen game as soon as the PS
    # menu opens. Keep that HWND available for Resume, but never for initial
    # launch-readiness timing.
    found.append((1,int(hwnd)));return True
   rect=wintypes.RECT()
   if not u.GetWindowRect(hwnd,ctypes.byref(rect)):return True
   width=rect.right-rect.left;height=rect.bottom-rect.top
   if width>=500 and height>=300:
    found.append((width*height,int(hwnd)))
   return True
  u.EnumWindows(CALLBACK(visit),0)
  return max(found)[1] if found else 0
 except Exception:return 0

_session_window=0
_session_window_since=0
_active_launch_profile={}
_launch_process_at=0.0
_window_stability_logged=False

# Session trace is bounded and records launch transitions without changing game behavior.
_session_events=[]
_session_events_lock=threading.RLock()
def session_event(stage,detail=''):
 with _session_events_lock:
  _session_events.append({'at':round(time.time(),3),'stage':str(stage)[:50],'detail':str(detail)[:180]})
  del _session_events[:-100]
def session_history():
 with _session_events_lock:return list(_session_events[-50:])

def active_session_status():
 global _session_window,_session_window_since,_window_stability_logged
 p=active_game_process()
 if not p:
  _session_window=0;_session_window_since=0;_window_stability_logged=False
  return {'running':False,'pid':None,'windowReady':False,'windowStable':False,'gameId':None,'gameName':None}
 hwnd=find_game_window(p.pid)
 if hwnd!=_session_window:
  elapsed_since_launch=time.monotonic()-_launch_process_at if _launch_process_at else 0
  session_event('window_detected' if hwnd else 'window_lost',f'type={_active_game_type}; after launch={elapsed_since_launch:.2f}s')
  _session_window=hwnd;_session_window_since=time.monotonic();_window_stability_logged=False
 profile=_active_launch_profile.copy()
 # Xenia reports a visible emulator window before SSX has started rendering.
 # This is a configurable delay, NOT a claim that the first playable frame is detectable.
 wait=profile.get('readySeconds',5.0 if _active_game_type=='rom' else 0.9)
 elapsed=time.monotonic()-_session_window_since if hwnd else 0
 stable=bool(hwnd) and elapsed>=wait
 if stable and not _window_stability_logged:
  _window_stability_logged=True
  session_event('window_stable',f'type={_active_game_type}; startup hold={elapsed:.2f}s')
 return {'running':True,'pid':p.pid,'gameId':_active_game_id,'gameName':_active_game_name,'windowReady':bool(hwnd),'windowStable':stable,
         'windowHandle':hwnd,'waitSeconds':round(wait,1),'windowElapsed':round(elapsed,1),
         'gameType':_active_game_type,'phase':'ready' if stable else ('warming' if hwnd else 'starting')}

def handoff_active_game():
 p=active_game_process()
 if not p:return False
 # Drop our topmost flag immediately BEFORE the foreground request.
 # Restoring it on rejection keeps the artwork on screen for manual retry.
 had_shield=_shield_on
 # FIRST focus the game while the existing Elmos window covers the desktop;
 # THEN release the topmost flag. This reduces the visible handoff gap.
 # Windows may still reject foreground changes or exclusive fullscreen modes.
 focused=focus_launched_game(p.pid,timeout=0.85)
 if focused:
  if had_shield:set_launch_shield(False)
 else:
  # Some Windows builds require the topmost flag to drop before accepting focus.
  if had_shield:
   set_launch_shield(False)
   focused=focus_launched_game(p.pid,timeout=0.35)
   if not focused:set_launch_shield(True)
 session_event('handoff_succeeded' if focused else 'handoff_blocked',f'type={_active_game_type}; since launch={(time.monotonic()-_launch_process_at):.2f}s' if _launch_process_at else f'type={_active_game_type}')
 return focused

def request_game_close():
 """Ask visible game window to close normally; never force-kill the game."""
 p=active_game_process()
 if p is None:return {'requested':False,'message':'No active game session.'}
 hwnd=find_game_window(p.pid)
 if not hwnd:return {'requested':False,'message':'Game window unavailable. Close it from the game or Windows.'}
 import ctypes
 ctypes.windll.user32.PostMessageW(hwnd,0x0010,0,0)
 return {'requested':True,'message':'Windows asked the game to close. Unsaved progress may be lost.'}

APP=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'SteamMatch'
LAUNCH_PROFILES=APP/'launch_profiles.json'; SETTINGS=APP/'settings.json'; REGISTRY=APP/'registry_v2.json'; ARCADE=APP/'arcade.json'; BACKUP=APP/'backups'; GROVE=APP/'grove_state.json'; GROVE_ART=APP/'grove_art'
DEFAULT_GAMES=Path('C:/Gaming/Games'); DEFAULT_EMULATORS=Path('C:/Gaming/Emulators')
BAD=('redist','_commonredist','setup','unins','crash','easyanticheat','eac','dxweb','vcredist','dotnet','oalinst','prereq','benchmark','updater','artwork_minisoundtrack','crashreport','anticheat','uninstall','redistributable','vc_redist')
PREFERRED={
 '7 days to die':'7DaysToDie.exe','buckshot roulette':'Buckshot Roulette.exe','control':'Control.exe',
 'keep talking and nobody explodes':'ktane.exe','outer wilds':'OuterWilds.exe','sekiro':'sekiro.exe',
 'silent hill 2':'SHProto.exe','the jackbox party pack 7':'The Jackbox Party Pack 7.exe'}


def load_launch_profile(gameid,kind='pc'):
 data=read_json(LAUNCH_PROFILES,{})
 v=data.get(str(gameid),{})
 default=5.0 if kind=='rom' else 0.9
 try:seconds=float(v.get('readySeconds',default))
 except (ValueError,TypeError):seconds=default
 return {'readySeconds':max(0.7,min(25.0,seconds))}


def save_launch_profile(gameid,seconds):
 try:seconds=float(seconds)
 except (TypeError,ValueError):raise ValueError('Invalid readiness time')
 if not 0.7<=seconds<=25.0:raise ValueError('Wait must be between 0.7 and 25 seconds')
 values=read_json(LAUNCH_PROFILES,{})
 values[str(gameid)]={'readySeconds':round(seconds,1)}
 write_json(LAUNCH_PROFILES,values)
 return values[str(gameid)]

def read_json(path,default):
 try:return json.loads(path.read_text(encoding='utf8'))
 except (OSError,ValueError,UnicodeError):return default

def write_json(path,obj):
 path.parent.mkdir(parents=True,exist_ok=True)
 with tempfile.NamedTemporaryFile(mode='w',encoding='utf8',dir=path.parent,delete=False) as fh:
  json.dump(obj,fh,indent=2);fh.flush();os.fsync(fh.fileno());tmp=fh.name
 os.replace(tmp,path)

def norm(s):return ' '.join(re.findall('[a-z0-9]+',str(s).lower()))
def friendly(s):
 return clean_game_title(s)

def normpath(s):return os.path.normcase(os.path.normpath(str(s).strip('"'))).casefold()
def quote(s):return '"'+str(s).strip('"')+'"'

def steam_root():
 opts=[]
 if sys.platform=='win32':
  try:
   import winreg
   for hive,k in ((winreg.HKEY_CURRENT_USER,r'Software\Valve\Steam'),(winreg.HKEY_LOCAL_MACHINE,r'SOFTWARE\WOW6432Node\Valve\Steam')):
    try:
     with winreg.OpenKey(hive,k) as h:
      for attr in ('SteamPath','InstallPath'):
       try:opts.append(Path(winreg.QueryValueEx(h,attr)[0]))
       except OSError:pass
    except OSError:pass
  except OSError:pass
 opts += [Path(r'C:\Program Files (x86)\Steam'),Path(r'C:\Program Files\Steam')]
 return next((p for p in opts if (p/'steam.exe').exists()),opts[0])

def steam_profile(steam,selected):
 root=steam/'userdata'
 if not root.exists():return None
 profiles=[p for p in root.iterdir() if p.is_dir() and p.name.isdigit() and p.name!='0']
 match=next((p for p in profiles if p.name==str(selected)),None)
 if match:return match
 if len(profiles)==1:return profiles[0]
 return None

def exe_candidates(folder):
 # Legacy-compatible API; candidates are now scored by game_discovery.
 return detect_pc_game(folder)['candidates']

def recognize(folder,prior):
 result=detect_pc_game(folder,prior)
 return result['exe'],result['uncertain'],result['candidates']


def read_shortcuts(profile):
 path=profile/'config'/'shortcuts.vdf';data=vdf.load_vdf(path);return path,data,data['shortcuts']

def appid(rec):return int(rec['appid']) & 0xffffffff

def resolve(rows,exe,args,prior):
 if prior.get('appid') is not None:
  matches=[(k,r) for k,r in rows.items() if isinstance(r,dict) and 'appid' in r and appid(r)==int(prior['appid'])]
  if len(matches)==1:return matches[0]
 # Matching launch options is essential when emulator EXE is shared by multiple games.
 matches=[(k,r) for k,r in rows.items() if isinstance(r,dict) and normpath(r.get('Exe',r.get('exe','')))==normpath(exe) and str(r.get('LaunchOptions','')).strip().casefold()==args.strip().casefold()]
 if len(matches)>1:raise RuntimeError('More than one Steam shortcut matches; please review in Steam.')
 return matches[0] if matches else None


def safe_write(path,data):
 payload=vdf.pack_obj(data);check,off=vdf.parse_obj(payload,0)
 if off!=len(payload) or check!=data:raise RuntimeError('Steam database round-trip verification failed; no changes made.')
 path.parent.mkdir(parents=True,exist_ok=True);BACKUP.mkdir(parents=True,exist_ok=True)
 if path.exists():shutil.copy2(path,BACKUP/('shortcuts-'+time.strftime('%Y%m%d-%H%M%S')+'-'+secrets.token_hex(3)+'.vdf.bak'))
 with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as fh:
  fh.write(payload);fh.flush();os.fsync(fh.fileno());tmp=fh.name
 try:os.replace(tmp,path)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)

def new_appid(rows):
 used={appid(r) for r in rows.values() if isinstance(r,dict) and 'appid' in r}
 while True:
  num=secrets.randbits(31)|0x80000000
  if num not in used:return num

def art_path(profile,id,suffix):
 grid=profile/'config'/'grid'
 for ext in ('.png','.jpg','.jpeg'):
  f=grid/(str(id)+suffix+ext)
  if f.is_file():return f
 return None

def art_info(profile,id):
 if not profile or id is None:return {}
 return {slot:bool(art_path(profile,id,s)) for slot,s in [('portrait','p'),('wide',''),('hero','_hero'),('logo','_logo'),('icon','_icon')]}

def steamgrid(endpoint,key):
 url='https://www.steamgriddb.com/api/v2/'+endpoint
 req=urllib.request.Request(url,headers={'Authorization':'Bearer '+key,'User-Agent':'SteamMatchArcade/1.0'})
 with urllib.request.urlopen(req,timeout=15) as resp:
  doc=json.load(resp)
 if not doc.get('success',False):raise RuntimeError('SteamGridDB rejected request: '+str(doc.get('errors',''))[:200])
 return doc.get('data',[])

def get_art(profile,id,gameid,key):
 grid=profile/'config'/'grid';grid.mkdir(parents=True,exist_ok=True)
 made=0;warnings=[]
 for kind,dim,suffix in [('grids','600x900','p'),('grids','920x430',''),('heroes',None,'_hero'),('logos',None,'_logo'),('icons',None,'_icon')]:
  if art_path(profile,id,suffix):continue
  try:
   items=steamgrid(f'{kind}/game/{gameid}'+(f'?dimensions={dim}' if dim else ''),key)
   urls=[x.get('url') for x in items if x.get('url') and Path(urllib.parse.urlsplit(x['url']).path).suffix.lower() in ('.png','.jpg','.jpeg')]
   if not urls:continue
   url=urls[0];ext=Path(urllib.parse.urlsplit(url).path).suffix.lower()
   req=urllib.request.Request(url,headers={'User-Agent':'SteamMatchArcade/1.0'})
   with urllib.request.urlopen(req,timeout=20) as response:raw=response.read(12_000_001)
   if not raw or len(raw)>12_000_000:continue
   if ext=='.png' and not raw.startswith(b'\x89PNG\r\n\x1a\n'):continue
   if ext in ('.jpg','.jpeg') and not raw.startswith(b'\xff\xd8'):continue
   with tempfile.NamedTemporaryFile(dir=grid,delete=False) as fh:fh.write(raw);tmp=fh.name
   os.replace(tmp,grid/(str(id)+suffix+ext));made+=1
  except Exception as exc:warnings.append(f'{kind}: {str(exc)[:100]}')
 return made,warnings

def repair_legacy(profile):
 grid=profile/'config'/'grid';_,_,rows=read_shortcuts(profile);count=0
 for r in rows.values():
  if not isinstance(r,dict) or 'appid' not in r:continue
  aid=appid(r);old=(aid<<32)|0x02000000
  for suffix in ('p','','_hero','_logo','_icon'):
   if art_path(profile,aid,suffix):continue
   oldfile=art_path(profile,old,suffix)
   if oldfile:shutil.copy2(oldfile,grid/(str(aid)+suffix+oldfile.suffix));count+=1
 return count

METADATA_DIR=APP/'store_metadata'

def store_metadata(title, match_hint=''):
 """Optional public Steam store lookup for launcher-only description and screenshots.
 Never use metadata title to change a Steam shortcut or claim ownership.
 """
 from game_descriptions import curated_metadata
 curated=curated_metadata(title)
 if curated:
  return curated
 METADATA_DIR.mkdir(parents=True,exist_ok=True)
 key=hashlib.sha256(norm(title).encode('utf8')).hexdigest()[:24]
 cache=METADATA_DIR/(key+'.json')
 if cache.exists() and time.time()-cache.stat().st_mtime<604800:
  return read_json(cache,{})
 try:
  # The optional known artwork match helps only with store search; exact title matching stays required.
  query=str(match_hint or title).strip()[:120]
  term=urllib.parse.quote(query)
  searchurl=f'https://store.steampowered.com/api/storesearch/?term={term}&l=english&cc=US'
  req=urllib.request.Request(searchurl,headers={'User-Agent':'Mozilla/5.0 SteamMatchArcade/1.0'})
  with urllib.request.urlopen(req,timeout=8) as response:results=json.load(response).get('items',[])
  exact=[x for x in results if norm(x.get('name',''))==norm(query)]
  if len(exact)!=1:return {'available':False,'reason':'No unambiguous Steam store page found. You can add your own notes.'}
  steamid=int(exact[0]['id'])
  url=f'https://store.steampowered.com/api/appdetails?appids={steamid}&cc=US&l=english'
  req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 SteamMatchArcade/1.0'})
  with urllib.request.urlopen(req,timeout=8) as response:detail=json.load(response)
  row=detail.get(str(steamid),{})
  if not row.get('success'):return {'available':False,'reason':'Details not publicly available.'}
  data=row.get('data',{})
  out={'available':True,'title':data.get('name',title),'description':re.sub(r'<[^>]*>','',data.get('short_description',''))[:1100],
   'release':data.get('release_date',{}).get('date',''),'genres':[x['description'] for x in data.get('genres',[])[:6]],
   'developer':', '.join(data.get('developers',[])[:3]),'steamStoreId':steamid,'screenshots':[], 'source':'Steam Store'}
  for shot in data.get('screenshots',[])[:5]:
   link=shot.get('path_thumbnail','')
   if link.startswith('https://') and ('steamstatic.com/' in link or 'akamaihd.net/' in link):out['screenshots'].append(link)
  write_json(cache,out)
  return out
 except Exception as e:
  return {'available':False,'reason':'Store metadata unavailable: '+str(e)[:100]}

def focus_launched_game(pid,timeout=18):
 """Best-effort foreground handoff for a newly launched Windows game.

 Never elevate, force a display mode, or steal focus after the startup window.
 Some launchers create a different child process; these may still need a manual
 Alt+Tab if their launch chain is unusual.
 """
 if sys.platform!='win32':return False
 try:
  import ctypes
  from ctypes import wintypes
  user=ctypes.windll.user32
  kernel=ctypes.windll.kernel32
  user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
  user.GetWindowThreadProcessId.restype=wintypes.DWORD
  user.EnumWindows.argtypes=[ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM),wintypes.LPARAM]
  user.EnumWindows.restype=wintypes.BOOL
  user.IsWindowVisible.argtypes=[wintypes.HWND];user.IsWindowVisible.restype=wintypes.BOOL
  user.GetWindow.argtypes=[wintypes.HWND,wintypes.UINT];user.GetWindow.restype=wintypes.HWND
  user.GetWindowTextLengthW.argtypes=[wintypes.HWND];user.GetWindowTextLengthW.restype=ctypes.c_int
  user.ShowWindow.argtypes=[wintypes.HWND,ctypes.c_int]
  user.SetForegroundWindow.argtypes=[wintypes.HWND];user.SetForegroundWindow.restype=wintypes.BOOL
  user.GetForegroundWindow.restype=wintypes.HWND
  user.GetCurrentThreadId=kernel.GetCurrentThreadId
  user.GetCurrentThreadId.restype=wintypes.DWORD
  user.AttachThreadInput.argtypes=[wintypes.DWORD,wintypes.DWORD,wintypes.BOOL]
  user.AttachThreadInput.restype=wintypes.BOOL
  enum_type=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
  start=time.monotonic()
  while time.monotonic()-start<timeout:
   # Use the same real-size, non-minimized window used for launch readiness.
   hwnd=find_game_window(pid,include_minimized=True)
   if hwnd:
    # Avoid disturbing a game Windows has already activated on its own.
    if user.GetForegroundWindow()==hwnd:return True
    user.ShowWindow(hwnd,9)  # SW_RESTORE; never send Escape or Alt+Enter
    foreground=user.GetForegroundWindow()
    foreground_tid=user.GetWindowThreadProcessId(foreground,None) if foreground else 0
    own_tid=kernel.GetCurrentThreadId()
    attached=bool(foreground_tid and foreground_tid!=own_tid and user.AttachThreadInput(own_tid,foreground_tid,True))
    try:
     user.SetForegroundWindow(hwnd)
    finally:
     if attached:user.AttachThreadInput(own_tid,foreground_tid,False)
    if user.GetForegroundWindow()==hwnd:return True
   time.sleep(.11)
 except Exception as e:
  print('Game focus handoff unavailable:',e)
 return False

class Engine:
 def __init__(self):
  APP.mkdir(parents=True,exist_ok=True);BACKUP.mkdir(exist_ok=True)
  self.cfg=read_json(SETTINGS,{})
  self.reg=read_json(REGISTRY,{})
  self.extra=read_json(ARCADE,{'emulators':{},'roms':{},'notes':{}})
  self.steam=Path(self.cfg.get('steam_path') or steam_root())
  self.profile=steam_profile(self.steam,self.cfg.get('steam_user','911263618'))
  self.games_root=Path(self.cfg.get('games_folder') or DEFAULT_GAMES)
  self.lock=threading.RLock()
  self.local=read_json(GROVE,{'games':{},'preferences':{'splash':True}})
  self._cache=None;self._cache_time=0
  self._pending_uninstall={}
 def save(self):
  self._cache=None
  write_json(SETTINGS,self.cfg);write_json(REGISTRY,self.reg);write_json(ARCADE,self.extra)
 def save_local(self):
  self._cache=None
  write_json(GROVE,self.local)
 def local_entry(self,gameid):return self.local.setdefault('games',{}).setdefault(gameid,{})
 def set_local_match(self,gameid,matchid,name):
  """Explicit artwork match updates all slots for the selected edition.

  Complete downloads in a private staging folder before replacing old artwork.
  Never silently leave a previous title's hero/cover behind after changing IDs.
  Steam shortcuts, game executables, and manual captures remain untouched.
  """
  with self.lock:
   g=self.find(gameid)
   if not g:raise RuntimeError('Game not found.')
   key=self.cfg.get('api_key','').strip()
   if not key:raise RuntimeError('Configure SteamGridDB API key in Settings.')
   gid=int(matchid)
   if gid<=0:raise RuntimeError('Invalid game match.')
   clean_name=str(name).strip()[:140]
   if not clean_name:raise RuntimeError('Select a named game match.')
   folder=GROVE_ART/hashlib.sha256(gameid.encode('utf8')).hexdigest()[:24]
   folder.mkdir(parents=True,exist_ok=True)
   previous=self.local.get('games',{}).get(gameid,{})
   different=previous.get('matchId') is None or int(previous.get('matchId'))!=gid
   slots=[('grids','600x900','portrait'),('grids','920x430','wide'),('heroes',None,'hero'),('logos',None,'logo')]
   downloaded=0;warnings=[]
   # Use a unique staging directory so half-finished downloads aren't served.
   with tempfile.TemporaryDirectory(prefix='media-stage-',dir=folder) as stage_name:
    stage=Path(stage_name)
    fetched={}
    for kind,dim,slot in slots:
     try:
      items=steamgrid(f'{kind}/game/{gid}'+(f'?dimensions={dim}' if dim else ''),key)
      urls=[x.get('url') for x in items if x.get('url') and Path(urllib.parse.urlsplit(x['url']).path).suffix.lower() in ('.png','.jpg','.jpeg')]
      if not urls:
       warnings.append(f'{slot}: unavailable from selected match')
       continue
      url=urls[0];ext=Path(urllib.parse.urlsplit(url).path).suffix.lower()
      req=urllib.request.Request(url,headers={'User-Agent':'ElmosWorld/2.8'})
      with urllib.request.urlopen(req,timeout=20) as resp:raw=resp.read(12_000_001)
      if not raw or len(raw)>12_000_000:raise ValueError('Image too large or empty')
      if ext=='.png' and not raw.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError('Invalid PNG image')
      if ext!='.png' and not raw.startswith(b'\xff\xd8'):raise ValueError('Invalid JPEG image')
      target=stage/(slot+ext);target.write_bytes(raw);fetched[slot]=target
     except Exception as e:warnings.append(f'{slot}: {str(e)[:130]}')
    if not fetched:
     raise RuntimeError('Artwork could not be retrieved; previous match kept unchanged. Try again later.')
    # Apply ALL downloaded slots, removing old formats for those slots. When
    # switching matches, remove unmatched old slots so two games never mix.
    for _,_,slot in slots:
     source=fetched.get(slot)
     if not source and not different:continue
     for ext in ('.png','.jpg','.jpeg'):
      old=folder/(slot+ext)
      if old.is_file():old.unlink()
     if source:
      os.replace(source,folder/source.name)
      downloaded+=1
   entry=self.local_entry(gameid)
   entry.update({'matchId':gid,'matchName':clean_name,'artVersion':int(time.time()*1000)})
   self.save_local()
   return {'downloaded':downloaded,'warnings':warnings,'matchedTitle':clean_name,
           'refreshGallery':True}
 def local_art_path(self,gameid,slot):
  folder=GROVE_ART/hashlib.sha256(gameid.encode('utf8')).hexdigest()[:24]
  for ext in ('.png','.jpg','.jpeg'):
   p=folder/(slot+ext)
   if p.is_file():return p
  g=self.find(gameid)
  if g and g.get('appid') is not None:return art_path(self.profile,g['appid'],{'portrait':'p','wide':'','hero':'_hero','logo':'_logo','icon':'_icon'}.get(slot,'p'))
  return None
 def health_check(self,gameid=None):
  """Read-only checks. No executables run, no game files changed."""
  games=self.list_games(force=True)
  if gameid is not None:
   games=[g for g in games if g['id']==gameid]
   if not games:raise RuntimeError('Game not found.')
  output=[]
  for g in games:
   problems=[]
   if not Path(g['exe']).is_file():problems.append('Game executable or emulator is missing')
   if g['type']=='rom':
    if not Path(g['gamefile']).is_file():problems.append('Disc image / ROM is missing')
   elif not Path(g['folder']).is_dir():problems.append('Game folder is missing')
   if g['uncertain'] and not problems:problems.append('Confirm the recommended executable')
   output.append({'id':g['id'],'name':g['name'],'status':'missing' if any('missing' in p for p in problems) else 'review' if problems else 'ready','issues':problems,'selectedExecutable':g['exe'],'alternatives':g['candidates'][:8],'platform':g['platform']})
  return {'checked':len(output),'ready':sum(x['status']=='ready' for x in output),'items':output}
 def collections(self):
  with self.lock:
   data=self.local.setdefault('collections',{})
   return [{'id':k,'name':v.get('name',k),'gameIds':v.get('gameIds',[])} for k,v in data.items()]
 def update_collection(self,action,name='',collectionid='',gameid=''):
  with self.lock:
   data=self.local.setdefault('collections',{})
   if action=='create':
    clean=' '.join(str(name).split())[:45]
    if not clean:raise RuntimeError('Collection name required.')
    cid=hashlib.sha256(clean.lower().encode()).hexdigest()[:16]
    if cid in data:raise RuntimeError('Collection already exists.')
    data[cid]={'name':clean,'gameIds':[]}
   elif action=='delete':
    if collectionid not in data:raise RuntimeError('Collection not found.')
    del data[collectionid]
   elif action in ('add','remove'):
    if collectionid not in data:raise RuntimeError('Collection not found.')
    if not self.find(gameid):raise RuntimeError('Game not found.')
    ids=data[collectionid].setdefault('gameIds',[])
    if action=='add' and gameid not in ids:ids.append(gameid)
    if action=='remove' and gameid in ids:ids.remove(gameid)
   else:raise RuntimeError('Unsupported collection action.')
   self.save_local();return {'ok':True,'collections':self.collections()}
 def make_backup(self):
  """Atomic local settings snapshot; never copies game installations or Steam data."""
  with self.lock:
   dest=APP/'restore_points';dest.mkdir(parents=True,exist_ok=True)
   stamp=time.strftime('%Y%m%d-%H%M%S')+'-'+secrets.token_hex(2)
   target=dest/stamp;target.mkdir()
   names={'settings.json':SETTINGS,'registry_v2.json':REGISTRY,'arcade.json':ARCADE,'grove_state.json':GROVE}
   for name,path in names.items():
    if path.is_file():shutil.copy2(path,target/name)
   (target/'manifest.json').write_text(json.dumps({'created':int(time.time()),'version':'1.8','files':[n for n,p in names.items() if p.is_file()]},indent=2),encoding='utf8')
   return {'ok':True,'name':stamp,'path':str(target),'files':len(list(target.glob('*.json')))-1}
 def backups(self):
  root=APP/'restore_points'
  if not root.exists():return []
  return [{'name':p.name,'date':p.stat().st_mtime} for p in sorted(root.iterdir(),reverse=True) if p.is_dir() and (p/'manifest.json').is_file()][:25]
 def restore_backup(self,name):
  """Restore chosen user state only, first saving current state. Caller restarts app."""
  if not re.fullmatch(r'[0-9]{8}-[0-9]{6}-[0-9a-f]{4}',str(name)):
   raise RuntimeError('Invalid backup name.')
  source=APP/'restore_points'/name
  if not (source/'manifest.json').is_file():raise RuntimeError('Backup does not exist.')
  with self.lock:
   checkpoint=self.make_backup()
   for filename,target in [('settings.json',SETTINGS),('registry_v2.json',REGISTRY),('arcade.json',ARCADE),('grove_state.json',GROVE)]:
    p=source/filename
    if p.is_file():
     validated=read_json(p,None)
     if not isinstance(validated,dict):raise RuntimeError('Backup contains invalid JSON: '+filename)
     write_json(target,validated)
   self.cfg=read_json(SETTINGS,{});self.reg=read_json(REGISTRY,{})
   self.extra=read_json(ARCADE,{'emulators':{},'roms':{},'notes':{}})
   self.local=read_json(GROVE,{'games':{},'preferences':{}})
   self.games_root=Path(self.cfg.get('games_folder') or DEFAULT_GAMES)
   self._cache=None
   return {'ok':True,'checkpoint':checkpoint['name'],'message':'Settings restored. Restart Elmos World to reload controller and appearance preferences.'}
 def activity(self):
  games=[g for g in self.list_games() if not g['hidden']]
  played=[g for g in games if g.get('lastPlayed')]
  total=sum(max(0,int(g.get('playSeconds') or 0)) for g in games)
  return {'totalSeconds':total,'sessionCount':sum(max(0,int(g.get('playCount') or 0)) for g in games),
          'gamesPlayed':len(played),'favorites':sum(bool(g['favorite']) for g in games),
          'recent':[{'id':g['id'],'name':g['name'],'seconds':int(g.get('playSeconds') or 0),'lastPlayed':g['lastPlayed']} for g in sorted(played,key=lambda x:x.get('lastPlayed') or 0,reverse=True)[:10]],
          'mostPlayed':[{'id':g['id'],'name':g['name'],'seconds':int(g.get('playSeconds') or 0)} for g in sorted(games,key=lambda x:x.get('playSeconds') or 0,reverse=True)[:10] if g.get('playSeconds')]}
 def platform_sources(self):
  from provider_adapters import discover
  return discover()
 def record_finished_session(self,gameid,started,process):
  try:process.wait()
  except Exception:return
  seconds=max(0,int(time.monotonic()-started))
  session_event('process_exited',f'{gameid[-55:]} · {seconds}s')
  with self.lock:
   entry=self.local_entry(gameid)
   entry['playSeconds']=int(entry.get('playSeconds',0))+seconds
   entry['lastSessionSeconds']=seconds
   entry['lastPlayed']=int(time.time())
   self.save_local()
  # A real game exit must wake the original launcher without requiring its
  # minimized JavaScript view to continue polling. A failed callback is safe.
  callback=getattr(self,'on_session_exit',None)
  with _active_game_lock:
   current=_active_game
  if current is not None and current is not process:callback=None
  if callable(callback):
   try: callback()
   except Exception:pass
 def set_favorite(self,gameid,favorite):
  with self.lock:
   if not self.find(gameid):raise RuntimeError('Game not found.')
   self.local_entry(gameid)['favorite']=bool(favorite);self.save_local();return {'ok':True}
 def set_compatibility_mode(self,gameid,enabled):
  """Opt-in minimal foreground handling for unstable fullscreen PC games."""
  with self.lock:
   g=self.find(gameid)
   if not g or g['type']!='pc':raise RuntimeError('Choose an existing PC game.')
   if type(enabled) is not bool:raise ValueError('Compatibility mode must be enabled or disabled.')
   self.local_entry(gameid)['lowImpactLaunch']=enabled
   self.save_local()
   return {'ok':True,'enabled':enabled}
 def uninstall_preview(self,gameid):
  """First stage: validate and bind a short-lived token to this exact folder."""
  import secrets
  from game_uninstall import validated_game_directory
  with self.lock:
   if active_game_process() is not None:
    raise RuntimeError('Close the active game before uninstalling anything.')
   g=self.find(gameid)
   folder=validated_game_directory(g,self.games_root)
   code=secrets.token_urlsafe(24)
   self._pending_uninstall={code:(gameid,str(folder),time.monotonic()+300)}
   return {'token':code,'name':g['name'],'folder':str(folder),
           'warning':'This permanently deletes the ENTIRE selected PC game folder, including any saves stored inside it. This cannot be undone. No separate Windows confirmation is shown. Other games and emulators are untouched. Windows permissions still apply.'}
 def uninstall_confirm(self,gameid,token,confirmation):
  """Second stage: explicit in-app approval; validate path again before deleting."""
  from game_uninstall import validated_game_directory,delete_entire_folder
  with self.lock:
   if confirmation!='DELETE_PERMANENTLY':raise ValueError('Explicit permanent deletion confirmation required.')
   if active_game_process() is not None:raise RuntimeError('Close the active game before uninstalling anything.')
   entry=self._pending_uninstall.pop(str(token),None)
   if not entry or entry[0]!=gameid or entry[2]<time.monotonic():
    raise ValueError('Removal confirmation has expired. Start again.')
   g=self.find(gameid)
   folder=validated_game_directory(g,self.games_root)
   if str(folder)!=entry[1]:raise ValueError('The game folder changed since confirmation. Start again.')
   delete_entire_folder(folder)
   self.local_entry(gameid)['hidden']=True
   self.save_local()
   return {'ok':True,'name':g['name'],'folder':str(folder),
           'message':'The selected game folder was deleted permanently. Other game folders and emulators were untouched.'}
 def remove_game_from_library(self,gameid):
  """Hide a PC game (restorable in Settings), unregister ROMs safely."""
  g=self.find(gameid)
  if not g:raise RuntimeError('Game not found.')
  if g['type']=='rom':return self.forget_rom(gameid)
  return self.set_hidden(gameid,True)
 def delete_hidden_selected(self,gameids):
  """Permanently forget selected hidden library entries, never their files."""
  with self.lock:
   if not isinstance(gameids,list) or not gameids or len(gameids)>200 or not all(isinstance(x,str) for x in gameids):
    raise ValueError('Select up to 200 hidden games to remove.')
   ids=list(dict.fromkeys(gameids))
   games={g['id']:g for g in self.list_games(force=False)}
   if any(i not in games or not games[i]['hidden'] for i in ids):
    raise ValueError('Only games currently hidden in Elmos World can be deleted here.')
   if active_game_process() is not None:
    raise RuntimeError('Close the running game first.')
   for gameid in ids:
    if games[gameid]['type']=='rom':
     self.extra['roms'].pop(gameid,None)
    self.local_entry(gameid)['excluded']=True
    self.local_entry(gameid)['hidden']=True
   self.save_local()
   self.save()
   return {'ok':True,'removed':len(ids),'message':f'{len(ids)} hidden game(s) forgotten. Files on disk were not deleted.'}
 def gfn_list(self):
  with self.lock:
   return [{'id':k,'name':v['name'],'shortcut':v['shortcut'], 'available':Path(v['shortcut']).is_file(),
            'steamId':v.get('steamId')}
           for k,v in self.local.setdefault('gfnGames',{}).items()]
 def gfn_import(self,path,title=None):
  from geforce_library import import_shortcut
  with self.lock:
   collection=self.local.setdefault('gfnGames',{})
   key=import_shortcut(collection,path,title)
   self.save_local()
   return {'ok':True,'id':key,'games':self.gfn_list()}
 def gfn_rename(self,gameid,title):
  with self.lock:
   item=self.local.setdefault('gfnGames',{}).get(gameid)
   if not item:raise ValueError('Cloud game not found.')
   clean=' '.join(str(title).split())[:140]
   if not clean:raise ValueError('Enter a game name.')
   item['name']=clean;self.save_local()
   return {'ok':True,'games':self.gfn_list()}
 def gfn_match_art(self,gameid):
  """Optional exact Steam Store title match for cover/hero only."""
  from backend import store_metadata
  with self.lock:
   item=self.local.setdefault('gfnGames',{}).get(gameid)
   if not item:raise ValueError('Cloud game not found.')
   name=item['name']
  data=store_metadata(name)
  if not data.get('available') or not data.get('steamStoreId'):
   return {'ok':False,'message':'No exact Steam Store artwork match. Keep the cloud card or rename it before retrying.'}
  with self.lock:
   current=self.local.setdefault('gfnGames',{}).get(gameid)
   if not current or current['name']!=name:raise ValueError('Cloud game changed; retry artwork match.')
   current['steamId']=int(data['steamStoreId']);self.save_local()
   return {'ok':True,'games':self.gfn_list()}
 def gfn_remove(self,gameid):
  with self.lock:
   item=self.local.setdefault('gfnGames',{}).pop(gameid,None)
   if not item:raise ValueError('Cloud game not found.')
   self.save_local()
   return {'ok':True,'games':self.gfn_list()}
 def gfn_launch(self,gameid):
  from geforce_library import launch_shortcut
  with self.lock:
   item=self.local.setdefault('gfnGames',{}).get(gameid)
   if not item:raise ValueError('Cloud game not found.')
   return launch_shortcut(item)
 def set_hidden(self,gameid,hidden):
  with self.lock:
   if not self.find(gameid):raise RuntimeError('Game not found')
   self.local_entry(gameid)['hidden']=bool(hidden)
   self.save_local()
   return {'ok':True,'message':'Removed from Elmos World library; game files and Steam entries are untouched.' if hidden else 'Game restored to your library.'}
 def forget_rom(self,gameid):
  """Remove only the launcher registration for an emulated title; never its ISO or emulator."""
  with self.lock:
   if gameid not in self.extra.get('roms',{}):
    raise RuntimeError('Not a registered emulator game.')
   rom=self.extra['roms'].pop(gameid)
   self.save()
   return {'ok':True,'message':'Removed emulator library entry for '+rom.get('name','game')+'. ISO and emulator were not changed.'}
 def set_preferences(self,preferences):
  with self.lock:
   current=self.local.setdefault('preferences',{})
   allowed={'layout':('grid','compact','cinema'),'previewOnFocus':(True,False),'launchMinimize':(True,False)}
   for key,choices in allowed.items():
    if key in preferences and preferences[key] in choices:current[key]=preferences[key]
   self.save_local()
   return {'ok':True,'preferences':current}
 def set_launch_mode(self,gameid,mode):
  # Compatibility endpoint: a prior release persisted Steam as the default.
  # v2.5 deliberately rejects that behavior rather than silently rewriting it.
  if mode!='direct':raise RuntimeError('Steam is a one-time option. Use Launch through Steam from Configure.')
  if not self.find(gameid):raise RuntimeError('Game not found.')
  return {'ok':True,'mode':'direct'}
 def set_custom_title(self,gameid,title):
  with self.lock:
   g=self.find(gameid)
   if not g or g['type']!='pc':raise RuntimeError('Select an existing PC game.')
   name=' '.join(str(title).strip().split())
   if not 2<=len(name)<=140:raise RuntimeError('Name must be 2 to 140 characters.')
   self.local_entry(gameid)['customTitle']=name
   self.save_local()
   return {'ok':True,'name':name}

 def launch_direct(self,gameid):
  with self.lock:
   # The library UI already scanned and validated these records. Reusing the
   # cached entry avoids a full os.walk of every installed game at Play time.
   # Always check the executable/game file on disk again before spawning.
   g=next((item for item in (getattr(self,'_cache',None) or []) if item['id']==gameid),None)
   if g is None:g=self.find(gameid)
   if not g:raise RuntimeError('Game not found.')
   if g['uncertain']:raise RuntimeError('Choose the correct executable first.')
   exe=Path(g['exe'])
   if not exe.is_file() or exe.suffix.lower()!='.exe':raise RuntimeError('Executable is missing.')
   if g['type']=='pc' and blocked_exe(exe):raise RuntimeError('An installer or maintenance utility cannot be launched as a game.')
   args=[]
   if g['type']=='rom':
    gamefile=Path(g['gamefile'])
    if not gamefile.is_file():raise RuntimeError('Game file is missing.')
    args=[str(gamefile)]
   if sys.platform!='win32':return {'message':'Windows only: launch verified but not executed here.','command':[str(exe)]+args}
   # Lock check and process creation as ONE operation. A second launch must
   # never orphan a live game or overwrite the tracked session.
   global _active_game,_active_game_type,_active_launch_profile,_active_game_id,_active_game_name
   global _session_window,_session_window_since,_launch_process_at,_window_stability_logged
   with _active_game_lock:
    if _active_game is not None and _active_game.poll() is None:
     session_event('launch_rejected',f'active pid={_active_game.pid}')
     raise RuntimeError('Another game is already running. Resume or close it before starting a new game.')
    # No shell, elevation or changes to emulator configuration.
    process=subprocess.Popen([str(exe)]+args,cwd=str(exe.parent),close_fds=True)
    _active_game=process
    _active_game_type=g['type']
    _active_game_id=gameid
    _active_game_name=g['name']
    _active_launch_profile=load_launch_profile(gameid,g['type'])
    _session_window=0;_session_window_since=0;_window_stability_logged=False
    _launch_process_at=time.monotonic()
   session_event('process_started',g['name'])
   # Game windows often appear seconds after the process starts. Hand focus to the
   # game when a visible top-level window appears, instead of hoping it is ready
   # at the fixed 800ms delay previously used by the web UI.
   # Window handoff is initiated only after the loading transition is ready.
   entry=self.local_entry(gameid);entry['lastPlayed']=int(time.time());entry['playCount']=entry.get('playCount',0)+1;self.save_local()
   threading.Thread(target=self.record_finished_session,args=(gameid,time.monotonic(),process),daemon=True,name='game-playtime').start()
   return {'message':'Launching '+g['name']+' directly.','command':[str(exe)]+args}
 def xenia_controller(self,emulatorid):
  with self.lock:
   em=self.extra.get('emulators',{}).get(emulatorid)
   if not em:raise RuntimeError('Emulator not found')
   exe=Path(em.get('exe',''))
   if 'xenia' not in exe.name.lower():raise RuntimeError('This controller preset is for Xenia Canary only.')
   if not exe.is_file():raise RuntimeError('Emulator executable is missing.')
   candidates=[exe.parent/'xenia-canary-config.toml',exe.parent/'xenia-canary.config.toml']
   config=next((p for p in candidates if p.is_file()),None)
   if not config:raise RuntimeError('Xenia config not found. Open Xenia once, then try again.')
   raw=config.read_text(encoding='utf-8-sig')
   # Match only the config key, preserving the rest of the file.
   pattern=r'(?m)^(\s*hid\s*=\s*)[\"\'][^\"\']*[\"\']'
   if not re.search(pattern,raw):raise RuntimeError('No supported hid setting found in Xenia config. No changes made.')
   changed=re.sub(pattern,lambda m:m.group(1)+'\"sdl\"',raw,count=1)
   if changed==raw:return {'message':'Xenia SDL controller mode already configured.'}
   backup=config.with_name(config.name+'.grove-'+time.strftime('%Y%m%d-%H%M%S')+'.bak')
   shutil.copy2(config,backup)
   with tempfile.NamedTemporaryFile(mode='w',encoding='utf8',dir=config.parent,delete=False) as fh:fh.write(changed);tmp=fh.name
   os.replace(tmp,config)
   return {'message':'Xenia SDL mode enabled. Backup: '+str(backup)}
 def list_games(self,force=False):
  with self.lock:
   if not force and self._cache is not None and time.monotonic()-self._cache_time<90:
    return self._cache
   games=self._scan_games()
   self._cache=games;self._cache_time=time.monotonic()
   return games
 def _scan_games(self):
  with self.lock:
   games=[]
   if self.games_root.is_dir():
    for folder in sorted(self.games_root.iterdir(),key=lambda p:p.name.lower()):
     if not folder.is_dir() or folder.is_symlink():continue
     uid='pc:'+str(folder).casefold()
     if self.local.get('games',{}).get(uid,{}).get('excluded'):continue
     prior=self.reg.get(str(folder),{})
     discovery=detect_pc_game(folder,prior)
     exe,uncertain,options=discovery['exe'],discovery['uncertain'],discovery['candidates']
     local_title=self.local.get('games',{}).get(uid,{}).get('customTitle')
     stored=prior.get('title','').strip()
     # Previously imported shortcuts may have persisted the meaningless outer
     # folder name. Preserve deliberate custom titles, not stale source codes.
     if stored and (stored.casefold()==folder.name.casefold() and JUNK_ROOT.fullmatch(folder.name.strip())):stored=''
     display=local_title or clean_game_title(stored or discovery['name'])
     game={'id':uid,'registryKey':str(folder),'name':display,'nameSource':'custom' if local_title else 'stored' if stored else discovery['source'],'detectionConfidence':discovery['confidence'],'type':'pc','folder':str(folder),'exe':exe,'args':'','candidates':options[:20],'uncertain':uncertain,'platform':'PC'}
     games.append(game)
   for key,rom in self.extra['roms'].items():
    em=self.extra['emulators'].get(rom.get('emulator',''),{})
    exe=em.get('exe','');filepath=rom.get('path','')
    args=quote(filepath) if filepath else ''
    games.append({'id':key,'registryKey':key,'name':rom['name'],'type':'rom','folder':str(Path(filepath).parent),'exe':exe,'args':args,'gamefile':filepath,'emulator':rom.get('emulator'),'uncertain':not Path(exe).is_file() or not Path(filepath).is_file(),'candidates':[],'platform':em.get('platform','Emulated')})
   rows={}
   try:
    if self.profile:_,_,rows=read_shortcuts(self.profile)
   except Exception:pass
   for g in games:
    prior=self.reg.get(g['registryKey'],{})
    try:found=resolve(rows,g['exe'],g['args'],prior) if g['exe'] else None
    except RuntimeError:found=None;g['uncertain']=True
    aid=appid(found[1]) if found else None
    arts=art_info(self.profile,aid)
    g['appid']=aid;g['art']=arts
    g['status']=('Review' if g['uncertain'] else ('Synced' if found else 'New'))
    if found and not arts.get('portrait'):g['status']='Artwork missing'
    g['sgdbId']=prior.get('sgdbId')
    g['synced']=bool(found)
    g['managed']=bool(prior.get('managed') and found and int(prior.get('appid',-1))==aid)
    g['hasKey']=bool(self.cfg.get('api_key'))
    g['note']=self.extra.get('notes',{}).get(g['id'],'')
    local=self.local.get('games',{}).get(g['id'],{})
    g['favorite']=bool(local.get('favorite'));g['lastPlayed']=local.get('lastPlayed',0);g['playCount']=local.get('playCount',0);g['playSeconds']=local.get('playSeconds',0);g['lastSessionSeconds']=local.get('lastSessionSeconds',0);g['launchMode']='direct' # Never persist Steam as the default: one-time opt-in only
    g['localMatch']=local.get('matchName','')
    g['artVersion']=local.get('artVersion',0)
    folder=GROVE_ART/hashlib.sha256(g['id'].encode('utf8')).hexdigest()[:24]
    g['localArt']={slot:any((folder/(slot+ext)).is_file() for ext in ('.png','.jpg','.jpeg')) for slot in ('portrait','wide','hero','logo')}
    g['art']={slot:g['localArt'].get(slot,False) or arts.get(slot,False) for slot in ('portrait','wide','hero','logo','icon')}
    g['launchReady']=not g['uncertain'] and bool(g['exe'])
    g['hidden']=bool(local.get('hidden',False))
    g['lowImpactLaunch']=bool(local.get('lowImpactLaunch', False))
   return games
 def find(self,gameid):
  return next((g for g in self.list_games() if g['id']==gameid),None)
 def info(self,force=False):
  games=self.list_games(force=force)
  return {'games':games,'steamPath':str(self.steam),'steamUser':self.profile.name if self.profile else None,'root':str(self.games_root),'steamRunning':vdf.steam_running() if sys.platform=='win32' else False,'keyConfigured':bool(self.cfg.get('api_key')),'preferences':self.local.get('preferences',{}),'launchProfiles':read_json(LAUNCH_PROFILES,{}),'emulators':self.extra['emulators'],'collections':self.collections(),'platforms':self.platform_sources(),'gfnGames':self.gfn_list(),'counts':{'all':len(games),'synced':sum(g['synced'] for g in games),'review':sum(g['uncertain'] and not g['hidden'] for g in games)}}
 def search(self,name):
  key=self.cfg.get('api_key','').strip()
  if not key:raise RuntimeError('Add your SteamGridDB API key under Settings first.')
  items=steamgrid('search/autocomplete/'+urllib.parse.quote(name,safe=''),key)
  return [{'id':x['id'],'name':x['name'],'release':x.get('release_date')} for x in items[:16]]
 def set_exe(self,gameid,path):
  with self.lock:
   g=self.find(gameid)
   if not g or g['type']!='pc':raise RuntimeError('Select a PC game.')
   target=Path(path)
   if not target.is_file() or target.suffix.lower()!='.exe' or blocked_exe(target) or target not in [Path(x['path']) for x in g['candidates']]:raise RuntimeError('Choose a detected game executable.')
   prior=self.reg.setdefault(g['registryKey'],{});prior['exe']=str(target);self.save()
 def set_emulator(self,name,exe,platform):
  with self.lock:
   p=Path(exe)
   if not p.is_file() or p.suffix.lower()!='.exe':raise RuntimeError('Select an existing emulator .exe.')
   eid=norm(name).replace(' ','-') or secrets.token_hex(3)
   self.extra['emulators'][eid]={'name':name,'exe':str(p),'platform':platform};self.save();return eid
 def add_rom(self,name,path,emulator):
  with self.lock:
   p=Path(path)
   if not p.is_file():raise RuntimeError('Select the game file, not just its folder.')
   if p.suffix.lower() not in ('.iso','.xex','.zar','.god','.cso','.gdi','.chd','.rvz','.wbfs','.wad','.nes','.sfc','.smc','.nsp','.xci','.bin','.cue','.elf','.pkg','.3ds','.cia','.z64','.n64','.v64','.gba','.gbc','.gb','.nds','.iso'):
    raise RuntimeError('Unsupported game file extension. Select a supported disc image or ROM.')
   if emulator not in self.extra['emulators']:raise RuntimeError('Choose a configured emulator.')
   eid='rom:'+hashlib.sha256((normpath(path)+'|'+emulator).encode('utf8')).hexdigest()[:20]
   self.extra['roms'][eid]={'name':name.strip() or p.stem,'path':str(p),'emulator':emulator};self.save();return eid
 def apply(self,gameid,matchid=None,matchname=None):
  with self.lock:
   if vdf.steam_running() and sys.platform=='win32':raise RuntimeError('Exit Steam completely (including the tray icon) before importing.')
   if not self.profile:raise RuntimeError('Steam account not selected. Open Settings.')
   g=self.find(gameid)
   if not g:raise RuntimeError('Game not found. Rescan first.')
   if g['uncertain']:raise RuntimeError('Choose the correct executable or emulator first.')
   if not Path(g['exe']).is_file():raise RuntimeError('Executable no longer exists.')
   if g['type']=='rom' and not Path(g['gamefile']).is_file():raise RuntimeError('Game image no longer exists.')
   prior=self.reg.setdefault(g['registryKey'],{})
   path,data,rows=read_shortcuts(self.profile)
   found=resolve(rows,g['exe'],g['args'],prior)
   created=False
   if found:aid=appid(found[1]);display=found[1].get('AppName',g['name'])
   else:
    aid=new_appid(rows);display=matchname or g['name']
    r={'appid':aid-2**32,'AppName':display,'Exe':quote(g['exe']),'StartDir':quote(str(Path(g['exe']).parent)),'icon':g['exe'],'ShortcutPath':'','LaunchOptions':g['args'],'IsHidden':0,'AllowDesktopConfig':1,'AllowOverlay':1,'OpenVR':0,'Devkit':0,'DevkitGameID':'','DevkitOverrideAppID':0,'LastPlayTime':0,'FlatpakAppID':'','tags':{}}
    idx=max([int(k) for k in rows if str(k).isdigit()]+[-1])+1
    rows[str(idx)]=r;safe_write(path,data);created=True
   prior.update({'appid':aid,'managed':prior.get('managed',False) or created,'exe':g['exe'],'title':display,'type':g['type']})
   if matchid is not None:prior['sgdbId']=int(matchid)
   self.save()
   # An explicit one-game import must not silently repair unrelated shortcuts.
   repaired=0
   downloaded=0;warnings=[]
   key=self.cfg.get('api_key','').strip();sgdb=prior.get('sgdbId')
   if key and sgdb:downloaded,warnings=get_art(self.profile,aid,sgdb,key)
   return {'created':created,'appid':aid,'repaired':repaired,'downloaded':downloaded,'warnings':warnings,'note':'Steam shortcut '+('created' if created else 'reused')+'. Restart Steam to view library changes.'}
 def sync_new(self):
  """One-click sync; only import confident executables with unique exact metadata matches.
  Existing Steam shortcuts are never reimported. Failures stay in review queue.
  """
  with self.lock:
   if vdf.steam_running() and sys.platform=='win32':
    raise RuntimeError('Exit Steam completely before syncing new games. Existing games are unchanged.')
   new=[];skipped=[];errors=[]
   for g in self.list_games():
    if g['synced']:continue
    if g['uncertain']:
     skipped.append(g['name']+': executable needs review');continue
    key=self.cfg.get('api_key','').strip()
    if not key:
     skipped.append(g['name']+': SteamGridDB key required');continue
    prior=self.reg.get(g['registryKey'],{})
    if prior.get('sgdbId'):
     match={'id':prior['sgdbId'],'name':g['name']}
    else:
     try:
      result=steamgrid('search/autocomplete/'+urllib.parse.quote(g['name'],safe=''),key)
      exact=[x for x in result if norm(x.get('name',''))==norm(g['name'])]
      if len(exact)!=1:
       skipped.append(g['name']+': title match needs review');continue
      match=exact[0]
     except Exception as e:
      errors.append(g['name']+': '+str(e)[:110]);continue
    try:
     result=self.apply(g['id'],match['id'],match['name'])
     if result['created']:new.append(g['name'])
    except Exception as e:errors.append(g['name']+': '+str(e)[:110])
   return {'imported':new,'skipped':skipped,'errors':errors}
 def remove(self,gameid):
  with self.lock:
   if vdf.steam_running() and sys.platform=='win32':raise RuntimeError('Exit Steam completely before editing shortcuts.')
   g=self.find(gameid)
   if not g or not g['synced']:raise RuntimeError('Game is not in Steam.')
   if not g['managed']:raise RuntimeError('This entry was not created by SteamMatch; remove it from Steam manually to avoid deleting another app’s shortcut.')
   prior=self.reg.get(g['registryKey'],{})
   path,data,rows=read_shortcuts(self.profile);found=resolve(rows,g['exe'],g['args'],prior)
   if not found:raise RuntimeError('Steam shortcut was not found.')
   del rows[found[0]];data['shortcuts']={str(i):r for i,r in enumerate(rows.values())}
   safe_write(path,data)
   prior.pop('appid',None);prior['managed']=False;self.save()
   return {'message':'Shortcut removed. Game files and artwork retained for recovery.'}
 def launch(self,gameid):
  g=self.find(gameid)
  if not g:raise RuntimeError('Game not found.')
  if not g['synced']:raise RuntimeError('Import this game into Steam first.')
  if sys.platform!='win32':return {'message':'Windows-only Steam launch; dry run.'}
  os.startfile('steam://rungameid/'+str((g['appid']<<32)|0x02000000))
  return {'message':'Requested launch through Steam. Steam Input availability depends on the game and overlay.'}
 def settings(self,changes):
  with self.lock:
   for key in ('games_folder','steam_path','steam_user','api_key'):
    if key in changes:self.cfg[key]=str(changes[key])
   self.steam=Path(self.cfg.get('steam_path') or steam_root())
   self.profile=steam_profile(self.steam,self.cfg.get('steam_user'))
   self.games_root=Path(self.cfg.get('games_folder') or DEFAULT_GAMES)
   self.save()
   return {'ok':True}
 def note(self,gameid,note):
  self.extra.setdefault('notes',{})[gameid]=str(note)[:5000];self.save()

 def _smart_history(self):
  saved=read_json(APP/'smart_moves.json',[])
  return saved if isinstance(saved,list) else []

 def _smart_record_move(self,result):
  history=self._smart_history()
  history.append({key:result[key] for key in ('kind','name','path','from','exe')})
  write_json(APP/'smart_moves.json',history[-100:])

 def smart_undo(self):
  """Undo only the latest recorded move if both paths are still safe."""
  from smart_discovery import undo_verified
  with self.lock:
   if active_game_process():raise RuntimeError('Finish your game before undoing organization.')
   history=self._smart_history()
   if not history:raise RuntimeError('There are no organized folders to undo.')
   record=history[-1]
   downloads=Path(os.environ.get('USERPROFILE',str(Path.home())))/'Downloads'
   undone=undo_verified(record,downloads,self.games_root,DEFAULT_EMULATORS)
   history.pop()
   write_json(APP/'smart_moves.json',history)
   # Remove only the matching registered emulator; never an unrelated entry.
   if record['kind']=='emulator':
    for eid,em in list(self.extra['emulators'].items()):
     if normpath(em.get('exe',''))==normpath(record['exe']):
      del self.extra['emulators'][eid]
      break
    self.save()
   self._cache=None;self._cache_time=0
   return {'ok':True,'undone':undone}

 def smart_preview(self):
  """Inspect Downloads and installed emulator folders without changing files."""
  from smart_discovery import scan_downloads, discover_emulators
  downloads=Path(os.environ.get('USERPROFILE',str(Path.home())))/'Downloads'
  found=scan_downloads(downloads)
  installed=discover_emulators(DEFAULT_EMULATORS)
  return {'downloads':str(downloads),'gamesFolder':str(self.games_root),
          'emulatorsFolder':str(DEFAULT_EMULATORS),
          'autoEnabled':bool(self.cfg.get('smart_auto_enabled',False)),
          'lastMove':self._smart_history()[-1] if self._smart_history() else None,
          'artEnabled':bool(self.cfg.get('api_key','').strip()),
          'items':found,'installedEmulators':installed,
          'counts':{'ready':sum(i['action']=='ready' for i in found),
                    'review':sum(i['action']=='review' for i in found),
                    'ignored':sum(i['action']=='ignore' for i in found)}}

 def smart_mode(self,enabled):
  """An explicit opt-in is required before background file moves."""
  with self.lock:
   self.cfg['smart_auto_enabled']=bool(enabled)
   self.save()
  return {'autoEnabled':bool(enabled)}

 def _smart_register_emulator(self,item):
  """Register a distinct, known emulator without launching or configuring it."""
  em=item.get('emulator') or {}
  if item.get('kind')!='emulator' or item.get('action')!='ready' or not em:return False
  path=Path(item['exe'])
  if not path.is_file():return False
  eid=norm(em.get('name','')).replace(' ','-')
  if not eid or eid in self.extra['emulators']:return False
  if any(normpath(x.get('exe',''))==normpath(path) for x in self.extra['emulators'].values()):return False
  self.extra['emulators'][eid]={'name':em['name'],'platform':em['platform'],'exe':str(path)}
  self.save()
  return True

 def _smart_exact_art(self,folder):
  """Only a unique exact SteamGridDB title may supply artwork."""
  from game_discovery import words
  try:
   key=self.cfg.get('api_key','').strip()
   if not key:return
   matches=steamgrid('search/autocomplete/'+urllib.parse.quote(folder.name,safe=''),key)
   ids={int(x['id']) for x in matches if x.get('id') and
        words(x.get('name',''))==words(folder.name) and
        'software' not in x.get('types',[])}
   if len(ids)!=1:return
   with self.lock:
    uid='pc:'+str(folder).casefold()
    game=self.find(uid)
    if not game or game['uncertain'] or game.get('localMatch'):return
    self.set_local_match(uid,next(iter(ids)),folder.name)
  except Exception as exc:
   try:
    with (APP/'smart_discovery_errors.log').open('a',encoding='utf8') as fh:
     fh.write('Artwork: '+str(exc)[:180]+'\n')
   except OSError:pass

 def smart_organize(self,manual=False):
  """Move only completed high-confidence folders, atomically and without overwriting."""
  from smart_discovery import scan_downloads, discover_emulators, move_verified
  if not manual and not self.cfg.get('smart_auto_enabled',False):
   return {'moved':[],'emulatorsRegistered':[],'skipped':[],
           'message':'Automatic organizing disabled.'}
  if active_game_process():
   return {'moved':[],'emulatorsRegistered':[],'skipped':[],
           'message':'A game is active. Organization deferred.'}
  downloads=Path(os.environ.get('USERPROFILE',str(Path.home())))/'Downloads'
  moved=[];registered=[];skipped=[];art_targets=[]
  with self.lock:
   for item in scan_downloads(downloads):
    if item['action']!='ready':continue
    try:
     result=move_verified(item,downloads,self.games_root,DEFAULT_EMULATORS)
     moved.append(result)
     self._smart_record_move(result)
     if result['kind']=='emulator':
      entry={'kind':'emulator','action':'ready','emulator':result['emulator'],'exe':result['exe']}
      if self._smart_register_emulator(entry):registered.append(result['name'])
     else:
      art_targets.append(Path(result['path']))
    except (OSError,ValueError) as exc:
     skipped.append({'name':item['filename'],'reason':str(exc)[:180]})
   for item in discover_emulators(DEFAULT_EMULATORS):
    if self._smart_register_emulator(item):registered.append(item['title'])
   if moved:self._cache=None;self._cache_time=0
  for folder in art_targets:
   threading.Thread(target=self._smart_exact_art,args=(folder,),daemon=True,name='smart-art').start()
  return {'moved':moved,'emulatorsRegistered':registered,'skipped':skipped,
          'message':f'Organized {len(moved)} verified folder(s).'}
