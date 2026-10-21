"""Configuração persistente (config.json): senha, sessões, favoritos."""

import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from pathlib import Path

SESSION_DAYS = 90
PBKDF2_ITERATIONS = 200_000

DEFAULTS = {
    "port": 8765,
    "discovery_port": 8766,
    # Aceita conexões da rede local (Wi-Fi de casa) além do Tailscale.
    "allow_lan": True,
    # Impede o PC de entrar em suspensão enquanto o servidor estiver rodando.
    "keep_awake": True,
    "password": None,
    "sessions": {},
    "favorites": [],
}


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Config:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self.data = json.loads(json.dumps(DEFAULTS))
        if self.path.exists():
            self.data.update(json.loads(self.path.read_text("utf-8")))

    def save(self):
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), "utf-8")
            os.replace(tmp, self.path)

    def get(self, key):
        return self.data.get(key, DEFAULTS.get(key))

    def set(self, key, value):
        self.data[key] = value
        self.save()

    # --- senha -----------------------------------------------------------

    @property
    def has_password(self) -> bool:
        return bool(self.data.get("password"))

    def set_password(self, password: str):
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
        self.data["password"] = {"salt": salt.hex(), "hash": digest.hex(), "iter": PBKDF2_ITERATIONS}
        # Trocar a senha desconecta todos os aparelhos.
        self.data["sessions"] = {}
        self.save()

    def check_password(self, password: str) -> bool:
        stored = self.data.get("password")
        if not stored:
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(stored["salt"]), stored["iter"]
        )
        return hmac.compare_digest(digest.hex(), stored["hash"])

    # --- sessões ---------------------------------------------------------

    def new_session(self, agent: str) -> str:
        token = secrets.token_urlsafe(32)
        self.data["sessions"][_token_hash(token)] = {"created": time.time(), "agent": agent[:160]}
        self.save()
        return token

    def check_session(self, token: str | None) -> bool:
        if not token:
            return False
        key = _token_hash(token)
        session = self.data["sessions"].get(key)
        if not session:
            return False
        if time.time() - session["created"] > SESSION_DAYS * 86400:
            del self.data["sessions"][key]
            self.save()
            return False
        return True

    def drop_session(self, token: str | None):
        if token and self.data["sessions"].pop(_token_hash(token), None):
            self.save()
