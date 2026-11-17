"""Windows desktop lifetime regressions: no invisible instance after closing."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
import launcher_entry


class DesktopLifetimeTests(unittest.TestCase):
    def test_double_launch_restores_main_window_instead_of_popup(self):
        with patch.object(launcher_entry,'single_instance',return_value=False), \
             patch.object(launcher_entry,'restore_existing_window',return_value=True) as restore, \
             patch.object(launcher_entry,'release_single_instance') as release, \
             patch.object(launcher_entry,'_notify') as notify:
            self.assertEqual(launcher_entry.start(),0)
        restore.assert_called_once_with()
        release.assert_called_once_with()
        notify.assert_not_called()

    def test_ghost_instance_help_only_targets_exact_elmos_exe(self):
        with patch.object(launcher_entry,'single_instance',return_value=False), \
             patch.object(launcher_entry,'restore_existing_window',return_value=False), \
             patch.object(launcher_entry,'release_single_instance'), \
             patch.object(launcher_entry,'_notify') as notify:
            self.assertEqual(launcher_entry.start(),0)
        text=notify.call_args.args[0]
        self.assertIn('ElmosWorld.exe',text)
        self.assertIn('Task Manager',text)
        self.assertNotIn('taskkill /f /im',text.lower())

    def test_exact_window_match_and_safe_focus_only(self):
        source=(ROOT/'app'/'launcher_entry.py').read_text(encoding='utf-8')
        self.assertIn("title = 'Elmos World · Tinkle_0nMe_Elmo'",source)
        self.assertIn('if buffer.value == title:',source)
        self.assertIn('user32.ShowWindow(hwnd, 9)',source)
        self.assertIn('user32.SetForegroundWindow(hwnd)',source)
        self.assertNotIn('TerminateProcess',source)

    def test_closed_window_forces_real_process_shutdown(self):
        source=(ROOT/'app'/'server.py').read_text(encoding='utf-8')
        self.assertIn('window.events.closed += on_window_closed',source)
        self.assertIn("threading.Timer(3.0,lambda:os._exit(0))",source)
        self.assertIn('server.shutdown()',source)
        self.assertIn('server.server_close()',source)
        self.assertIn('monitor.stop()',source)
        self.assertIn('global_native_menu.stop()',source)
        self.assertIn('os._exit(0)',source)
        # Game processes continue independently; never terminate all games.
        self.assertNotIn('taskkill /im',source.lower())

    def test_background_services_obey_close(self):
        joystick=(ROOT/'app'/'controller_input.py').read_text(encoding='utf-8')
        menu=(ROOT/'app'/'native_game_menu.py').read_text(encoding='utf-8')
        self.assertIn('self._stop=threading.Event()',joystick)
        self.assertIn('while not self._stop.is_set()',joystick)
        self.assertIn('def stop(self):',joystick)
        self.assertIn("self._queue.put(('quit',None))",menu)
        self.assertIn('self._tk.destroy()',menu)

    def test_quit_control_available_in_hub_and_settings(self):
        html=(ROOT/'app'/'index.html').read_text(encoding='utf-8')
        script=(ROOT/'app'/'app.js').read_text(encoding='utf-8')
        css=(ROOT/'app'/'premium_33.css').read_text(encoding='utf-8')
        self.assertIn('id="quitElmos"',html)
        self.assertIn('id="quitElmosSettings"',html)
        self.assertIn("('quitElmos').onclick=quitElmosWorld",script)
        self.assertIn("('quitElmosSettings').onclick=quitElmosWorld",script)
        self.assertIn("api('/api/quit',{})",script)
        self.assertIn('.rail-bottom .quit-elmos',css)

    def test_quit_is_authenticated_and_releases_launcher_without_killing_game(self):
        source=(ROOT/'app'/'server.py').read_text(encoding='utf-8')
        handler=source[source.index("   if action=='/api/quit':"):
                       source.index("   elif action=='/api/update-config':")]
        self.assertIn("'quitting':True",handler)
        self.assertIn("threading.Timer(0.75,lambda:os._exit(0)).start()",handler)
        self.assertNotIn('close_active_game',handler)
        self.assertNotIn('TerminateProcess',handler)
        self.assertLess(source.index("if not self.valid():return self.error(403"),source.index("if action=='/api/quit':"))

    def test_installer_waits_for_prior_instance_before_reinstall(self):
        script=(ROOT/'app'/'apply_update.ps1').read_text(encoding='utf-8')
        self.assertIn('Get-Process -Id $ParentId',script)
        self.assertIn('Set-UpdateState \'waiting\'',script)
        self.assertIn("'-AppExe'",(ROOT/'app'/'update_center.py').read_text(encoding='utf-8'))


if __name__=='__main__':
    unittest.main()
