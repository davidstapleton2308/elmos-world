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
    def test_disconnect_is_neutral(self):
        self.assertIsNone(n.frame_from_snapshot(dict(connected=False,mode='mapped SDL',name='Wireless Controller')))
    def test_require_mapped_sony(self):
        self.assertIsNone(n.frame_from_snapshot(dict(connected=True,mode='raw SDL joystick',name='Wireless Controller')))
    def test_clamp_bad_inputs(self):
        self.assertEqual(n.clamp('bad',-1,1),0)
        self.assertEqual(n.clamp(2,0,1),1)

if __name__=='__main__':
    unittest.main()
