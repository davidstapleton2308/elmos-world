"""Read-only input service for the Elmos World interface.
Mapped SDL gamepads are preferred, raw SDL joysticks are supported too.
Never generates virtual devices, elevates games or captures game input.
"""
import os, threading, time, json
from pathlib import Path

class RisingPress:
    """One action per physical press, regardless of poll frequency."""
    def __init__(self): self.was_down = False
    def update(self, pressed):
        fire = bool(pressed) and not self.was_down
        self.was_down = bool(pressed)
        return fire

class ControllerMonitor:
    def __init__(self):
        self.lock=threading.RLock()
        self.state=dict(available=False, connected=False, mode='none', name='', buttons={}, axes=[0,0,0,0], rawButtons=[], rawAxes=[], hats=[], devices=[], error='Starting native controller reader…')
        self.thread=None
        self.return_handler=None
        self.menu_input_handler=None  # foreground-independent native game-menu navigation
        self.navigation_map={'a':0,'b':1}
        self.guide_file=Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'ElmosWorld' / 'controller.json'
        self.guide_index=10
        try:
            cfg=json.loads(self.guide_file.read_text(encoding='utf-8'))
            if type(cfg.get('guide_index')) is int and 0 <= cfg['guide_index'] <= 39:
                self.guide_index=cfg['guide_index']
        except (OSError,ValueError,TypeError): pass
    def set_navigation_map(self, mapping):
        if not isinstance(mapping,dict):raise ValueError("Controller map must be an object")
        result={}
        for key in ("a","b"):
            value=mapping.get(key, self.navigation_map[key])
            if type(value) is not int or not 0<=value<=39:raise ValueError("Invalid gamepad button mapping")
            result[key]=value
        with self.lock:self.navigation_map.update(result)
        return dict(self.navigation_map)

    def set_guide_index(self,index):
        if type(index) is not int or not 0 <= index <= 39:
            raise ValueError('Invalid PS button index')
        with self.lock: self.guide_index=index
        self.guide_file.parent.mkdir(parents=True,exist_ok=True)
        tmp=self.guide_file.with_suffix('.tmp')
        tmp.write_text(json.dumps({'guide_index':index}),encoding='utf-8')
        os.replace(tmp,self.guide_file)
        return {'guideIndex':index}

    def start(self):
        if self.thread:return
        self.thread=threading.Thread(target=self._loop,name='Elmos controller monitor',daemon=True)
        self.thread.start()
    def snapshot(self):
        with self.lock:
            return dict({k:(dict(v) if isinstance(v,dict) else list(v) if isinstance(v,list) else v) for k,v in self.state.items()},guideIndex=self.guide_index)
    def _publish(self,**data):
        with self.lock:self.state.update(data)
    def _loop(self):
        os.environ.setdefault('SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS','1')
        try:
            import pygame
            from pygame._sdl2 import controller
        except Exception as exc:
            self._publish(error='pygame-ce unavailable: '+str(exc)+'; run py -m pip install pygame-ce')
            return
        try:
            pygame.init(); pygame.joystick.init(); controller.init()
        except Exception as exc:
            self._publish(error='SDL initialization failed: '+str(exc));return
        current=None;device_id=None;gamepad=None;ps_press=RisingPress()
        names={'a':'CONTROLLER_BUTTON_A','b':'CONTROLLER_BUTTON_B','x':'CONTROLLER_BUTTON_X','y':'CONTROLLER_BUTTON_Y','up':'CONTROLLER_BUTTON_DPAD_UP','down':'CONTROLLER_BUTTON_DPAD_DOWN','left':'CONTROLLER_BUTTON_DPAD_LEFT','right':'CONTROLLER_BUTTON_DPAD_RIGHT','lb':'CONTROLLER_BUTTON_LEFTSHOULDER','rb':'CONTROLLER_BUTTON_RIGHTSHOULDER','start':'CONTROLLER_BUTTON_START','back':'CONTROLLER_BUTTON_BACK','guide':'CONTROLLER_BUTTON_GUIDE'}
        codes={n:getattr(pygame,c,getattr(controller,c,None)) for n,c in names.items()}
        try:
            while True:
                pygame.event.pump()
                count=pygame.joystick.get_count()
                devices=[]
                for i in range(count):
                    try:devices.append({'index':i,'name':pygame.joystick.Joystick(i).get_name(),'mapped':bool(controller.is_controller(i))})
                    except Exception:pass
                if not count:
                    current=None;device_id=None;gamepad=None;ps_press.update(False)
                    self._publish(available=True,connected=False,mode='none',name='',buttons={},rawButtons=[],rawAxes=[],hats=[],axes=[0,0,0,0],devices=[],error='No joystick detected by SDL. Check Windows joy.cpl or try USB.')
                    time.sleep(.14);continue
                # Prefer the physical PlayStation controller over virtual Xbox devices.
                preferred=next((i for i in range(count) if any(x in pygame.joystick.Joystick(i).get_name().lower() for x in ('wireless controller','dualshock','sony','dualsense'))),None)
                chosen=preferred if preferred is not None else next((i for i in range(count) if controller.is_controller(i)),0)
                if chosen!=device_id or current is None:
                    try:
                        if current:current.quit()
                    except Exception:pass
                    current=pygame.joystick.Joystick(chosen);current.init();device_id=chosen;ps_press.update(False)
                    gamepad=None
                    if controller.is_controller(chosen):
                        try:gamepad=controller.Controller(chosen)
                        except Exception:pass
                raw_buttons=[bool(current.get_button(i)) for i in range(min(current.get_numbuttons(),40))]
                raw_axes=[round(float(current.get_axis(i)),3) for i in range(min(current.get_numaxes(),12))]
                hats=[list(current.get_hat(i)) for i in range(min(current.get_numhats(),4))]
                mapped=bool(controller.is_controller(chosen) and gamepad)
                buttons={};axes=[raw_axes[0] if len(raw_axes)>0 else 0, raw_axes[1] if len(raw_axes)>1 else 0, 0, 0]
                if mapped:
                    try:
                        ctl=gamepad
                        buttons={n:bool(ctl.get_button(c)) if c is not None else False for n,c in codes.items()}
                        # SDL-mapped controller axes: LX, LY, RX, RY. Right-stick input
                        # is exposed read-only to the launcher for page scrolling.
                        # It is NOT remapped or injected into running games.
                        axes=[max(-1,min(1,ctl.get_axis(getattr(pygame,label,index))/32767.0))
                              for label,index in (('CONTROLLER_AXIS_LEFTX',0),('CONTROLLER_AXIS_LEFTY',1),
                                                  ('CONTROLLER_AXIS_RIGHTX',2),('CONTROLLER_AXIS_RIGHTY',3))]
                    except Exception:
                        mapped=False
                if mapped:
                    # SDL may omit Guide even when the raw joystick exposes the PS button.
                    buttons['guide']=buttons.get('guide',False) or (self.guide_index<len(raw_buttons) and raw_buttons[self.guide_index])
                if not mapped:
                    b=lambda n:raw_buttons[n] if n<len(raw_buttons) else False
                    hat=hats[0] if hats else [0,0]
                    buttons={'a':b(self.navigation_map['a']),'b':b(self.navigation_map['b']),'x':b(2),'y':b(3),'lb':b(4),'rb':b(5),'back':b(8),'start':b(9),'guide':b(self.guide_index),'up':hat[1]>0,'down':hat[1]<0,'left':hat[0]<0,'right':hat[0]>0}
                # PS/Guide by itself opens the Elmos menu; no Options chord.
                # Edge-triggered so holding it does not reopen or repeat.
                if ps_press.update(buttons.get('guide',False)) and self.return_handler:
                    try:self.return_handler()
                    except Exception:pass
                if self.menu_input_handler:
                    try:self.menu_input_handler(buttons,axes)
                    except Exception:pass
                self._publish(available=True,connected=True,mode='mapped SDL' if mapped else 'raw SDL joystick',name=current.get_name(),buttons=buttons,axes=[round(float(x),3) for x in axes[:4]],rawButtons=raw_buttons,rawAxes=raw_axes,hats=hats,devices=devices,error='')
                time.sleep(.04)
        except Exception as exc:
            self._publish(error='Controller read error: '+repr(exc),connected=False)

monitor=ControllerMonitor()
