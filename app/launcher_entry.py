"""Elmos World desktop entrypoint for the standalone Windows release.

Keeps the existing session/game engine unchanged.  Adds a stable single-instance
mutex and local crash logs for a console-free desktop executable.
"""
from __future__ import annotations

import ctypes
import os
from pathlib import Path
import runpy
import sys
import traceback
from datetime import datetime

APP_TITLE = 'Elmos World'
_MUTEX_NAME = r'Local\ElmosWorldDesktopApp'
_mutex_handle = None


def log_path():
    base = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'ElmosWorld' / 'logs'
    base.mkdir(parents=True, exist_ok=True)
    return base / 'launcher.log'


def single_instance():
    """Keep only one copy of the desktop shell running (no admin required)."""
    global _mutex_handle
    if os.name != 'nt':
        return True
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel.CreateMutexW(None, False, _MUTEX_NAME)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    _mutex_handle = handle
    return ctypes.get_last_error() != 183  # ERROR_ALREADY_EXISTS



def restore_existing_window():
    """An explicit second launch should bring the existing desktop shell forward.

    Only target Elmos's exact window title. Never terminate another process and
    never delete a guessed PID/lock file.
    """
    if os.name != 'nt':
        return False
    from ctypes import wintypes
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    title = 'Elmos World · Tinkle_0nMe_Elmo'
    matches = []
    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = (enum_proc, wintypes.LPARAM)
    user32.EnumWindows.restype = wintypes.BOOL
    user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = (wintypes.HWND, ctypes.c_wchar_p, ctypes.c_int)
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
    user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.IsWindow.argtypes = (wintypes.HWND,)
    user32.IsWindow.restype = wintypes.BOOL

    @enum_proc
    def found(hwnd, _):
        length = user32.GetWindowTextLengthW(hwnd)
        if length < 5 or length > 250:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, len(buffer))
        if buffer.value == title:
            matches.append(hwnd)
            return False
        return True

    user32.EnumWindows(found, 0)
    if not matches or not user32.IsWindow(matches[0]):
        return False
    hwnd = matches[0]
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.SetForegroundWindow(hwnd)
    return True


def release_single_instance():
    """Close only the handle owned by this process; Windows owns mutex cleanup."""
    global _mutex_handle
    if _mutex_handle and os.name == 'nt':
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
        kernel.CloseHandle.restype = ctypes.c_int
        kernel.CloseHandle(_mutex_handle)
        _mutex_handle = None


def _notify(text):
    if os.name == 'nt':
        ctypes.windll.user32.MessageBoxW(None, str(text), APP_TITLE, 0x40)
    else:
        print(text)


def self_test():
    """Offline packaging check for a Windows release without opening the UI."""
    import importlib
    base = Path(__file__).resolve().parent
    for filename in ('index.html', 'app.js', 'app.css', 'premium_31.css', 'graphite_weave.svg'):
        if not (base / filename).is_file():
            raise RuntimeError('Bundled application resource missing: ' + filename)
    for module in ('backend', 'server', 'update_center', 'webview', 'pygame', 'tkinter'):
        importlib.import_module(module)
    return True


def start():
    if '--apply-update' in sys.argv:
        import update_center
        try:
            idx = sys.argv.index('--apply-update')
            return update_center.apply_update(sys.argv[idx+1], sys.argv[idx+2])
        except (IndexError, ValueError):
            return 2
    if '--self-test' in sys.argv:
        try:
            self_test()
            return 0
        except BaseException:
            with log_path().open('a', encoding='utf-8') as stream:
                traceback.print_exc(file=stream)
            return 2
    if not single_instance():
        if not restore_existing_window():
            _notify('Elmos World is still running in the background, but its window could not be found.\n\n'
                    'To recover, open Task Manager > Details, find ElmosWorld.exe, '
                    'and End task for that exact process. Then open Elmos World again.\n\n'
                    'Your games and settings will not be deleted.')
        release_single_instance()
        return 0

    path = log_path()
    # Windows GUI applications have no usable stdout/stderr by default.
    # Keep a local diagnostic log so startup failures can be reported.
    with path.open('a', encoding='utf-8', buffering=1) as stream:
        stream.write('\n=== Elmos World 3.1.1 start ' + datetime.now().isoformat(timespec='seconds') + ' ===\n')
        previous_out, previous_err = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = stream, stream
        try:
            runpy.run_module('server', run_name='__main__')
            return 0
        except BaseException:
            traceback.print_exc(file=stream)
            _notify('Elmos World could not start. A diagnostic log was saved to:\n' + str(path))
            return 1
        finally:
            sys.stdout, sys.stderr = previous_out, previous_err
            release_single_instance()


if __name__ == '__main__':
    sys.exit(start())
