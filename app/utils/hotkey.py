"""全局热键模块，基于 Win32 RegisterHotKey API."""

import ctypes
from ctypes import wintypes


# ── Win32 结构体 ────────────────────────────────────────

class MSG(ctypes.Structure):
    """Windows MSG 结构体."""
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt_x", wintypes.LONG),
        ("pt_y", wintypes.LONG),
    ]


# ── Win32 常量 ──────────────────────────────────────────

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008

WM_HOTKEY = 0x0312

_MODIFIER_MAP = {
    "ctrl": MOD_CONTROL,
    "shift": MOD_SHIFT,
    "alt": MOD_ALT,
    "win": MOD_WIN,
}

_VK_MAP = {
    **{f"f{i}": 0x6F + i for i in range(1, 13)},  # F1-F12: VK_F1=0x70..VK_F12=0x7B
    **{chr(ord("a") + i): ord("A") + i for i in range(26)},  # A-Z
    **{str(i): ord("0") + i for i in range(10)},  # 0-9
    # 导航键
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
    # 编辑键
    "insert": 0x2D,
    "delete": 0x2E,
}


# ── Win32 API ───────────────────────────────────────────

_user32 = ctypes.windll.user32

_RegisterHotKey = _user32.RegisterHotKey
_RegisterHotKey.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_uint)
_RegisterHotKey.restype = ctypes.c_bool

_UnregisterHotKey = _user32.UnregisterHotKey
_UnregisterHotKey.argtypes = (ctypes.c_void_p, ctypes.c_int)
_UnregisterHotKey.restype = ctypes.c_bool

_GetLastError = ctypes.windll.kernel32.GetLastError
_GetLastError.restype = ctypes.c_uint


def parse_hotkey(hotkey_str: str) -> tuple[int, int] | None:
    """解析热键字符串，返回 (modifiers, vk) 或 None.

    支持格式: "Ctrl+Shift+F11", "Alt+A", "Ctrl+Win+S" 等.
    修饰符: Ctrl, Shift, Alt, Win（不区分大小写）.
    按键: F1-F12, A-Z, 0-9.
    """
    parts = [p.strip() for p in hotkey_str.split("+")]
    if len(parts) < 2:
        return None

    modifiers = 0
    vk = None

    for part in parts:
        key = part.lower()
        if key in _MODIFIER_MAP:
            modifiers |= _MODIFIER_MAP[key]
        elif key in _VK_MAP:
            if vk is not None:
                return None
            vk = _VK_MAP[key]
        else:
            return None

    if vk is None:
        return None

    return (modifiers, vk)


def register_hotkey(hwnd: int, modifiers: int, vk: int, hotkey_id: int = 1) -> bool:
    """注册全局热键. 返回 True 表示成功.

    如果组合键已被占用（如上次进程残留），会先尝试注销再重新注册.
    返回的 hwnd 需要传给 unregister_hotkey 用于注销.
    """
    # 先尝试注销同一 HWND+ID 的残留注册
    _UnregisterHotKey(ctypes.c_void_p(hwnd), hotkey_id)
    success = _RegisterHotKey(ctypes.c_void_p(hwnd), hotkey_id, modifiers, vk)
    if not success:
        err = _GetLastError()
        print(f"[Hotkey] RegisterHotKey 失败: HWND=0x{hwnd:X}, "
              f"mod=0x{modifiers:X}, vk=0x{vk:X}, 错误码={err}")
    else:
        print(f"[Hotkey] 热键已注册: mod=0x{modifiers:X}, vk=0x{vk:X}")
    return success


def unregister_hotkey(hwnd: int, hotkey_id: int = 1) -> None:
    """注销全局热键. hwnd 必须与注册时使用的相同."""
    _UnregisterHotKey(ctypes.c_void_p(hwnd), hotkey_id)
