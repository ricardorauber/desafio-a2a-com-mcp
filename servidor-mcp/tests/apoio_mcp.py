import itertools
import json

from starlette.testclient import TestClient

from servidor_mcp.servidor import criar_app

PROTOCOLO = "2026-07-28"
COM_ELICITATION = {"elicitation": {"form": {}}}
_ids = itertools.count(1)


def h(hora: str, dia: str = "2026-11-03") -> str:
    return f"{dia}T{hora}:00-03:00"


class ClienteMCP:
    """Minimal raw JSON-RPC client, shaped like the starter validator."""

    def __init__(self, http: TestClient) -> None:
        self.http = http

    def chamar(self, metodo, params=None, *, nome=None, capacidades=COM_ELICITATION, omitir=None, traceparent=None):
        meta = {
            "io.modelcontextprotocol/protocolVersion": PROTOCOLO,
            "io.modelcontextprotocol/clientCapabilities": capacidades,
        }
        if traceparent:
            meta["traceparent"] = traceparent
        if omitir:
            meta.pop(f"io.modelcontextprotocol/{omitir}")
        cabecalhos = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": PROTOCOLO,
            "Mcp-Method": metodo,
        }
        if nome:
            cabecalhos["Mcp-Name"] = nome
        corpo = {"jsonrpc": "2.0", "id": next(_ids), "method": metodo, "params": {**(params or {}), "_meta": meta}}
        resposta = self.http.post("/mcp", content=json.dumps(corpo), headers=cabecalhos)
        return resposta.status_code, resposta.json()

    def ferramenta(self, nome, argumentos, **kw):
        return self.chamar("tools/call", {"name": nome, "arguments": argumentos}, nome=nome, **kw)


def texto(resultado: dict) -> str:
    return " ".join(p.get("text", "") for p in resultado.get("content", []))
