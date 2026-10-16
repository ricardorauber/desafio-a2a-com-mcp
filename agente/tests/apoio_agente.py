"""Run the real MCP server app in a background uvicorn thread, capturing raw requests."""

from __future__ import annotations

import json
import secrets
import socket
import threading
import time
from contextlib import contextmanager

import uvicorn


def porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Captura:
    def __init__(self, app) -> None:
        self.app = app
        self.requests: list[dict] = []

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        corpo, mensagens = b"", []
        while True:
            m = await receive()
            mensagens.append(m)
            corpo += m.get("body", b"")
            if not m.get("more_body"):
                break
        cabecalhos = {k.decode().lower(): v.decode() for k, v in scope["headers"]}
        self.requests.append({"headers": cabecalhos, "body": json.loads(corpo or b"{}")})

        async def reenviar():
            return mensagens.pop(0) if mensagens else await receive()

        return await self.app(scope, reenviar, send)


@contextmanager
def servidor_mcp_em_segundo_plano():
    from servidor_mcp.seguranca import seguranca_do_ambiente
    from servidor_mcp.servidor import criar_app

    seguranca = seguranca_do_ambiente({"REQUEST_STATE_SECRET": secrets.token_hex(32)})
    captura = Captura(criar_app(seguranca=seguranca))
    porta = porta_livre()
    servidor = uvicorn.Server(uvicorn.Config(captura, host="127.0.0.1", port=porta, log_level="warning"))
    thread = threading.Thread(target=servidor.run, daemon=True)
    thread.start()
    while not servidor.started:
        time.sleep(0.02)
    try:
        yield f"http://127.0.0.1:{porta}/mcp", captura
    finally:
        servidor.should_exit = True
        thread.join(timeout=5)
