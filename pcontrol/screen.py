"""Captura da tela em JPEG."""

import io
import threading
from concurrent.futures import ThreadPoolExecutor

import mss
from PIL import Image

# O mss não é thread-safe: toda captura roda nesta única thread.
executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="captura")
_local = threading.local()


def _sct(reset=False):
    sct = getattr(_local, "sct", None)
    if reset and sct is not None:
        sct.close()
        sct = None
    if sct is None:
        sct = _local.sct = mss.MSS()
    return sct


def list_monitors():
    monitors = _sct(reset=True).monitors[1:]
    return [
        {
            "left": m["left"],
            "top": m["top"],
            "width": m["width"],
            "height": m["height"],
            "primary": bool(m.get("is_primary")),
        }
        for m in monitors
    ]


def grab(index: int, scale: float, quality: int, previous: bytes | None):
    """Retorna (jpeg, raw). jpeg é None quando a tela não mudou desde `previous`."""
    sct = _sct()
    monitors = sct.monitors
    mon = monitors[index + 1] if 0 <= index < len(monitors) - 1 else monitors[1]
    shot = sct.grab(mon)
    raw = shot.bgra
    if previous is not None and raw == previous:
        return None, raw
    img = Image.frombytes("RGB", shot.size, raw, "raw", "BGRX")
    if scale < 0.99:
        size = (max(1, round(shot.width * scale)), max(1, round(shot.height * scale)))
        img = img.resize(size, Image.Resampling.BILINEAR)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality)
    return buf.getvalue(), raw
