"""Responde ao app do celular que procura o PC na rede Wi-Fi (broadcast UDP)."""

import asyncio
import json
import socket

from . import VERSION, system

QUESTION = b"PCONTROL_DISCOVER"


class _Responder(asyncio.DatagramProtocol):
    def __init__(self, port: int):
        self.port = port
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        if data.strip() != QUESTION or system.classify_ip(addr[0]) is None:
            return
        answer = {"app": "pcontrol", "name": socket.gethostname(), "port": self.port, "version": VERSION}
        self.transport.sendto(json.dumps(answer).encode(), addr)


async def start(http_port: int, discovery_port: int):
    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(
        lambda: _Responder(http_port), local_addr=("0.0.0.0", discovery_port)
    )
    return transport
