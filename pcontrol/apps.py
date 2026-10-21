"""Lista de apps do PC (menu Iniciar, Steam, favoritos) e extração de ícones."""

import ctypes
import hashlib
import io
import json
import os
import re
import subprocess
import threading
import winreg
from concurrent.futures import ThreadPoolExecutor
from ctypes import wintypes
from pathlib import Path

from PIL import Image

CREATE_NO_WINDOW = 0x08000000

# Atalhos do menu Iniciar que não são apps de verdade.
JUNK = re.compile(
    r"uninstall|desinstal|remover |readme|leia-me|leiame|license|licen[çc]a|help|ajuda|manual|"
    r"documenta|release notes|website|site da web|changelog|what's new|novidades",
    re.I,
)

# AppIDs da Steam que são ferramentas, não jogos.
STEAM_TOOLS = {"228980", "1070560", "1391110", "1493710", "1628350", "2180100"}


# --- menu Iniciar ---------------------------------------------------------

_START_APPS_PS = r"""
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$items = $null
try { $items = Get-StartApps | ForEach-Object { [pscustomobject]@{ name = $_.Name; id = $_.AppID } } } catch {}
if (-not $items) {
  $items = (New-Object -ComObject Shell.Application).NameSpace('shell:::{4234d49b-0245-4df3-b780-3893943456e1}').Items() |
    ForEach-Object { [pscustomobject]@{ name = $_.Name; id = $_.Path } }
}
@($items) | ConvertTo-Json -Compress
"""


def start_apps():
    out = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", _START_APPS_PS],
        capture_output=True,
        timeout=60,
        creationflags=CREATE_NO_WINDOW,
    )
    try:
        items = json.loads(out.stdout.decode("utf-8", "replace") or "[]")
    except ValueError:
        return []
    if isinstance(items, dict):
        items = [items]
    apps, seen = [], set()
    for item in items:
        name, app_id = (item.get("name") or "").strip(), item.get("id") or ""
        if not name or not app_id or JUNK.search(name):
            continue
        if app_id.lower().startswith(("http:", "https:", "steam:")) or app_id.lower().endswith((".url", ".chm", ".txt", ".pdf", ".htm", ".html")):
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        apps.append({"name": name, "id": app_id})
    apps.sort(key=lambda a: a["name"].lower())
    return apps


# --- Steam ----------------------------------------------------------------

def steam_path() -> Path | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
            path = Path(winreg.QueryValueEx(key, "SteamPath")[0])
            return path if path.exists() else None
    except OSError:
        return None


def _vdf_values(text: str, key: str):
    return re.findall(r'"%s"\s+"((?:[^"\\]|\\.)*)"' % re.escape(key), text, re.I)


def steam_games():
    root = steam_path()
    if not root:
        return []
    libraries = [root]
    vdf = root / "steamapps" / "libraryfolders.vdf"
    if vdf.exists():
        for p in _vdf_values(vdf.read_text("utf-8", "replace"), "path"):
            lib = Path(p.replace("\\\\", "\\"))
            if lib not in libraries:
                libraries.append(lib)
    games = {}
    for lib in libraries:
        apps_dir = lib / "steamapps"
        if not apps_dir.exists():
            continue
        for manifest in apps_dir.glob("appmanifest_*.acf"):
            try:
                text = manifest.read_text("utf-8", "replace")
            except OSError:
                continue
            appid = (_vdf_values(text, "appid") or [""])[0]
            name = (_vdf_values(text, "name") or [""])[0]
            if appid and name and appid not in STEAM_TOOLS and "redistributable" not in name.lower():
                games[appid] = {"appid": appid, "name": name}
    return sorted(games.values(), key=lambda g: g["name"].lower())


def steam_cover(appid: str) -> Path | None:
    """Capa vertical já baixada pela Steam (appcache/librarycache)."""
    root = steam_path()
    if not root or not appid.isdigit():
        return None
    cache = root / "appcache" / "librarycache"
    for pattern in (f"{appid}/**/library_600x900.jpg", f"{appid}/**/library_capsule.jpg", f"{appid}_library_600x900.jpg"):
        for found in cache.glob(pattern):
            return found
    return None


# --- ícones ---------------------------------------------------------------

shell32 = ctypes.WinDLL("shell32")
user32 = ctypes.WinDLL("user32")
gdi32 = ctypes.WinDLL("gdi32")
ole32 = ctypes.WinDLL("ole32")


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

    def __init__(self, text):
        import uuid

        u = uuid.UUID(text)
        super().__init__(u.time_low, u.time_mid, u.time_hi_version, (ctypes.c_ubyte * 8)(*u.bytes[8:]))


class SHFILEINFOW(ctypes.Structure):
    _fields_ = [
        ("hIcon", wintypes.HICON),
        ("iIcon", ctypes.c_int),
        ("dwAttributes", wintypes.DWORD),
        ("szDisplayName", wintypes.WCHAR * 260),
        ("szTypeName", wintypes.WCHAR * 80),
    ]


class ICONINFO(ctypes.Structure):
    _fields_ = [
        ("fIcon", wintypes.BOOL),
        ("xHotspot", wintypes.DWORD),
        ("yHotspot", wintypes.DWORD),
        ("hbmMask", wintypes.HBITMAP),
        ("hbmColor", wintypes.HBITMAP),
    ]


class BITMAP(ctypes.Structure):
    _fields_ = [
        ("bmType", wintypes.LONG),
        ("bmWidth", wintypes.LONG),
        ("bmHeight", wintypes.LONG),
        ("bmWidthBytes", wintypes.LONG),
        ("bmPlanes", wintypes.WORD),
        ("bmBitsPixel", wintypes.WORD),
        ("bmBits", ctypes.c_void_p),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


shell32.SHParseDisplayName.argtypes = (wintypes.LPCWSTR, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p), wintypes.ULONG, ctypes.c_void_p)
shell32.SHGetFileInfoW.argtypes = (ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(SHFILEINFOW), wintypes.UINT, wintypes.UINT)
shell32.SHGetFileInfoW.restype = ctypes.c_size_t
shell32.SHGetImageList.argtypes = (ctypes.c_int, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))
ole32.CoTaskMemFree.argtypes = (ctypes.c_void_p,)
user32.GetIconInfo.argtypes = (wintypes.HICON, ctypes.POINTER(ICONINFO))
user32.DestroyIcon.argtypes = (wintypes.HICON,)
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = (wintypes.HWND, wintypes.HDC)
gdi32.GetObjectW.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p)
gdi32.GetDIBits.argtypes = (wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT, ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT)
gdi32.DeleteObject.argtypes = (wintypes.HANDLE,)

IID_IImageList = GUID("46EB5926-582E-4017-9FDF-E8998DAA0950")
SHGFI_SYSICONINDEX, SHGFI_PIDL = 0x4000, 0x8
SHIL_EXTRALARGE, SHIL_JUMBO = 2, 4
_GetIcon = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.POINTER(wintypes.HICON))

# Ícones usam COM: tudo numa thread própria, com COM inicializado.
icon_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="icones", initializer=lambda: ole32.CoInitialize(None))
_image_lists: dict[int, ctypes.c_void_p] = {}
_cache_lock = threading.Lock()


def _image_list(kind):
    if kind not in _image_lists:
        ptr = ctypes.c_void_p()
        if shell32.SHGetImageList(kind, ctypes.byref(IID_IImageList), ctypes.byref(ptr)) != 0:
            return None
        _image_lists[kind] = ptr
    return _image_lists[kind]


def _bitmap_bits(hbm, w, h):
    bmi = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    # BITMAPINFO = header + 1 cor; espaço extra evita estouro em bitmaps monocromáticos.
    buf_bmi = ctypes.create_string_buffer(ctypes.sizeof(bmi) + 16)
    ctypes.memmove(buf_bmi, ctypes.byref(bmi), ctypes.sizeof(bmi))
    pixels = ctypes.create_string_buffer(w * h * 4)
    hdc = user32.GetDC(None)
    gdi32.GetDIBits(hdc, hbm, 0, h, pixels, buf_bmi, 0)
    user32.ReleaseDC(None, hdc)
    return pixels.raw


def _hicon_to_image(hicon) -> Image.Image | None:
    info = ICONINFO()
    if not user32.GetIconInfo(hicon, ctypes.byref(info)):
        return None
    try:
        if not info.hbmColor:
            return None
        bm = BITMAP()
        gdi32.GetObjectW(info.hbmColor, ctypes.sizeof(bm), ctypes.byref(bm))
        w, h = bm.bmWidth, bm.bmHeight
        img = Image.frombytes("RGBA", (w, h), _bitmap_bits(info.hbmColor, w, h), "raw", "BGRA")
        if img.getchannel("A").getextrema()[1] == 0:
            # Ícone antigo sem canal alfa: a transparência vem da máscara.
            mask = Image.frombytes("RGBA", (w, h), _bitmap_bits(info.hbmMask, w, h), "raw", "BGRA")
            img.putalpha(mask.getchannel("R").point(lambda v: 0 if v else 255))
        return img
    finally:
        if info.hbmColor:
            gdi32.DeleteObject(info.hbmColor)
        if info.hbmMask:
            gdi32.DeleteObject(info.hbmMask)


def _icon_from_list(kind, index):
    ilist = _image_list(kind)
    if not ilist:
        return None
    vtable = ctypes.cast(ilist, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    hicon = wintypes.HICON()
    if _GetIcon(vtable[10])(ilist, index, 1, ctypes.byref(hicon)) != 0 or not hicon:
        return None
    try:
        return _hicon_to_image(hicon)
    finally:
        user32.DestroyIcon(hicon)


def _render_icon(parse_name: str) -> bytes | None:
    pidl = ctypes.c_void_p()
    if shell32.SHParseDisplayName(parse_name, None, ctypes.byref(pidl), 0, None) != 0:
        return None
    try:
        sfi = SHFILEINFOW()
        if not shell32.SHGetFileInfoW(pidl, 0, ctypes.byref(sfi), ctypes.sizeof(sfi), SHGFI_PIDL | SHGFI_SYSICONINDEX):
            return None
    finally:
        ole32.CoTaskMemFree(pidl)
    img = _icon_from_list(SHIL_JUMBO, sfi.iIcon)
    bbox = img.getchannel("A").getbbox() if img else None
    if not bbox or (bbox[2] <= 64 and bbox[3] <= 64):
        # Sem versão grande: o "jumbo" vem com o ícone pequeno num canto.
        img = _icon_from_list(SHIL_EXTRALARGE, sfi.iIcon) or img
        bbox = img.getchannel("A").getbbox() if img else None
    if not img or not bbox:
        return None
    img = img.crop(bbox)
    side = max(img.size)
    square = Image.new("RGBA", (side, side))
    square.paste(img, ((side - img.width) // 2, (side - img.height) // 2))
    if side > 128:
        square = square.resize((128, 128), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    square.save(buf, "PNG")
    return buf.getvalue()


def icon_png(cache_dir: Path, parse_name: str) -> bytes | None:
    """PNG do ícone de um app ("shell:AppsFolder\\...") ou arquivo, com cache em disco."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / (hashlib.sha1(parse_name.encode()).hexdigest() + ".png")
    if path.exists():
        return path.read_bytes()
    data = _render_icon(parse_name)
    if data:
        with _cache_lock:
            path.write_bytes(data)
    return data


# --- abrir ---------------------------------------------------------------

def launch_app(app_id: str):
    os.startfile("shell:AppsFolder\\" + app_id)


def launch_file(path: str):
    """Abre o arquivo na pasta onde ele está (jogos e programas costumam precisar disso)."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(path)
    os.startfile(str(p), cwd=str(p.parent))


def launch_steam(appid: str):
    if not appid.isdigit():
        raise ValueError("appid inválido")
    os.startfile(f"steam://rungameid/{appid}")
