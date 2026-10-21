"""Inicia o PControl no PC.

    python server.py            inicia o servidor
    python server.py --senha    define (ou troca) a senha de acesso
"""

import argparse
import asyncio
import getpass
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _setup_logging():
    # Sem console (pythonw, inicialização automática): tudo vai para pcontrol.log.
    if sys.stdout is None or sys.stderr is None:
        log_path = ROOT / "pcontrol.log"
        if log_path.exists() and log_path.stat().st_size > 2 * 1024 * 1024:
            log_path.unlink()
        stream = open(log_path, "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = stream
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)


def _ask_password(config):
    print("Escolha a senha que o celular vai pedir para entrar (mínimo 6 caracteres).")
    while True:
        first = getpass.getpass("Senha: ")
        if len(first) < 6:
            print("Muito curta, tente de novo.")
            continue
        if getpass.getpass("Repita a senha: ") != first:
            print("As senhas não batem, tente de novo.")
            continue
        config.set_password(first)
        print("Senha salva. Aparelhos que já estavam conectados vão precisar entrar de novo.")
        return


async def _serve(state, port, discovery_port):
    from aiohttp import web as aioweb

    from pcontrol import discovery, system, web

    app = web.create_app(state)
    runner = aioweb.AppRunner(app, access_log=None)
    await runner.setup()
    site = aioweb.TCPSite(runner, "0.0.0.0", port)
    try:
        await site.start()
    except OSError:
        logging.error("A porta %s já está em uso. O PControl já está rodando?", port)
        await runner.cleanup()
        return 1
    try:
        await discovery.start(port, discovery_port)
    except OSError as exc:
        logging.warning("Busca automática na rede desativada (porta UDP %s): %s", discovery_port, exc)

    print()
    print("  PControl rodando.")
    lan, ts = system.lan_ip(), system.tailscale_ip()
    if lan:
        print(f"  Wi-Fi de casa:        http://{lan}:{port}")
    if ts:
        print(f"  De qualquer lugar:    http://{ts}:{port}  (Tailscale)")
    else:
        print("  De qualquer lugar:    instale o Tailscale no PC e no celular (veja o README).")
    print(f"  QR code para o celular: abra http://localhost:{port}/conectar neste PC")
    print()
    await asyncio.Event().wait()


def main():
    parser = argparse.ArgumentParser(description="PControl: controle o PC pelo celular")
    parser.add_argument("--senha", action="store_true", help="define a senha de acesso")
    parser.add_argument("--config", type=Path, default=ROOT / "config.json")
    parser.add_argument("--porta", type=int)
    args = parser.parse_args()

    _setup_logging()

    from pcontrol import system
    from pcontrol.config import Config
    from pcontrol.web import State

    config = Config(args.config)
    if args.senha:
        _ask_password(config)
        return 0
    if not config.has_password:
        logging.error("Nenhuma senha definida. Rode configurar.bat (ou: python server.py --senha).")
        return 1

    system.enable_dpi_awareness()
    if config.get("keep_awake"):
        system.keep_awake(True)

    port = args.porta or config.get("port")
    config.data["port"] = port
    state = State(config, ROOT)
    try:
        return asyncio.run(_serve(state, port, config.get("discovery_port")))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
