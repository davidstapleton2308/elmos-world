"""Read process state without signalling it."""
import os


def pid_alive(pid: int) -> bool:
    if type(pid) is not int or not 0 < pid < 2**32:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel.CloseHandle.restype = wintypes.BOOL
        synchronize = 0x00100000
        wait_timeout = 0x102
        access_denied = 5
        handle = kernel.OpenProcess(synchronize, False, pid)
        if not handle:
            return ctypes.get_last_error() == access_denied
        try:
            return kernel.WaitForSingleObject(handle, 0) == wait_timeout
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except (OSError, ValueError):
        return False
