"""Compact controller-first in-game control panel for Elmos World.

This is deliberately NOT a fullscreen launch-cover window. A small, topmost
panel appears above the game, and the existing main webview stays minimized.
Controller input comes directly from the SDL monitor, independently of WebView
focus. On true exclusive fullscreen Windows may prevent ordinary overlays.
"""
from __future__ import annotations

import queue
import threading
import time


class MenuInput:
    """Pure edge/held controller navigation so it can be regression-tested."""
    def __init__(self):
        self.previous = {'a':False, 'b':False}
        self.last_direction = 0
        self.next_repeat_at = 0.0

    def reset(self):
        self.previous = {'a':False, 'b':False}
        self.last_direction = 0
        self.next_repeat_at = 0.0

    def feed(self, buttons, axes=(0.0, 0.0), now=None):
        if now is None: now=time.monotonic()
        buttons=buttons or {}
        try: vertical=float((axes or [0,0])[1])
        except (TypeError, ValueError, IndexError): vertical=0.0
        direction=(1 if buttons.get('down') or vertical>.62 else
                   -1 if buttons.get('up') or vertical<-.62 else 0)
        events=[]
        if direction and (direction!=self.last_direction or now>=self.next_repeat_at):
            events.append(('move', direction))
            self.next_repeat_at=now+(0.31 if direction!=self.last_direction else 0.19)
        self.last_direction=direction
        for key, action in [('a','choose'),('b','resume')]:
            down=bool(buttons.get(key))
            if down and not self.previous[key]: events.append((action,None))
            self.previous[key]=down
        return events


class NativeGameMenu:
    """Owns Tk on its own thread; cross-thread requests go through a queue."""
    ACTIONS=('resume','home','quit')

    def __init__(self, on_resume, on_home, on_quit):
        self.callbacks={'resume':on_resume,'home':on_home,'quit':on_quit}
        self._queue=queue.Queue()
        self._guard=threading.RLock()
        self._visible=False
        self._started=False
        self._ready=threading.Event()
        self._hidden_ack=threading.Event()
        self._hidden_ack.set()
        self._failed=False
        self._index=0
        self._input=MenuInput()
        self._tk=None
        self._buttons=[]

    @property
    def visible(self):
        with self._guard:return self._visible

    def start(self):
        with self._guard:
            if self._started:return not self._failed
            self._started=True
            threading.Thread(target=self._run,daemon=True,name='Elmos native control panel').start()
        # Don't stall the game if Tk is not installed or couldn't initialize.
        self._ready.wait(timeout=1.8)
        return self._ready.is_set() and not self._failed

    def show(self, title):
        if not self.start():return False
        with self._guard:
            if self._visible:return True
            self._visible=True
            self._index=0
            self._input.reset()
        self._hidden_ack.clear()
        self._queue.put(('show',str(title or 'Game session')[:105]))
        return True

    def hide(self):
        with self._guard:self._visible=False;self._input.reset()
        if self._started:self._queue.put(('hide',None))

    def gamepad(self, buttons, axes):
        """Called on the native SDL thread; never calls Tk from that thread."""
        with self._guard:
            if not self._visible:return False
            events=self._input.feed(buttons,axes)
        for event in events:self._queue.put(event)
        return True

    def select(self,action):
        if action not in self.ACTIONS:return
        self.hide()
        # Never run a game-close wait or a Windows foreground retry on Tk's UI loop.
        threading.Thread(target=self._invoke,args=(action,),daemon=True,name='Elmos game action').start()

    def _invoke(self,action):
        self._hidden_ack.wait(timeout=0.45)  # let Tk withdraw before game-focus request
        try:self.callbacks[action]()
        except Exception as exc:print('Native game menu action failed:',action,exc)

    def _run(self):
        try:
            import tkinter as tk
            root=tk.Tk()
            self._tk=root
            root.title('Elmos World — Game Controls')
            root.withdraw()
            root.configure(bg='#0b1013')
            root.overrideredirect(True)
            root.attributes('-topmost',True)
            try:root.attributes('-toolwindow',True)
            except Exception:pass
            root.resizable(False,False)
            root.bind('<Up>',lambda e:self._queue.put(('move',-1)))
            root.bind('<Down>',lambda e:self._queue.put(('move',1)))
            root.bind('<Return>',lambda e:self._queue.put(('choose',None)))
            root.bind('<Escape>',lambda e:self._queue.put(('resume',None)))
            border=tk.Frame(root,bg='#7d6652',padx=1,pady=1)
            border.pack(fill='both',expand=True)
            card=tk.Frame(border,bg='#11181a',padx=28,pady=20)
            card.pack(fill='both',expand=True)
            tk.Label(card,text='E L M O S   W O R L D   /   C O N T R O L   C E N T E R',
                     font=('Segoe UI',9,'bold'),fg='#d9a66f',bg='#11181a').pack(anchor='w')
            tk.Label(card,text='GAME SESSION',font=('Segoe UI',11,'bold'),fg='#9aada7',bg='#11181a').pack(anchor='w',pady=(20,0))
            self._game_title=tk.Label(card,text='Game',font=('Segoe UI',24,'bold'),
                                      wraplength=510,justify='left',anchor='w',fg='#f3f5f1',bg='#11181a')
            self._game_title.pack(fill='x',anchor='w',pady=(2,14))
            tk.Label(card,text='Use the D-pad to choose • Cross to select • Circle to resume',
                     font=('Segoe UI',10),fg='#a0b2ae',bg='#11181a').pack(anchor='w',pady=(0,16))
            for index,(name,text) in enumerate((('resume','▶   RESUME GAME'),('home','⌂   RETURN TO ELMOS WORLD'),('quit','⏻   QUIT GAME'))):
                item=tk.Frame(card,bg='#263336',padx=1,pady=1)
                item.pack(fill='x',pady=5)
                label=tk.Label(item,text=text,font=('Segoe UI',13,'bold'),anchor='w',padx=22,pady=13,
                               fg='#f4f4f2',bg='#1a2628',cursor='hand2')
                label.pack(fill='both',expand=True)
                label.bind('<Button-1>',lambda e,action=name:self.select(action))
                item.bind('<Button-1>',lambda e,action=name:self.select(action))
                self._buttons.append((item,label))
            tk.Label(card,text='A compact game menu. Some exclusive-fullscreen games may hide overlays.',
                     font=('Segoe UI',9),fg='#81918d',bg='#11181a').pack(anchor='w',pady=(17,0))
            self._paint()
            self._ready.set()
            root.after(35,self._drain)
            root.mainloop()
        except Exception as exc:
            print('Elmos native game overlay unavailable:',exc)
            with self._guard:self._failed=True;self._visible=False
            self._ready.set()

    def _paint(self):
        for i,(frame,label) in enumerate(self._buttons):
            if i==self._index:
                frame.configure(bg='#d4a16d')
                label.configure(bg='#27322f',fg='#fff7ed')
            else:
                frame.configure(bg='#354044')
                label.configure(bg='#172023',fg='#d1ded9')

    def _position(self):
        root=self._tk
        width,height=610,485
        x=(root.winfo_screenwidth()-width)//2
        y=(root.winfo_screenheight()-height)//2
        # Where possible center over the actual game's monitor/window.
        try:
            import ctypes
            from ctypes import wintypes
            from backend import active_game_process, find_game_window
            p=active_game_process()
            hwnd=find_game_window(p.pid,include_minimized=True) if p else 0
            if hwnd:
                rect=wintypes.RECT()
                if ctypes.windll.user32.GetWindowRect(hwnd,ctypes.byref(rect)):
                    x=rect.left+((rect.right-rect.left)-width)//2
                    y=rect.top+((rect.bottom-rect.top)-height)//2
        except Exception:pass
        root.geometry(f'{width}x{height}+{max(0,x)}+{max(0,y)}')

    def _drain(self):
        try:
            while True:
                event,value=self._queue.get_nowait()
                if event=='show':
                    self._game_title.configure(text=value)
                    self._index=0;self._paint();self._position()
                    self._tk.deiconify();self._tk.lift()
                    self._tk.attributes('-topmost',True)
                elif event=='hide':self._tk.withdraw();self._hidden_ack.set()
                elif not self.visible:continue
                elif event=='move':
                    self._index=max(0,min(len(self.ACTIONS)-1,self._index+int(value)))
                    self._paint()
                elif event=='choose':self.select(self.ACTIONS[self._index])
                elif event=='resume':self.select('resume')
        except queue.Empty:pass
        except Exception as exc:print('Elmos control panel event:',exc)
        self._tk.after(35,self._drain)
