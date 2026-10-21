"""Mouse e teclado via SendInput (Win32)."""

import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000
MOUSEEVENTF_VIRTUALDESK = 0x4000
MOUSEEVENTF_ABSOLUTE = 0x8000

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN, SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 76, 77, 78, 79

ULONG_PTR = ctypes.c_size_t


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT
user32.GetCursorPos.argtypes = (ctypes.POINTER(wintypes.POINT),)
user32.MapVirtualKeyW.argtypes = (wintypes.UINT, wintypes.UINT)
user32.MapVirtualKeyW.restype = wintypes.UINT
user32.VkKeyScanW.argtypes = (wintypes.WCHAR,)
user32.VkKeyScanW.restype = ctypes.c_short

VK = {
    "backspace": 0x08, "tab": 0x09, "enter": 0x0D, "shift": 0x10, "ctrl": 0x11, "alt": 0x12,
    "pause": 0x13, "capslock": 0x14, "esc": 0x1B, "space": 0x20, "pageup": 0x21, "pagedown": 0x22,
    "end": 0x23, "home": 0x24, "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "printscreen": 0x2C, "insert": 0x2D, "delete": 0x2E, "win": 0x5B, "menu": 0x5D,
    "volumemute": 0xAD, "volumedown": 0xAE, "volumeup": 0xAF,
    "medianext": 0xB0, "mediaprev": 0xB1, "mediastop": 0xB2, "mediaplay": 0xB3,
    **{f"f{i}": 0x6F + i for i in range(1, 25)},
}

# Teclas que precisam da flag "extended" para não virarem as do teclado numérico.
EXTENDED = {
    0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2C, 0x2D, 0x2E, 0x5B, 0x5D,
    0xAD, 0xAE, 0xAF, 0xB0, 0xB1, 0xB2, 0xB3,
}

BUTTONS = {
    "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
    "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
    "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
}


def _send(inputs):
    if not inputs:
        return
    for start in range(0, len(inputs), 200):
        chunk = inputs[start:start + 200]
        arr = (INPUT * len(chunk))(*chunk)
        user32.SendInput(len(chunk), arr, ctypes.sizeof(INPUT))


def _mouse(flags, dx=0, dy=0, data=0):
    inp = INPUT(type=INPUT_MOUSE)
    inp.mi = MOUSEINPUT(dx, dy, data & 0xFFFFFFFF, flags, 0, 0)
    return inp


def _key(vk=0, up=False, scan=0, flags=0):
    if vk in EXTENDED:
        flags |= KEYEVENTF_EXTENDEDKEY
    if up:
        flags |= KEYEVENTF_KEYUP
    if vk and not scan:
        scan = user32.MapVirtualKeyW(vk, 0)
    inp = INPUT(type=INPUT_KEYBOARD)
    inp.ki = KEYBDINPUT(vk, scan, flags, 0, 0)
    return inp


def virtual_screen():
    gm = user32.GetSystemMetrics
    return gm(SM_XVIRTUALSCREEN), gm(SM_YVIRTUALSCREEN), gm(SM_CXVIRTUALSCREEN), gm(SM_CYVIRTUALSCREEN)


def cursor_pos():
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def move_to(x, y):
    left, top, width, height = virtual_screen()
    x = min(max(int(x), left), left + width - 1)
    y = min(max(int(y), top), top + height - 1)
    nx = round((x - left) * 65535 / max(width - 1, 1))
    ny = round((y - top) * 65535 / max(height - 1, 1))
    _send([_mouse(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK, nx, ny)])


def move_by(dx, dy):
    x, y = cursor_pos()
    move_to(x + dx, y + dy)


def button(name, action):
    down, up = BUTTONS.get(name, BUTTONS["left"])
    if action == "down":
        _send([_mouse(down)])
    elif action == "up":
        _send([_mouse(up)])
    elif action == "double":
        _send([_mouse(down), _mouse(up), _mouse(down), _mouse(up)])
    else:
        _send([_mouse(down), _mouse(up)])


def scroll(dy=0, dx=0):
    inputs = []
    if dy:
        inputs.append(_mouse(MOUSEEVENTF_WHEEL, data=int(dy)))
    if dx:
        inputs.append(_mouse(MOUSEEVENTF_HWHEEL, data=int(dx)))
    _send(inputs)


def _vk_for(name: str) -> tuple[int, list[int]]:
    """Converte o nome de uma tecla em (vk, modificadores extras necessários)."""
    name = name.lower()
    if name in VK:
        return VK[name], []
    if len(name) == 1:
        res = user32.VkKeyScanW(name)
        if res == -1:
            return 0, []
        vk, shift_state = res & 0xFF, (res >> 8) & 0xFF
        extra = []
        if shift_state & 1:
            extra.append(VK["shift"])
        return vk, extra
    return 0, []


def press(keys: list[str], repeat: int = 1):
    """Pressiona uma combinação, ex.: ["ctrl", "shift", "esc"]."""
    vks = []
    for name in keys:
        vk, extra = _vk_for(name)
        for e in extra:
            if e not in vks:
                vks.append(e)
        if vk and vk not in vks:
            vks.append(vk)
    if not vks:
        return
    seq = []
    for _ in range(max(1, min(int(repeat), 500))):
        seq += [_key(vk) for vk in vks]
        seq += [_key(vk, up=True) for vk in reversed(vks)]
    _send(seq)


def key_state(name: str, down: bool):
    vk, _ = _vk_for(name)
    if vk:
        _send([_key(vk, up=not down)])


def type_text(text: str):
    seq = []
    for ch in text:
        if ch == "\n":
            seq += [_key(VK["enter"]), _key(VK["enter"], up=True)]
            continue
        if ch == "\r":
            continue
        if ch == "\t":
            seq += [_key(VK["tab"]), _key(VK["tab"], up=True)]
            continue
        units = ch.encode("utf-16-le")
        for i in range(0, len(units), 2):
            code = int.from_bytes(units[i:i + 2], "little")
            seq.append(_key(scan=code, flags=KEYEVENTF_UNICODE))
            seq.append(_key(scan=code, flags=KEYEVENTF_UNICODE, up=True))
    _send(seq)
