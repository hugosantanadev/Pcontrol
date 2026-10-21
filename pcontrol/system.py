"""Energia, volume, área de transferência, janelas, processos e informações do PC."""

import ctypes
import ipaddress
import json
import os
import shutil
import socket
import subprocess
import time
from ctypes import wintypes

import psutil

from . import inputs

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi")

CREATE_NO_WINDOW = 0x08000000

TAILSCALE_NETS = [ipaddress.ip_network("100.64.0.0/10"), ipaddress.ip_network("fd7a:115c:a1e0::/48")]
LAN_NETS = [
    ipaddress.ip_network(n)
    for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16", "fe80::/10", "fc00::/7")
]
LOOPBACK_NETS = [ipaddress.ip_network("127.0.0.0/8"), ipaddress.ip_network("::1/128")]


def enable_dpi_awareness():
    """Coordenadas em pixels físicos, iguais às da captura."""
    try:
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.WinDLL("shcore").SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        user32.SetProcessDPIAware()


# --- rede ----------------------------------------------------------------

def classify_ip(ip: str) -> str | None:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return None
    if getattr(addr, "ipv4_mapped", None):
        addr = addr.ipv4_mapped
    if any(addr in n for n in LOOPBACK_NETS):
        return "local"
    if any(addr in n for n in TAILSCALE_NETS):
        return "tailscale"
    if any(addr in n for n in LAN_NETS):
        return "lan"
    return None


def lan_ip() -> str | None:
    """IP do PC na rede local (o da interface com rota padrão)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))
            ip = s.getsockname()[0]
            return ip if classify_ip(ip) == "lan" else None
    except OSError:
        return None


def tailscale_ip() -> str | None:
    for addrs in psutil.net_if_addrs().values():
        for a in addrs:
            if a.family == socket.AF_INET and classify_ip(a.address) == "tailscale":
                return a.address
    return None


def tailscale_dns_name() -> str | None:
    exe = shutil.which("tailscale") or r"C:\Program Files\Tailscale\tailscale.exe"
    if not os.path.exists(exe):
        return None
    try:
        out = subprocess.run(
            [exe, "status", "--json"], capture_output=True, timeout=5, creationflags=CREATE_NO_WINDOW
        )
        name = json.loads(out.stdout).get("Self", {}).get("DNSName", "")
        return name.rstrip(".") or None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


# --- energia -------------------------------------------------------------

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


def keep_awake(on: bool):
    """Vale para a thread que chama: sempre chamar pela thread principal."""
    flags = ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if on else 0)
    kernel32.SetThreadExecutionState(ctypes.c_uint(flags))


def _run(args):
    subprocess.Popen(args, creationflags=CREATE_NO_WINDOW)


def power(action: str, delay: int = 0):
    delay = max(0, min(int(delay), 24 * 3600))
    if action == "lock":
        user32.LockWorkStation()
    elif action == "screen_off":
        user32.PostMessageW(0xFFFF, 0x0112, 0xF170, 2)  # HWND_BROADCAST, WM_SYSCOMMAND, SC_MONITORPOWER
    elif action == "sleep":
        _run([
            "powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command",
            "Add-Type -AssemblyName System.Windows.Forms;"
            "[System.Windows.Forms.Application]::SetSuspendState('Suspend', $false, $false)",
        ])
    elif action == "shutdown":
        _run(["shutdown", "/s", "/t", str(delay)])
    elif action == "restart":
        _run(["shutdown", "/r", "/t", str(delay)])
    elif action == "cancel":
        _run(["shutdown", "/a"])
    else:
        raise ValueError("ação desconhecida")


# --- volume --------------------------------------------------------------

def _endpoint():
    from pycaw.pycaw import AudioUtilities

    return AudioUtilities.GetSpeakers().EndpointVolume


def get_volume():
    try:
        ev = _endpoint()
        return {"level": round(ev.GetMasterVolumeLevelScalar() * 100), "muted": bool(ev.GetMute())}
    except Exception:
        return {"level": None, "muted": None}


def audio_playing(process_name: str) -> bool:
    """Se o programa (ex.: brave.exe) está tocando som agora."""
    from pycaw.pycaw import AudioUtilities

    for session in AudioUtilities.GetAllSessions():
        try:
            if session.Process and session.Process.name().lower() == process_name.lower() and session.State == 1:
                return True
        except Exception:
            continue
    return False


def set_volume(level=None, muted=None):
    ev = _endpoint()
    if level is not None:
        ev.SetMasterVolumeLevelScalar(max(0.0, min(1.0, float(level) / 100)), None)
    if muted is not None:
        ev.SetMute(1 if muted else 0, None)
    return get_volume()


# --- área de transferência ----------------------------------------------

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

user32.OpenClipboard.argtypes = (wintypes.HWND,)
user32.GetClipboardData.argtypes = (wintypes.UINT,)
user32.GetClipboardData.restype = wintypes.HANDLE
user32.SetClipboardData.argtypes = (wintypes.UINT, wintypes.HANDLE)
user32.SetClipboardData.restype = wintypes.HANDLE
kernel32.GlobalAlloc.argtypes = (wintypes.UINT, ctypes.c_size_t)
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = (wintypes.HGLOBAL,)
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = (wintypes.HGLOBAL,)


def _open_clipboard():
    for _ in range(10):
        if user32.OpenClipboard(None):
            return
        time.sleep(0.05)
    raise OSError("área de transferência ocupada")


def get_clipboard() -> str:
    _open_clipboard()
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return ""
        ptr = kernel32.GlobalLock(handle)
        try:
            return ctypes.wstring_at(ptr)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def set_clipboard(text: str):
    data = text.encode("utf-16-le") + b"\0\0"
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
    ptr = kernel32.GlobalLock(handle)
    ctypes.memmove(ptr, data, len(data))
    kernel32.GlobalUnlock(handle)
    _open_clipboard()
    try:
        user32.EmptyClipboard()
        user32.SetClipboardData(CF_UNICODETEXT, handle)
    finally:
        user32.CloseClipboard()


# --- janelas -------------------------------------------------------------

GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
GW_OWNER = 4
DWMWA_CLOAKED = 14
SW_RESTORE, SW_MINIMIZE = 9, 6
WM_CLOSE = 0x0010

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.GetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int)
user32.GetWindow.restype = wintypes.HWND
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.AttachThreadInput.argtypes = (wintypes.DWORD, wintypes.DWORD, wintypes.BOOL)


def _is_app_window(hwnd) -> bool:
    if not user32.IsWindowVisible(hwnd) or user32.GetWindow(hwnd, GW_OWNER):
        return False
    if user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
        return False
    cloaked = wintypes.DWORD()
    dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
    return not cloaked.value


def windows():
    found = []

    def callback(hwnd, _):
        if _is_app_window(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                found.append((hwnd, buf.value))
        return True

    user32.EnumWindows(WNDENUMPROC(callback), 0)
    foreground = user32.GetForegroundWindow()
    result = []
    for hwnd, title in found:
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        try:
            proc = psutil.Process(pid.value).name()
        except psutil.Error:
            proc = ""
        if proc.lower() == "textinputhost.exe" or (proc.lower() == "explorer.exe" and title == "Program Manager"):
            continue
        result.append({
            "hwnd": int(hwnd),
            "title": title,
            "process": proc,
            "pid": pid.value,
            "minimized": bool(user32.IsIconic(hwnd)),
            "active": hwnd == foreground,
        })
    return result


def foreground_window() -> int:
    return user32.GetForegroundWindow() or 0


def _bring_to_front(hwnd):
    """O Windows só deixa trazer janela para a frente quem já está na frente; então
    "emprestamos" a fila de entrada da janela atual enquanto trocamos o foco."""
    foreground = user32.GetForegroundWindow()
    if foreground == hwnd.value:
        return
    ours = kernel32.GetCurrentThreadId()
    theirs = user32.GetWindowThreadProcessId(foreground, None) if foreground else 0
    attached = bool(theirs and theirs != ours and user32.AttachThreadInput(ours, theirs, True))
    try:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(ours, theirs, False)
    if user32.GetForegroundWindow() != hwnd.value:
        # Plano B: uma tecla sem função conta como "última entrada" e libera a troca.
        # (Não usar Alt: a janela recebe o Alt solto, abre o menu e engole a próxima tecla.)
        inputs.key_state("f24", True)
        inputs.key_state("f24", False)
        user32.SetForegroundWindow(hwnd)


def window_action(hwnd: int, action: str):
    hwnd = wintypes.HWND(hwnd)
    if not user32.IsWindow(hwnd):
        raise ValueError("essa janela não existe mais")
    if action == "focus":
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        _bring_to_front(hwnd)
    elif action == "minimize":
        user32.ShowWindow(hwnd, SW_MINIMIZE)
    elif action == "close":
        user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
    else:
        raise ValueError("ação desconhecida")


# --- processos e estatísticas -------------------------------------------

_procs: dict[int, psutil.Process] = {}


def processes():
    """Processos agrupados por nome (o Chrome vira uma linha só)."""
    cpus = psutil.cpu_count() or 1
    seen = set()
    groups: dict[str, dict] = {}
    for proc in psutil.process_iter(["pid", "name", "memory_info"]):
        pid = proc.info["pid"]
        if pid in (0, 4) or not proc.info["name"]:
            continue
        seen.add(pid)
        tracked = _procs.setdefault(pid, proc)
        try:
            cpu = tracked.cpu_percent(None) / cpus
        except psutil.Error:
            cpu = 0.0
        mem = proc.info["memory_info"].rss if proc.info["memory_info"] else 0
        name = proc.info["name"]
        g = groups.setdefault(name.lower(), {"name": name, "count": 0, "memory": 0, "cpu": 0.0, "pids": []})
        g["count"] += 1
        g["memory"] += mem
        g["cpu"] += cpu
        g["pids"].append(pid)
    for pid in list(_procs):
        if pid not in seen:
            del _procs[pid]
    result = sorted(groups.values(), key=lambda g: g["memory"], reverse=True)
    for g in result:
        g["cpu"] = round(g["cpu"], 1)
    return result


def kill(pids: list[int]):
    killed, denied = 0, 0
    for pid in pids:
        try:
            psutil.Process(int(pid)).kill()
            killed += 1
        except psutil.NoSuchProcess:
            pass
        except psutil.Error:
            denied += 1
    return {"killed": killed, "denied": denied}


def stats():
    mem = psutil.virtual_memory()
    disks = []
    for part in psutil.disk_partitions(all=False):
        if "cdrom" in part.opts or not part.fstype:
            continue
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except OSError:
            continue
        disks.append({"name": part.mountpoint.rstrip("\\"), "total": usage.total, "used": usage.used, "percent": usage.percent})
    battery = psutil.sensors_battery()
    return {
        "host": socket.gethostname(),
        "cpu": psutil.cpu_percent(None),
        "memory": {"total": mem.total, "used": mem.total - mem.available, "percent": mem.percent},
        "disks": disks,
        "uptime": int(time.time() - psutil.boot_time()),
        "battery": {"percent": round(battery.percent), "plugged": bool(battery.power_plugged)} if battery else None,
    }


# --- lixeira --------------------------------------------------------------

class SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("wFunc", wintypes.UINT),
        ("pFrom", wintypes.LPCWSTR),
        ("pTo", wintypes.LPCWSTR),
        ("fFlags", ctypes.c_ushort),
        ("fAnyOperationsAborted", wintypes.BOOL),
        ("hNameMappings", ctypes.c_void_p),
        ("lpszProgressTitle", wintypes.LPCWSTR),
    ]


def recycle(path: str):
    """Manda para a Lixeira (dá para recuperar)."""
    op = SHFILEOPSTRUCTW()
    op.wFunc = 3  # FO_DELETE
    op.pFrom = os.path.abspath(path) + "\0"
    op.fFlags = 0x0040 | 0x0010 | 0x0004 | 0x0400  # ALLOWUNDO | NOCONFIRMATION | SILENT | NOERRORUI
    result = shell32.SHFileOperationW(ctypes.byref(op))
    if result != 0 or op.fAnyOperationsAborted:
        raise OSError(f"não foi possível mover para a Lixeira (código {result})")
