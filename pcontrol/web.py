"""Servidor HTTP/WebSocket: interface do celular, API e transmissão da tela."""

import asyncio
import hashlib
import json
import logging
import os
import socket
import time
from pathlib import Path
from urllib.parse import quote, urlsplit

import aiohttp
import segno
from aiohttp import WSMsgType, web

from . import VERSION, apps, files, inputs, screen, system, youtube
from .config import SESSION_DAYS, Config

COOKIE = "pc_session"
PUBLIC_API = {"/api/login", "/api/ping"}
APPS_CACHE_SECONDS = 600

log = logging.getLogger("pcontrol")


class State:
    def __init__(self, config: Config, root: Path):
        self.config = config
        self.root = root
        self.static = root / "static"
        self.cache = root / "cache"
        self.apk = root / "dist" / "PControl.apk"
        self.failed_logins: dict[str, list[float]] = {}
        self.apps_cache: tuple[float, list] | None = None
        self.http: aiohttp.ClientSession | None = None


def _state(request) -> State:
    return request.app["state"]


def _client_kind(request) -> str | None:
    return system.classify_ip(request.remote or "")


async def _blocking(func, *args, executor=None):
    return await asyncio.get_running_loop().run_in_executor(executor, func, *args)


# --- middleware ----------------------------------------------------------

@web.middleware
async def guard(request: web.Request, handler):
    state = _state(request)
    kind = _client_kind(request)
    if kind is None or (kind == "lan" and not state.config.get("allow_lan")):
        return web.Response(status=403, text="Acesso negado para este endereço.")
    path = request.path
    if path.startswith("/conectar") and kind != "local":
        return web.Response(status=403, text="Abra esta página no próprio PC.")
    if (path.startswith("/api/") or path == "/ws") and path not in PUBLIC_API:
        if not state.config.check_session(request.cookies.get(COOKIE)):
            return web.json_response({"error": "login"}, status=401)
    try:
        resp = await handler(request)
    except web.HTTPException:
        raise
    except (ValueError, KeyError, FileNotFoundError, PermissionError, OSError) as exc:
        log.info("erro em %s: %r", path, exc)
        resp = web.json_response({"error": _error_text(exc)}, status=400)
    except Exception as exc:
        log.exception("falha em %s", path)
        resp = web.json_response({"error": f"Erro no PC: {exc}"}, status=500)
    if not resp.prepared:
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        if path.startswith("/api/"):
            resp.headers.setdefault("Cache-Control", "no-store")
        else:
            resp.headers.setdefault("Cache-Control", "no-cache")
    return resp


def _error_text(exc) -> str:
    if isinstance(exc, FileNotFoundError):
        return "Arquivo ou pasta não encontrado."
    if isinstance(exc, PermissionError):
        return "Sem permissão para isso."
    if isinstance(exc, KeyError):
        return f"Faltou o campo {exc}."
    return str(exc) or exc.__class__.__name__


async def _json(request) -> dict:
    try:
        data = await request.json()
    except ValueError:
        raise ValueError("JSON inválido")
    if not isinstance(data, dict):
        raise ValueError("JSON inválido")
    return data


# --- páginas -------------------------------------------------------------

async def index(request):
    return web.FileResponse(_state(request).static / "index.html")


async def download_apk(request):
    apk = _state(request).apk
    if not apk.exists():
        return web.Response(status=404, text="O APK ainda não foi gerado. Rode android\\build.bat no PC.")
    return web.FileResponse(apk, headers={
        "Content-Type": "application/vnd.android.package-archive",
        "Content-Disposition": 'attachment; filename="PControl.apk"',
    })


def _addresses(state: State):
    port = state.config.get("port")
    out = []
    lan = system.lan_ip()
    if lan:
        out.append({"kind": "lan", "label": "Wi-Fi de casa", "url": f"http://{lan}:{port}"})
    ts = system.tailscale_ip()
    if ts:
        out.append({"kind": "tailscale", "label": "De qualquer lugar (Tailscale)", "url": f"http://{ts}:{port}"})
    return out


async def connect_page(request):
    """Página só para o próprio PC: QR codes para o celular."""
    state = _state(request)
    addresses = await _blocking(_addresses, state)
    blocks = []
    for addr in addresses:
        qr = segno.make(addr["url"], error="m").svg_inline(scale=6, dark="#111", light="#fff")
        blocks.append(
            f'<div class="card"><h2>{addr["label"]}</h2>{qr}<code>{addr["url"]}</code></div>'
        )
    if addresses and state.apk.exists():
        apk_url = addresses[0]["url"] + "/app.apk"
        qr = segno.make(apk_url, error="m").svg_inline(scale=6, dark="#111", light="#fff")
        blocks.insert(0, f'<div class="card"><h2>1. Baixe o app (Android)</h2>{qr}<code>{apk_url}</code></div>')
    if not any(a["kind"] == "tailscale" for a in addresses):
        blocks.append(
            '<div class="card"><h2>Fora de casa</h2><p>Instale o <b>Tailscale</b> no PC e no celular '
            "(mesma conta) e recarregue esta página. Aparece um segundo endereço aqui.</p></div>"
        )
    html = f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>PControl · conectar</title>
<style>
body{{margin:0;font:16px/1.5 system-ui,sans-serif;background:#0f1115;color:#e8eaed;padding:32px}}
h1{{margin:0 0 4px;font-size:24px}} p.sub{{margin:0 0 24px;color:#9aa0a6}}
.grid{{display:flex;flex-wrap:wrap;gap:20px}}
.card{{background:#181b21;border:1px solid #2a2f38;border-radius:14px;padding:20px;max-width:300px}}
.card h2{{margin:0 0 12px;font-size:16px}} .card svg{{display:block;border-radius:8px;margin-bottom:10px}}
code{{font-size:14px;color:#8ab4f8;word-break:break-all}}
</style></head><body>
<h1>PControl em {socket.gethostname()}</h1>
<p class="sub">Aponte a câmera do celular para um QR code. Use a senha que você definiu no configurar.bat.</p>
<div class="grid">{''.join(blocks) or '<p>Nenhuma rede encontrada.</p>'}</div>
</body></html>"""
    return web.Response(text=html, content_type="text/html")


# --- login ---------------------------------------------------------------

async def ping(request):
    return web.json_response({"app": "pcontrol", "name": socket.gethostname(), "version": VERSION})


async def login(request):
    state = _state(request)
    ip = request.remote or "?"
    now = time.time()
    recent = [t for t in state.failed_logins.get(ip, []) if now - t < 300]
    state.failed_logins[ip] = recent
    if len(recent) >= 8:
        return web.json_response({"error": "Muitas tentativas. Espere 5 minutos."}, status=429)
    data = await _json(request)
    password = str(data.get("password", ""))
    ok = await _blocking(state.config.check_password, password)
    if not ok:
        recent.append(now)
        await asyncio.sleep(0.8)
        return web.json_response({"error": "Senha incorreta."}, status=403)
    token = state.config.new_session(request.headers.get("User-Agent", ""))
    body = {"ok": True}
    if request.headers.get("X-PControl-App") == "1":
        body["token"] = token
    resp = web.json_response(body)
    resp.set_cookie(COOKIE, token, max_age=SESSION_DAYS * 86400, httponly=True, samesite="Lax", path="/")
    return resp


async def logout(request):
    _state(request).config.drop_session(request.cookies.get(COOKIE))
    resp = web.json_response({"ok": True})
    resp.del_cookie(COOKIE, path="/")
    return resp


async def info(request):
    state = _state(request)
    port = state.config.get("port")
    lan, ts = await _blocking(lambda: (system.lan_ip(), system.tailscale_ip()))
    return web.json_response({
        "host": socket.gethostname(),
        "version": VERSION,
        "port": port,
        "lan": f"http://{lan}:{port}" if lan else None,
        "tailscale": f"http://{ts}:{port}" if ts else None,
        "via": _client_kind(request),
        "keep_awake": state.config.get("keep_awake"),
    })


# --- sistema -------------------------------------------------------------

async def stats(request):
    return web.json_response(await _blocking(system.stats))


async def windows(request):
    return web.json_response(await _blocking(system.windows))


async def window_action(request):
    data = await _json(request)
    await _blocking(system.window_action, int(data["hwnd"]), str(data["action"]))
    return web.json_response({"ok": True})


async def processes(request):
    return web.json_response(await _blocking(system.processes))


async def kill(request):
    data = await _json(request)
    pids = [int(p) for p in data["pids"]][:500]
    return web.json_response(await _blocking(system.kill, pids))


async def power(request):
    data = await _json(request)
    action = str(data["action"])
    delay = int(data.get("delay", 0))
    # Responde antes de desligar/suspender, senão o celular fica sem resposta.
    asyncio.get_running_loop().call_later(0.4, system.power, action, delay)
    return web.json_response({"ok": True})


async def get_volume(request):
    return web.json_response(system.get_volume())


async def set_volume(request):
    data = await _json(request)
    return web.json_response(system.set_volume(data.get("level"), data.get("muted")))


async def press_key(request):
    data = await _json(request)
    keys = [str(k) for k in data["keys"]][:6]
    inputs.press(keys, int(data.get("repeat", 1)))
    return web.json_response({"ok": True})


async def type_text(request):
    data = await _json(request)
    inputs.type_text(str(data["text"])[:20000])
    return web.json_response({"ok": True})


async def get_clipboard(request):
    return web.json_response({"text": system.get_clipboard()})


async def set_clipboard(request):
    data = await _json(request)
    system.set_clipboard(str(data["text"]))
    return web.json_response({"ok": True})


async def open_url(request):
    data = await _json(request)
    url = str(data["url"]).strip()
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url
    if not urlsplit(url).netloc:
        raise ValueError("link inválido")
    os.startfile(url)
    return web.json_response({"ok": True})


async def keep_awake(request):
    state = _state(request)
    data = await _json(request)
    on = bool(data["on"])
    state.config.set("keep_awake", on)
    system.keep_awake(on)
    return web.json_response({"ok": True, "on": on})


# --- apps ----------------------------------------------------------------

def _favorite_id(path: str) -> str:
    return hashlib.sha1(path.lower().encode()).hexdigest()[:12]


async def list_apps(request):
    state = _state(request)
    refresh = request.query.get("refresh") == "1"
    if refresh or not state.apps_cache or time.time() - state.apps_cache[0] > APPS_CACHE_SECONDS:
        state.apps_cache = (time.time(), await _blocking(apps.start_apps))
    steam = await _blocking(apps.steam_games)
    steam_names = {g["name"].lower() for g in steam}
    start = [a for a in state.apps_cache[1] if a["name"].lower() not in steam_names]
    return web.json_response({
        "favorites": state.config.get("favorites"),
        "steam": steam,
        "apps": start,
    })


async def app_icon(request):
    state = _state(request)
    if "app" in request.query:
        target = "shell:AppsFolder\\" + request.query["app"]
    elif "file" in request.query:
        target = str(files.resolve(request.query["file"]))
    else:
        raise ValueError("informe app ou file")
    data = await _blocking(apps.icon_png, state.cache / "icons", target, executor=apps.icon_executor)
    if not data:
        raise web.HTTPNotFound()
    return web.Response(body=data, content_type="image/png", headers={"Cache-Control": "private, max-age=604800"})


async def steam_cover(request):
    appid = request.match_info["appid"]
    cover = await _blocking(apps.steam_cover, appid)
    if cover:
        return web.FileResponse(cover, headers={"Cache-Control": "private, max-age=604800"})
    raise web.HTTPFound(f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/library_600x900.jpg")


async def launch(request):
    data = await _json(request)
    kind = data["kind"]
    if kind == "app":
        apps.launch_app(str(data["id"]))
    elif kind == "steam":
        apps.launch_steam(str(data["id"]))
    elif kind == "file":
        apps.launch_file(str(files.resolve(str(data["path"]))))
    else:
        raise ValueError("tipo desconhecido")
    return web.json_response({"ok": True})


async def favorites(request):
    state = _state(request)
    data = await _json(request)
    favs = [f for f in state.config.get("favorites")]
    if data["action"] == "add":
        path = str(files.resolve(str(data["path"])))
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        fid = _favorite_id(path)
        if not any(f["id"] == fid for f in favs):
            name = str(data.get("name") or Path(path).stem)[:80]
            favs.append({"id": fid, "name": name, "path": path})
    elif data["action"] == "remove":
        favs = [f for f in favs if f["id"] != data["id"]]
    else:
        raise ValueError("ação desconhecida")
    state.config.set("favorites", favs)
    return web.json_response({"favorites": favs})


# --- YouTube -------------------------------------------------------------

async def youtube_search(request):
    state = _state(request)
    query = request.query.get("q", "").strip()
    if not query:
        return web.json_response({"results": []})
    try:
        results = await youtube.search(state.http, query)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
        log.info("busca no YouTube falhou: %r", exc)
        return web.json_response({"results": [], "error": "Não consegui buscar no YouTube agora."})
    return web.json_response({"results": results})


def _youtube_title(window) -> str | None:
    """Título do vídeo se a aba ativa da janela for do YouTube, sem o "(3) " de notificações."""
    title = window["title"]
    if " - youtube" not in title.lower():
        return None
    if title.startswith("(") and ") " in title:
        title = title.split(") ", 1)[1]
    return title


async def _play_youtube(url: str):
    # Reaproveita a aba do YouTube que já estiver aberta, para não ficar com dois vídeos tocando.
    wins = await _blocking(system.windows)
    tab = next((w for w in wins if _youtube_title(w)), None)
    previous = _youtube_title(tab) if tab else None
    reused = False
    if tab:
        await _blocking(system.window_action, tab["hwnd"], "focus")
        await asyncio.sleep(0.4)
        if system.foreground_window() == tab["hwnd"]:
            inputs.press(["ctrl", "l"])
            await asyncio.sleep(0.2)
            inputs.type_text(url)
            inputs.press(["enter"])
            reused = True
    if not reused:
        previous = None
        os.startfile(url)

    # O Brave (e às vezes outros navegadores) abre o vídeo pausado. Espera a página
    # carregar e, se o navegador não estiver tocando nada, aperta K (play).
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 20
    video = None
    while loop.time() < deadline:
        await asyncio.sleep(0.8)
        wins = await _blocking(system.windows)
        active = next((w for w in wins if w["active"]), None)
        title = _youtube_title(active) if active else None
        if title and title != previous:
            video = active
            break
    if not video:
        return
    await asyncio.sleep(3)
    if system.audio_playing(video["process"]):
        return
    if system.foreground_window() == video["hwnd"]:
        log.info("vídeo abriu pausado; apertando play")
        inputs.press(["k"])


async def youtube_play(request):
    data = await _json(request)
    video = str(data.get("id") or "")
    if "url" in data:
        video = youtube.video_id_from_url(str(data["url"])) or ""
    if len(video) != 11 or not all(c.isalnum() or c in "-_" for c in video):
        raise ValueError("vídeo inválido")
    async def run():
        try:
            await _play_youtube(f"https://www.youtube.com/watch?v={video}")
        except Exception:
            log.exception("falha ao tocar o vídeo")

    tasks = request.app["background"]
    task = asyncio.create_task(run())
    tasks.add(task)
    task.add_done_callback(tasks.discard)
    return web.json_response({"ok": True})


# --- arquivos ------------------------------------------------------------

async def list_files(request):
    path = request.query.get("path", "")
    if not path:
        return web.json_response({"path": "", "parent": None, "places": await _blocking(files.places)})
    show_hidden = request.query.get("hidden") == "1"
    return web.json_response(await _blocking(files.list_dir, path, show_hidden))


async def download_file(request):
    path = files.resolve(request.query["path"])
    if not path.is_file():
        raise FileNotFoundError(str(path))
    disposition = "inline" if request.query.get("inline") == "1" else "attachment"
    return web.FileResponse(path, headers={
        "Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(path.name)}",
        "Cache-Control": "no-store",
    })


async def upload_files(request):
    folder = files.resolve(request.query["dir"])
    if not folder.is_dir():
        raise FileNotFoundError(str(folder))
    reader = await request.multipart()
    saved = []
    async for part in reader:
        if not part.filename:
            continue
        name = files.check_name(os.path.basename(part.filename.replace("\\", "/")))
        target = files.unique_path(folder, name)
        try:
            with open(target, "wb") as fh:
                while chunk := await part.read_chunk(512 * 1024):
                    fh.write(chunk)
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        saved.append(target.name)
    return web.json_response({"saved": saved})


async def make_dir(request):
    data = await _json(request)
    folder = files.resolve(str(data["dir"]))
    target = folder / files.check_name(str(data["name"]))
    target.mkdir()
    return web.json_response({"ok": True, "path": str(target)})


async def rename_file(request):
    data = await _json(request)
    path = files.resolve(str(data["path"]))
    target = path.with_name(files.check_name(str(data["name"])))
    if target.exists():
        raise ValueError("já existe um item com esse nome")
    path.rename(target)
    return web.json_response({"ok": True, "path": str(target)})


async def delete_file(request):
    data = await _json(request)
    path = files.resolve(str(data["path"]))
    if not path.exists():
        raise FileNotFoundError(str(path))
    if path.parent == path:
        raise ValueError("não dá para apagar um disco inteiro")
    await _blocking(system.recycle, str(path))
    return web.json_response({"ok": True})


async def open_file(request):
    data = await _json(request)
    apps.launch_file(str(files.resolve(str(data["path"]))))
    return web.json_response({"ok": True})


# --- tela ao vivo (WebSocket) ---------------------------------------------

class ScreenSession:
    def __init__(self, ws):
        self.ws = ws
        self.monitors: list[dict] = []
        self.monitor = 0
        self.scale = 0.6
        self.quality = 55
        self.fps = 15
        self.want_frame = asyncio.Event()
        self.previous: bytes | None = None
        self.last_cursor = None
        self.held_buttons: set[str] = set()

    @property
    def mon(self):
        return self.monitors[self.monitor] if self.monitors else {"left": 0, "top": 0, "width": 1, "height": 1}


def _clamp(value, low, high):
    return max(low, min(high, value))


def _handle_input(sess: ScreenSession, msg: dict):
    kind = msg.get("t")
    if kind == "frame":
        sess.want_frame.set()
    elif kind == "cfg":
        if "monitor" in msg:
            sess.monitor = _clamp(int(msg["monitor"]), 0, max(len(sess.monitors) - 1, 0))
        if "scale" in msg:
            sess.scale = _clamp(float(msg["scale"]), 0.2, 1.0)
        if "quality" in msg:
            sess.quality = _clamp(int(msg["quality"]), 10, 95)
        if "fps" in msg:
            sess.fps = _clamp(int(msg["fps"]), 1, 30)
        sess.previous = None
        sess.last_cursor = None
    elif kind == "move":
        inputs.move_by(round(float(msg["dx"])), round(float(msg["dy"])))
    elif kind == "moveto":
        mon = sess.mon
        x = mon["left"] + _clamp(float(msg["x"]), 0.0, 1.0) * (mon["width"] - 1)
        y = mon["top"] + _clamp(float(msg["y"]), 0.0, 1.0) * (mon["height"] - 1)
        inputs.move_to(round(x), round(y))
    elif kind == "btn":
        name = msg.get("b", "left")
        if name not in inputs.BUTTONS:
            return
        action = msg.get("a", "click")
        if action == "down":
            sess.held_buttons.add(name)
        elif action == "up":
            sess.held_buttons.discard(name)
        inputs.button(name, action)
    elif kind == "scroll":
        inputs.scroll(_clamp(int(msg.get("dy", 0)), -2400, 2400), _clamp(int(msg.get("dx", 0)), -2400, 2400))
    elif kind == "text":
        inputs.type_text(str(msg["s"])[:5000])
    elif kind == "key":
        inputs.press([str(k) for k in msg["keys"]][:6], _clamp(int(msg.get("n", 1)), 1, 200))


async def _frame_loop(sess: ScreenSession):
    loop = asyncio.get_running_loop()
    unavailable = False
    while True:
        await sess.want_frame.wait()
        sess.want_frame.clear()
        while True:
            started = loop.time()
            try:
                jpeg, raw = await loop.run_in_executor(
                    screen.executor, screen.grab, sess.monitor, sess.scale, sess.quality, sess.previous
                )
            except Exception as exc:
                # Tela de bloqueio/UAC: o Windows não deixa capturar.
                if not unavailable:
                    log.info("captura indisponível: %r", exc)
                    await sess.ws.send_json({"t": "status", "msg": "unavailable"})
                    unavailable = True
                sess.previous = None
                await asyncio.sleep(1.5)
                continue
            unavailable = False
            sess.previous = raw
            if jpeg is None:
                await asyncio.sleep(0.15)
                continue
            break
        await sess.ws.send_bytes(jpeg)
        wait = 1 / sess.fps - (loop.time() - started)
        if wait > 0:
            await asyncio.sleep(wait)


async def _cursor_loop(sess: ScreenSession):
    while True:
        await asyncio.sleep(0.04)
        x, y = inputs.cursor_pos()
        key = (x, y, sess.monitor)
        if key == sess.last_cursor:
            continue
        sess.last_cursor = key
        mon = sess.mon
        await sess.ws.send_json({
            "t": "cursor",
            "x": round((x - mon["left"] + 0.5) / mon["width"], 5),
            "y": round((y - mon["top"] + 0.5) / mon["height"], 5),
        })


async def websocket(request):
    origin = request.headers.get("Origin")
    if origin and urlsplit(origin).netloc != request.host:
        raise web.HTTPForbidden()
    ws = web.WebSocketResponse(heartbeat=20, compress=False, max_msg_size=1024 * 1024)
    await ws.prepare(request)
    sess = ScreenSession(ws)
    sess.monitors = await _blocking(screen.list_monitors, executor=screen.executor)
    await ws.send_json({"t": "hello", "monitors": sess.monitors, "host": socket.gethostname()})
    tasks = [asyncio.create_task(_frame_loop(sess)), asyncio.create_task(_cursor_loop(sess))]
    try:
        async for msg in ws:
            if msg.type != WSMsgType.TEXT:
                continue
            try:
                _handle_input(sess, json.loads(msg.data))
            except (ValueError, KeyError, TypeError) as exc:
                log.info("mensagem inválida: %r", exc)
    finally:
        for task in tasks:
            task.cancel()
        # Nunca deixar um botão "preso" se a conexão cair no meio de um arrasto.
        for name in sess.held_buttons:
            inputs.button(name, "up")
    return ws


# --- app -------------------------------------------------------------------

async def _on_startup(app):
    state: State = app["state"]
    state.http = aiohttp.ClientSession()

    async def warm_apps():
        try:
            state.apps_cache = (time.time(), await _blocking(apps.start_apps))
        except Exception as exc:
            log.info("não consegui listar os apps: %r", exc)

    app["warm"] = asyncio.create_task(warm_apps())


async def _on_cleanup(app):
    state: State = app["state"]
    if state.http:
        await state.http.close()


def create_app(state: State) -> web.Application:
    app = web.Application(middlewares=[guard], client_max_size=8 * 1024 * 1024)
    app["state"] = state
    app["background"] = set()
    app.on_startup.append(_on_startup)
    app.on_cleanup.append(_on_cleanup)
    app.add_routes([
        web.get("/", index),
        web.get("/conectar", connect_page),
        web.get("/app.apk", download_apk),
        web.get("/ws", websocket),
        web.get("/api/ping", ping),
        web.post("/api/login", login),
        web.post("/api/logout", logout),
        web.get("/api/info", info),
        web.get("/api/stats", stats),
        web.get("/api/windows", windows),
        web.post("/api/windows/action", window_action),
        web.get("/api/processes", processes),
        web.post("/api/processes/kill", kill),
        web.post("/api/power", power),
        web.get("/api/volume", get_volume),
        web.post("/api/volume", set_volume),
        web.post("/api/key", press_key),
        web.post("/api/type", type_text),
        web.get("/api/clipboard", get_clipboard),
        web.post("/api/clipboard", set_clipboard),
        web.post("/api/open", open_url),
        web.post("/api/keep-awake", keep_awake),
        web.get("/api/apps", list_apps),
        web.get("/api/apps/icon", app_icon),
        web.get("/api/apps/steam/{appid}/cover", steam_cover),
        web.post("/api/apps/launch", launch),
        web.post("/api/apps/favorites", favorites),
        web.get("/api/youtube/search", youtube_search),
        web.post("/api/youtube/play", youtube_play),
        web.get("/api/files", list_files),
        web.get("/api/files/download", download_file),
        web.post("/api/files/upload", upload_files),
        web.post("/api/files/mkdir", make_dir),
        web.post("/api/files/rename", rename_file),
        web.post("/api/files/delete", delete_file),
        web.post("/api/files/open", open_file),
        web.static("/s", state.static),
    ])
    return app
