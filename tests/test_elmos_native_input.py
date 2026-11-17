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
        pad.left_joystick_float.assert_called_once_with(x_value_float=0.5,y_value_float=0.25)
        pad.right_joystick_float.assert_called_once_with(x_value_float=-0.3,y_value_float=-0.9)
        pad.update.assert_called_once_with()
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
        self.assertEqual(frame['axes'],[.5,-.25,-.4,.8])
        self.assertEqual(frame['triggers'],[0.,1.])

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
