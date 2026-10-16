"""The agent as MCP host: one SDK client, runtime discovery and the raw MRTR view.

This layer translates protocol only. Room rules (conflicts, policy, which rooms
are offered) are decided by the MCP server; `request_state` is carried as an
opaque string and never opened.
"""

from __future__ import annotations

import logging
from contextlib import AsyncExitStack
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Union

from mcp_types import (
    CallToolResult,
    ClientCapabilities,
    ElicitationCapability,
    ElicitRequest,
    ElicitResult,
    FormElicitationCapability,
    Implementation,
    InputRequiredResult,
    TextContent,
)

from mcp import Client
from mcp.client.session import ClientSession
from mcp.shared.exceptions import MCPError

from agente_a2a.trace import traceparent_filho

logger = logging.getLogger(__name__)

PROTOCOLO = "2026-07-28"
FERRAMENTA = "reservar_sala"
URI_POLITICA = "politica://uso"
INFO_DO_CLIENTE = Implementation(name="agente-central-de-salas", version="1.0.0")
SO_FORMULARIO = ElicitationCapability(form=FormElicitationCapability())

FERRAMENTA_AUSENTE = f"Ferramenta {FERRAMENTA} nao encontrada no servidor MCP"
SERVIDOR_INDISPONIVEL = "Servidor MCP indisponivel"
ENTRADA_INESPERADA = "Pedido de entrada inesperado do servidor MCP"


@dataclass(frozen=True)
class Concluida:
    dados: dict[str, Any]
    politica: str


@dataclass(frozen=True)
class Recusada:
    motivo: str | None


@dataclass(frozen=True)
class Pausada:
    chave: str
    alternativas: tuple[str, ...]
    politica: str
    request_state: str = field(repr=False)


@dataclass(frozen=True)
class FalhaFerramenta:
    texto: str


@dataclass(frozen=True)
class FalhaProtocolo:
    texto: str


Resultado = Union[Concluida, Recusada, Pausada, FalhaFerramenta, FalhaProtocolo]


class _Falha(Exception):
    def __init__(self, resultado: FalhaProtocolo) -> None:
        self.resultado = resultado


def capacidades_so_formulario(capacidades: ClientCapabilities) -> ClientCapabilities:
    """Advertise form-mode elicitation only.

    The SDK advertises `{"form": {}, "url": {}}` whenever an elicitation callback
    exists and nothing otherwise; the agent needs exactly `{"form": {}}` and no
    callback, because every question must travel back to the A2A client.
    """
    return capacidades.model_copy(update={"elicitation": SO_FORMULARIO})


class _ClienteSoFormulario(Client):
    async def _build_session(self, exit_stack: AsyncExitStack) -> ClientSession:
        sessao = await super()._build_session(exit_stack)
        original = sessao._build_capabilities
        sessao._build_capabilities = lambda versao: capacidades_so_formulario(original(versao))  # type: ignore[method-assign]
        return sessao


def versao_da_politica(texto: str) -> str:
    primeira = texto.splitlines()[0] if texto else ""
    chave, _, valor = primeira.partition(":")
    if chave.strip() != "versao" or not valor.strip():
        raise ValueError("politica sem a linha 'versao: <valor>'")
    return valor.strip()


def classificar(resultado: CallToolResult | InputRequiredResult, politica: str) -> Resultado:
    if isinstance(resultado, InputRequiredResult):
        return _pausa(resultado, politica)
    if resultado.is_error:
        return FalhaFerramenta("\n".join(b.text for b in resultado.content if isinstance(b, TextContent)))
    dados = resultado.structured_content or {}
    if dados.get("reservado") is True:
        return Concluida(dados, politica)
    return Recusada(dados.get("motivo"))


def _pausa(resultado: InputRequiredResult, politica: str) -> Resultado:
    pedidos = resultado.input_requests or {}
    if len(pedidos) != 1 or not resultado.request_state:
        return FalhaProtocolo(ENTRADA_INESPERADA)
    chave, pedido = next(iter(pedidos.items()))
    params = pedido.params if isinstance(pedido, ElicitRequest) else None
    if params is None or getattr(params, "mode", "form") != "form":
        return FalhaProtocolo(ENTRADA_INESPERADA)
    campo = (params.requested_schema.get("properties") or {}).get("sala") or {}
    alternativas = campo.get("enum") or ([campo["const"]] if "const" in campo else [])
    if not alternativas:
        return FalhaProtocolo(ENTRADA_INESPERADA)
    return Pausada(chave, tuple(str(a) for a in alternativas), politica, resultado.request_state)


class HostMCP:
    """MCP client side of the agent. Every request is self-contained (no session).

    A fresh SDK `Client` is opened per operation: with the protocol version
    pinned there is no handshake, and a transport failure (the SDK tears the
    whole client down on a connection error) stays confined to one operation.
    """

    def __init__(self, url: str) -> None:
        self._url = url

    async def reservar(self, argumentos: dict[str, str], trace_id: str) -> Resultado:
        """Discover the tools, read the policy, then call `reservar_sala` once."""

        async def corpo(cliente: Client) -> Resultado:
            await _exigir_ferramenta(cliente, trace_id)
            politica = await _ler_politica(cliente, trace_id)
            return classificar(await _chamar(cliente, argumentos, trace_id), politica)

        return await self._operacao(corpo)

    async def retomar(
        self,
        argumentos: dict[str, str],
        chave: str,
        resposta: ElicitResult,
        request_state: str,
        politica: str,
        trace_id: str,
    ) -> Resultado:
        """Re-send the original `tools/call` (new JSON-RPC id) with the answer and the echoed state."""

        async def corpo(cliente: Client) -> Resultado:
            # Listing first also primes the SDK's output-schema cache, which would
            # otherwise re-list on its own without this Task's trace context.
            await _exigir_ferramenta(cliente, trace_id)
            resultado = await _chamar(cliente, argumentos, trace_id, {chave: resposta}, request_state)
            return classificar(resultado, politica)

        return await self._operacao(corpo)

    async def _operacao(self, corpo: Callable[[Client], Awaitable[Resultado]]) -> Resultado:
        try:
            async with _ClienteSoFormulario(self._url, mode=PROTOCOLO, client_info=INFO_DO_CLIENTE, cache=None) as cliente:
                try:
                    return await corpo(cliente)
                except _Falha as falha:
                    return falha.resultado
                except MCPError as erro:
                    return FalhaProtocolo(f"Erro MCP {erro.error.code}: {erro.error.message}")
        except Exception:
            logger.exception("MCP request failed")
            return FalhaProtocolo(SERVIDOR_INDISPONIVEL)


async def _exigir_ferramenta(cliente: Client, trace_id: str) -> None:
    lista = await cliente.list_tools(meta=_meta(trace_id))
    if FERRAMENTA not in {t.name for t in lista.tools}:
        raise _Falha(FalhaProtocolo(FERRAMENTA_AUSENTE))


async def _ler_politica(cliente: Client, trace_id: str) -> str:
    leitura = await cliente.read_resource(URI_POLITICA, meta=_meta(trace_id))
    texto = next((c.text for c in leitura.contents if getattr(c, "text", None)), "")
    try:
        return versao_da_politica(texto)
    except ValueError as erro:
        raise _Falha(FalhaProtocolo(str(erro))) from None


async def _chamar(
    cliente: Client,
    argumentos: dict[str, str],
    trace_id: str,
    respostas: dict[str, ElicitResult] | None = None,
    request_state: str | None = None,
) -> CallToolResult | InputRequiredResult:
    return await cliente.session.call_tool(
        FERRAMENTA,
        argumentos,
        input_responses=respostas,
        request_state=request_state,
        meta=_meta(trace_id),
        allow_input_required=True,
    )


def _meta(trace_id: str) -> dict[str, str]:
    return {"traceparent": traceparent_filho(trace_id)}
