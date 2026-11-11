import json, os, sys, secrets, threading, webbrowser, time, mimetypes, traceback, subprocess, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit,parse_qs
from pathlib import Path
from backend import Engine, Path as FilePath, APP, active_game_process
from game_media import ScreenshotLibrary
from controller_input import monitor
from native_game_menu import NativeGameMenu
import update_center
HERE=Path(__file__).parent
engine=Engine()
media=ScreenshotLibrary(APP/'game_screenshots', pause_while_playing=lambda:bool(active_game_process()))
token=secrets.token_urlsafe(28)
_menu_lock=threading.Lock()
_menu_requested=0.0
_menu_last_pressed=0.0
_native_menu=None

def choose_file(kind):
 import tkinter as tk
 from tkinter import filedialog
 root=tk.Tk();root.withdraw();root.attributes('-topmost',True)
 try:
  if kind=='emulator':return filedialog.askopenfilename(title='Select emulator executable',initialdir=str(Path('C:/Gaming/Emulators')),filetypes=[('Windows programs','*.exe')])
  if kind=='game':return filedialog.askopenfilename(title='Select disc image or game file',initialdir=str(Path('C:/Gaming/Games')))
  if kind=='gfn-shortcut':return filedialog.askopenfilename(title='Choose a GeForce NOW game shortcut',filetypes=[('GeForce NOW shortcuts','*.lnk *.url')],initialdir=str(Path.home()/'Desktop'))
  if kind=='folder':return filedialog.askdirectory(title='Choose games folder',initialdir=str(Path('C:/Gaming')))
  return ''
 finally:root.destroy()

def choose_images():
 import tkinter as tk
 from tkinter import filedialog
 root=tk.Tk();root.withdraw();root.attributes('-topmost',True)
 try:
  return list(filedialog.askopenfilenames(title='Import game screenshots (images only)',
      filetypes=[('Image files','*.png *.jpg *.jpeg *.webp')]))
 finally:root.destroy()

class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):
  u=urlsplit(self.path)
  if u.path=='/':
   return self.send_file(HERE/'index.html','text/html; charset=utf-8')
  if u.path=='/app.css':return self.send_file(HERE/'app.css','text/css; charset=utf-8')
  if u.path=='/premium_23.css':return self.send_file(HERE/'premium_23.css','text/css; charset=utf-8')
  if u.path=='/premium_24.css':return self.send_file(HERE/'premium_24.css','text/css; charset=utf-8')
  if u.path=='/premium_25.css':return self.send_file(HERE/'premium_25.css','text/css; charset=utf-8')
  if u.path=='/premium_26.css':return self.send_file(HERE/'premium_26.css','text/css; charset=utf-8')
  if u.path=='/premium_27.css':return self.send_file(HERE/'premium_27.css','text/css; charset=utf-8')
  if u.path=='/premium_28.css':return self.send_file(HERE/'premium_28.css','text/css; charset=utf-8')
  if u.path=='/premium_30.css':return self.send_file(HERE/'premium_30.css','text/css; charset=utf-8')
  if u.path=='/premium_31.css':return self.send_file(HERE/'premium_31.css','text/css; charset=utf-8')
  if u.path=='/app.js':return self.send_file(HERE/'app.js','text/javascript; charset=utf-8')
  if u.path=='/graphite_weave.svg':return self.send_file(HERE/'graphite_weave.svg','image/svg+xml',cache=True)
  if not self.valid():return self.error(403,'Unauthorized local request')
  if u.path=='/api/controller':
   with _menu_lock:
    pending=_menu_requested
   return self.result(dict(monitor.snapshot(),menuRequested=pending))
  if u.path=='/api/health':
   try:return self.result(engine.health_check(parse_qs(u.query).get('id',[None])[0]))
   except Exception as exc:return self.error(400,str(exc))
  if u.path=='/api/update-status':
   try:
    info=update_center.latest()
    return self.result({k:v for k,v in info.items() if not k.startswith('_')})
   except Exception as exc:return self.error(400,str(exc))
  if u.path=='/api/backups':return self.result(engine.backups())
  if u.path=='/api/platforms':return self.result(engine.platform_sources())
  if u.path=='/api/gfn-shortcuts':
   from geforce_library import desktop_candidates
   return self.result({'shortcuts':desktop_candidates()})
  if u.path=='/api/activity':return self.result(engine.activity())
  if u.path=='/api/session-history':
   from backend import session_history
   return self.result(session_history())
  if u.path=='/api/game-session':
   from backend import active_session_status
   return self.result(active_session_status())
  if u.path=='/api/state':return self.result(engine.info(force=parse_qs(u.query).get('refresh',['0'])[0]=='1'))
  if u.path=='/api/metadata':
   from backend import store_metadata
   fields=parse_qs(u.query)
   title=fields.get('name',[''])[0][:120]
   match=fields.get('match',[''])[0][:120]
   return self.result(store_metadata(title,match) if title else {'available':False})
  if u.path=='/api/game-gallery':
   fields=parse_qs(u.query)
   game=engine.find(fields.get('id',[''])[0])
   if not game:return self.error(404,'Game not found')
   view=media.status(game['id'],game['name'],game.get('localMatch',''))
   view['screenshots']=[f'/api/game-shot?id={urllib.parse.quote(game["id"],safe="")}&index={n}&v={view["generation"]}&token={token}'
                        for n in view['indexes']]
   return self.result(view)
  if u.path=='/api/game-shot':
   fields=parse_qs(u.query)
   game=engine.find(fields.get('id',[''])[0])
   if not game:return self.error(404,'Game not found')
   try:n=int(fields.get('index',['-1'])[0])
   except ValueError:return self.error(404,'Screenshot missing')
   if n<0 or n>99:return self.error(404,'Screenshot missing')
   path=media.image(game['id'],game['name'],game.get('localMatch',''),n)
   if not path:return self.error(404,'Screenshot missing')
   return self.send_file(path,mimetypes.guess_type(str(path))[0] or 'image/jpeg',cache=True)
  if u.path=='/api/gallery-batch':
   return self.result(media.batch_status())
  if u.path=='/api/search':
   try:return self.result(engine.search(parse_qs(u.query).get('q',[''])[0]))
   except Exception as exc:return self.error(400,str(exc))
  if u.path=='/api/local-art':
   params=parse_qs(u.query)
   try:
    gid=params.get('id',[''])[0];slot=params.get('slot',['portrait'])[0]
    if slot not in ('portrait','wide','hero','logo','icon') or not engine.find(gid):return self.error(404,'Artwork missing')
    p=engine.local_art_path(gid,slot)
    if not p:return self.error(404,'Artwork missing')
    return self.send_file(p,mimetypes.guess_type(str(p))[0] or 'image/png',cache=True)
   except Exception:return self.error(404,'Artwork missing')
  if u.path=='/api/art':
   params=parse_qs(u.query)
   try:
    ident=int(params.get('id',['0'])[0]);slot=params.get('slot',['portrait'])[0]
    suffix={'portrait':'p','wide':'','hero':'_hero','logo':'_logo','icon':'_icon'}.get(slot)
    if suffix is None or not engine.profile:return self.error(404,'Artwork missing')
    from backend import art_path
    p=art_path(engine.profile,ident,suffix)
    if not p:return self.error(404,'Artwork missing')
    return self.send_file(p,mimetypes.guess_type(str(p))[0] or 'image/png',cache=True)
   except Exception:return self.error(404,'Artwork missing')
  self.error(404,'Not found')
 def do_POST(self):
  if not self.valid():return self.error(403,'Unauthorized local request')
  if int(self.headers.get('Content-Length','0'))>15000:return self.error(413,'Too large')
  try:
   body=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))) or b'{}')
   action=urlsplit(self.path).path
   if action=='/api/update-config':
    out={'repository':update_center.configure(body.get('repository',''))}
   elif action=='/api/update-install':
    if active_game_process():raise RuntimeError('Finish your running game before updating.')
    installer=update_center.prepare()
    if active_game_process():raise RuntimeError('A game started during download. Installation cancelled.')
    engine.make_backup()
    update_center.launch_helper(installer,os.getpid())
    out={'ok':True,'restarting':True}
    # Send the response first, then exit so the detached helper can install.
    threading.Timer(1.4,lambda:os._exit(0)).start()
   elif action=='/api/pick':out={'path':choose_file(body.get('kind'))}
   elif action=='/api/exe':engine.set_exe(body['id'],body['path']);out={'ok':True}
   elif action=='/api/game-title':out=engine.set_custom_title(body['id'],body['title'])
   elif action=='/api/emulator':out={'id':engine.set_emulator(body['name'],body['exe'],body['platform'])}
   elif action=='/api/rom':out={'id':engine.add_rom(body['name'],body['path'],body['emulator'])}
   elif action=='/api/apply':out=engine.apply(body['id'],body.get('matchId'),body.get('matchName'))
   elif action=='/api/sync':out=engine.sync_new()
   elif action=='/api/remove':out=engine.remove(body['id'])
   elif action=='/api/launch':
    mode=body.get('mode','direct')
    if mode not in ('direct','steam'):raise ValueError('Invalid launch mode')
    out=engine.launch_direct(body['id']) if mode=='direct' else engine.launch(body['id'])
   elif action=='/api/refresh-gallery':
    game=engine.find(body.get('id',''))
    if not game:raise ValueError('Game not found')
    queued=media.refresh(game['id'],game['name'],game.get('localMatch',''),force=True)
    out={'queued':queued,'message':'Checking available game media' if queued else 'Game media refresh already running'}
   elif action=='/api/import-game-shots':
    game=engine.find(body.get('id',''))
    if not game:raise ValueError('Game not found')
    out=media.import_images(game['id'],choose_images())
   elif action=='/api/refresh-all-galleries':
    games=[g for g in engine.list_games(force=False) if not g.get('hidden')]
    out=media.batch_refresh(games,force=bool(body.get('force')))
   elif action=='/api/controller-map':out={'buttons':monitor.set_navigation_map(body.get('buttons',{}))}
   elif action=='/api/shield':
    from backend import set_launch_shield
    out=set_launch_shield(bool(body.get('enabled')))
   elif action=='/api/compatibility':out=engine.set_compatibility_mode(body['id'],body['enabled'])
   elif action=='/api/remove-library':out=engine.remove_game_from_library(body['id'])
   elif action=='/api/hidden-delete':out=engine.delete_hidden_selected(body.get('ids',[]))
   elif action=='/api/gfn-import':out=engine.gfn_import(body.get('path',''),body.get('title'))
   elif action=='/api/gfn-rename':out=engine.gfn_rename(body.get('id',''),body.get('title',''))
   elif action=='/api/gfn-remove':out=engine.gfn_remove(body.get('id',''))
   elif action=='/api/gfn-art':out=engine.gfn_match_art(body.get('id',''))
   elif action=='/api/gfn-launch':out=engine.gfn_launch(body.get('id',''))
   elif action=='/api/uninstall-preview':out=engine.uninstall_preview(body['id'])
   elif action=='/api/uninstall-confirm':out=engine.uninstall_confirm(body['id'],body.get('token',''),body.get('confirmation',''))
   elif action=='/api/launch-profile':
    from backend import save_launch_profile
    gameid=body.get('id','')
    if not engine.find(gameid):raise ValueError('Game not found')
    out=save_launch_profile(gameid,body.get('readySeconds'))
   elif action=='/api/handoff':
    from backend import handoff_active_game, active_session_status, find_game_window
    # Low-impact games skip aggressive foreground stealing on launch. The
    # launcher minimizes when a stable game window appears; existing PS controls
    # and ordinary game launches are unchanged.
    status=active_session_status()
    setting=engine.local.get('games',{}).get(status.get('gameId'),{})
    low_impact=bool(setting.get('lowImpactLaunch',False))
    focused=False if low_impact and status.get('windowReady') else handoff_active_game()
    status=active_session_status()
    process=active_game_process()
    resumable=bool(process and find_game_window(process.pid,include_minimized=True))
    out={'focused':focused,'running':status['running'],'windowReady':status['windowReady'],'resumableWindow':resumable,'lowImpact':low_impact}
   elif action=='/api/close-game':
    from backend import close_active_game
    out=close_active_game()
   elif action=='/api/library-match':
    out=engine.set_local_match(body['id'],body['matchId'],body['matchName'])
    game=engine.find(body['id'])
    if game:
     out['galleryQueued']=media.refresh(game['id'],game['name'],game.get('localMatch',''),force=True)
   elif action=='/api/collection':out=engine.update_collection(body.get('action',''),body.get('name',''),body.get('collectionId',''),body.get('gameId',''))
   elif action=='/api/backup':out=engine.make_backup()
   elif action=='/api/restore':out=engine.restore_backup(body.get('name',''))
   elif action=='/api/favorite':out=engine.set_favorite(body['id'],body['favorite'])
   elif action=='/api/hide':out=engine.set_hidden(body['id'],body['hidden'])
   elif action=='/api/forget-rom':out=engine.forget_rom(body['id'])
   elif action=='/api/preferences':out=engine.set_preferences(body)
   elif action=='/api/launch-mode':out=engine.set_launch_mode(body['id'],body['mode'])
   elif action=='/api/guide-index':out=monitor.set_guide_index(body.get('index'))
   elif action=='/api/xenia-sdl':out=engine.xenia_controller(body['emulator'])
   elif action=='/api/open-platform':
    name=str(body.get('name',''))
    available={p['name']:p for p in engine.platform_sources() if p.get('installed') and p.get('launcherPath')}
    if name not in available:raise ValueError('Platform launcher not detected')
    target=Path(available[name]['launcherPath'])
    if not target.is_file() or target.suffix.lower()!='.exe':raise ValueError('Launcher is missing')
    if sys.platform!='win32':out={'ok':True,'dryRun':True,'name':name}
    else:
     subprocess.Popen([str(target)],cwd=str(target.parent),close_fds=True)
     out={'ok':True,'name':name}
   elif action=='/api/settings':out=engine.settings(body)
   elif action=='/api/note':engine.note(body['id'],body['note']);out={'ok':True}
   elif action=='/api/repair':
    from backend import repair_legacy,vdf
    if vdf.steam_running() and sys.platform=='win32':raise RuntimeError('Exit Steam completely first.')
    out={'repaired':repair_legacy(engine.profile)}
   else:return self.error(404,'Not found')
   return self.result(out)
  except Exception as exc:return self.error(400,str(exc))
 def valid(self):return self.headers.get('X-SteamMatch-Token')==token or (urlsplit(self.path).path in ('/api/art','/api/local-art','/api/game-shot') and parse_qs(urlsplit(self.path).query).get('token',[''])[0]==token)
 def send_file(self,path,content_type,cache=False):
  try:raw=path.read_bytes()
  except OSError:return self.error(404,'Not found')
  self.send_response(200);self.send_header('Content-Type',content_type);self.send_header('Content-Length',str(len(raw)))
  self.send_header('Cache-Control','private, max-age=3600' if cache else 'no-store')
  self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(raw)
 def result(self,data):
  raw=json.dumps(data).encode('utf8');self.send_response(200);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(raw)
 def error(self,code,message):
  raw=json.dumps({'error':message}).encode('utf8');self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)

def open_app_window(url):
 if sys.platform=='win32':
  for app in (Path(os.environ.get('PROGRAMFILES(X86)',r'C:\Program Files (x86)'))/'Microsoft/Edge/Application/msedge.exe',
              Path(os.environ.get('PROGRAMFILES',r'C:\Program Files'))/'Microsoft/Edge/Application/msedge.exe',
              Path(os.environ.get('PROGRAMFILES',r'C:\Program Files'))/'Google/Chrome/Application/chrome.exe'):
   if app.is_file():
    try:
     subprocess.Popen([str(app),'--kiosk','--app='+url],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
     return
    except OSError:pass
 webbrowser.open(url)

def restore_elmos_window():
 # A game can exit while the startup shield is still topmost (Windows may
 # reject fullscreen foreground changes). Never strand the restored launcher
 # in that state; always release the *existing* window shield on recovery.
 try:
  from backend import set_launch_shield
  set_launch_shield(False)
 except Exception:pass
 try:
  import webview
  if not webview.windows:return
  w=webview.windows[0]
  w.restore();w.show()
  if sys.platform=='win32':
   try:
    import ctypes
    handle=getattr(w.native,'Handle',None)
    if handle:ctypes.windll.user32.SetForegroundWindow(int(handle.ToInt64()) if hasattr(handle,'ToInt64') else int(handle))
   except Exception:pass
 except Exception:pass

def restore_elmos_after_game_exit():
 """Wake the native window AND its JavaScript state after game process exit."""
 if _native_menu:_native_menu.hide()
 try:
  from backend import session_event
  session_event('native_exit_wakeup','Restoring library after tracked process exit')
 except Exception:pass
 restore_elmos_window()
 try:
  import webview
  if webview.windows:
   webview.windows[0].run_js('window.elmoOnNativeGameExit?.()')
 except Exception:pass

def resume_game_from_native_menu():
 """Dismiss the small native panel and refocus the SAME running process."""
 from backend import active_game_process, focus_launched_game, set_launch_shield, session_event
 set_launch_shield(False)
 p=active_game_process()
 if p:
  result=focus_launched_game(p.pid,timeout=0.75)
  session_event('native_menu_resume','focused' if result else 'Windows refused focus; use Alt+Tab')


def return_home_from_native_menu():
 """Leave the game running, but bring back the original fullscreen library."""
 from backend import set_launch_shield, session_event
 set_launch_shield(False)
 session_event('native_menu_home','Game remains open')
 restore_elmos_window()
 try:
  import webview
  if webview.windows:
   webview.windows[0].run_js('window.elmoNativeReturnHome?.()')
 except Exception:pass


def quit_game_from_native_menu():
 """Close only the game process Elmos started; then restore the library."""
 from backend import close_active_game, set_launch_shield, session_event
 set_launch_shield(False)
 result=close_active_game()
 session_event('native_menu_quit',str(result.get('message',''))[:160])
 if result.get('closed'):restore_elmos_after_game_exit()
 else:
  # A failed quit is not a reason to overwrite a still-running game session.
  restore_elmos_window()
  try:
   import webview
   if webview.windows:webview.windows[0].run_js('window.elmoNativeReturnHome?.()')
  except Exception:pass


def show_game_menu():
 """Use a controller-operated *compact* panel above the game, not the library.

 The previous version restored the entire fullscreen WebView and then waited
 for JavaScript focus to work. That made the menu cover the game and caused
 dropped controller input. The separate panel has its own native SDL routing.
 """
 global _menu_requested,_menu_last_pressed
 from backend import active_session_status, session_event
 if not active_session_status().get('running'):return
 with _menu_lock:
  now=time.monotonic()
  if now-_menu_last_pressed<0.75:return
  _menu_last_pressed=now
 menu=_native_menu
 if menu is not None and menu.visible:
  menu.select('resume');return
 if menu is not None and menu.show(active_session_status().get('gameName')):
  session_event('native_overlay_opened','Compact controller-first game controls')
  return
 # Fallback only when Tk cannot create the panel (e.g. browser-only mode).
 with _menu_lock:_menu_requested=now
 session_event('native_overlay_fallback','Using original browser menu')
 restore_elmos_window()
 try:
  import webview
  if webview.windows:webview.windows[0].run_js('window.elmoReceiveNativeMenu?.()')
 except Exception:pass


def start_hotkey_monitor():
 """Windows global Ctrl+Alt+G to restore the native Elmos World window.
 No keyboard hooks, admin rights or interception of game input.
 """
 if sys.platform!='win32':return
 try:
  import ctypes
  from ctypes import wintypes
  user32=ctypes.windll.user32
  MOD_ALT=0x0001;MOD_CONTROL=0x0002;MOD_NOREPEAT=0x4000
  if not user32.RegisterHotKey(None,0xE101,MOD_ALT|MOD_CONTROL|MOD_NOREPEAT,0x47):
   print('Ctrl+Alt+G hotkey unavailable; use Alt+Tab instead.');return
  print('Game menu hotkey: Ctrl+Alt+G')
  msg=wintypes.MSG()
  while user32.GetMessageW(ctypes.byref(msg),None,0,0)>0:
   if msg.message==0x0312 and msg.wParam==0xE101:
    show_game_menu()
  user32.UnregisterHotKey(None,0xE101)
 except Exception as exc:print('Hotkey disabled:',exc)

def start_input_services():
 # Plain Escape belongs to the game. No global keyboard interception.
 threading.Thread(target=start_hotkey_monitor,daemon=True,name='Elmos menu hotkey').start()

class WindowBridge:
 def toggle_fullscreen(self):
  try:
   import webview
   if webview.windows:webview.windows[0].toggle_fullscreen();return True
  except Exception:pass
  return False
 def restore(self):
  try:
   import webview
   if webview.windows:
    webview.windows[0].restore();webview.windows[0].show()
   return True
  except Exception:return False
 def minimize(self):
  try:
   import webview
   if webview.windows:webview.windows[0].minimize()
   return True
  except Exception:return False

if __name__=='__main__':
 if sys.platform!='win32':print('The launcher is designed for Windows; demo browser mode will still start.')
 server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
 url=f'http://127.0.0.1:{server.server_address[1]}/#token={token}'
 print('ELMOS WORLD — LOCAL ONLY\n'+url+'\nClose this window to stop the launcher.\n')
 global_native_menu=NativeGameMenu(resume_game_from_native_menu,return_home_from_native_menu,quit_game_from_native_menu)
 _native_menu=global_native_menu
 global_native_menu.start()  # prewarm compact panel; first PS press has no Tk startup delay
 monitor.return_handler=show_game_menu
 monitor.menu_input_handler=global_native_menu.gamepad
 monitor.start()
 try:
  import webview
  threading.Thread(target=server.serve_forever,daemon=True).start()
  webview.create_window('Elmos World · Tinkle_0nMe_Elmo',url,width=1470,height=930,min_size=(980,660),background_color='#0a0e10',js_api=WindowBridge(),fullscreen=True)
  engine.on_session_exit=restore_elmos_after_game_exit
  webview.start(start_input_services)
  server.shutdown()
 except ImportError:
  threading.Timer(0.65,lambda:open_app_window(url)).start()
  try:server.serve_forever()
  except KeyboardInterrupt:pass
