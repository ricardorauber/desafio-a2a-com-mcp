"""One stderr line per HTTP request: JSON-RPC method, id, traceparent and status.

It wraps the whole ASGI app, so requests the SDK rejects before any handler
runs (missing `_meta`, header mismatch) are logged too.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("servidor_mcp.requests")


def _campos(corpo: bytes) -> dict[str, Any]:
    try:
        mensagem = json.loads(corpo)
    except (ValueError, UnicodeDecodeError):
        return {}
    if not isinstance(mensagem, dict):
        return {}
    params = mensagem.get("params") if isinstance(mensagem.get("params"), dict) else {}
    meta = params.get("_meta") if isinstance(params.get("_meta"), dict) else {}
    return {
        "method": mensagem.get("method"),
        "id": mensagem.get("id"),
        "name": params.get("name") or params.get("uri"),
        "traceparent": meta.get("traceparent"),
    }


def _valor(valor: Any) -> str:
    return "-" if valor is None else json.dumps(valor) if not isinstance(valor, str) else valor


class RegistroDeRequests:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        mensagens: list[Message] = []
        corpo = b""
        while True:
            mensagem = await receive()
            mensagens.append(mensagem)
            corpo += mensagem.get("body", b"")
            if mensagem["type"] != "http.request" or not mensagem.get("more_body"):
                break

        async def reenviar() -> Message:
            return mensagens.pop(0) if mensagens else await receive()

        status: list[int] = []

        async def capturar(mensagem: Message) -> None:
            if mensagem["type"] == "http.response.start":
                status.append(mensagem["status"])
            await send(mensagem)

        try:
            await self.app(scope, reenviar, capturar)
        finally:
            campos = _campos(corpo)
            logger.info(
                "%s %s method=%s id=%s name=%s traceparent=%s status=%s",
                scope.get("method"),
                scope.get("path"),
                _valor(campos.get("method")),
                _valor(campos.get("id")),
                _valor(campos.get("name")),
                _valor(campos.get("traceparent")),
                status[0] if status else "-",
            )
