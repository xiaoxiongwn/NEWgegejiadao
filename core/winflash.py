# -*- coding: utf-8 -*-
import ctypes

FLASHW_ALL = 3
FLASHW_TIMERNOFG = 12


class _FLASHWINFO(ctypes.Structure):
    _fields_ = [
        ('cbSize', ctypes.c_uint),
        ('hwnd', ctypes.c_void_p),
        ('dwFlags', ctypes.c_uint),
        ('uCount', ctypes.c_uint),
        ('dwTimeout', ctypes.c_uint),
    ]


def flash_window(hwnd, count=8):
    """让任务栏图标闪烁，提醒用户注意（Windows专用）"""
    try:
        info = _FLASHWINFO()
        info.cbSize = ctypes.sizeof(_FLASHWINFO)
        info.hwnd = hwnd
        info.dwFlags = FLASHW_ALL | FLASHW_TIMERNOFG
        info.uCount = count
        info.dwTimeout = 0
        ctypes.windll.user32.FlashWindowEx(ctypes.byref(info))
    except Exception:
        pass
