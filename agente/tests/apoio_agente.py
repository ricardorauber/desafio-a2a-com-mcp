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


class HostFalso:
    """Stands in for `HostMCP`: returns queued results and records every call."""

    def __init__(self, *resultados) -> None:
        self.resultados = list(resultados)
        self.chamadas: list[tuple[str, tuple]] = []

    async def reservar(self, argumentos, trace_id):
        self.chamadas.append(("reservar", (argumentos, trace_id)))
        return self.resultados.pop(0)

    async def retomar(self, argumentos, chave, resposta, request_state, politica, trace_id):
        self.chamadas.append(("retomar", (argumentos, chave, resposta, request_state, politica, trace_id)))
        return self.resultados.pop(0)


class ClienteA2A:
    def __init__(self, http) -> None:
        self.http = http
        self.n = 0
        self.corpos: list[str] = []

    def rpc(self, metodo, params, cabecalhos=None):
        self.n += 1
        resposta = self.http.post("/a2a", json={"jsonrpc": "2.0", "id": self.n, "method": metodo, "params": params}, headers=cabecalhos or {})
        self.corpos.append(resposta.text)
        return resposta.json()

    def enviar(self, texto, task_id=None, traceparent=None):
        self.n += 1
        mensagem = {"messageId": f"msg-{self.n}", "role": "ROLE_USER", "parts": [{"text": texto}]}
        if task_id:
            mensagem["taskId"] = task_id
        return self.rpc("SendMessage", {"message": mensagem}, {"traceparent": traceparent} if traceparent else None)

    def obter(self, task_id):
        return self.rpc("GetTask", {"id": task_id})


def tarefa(resposta: dict) -> dict:
    resultado = resposta.get("result") or {}
    return resultado.get("task") or resultado


def estado(resposta: dict) -> str:
    return tarefa(resposta).get("status", {}).get("state", "")


def mensagem(resposta: dict) -> str:
    return " ".join(p.get("text", "") for p in tarefa(resposta).get("status", {}).get("message", {}).get("parts", []))
