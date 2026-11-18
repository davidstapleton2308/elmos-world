"""Offline Elmos-owned Xbox 360 mapping and lifecycle regression tests."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import elmos_native_input as n

class NativeInputTests(unittest.TestCase):
    def test_sony_button_axes_and_trigger_mapping(self):
        frame=n.frame_from_snapshot(dict(connected=True,mode='mapped SDL',name='Wireless Controller',
            buttons={'a':True,'lb':True,'up':True},axes=[0.5,-0.25,-0.3,0.9],triggers=[0.2,0.8]))
        self.assertEqual(frame['buttons'], ['XUSB_GAMEPAD_A','XUSB_GAMEPAD_LEFT_SHOULDER','XUSB_GAMEPAD_DPAD_UP'])
        self.assertEqual(frame['triggers'],[0.2,0.8])
        vg=MagicMock()
        pad=MagicMock()
        n.apply_frame(pad,vg,frame)
        pad.reset.assert_called_once_with()
        pad.left_joystick_float.assert_called_once_with(x_value_float=frame['axes'][0],y_value_float=-frame['axes'][1])
        pad.right_joystick_float.assert_called_once_with(x_value_float=frame['axes'][2],y_value_float=-frame['axes'][3])
        pad.update.assert_called_once_with()
    def test_windows_ps4_controller_name_bridges_mapped_sdl(self):
        frame=n.frame_from_snapshot(dict(
            connected=True, mode='mapped SDL', name='PS4 Controller',
            buttons={'a':True, 'b':True, 'guide':True},
            axes=[.25,-.5,-.75,.5],triggers=[0.,1.]))
        self.assertIsNotNone(frame)
        self.assertEqual(frame['name'], 'PS4 Controller')
        self.assertIn('XUSB_GAMEPAD_A', frame['buttons'])
        self.assertIn('XUSB_GAMEPAD_B', frame['buttons'])
        self.assertIn('XUSB_GAMEPAD_GUIDE', frame['buttons'])
        self.assertEqual(frame['axes'], n.neutralize_stick_drift([.25,-.5,-.75,.5]))
        self.assertEqual(frame['triggers'], [0.,1.])

    def test_ps4_like_virtual_device_names_are_rejected(self):
        for name in ('PS4 Controller ViGEm', 'PS4 Controller VIIPER', 'Xbox PS4 Controller'):
            self.assertIsNone(n.frame_from_snapshot(dict(
                connected=True,mode='mapped SDL',name=name,
                buttons={'a':True},axes=[0,0,0,0],triggers=[0,0])))

    def test_no_virtual_feedback_loop(self):
        self.assertIsNone(n.frame_from_snapshot(dict(connected=True,mode='mapped SDL',name='Xbox 360 Controller',axes=[0]*4)))
    def test_stick_clicks_map_to_xbox_thumb_buttons(self):
        frame=n.frame_from_snapshot(dict(connected=True,mode='mapped SDL',name='Wireless Controller',
            buttons={'l3':True,'r3':True},axes=[0,0,0,0]))
        self.assertIn('XUSB_GAMEPAD_LEFT_THUMB',frame['buttons'])
        self.assertIn('XUSB_GAMEPAD_RIGHT_THUMB',frame['buttons'])
    def test_retry_driver_setup_is_requested_without_second_worker(self):
        from unittest.mock import MagicMock
        engine=n.NativeInput(MagicMock())
        engine._thread=MagicMock()
        engine._thread.is_alive.return_value=True
        engine.start()
        self.assertTrue(engine._retry_setup.is_set())
        engine._thread.start.assert_not_called()
    def test_optional_rumble_failure_does_not_prevent_virtual_xbox(self):
        import os
        import subprocess
        from unittest.mock import MagicMock
        import types
        source=MagicMock()
        engine=n.NativeInput(source)
        calls=[0]
        def snapshot():
            calls[0]+=1
            if calls[0]>=2:
                engine._stop.set()
            return {'connected':False,'mode':'none','name':'','error':''}
        source.snapshot.side_effect=snapshot
        pad=MagicMock()
        pad.register_notification.side_effect=RuntimeError('rumble unsupported')
        vg=types.SimpleNamespace(VX360Gamepad=lambda:pad)
        with (patch.object(n.os, 'name', 'nt'),
              patch('elmos_input_driver.is_installed', return_value=True),
              patch.dict(sys.modules, {'vgamepad':vg}),
              patch.object(subprocess, 'run',
                           return_value=MagicMock(stdout='INFO: No tasks are running'))):
            engine._run()
        self.assertGreaterEqual(pad.update.call_count, 1)
        pad.unregister_notification.assert_not_called()
        self.assertFalse(engine.status()['virtualConnected'])
        self.assertNotIn('Xbox 360 bridge error', engine.status()['message'])

    def test_raw_ds4_live_bridge_emits_expected_xinput_report(self):
        import types
        from unittest.mock import MagicMock
        import subprocess
        physical=MagicMock()
        engine=n.NativeInput(physical)
        raw_buttons=[False]*14
        raw_buttons[1]=True  # physical Cross -> virtual Xbox A
        raw_buttons[2]=True  # physical Circle -> virtual Xbox B
        raw_buttons[12]=True # physical PS -> virtual Xbox Guide
        physical.snapshot.side_effect=[
            dict(connected=True,mode='raw SDL joystick',name='Wireless Controller',
                 rawButtons=raw_buttons,rawAxes=[.4,-.1,.6,.25,-1,1],
                 hats=[[1,0]],error=''),
            dict(connected=False,mode='none',name=''),
        ]
        pad=MagicMock()
        vg=types.SimpleNamespace(
            VX360Gamepad=lambda:pad,
            XUSB_BUTTON=MagicMock())
        def read_once():
            try:
                return next(raw_state)
            except StopIteration:
                engine._stop.set()
                return dict(connected=False,mode='none')
        raw_state=iter(physical.snapshot.side_effect)
        physical.snapshot.side_effect=read_once
        with (patch.object(n.os,'name','nt'),
              patch('elmos_input_driver.is_installed',return_value=True),
              patch.dict(sys.modules,{'vgamepad':vg}),
              patch.object(subprocess,'run',
                           return_value=MagicMock(stdout='INFO: No tasks are running'))):
            engine._run()
        # These prove the real bridge path applies the raw DS4 frame, not just
        # that a virtual device was created and then left idle.
        self.assertGreaterEqual(pad.left_joystick_float.call_count,1)
        pad.left_joystick_float.assert_any_call(
            x_value_float=n.neutralize_stick_drift([.4,-.1,.6,.25])[0],y_value_float=-n.neutralize_stick_drift([.4,-.1,.6,.25])[1])
        pad.right_joystick_float.assert_any_call(
            x_value_float=n.neutralize_stick_drift([.4,-.1,.6,.25])[2],y_value_float=-n.neutralize_stick_drift([.4,-.1,.6,.25])[3])
        pad.left_trigger_float.assert_any_call(value_float=0.)
        pad.right_trigger_float.assert_any_call(value_float=1.)
        self.assertGreaterEqual(pad.press_button.call_count,3)

    def test_runtime_release_never_bundles_ds4windows(self):
        root=Path(__file__).resolve().parents[1]
        server=(root/'app'/'server.py').read_text(encoding='utf-8')
        spec=(root/'build'/'ElmosWorld.spec').read_text(encoding='utf-8')
        workflow=(root/'.github/workflows/build-windows-release.yml').read_text(encoding='utf-8')
        self.assertIn('native_input.start()',server)
        self.assertIn('native_input.stop(',server)
        self.assertNotIn('ds4_engine.start()',server)
        self.assertNotIn('ds4windows-3-3-3.zip',spec)
        self.assertNotIn('ds4windows-3-3-3.zip',workflow)
        self.assertFalse((root/'app'/'elmos_ds4_engine.py').exists())

    def test_disconnect_is_neutral(self):
        self.assertIsNone(n.frame_from_snapshot(dict(connected=False,mode='mapped SDL',name='Wireless Controller')))
    def test_raw_sony_directinput_maps_cross_circle_square_triangle_and_sticks(self):
        buttons=[False]*14
        for i in (0,1,4,9,10,12): buttons[i]=True
        frame=n.frame_from_snapshot(dict(
            connected=True,mode='raw SDL joystick',name='Wireless Controller',
            rawButtons=buttons,rawAxes=[.5,-.25,-.4,.8,-1.,1.],hats=[[0,1]]))
        self.assertIsNotNone(frame)
        for code in ('XUSB_GAMEPAD_A','XUSB_GAMEPAD_X','XUSB_GAMEPAD_LEFT_SHOULDER',
                     'XUSB_GAMEPAD_START','XUSB_GAMEPAD_LEFT_THUMB','XUSB_GAMEPAD_GUIDE','XUSB_GAMEPAD_DPAD_UP'):
            self.assertIn(code,frame['buttons'])
        self.assertNotIn('XUSB_GAMEPAD_B',frame['buttons'])
        self.assertNotIn('XUSB_GAMEPAD_RIGHT_THUMB',frame['buttons'])
        self.assertEqual(frame['axes'],n.neutralize_stick_drift([.5,-.25,-.4,.8]))
        self.assertEqual(frame['triggers'],[0.,1.])

    def test_idle_stick_drift_is_neutralized(self):
        self.assertEqual(n.neutralize_stick_drift([.10,.06,-.10,.02]),[0.,0.,0.,0.])
        self.assertEqual(n.neutralize_stick_drift([0.,0.,0.,0.]),[0.,0.,0.,0.])
        self.assertEqual(n.neutralize_stick_drift([1.,0.,0.,-1.]),[1.,0.,0.,-1.])

    def test_raw_ds4_digital_trigger_fallback(self):
        buttons=[False]*14
        buttons[6]=True
        frame=n.frame_from_snapshot(dict(
            connected=True,mode='raw SDL joystick',name='DualShock 4',
            rawButtons=buttons,rawAxes=[0,0,0,0],hats=[]))
        self.assertEqual(frame['triggers'],[1.,0.])

    def test_raw_ds4_not_matched_with_fewer_usable_axes_or_buttons(self):
        self.assertIsNone(n.frame_from_snapshot(dict(
            connected=True,mode='raw SDL joystick',name='Wireless Controller',
            rawButtons=[True,False],rawAxes=[0,0,0,0])))

    def test_virtual_viiper_and_xbox_are_never_used_as_input(self):
        for name in ('VIIPER Controller','Xbox 360 Controller','ViGEm Virtual Controller'):
            self.assertIsNone(n.frame_from_snapshot(dict(
                connected=True,mode='raw SDL joystick',name=name,
                rawButtons=[True]*14,rawAxes=[0,0,0,0])))
    def test_clamp_bad_inputs(self):
        self.assertEqual(n.clamp('bad',-1,1),0)
        self.assertEqual(n.clamp(2,0,1),1)

if __name__=='__main__':
    unittest.main()
