"""Navegação de pastas e arquivos do PC."""

import os
import stat
from pathlib import Path

FILE_ATTRIBUTE_HIDDEN = 0x2
FILE_ATTRIBUTE_SYSTEM = 0x4
INVALID_NAME_CHARS = set('<>:"/\\|?*') | {chr(i) for i in range(32)}


def check_name(name: str) -> str:
    name = name.strip().rstrip(".")
    if not name or name in (".", "..") or any(c in INVALID_NAME_CHARS for c in name):
        raise ValueError("nome inválido")
    return name


def resolve(path: str) -> Path:
    p = Path(path)
    if not p.is_absolute():
        raise ValueError("caminho precisa ser absoluto")
    return p


def places():
    home = Path.home()
    out = []
    for label, names in (
        ("Área de Trabalho", ["Desktop", "OneDrive/Desktop", "OneDrive/Área de Trabalho"]),
        ("Downloads", ["Downloads"]),
        ("Documentos", ["Documents", "OneDrive/Documents", "OneDrive/Documentos"]),
        ("Imagens", ["Pictures", "OneDrive/Pictures", "OneDrive/Imagens"]),
        ("Vídeos", ["Videos"]),
        ("Músicas", ["Music"]),
    ):
        for name in names:
            candidate = home / name
            if candidate.is_dir():
                out.append({"name": label, "path": str(candidate), "kind": "folder"})
                break
    drives = os.listdrives() if hasattr(os, "listdrives") else [f"{c}:\\" for c in "CDEFGHIJ" if os.path.exists(f"{c}:\\")]
    for drive in drives:
        out.append({"name": drive.rstrip("\\"), "path": drive, "kind": "drive"})
    return out


def list_dir(path: str, show_hidden: bool):
    base = resolve(path)
    entries = []
    with os.scandir(base) as it:
        for entry in it:
            try:
                st = entry.stat()
            except OSError:
                continue
            attrs = getattr(st, "st_file_attributes", 0)
            hidden = bool(attrs & (FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM)) or entry.name.startswith(".")
            if hidden and not show_hidden:
                continue
            is_dir = stat.S_ISDIR(st.st_mode)
            entries.append({
                "name": entry.name,
                "dir": is_dir,
                "size": None if is_dir else st.st_size,
                "modified": int(st.st_mtime),
                "hidden": hidden,
            })
    entries.sort(key=lambda e: (not e["dir"], e["name"].lower()))
    parent = str(base.parent) if base.parent != base else ""
    return {"path": str(base), "parent": parent, "entries": entries}


def unique_path(folder: Path, name: str) -> Path:
    target = folder / name
    stem, suffix = os.path.splitext(name)
    n = 1
    while target.exists():
        target = folder / f"{stem} ({n}){suffix}"
        n += 1
    return target
