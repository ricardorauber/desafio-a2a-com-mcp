"""MCP server of the room booking domain (Streamable HTTP, revision 2026-07-28)."""

from __future__ import annotations

import json
import secrets
from typing import Any

from mcp_types import (
    MISSING_REQUIRED_CLIENT_CAPABILITY,
    ClientCapabilities,
    ElicitationCapability,
    ElicitRequest,
    ElicitRequestFormParams,
    ElicitResult,
    FormElicitationCapability,
    InputRequiredResult,
    MissingRequiredClientCapabilityErrorData,
)
from pydantic import BaseModel
from starlette.types import ASGIApp

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.request_state import RequestStateSecurity
from mcp.shared.exceptions import MCPError

from servidor_mcp.dominio import ERRO_SEM_ALTERNATIVAS, Agenda, ErroDeDominio, Reserva
from servidor_mcp.log import RegistroDeRequests

NOME = "central-de-salas"
VERSAO = "1.0.0"
URI_POLITICA = "politica://uso"
CHAVE_ESCOLHA = "escolha_de_sala"
PERGUNTA = "A sala pedida esta ocupada nesse intervalo. Escolha uma alternativa."
MOTIVOS_DE_RECUSA = {"decline": "recusado", "cancel": "cancelado"}


class SalaOut(BaseModel):
    id: str
    nome: str
    capacidade: int
    recursos: list[str]


class ListaDeSalas(BaseModel):
    salas: list[SalaOut]


class ConflitoOut(BaseModel):
    id: str
    inicio: str
    fim: str
    responsavel: str


class Disponibilidade(BaseModel):
    sala: str
    livre: bool
    conflitos: list[ConflitoOut]


class ReservaOut(BaseModel):
    reserva: str | None = None
    reservado: bool = True
    sala: str | None = None
    inicio: str | None = None
    fim: str | None = None
    responsavel: str | None = None
    politica: str | None = None
    motivo: str | None = None


def criar_servidor(agenda: Agenda, seguranca: RequestStateSecurity | None = None) -> MCPServer:
    # Subscriptions are out of scope: without `subscriptions/listen` the server
    # advertises neither `resources.subscribe` nor `listChanged`.
    mcp = MCPServer(NOME, version=VERSAO, request_state_security=seguranca, subscriptions=False)

    def validar(sala: str, inicio: str, fim: str):
        try:
            return agenda.validar(sala, inicio, fim)
        except ErroDeDominio as erro:
            raise ToolError(str(erro)) from None

    @mcp.tool(description="Lista todas as salas com capacidade e recursos.")
    def listar_salas() -> ListaDeSalas:
        return ListaDeSalas(
            salas=[SalaOut(id=s.id, nome=s.nome, capacidade=s.capacidade, recursos=list(s.recursos)) for s in agenda.salas]
        )

    @mcp.tool(description="Diz se uma sala esta livre no intervalo, e quais reservas conflitam.")
    def consultar_disponibilidade(sala: str, inicio: str, fim: str) -> Disponibilidade:
        conflitos = agenda.conflitos(sala, validar(sala, inicio, fim))
        return Disponibilidade(
            sala=sala,
            livre=not conflitos,
            conflitos=[ConflitoOut(id=r.id, inicio=r.inicio, fim=r.fim, responsavel=r.responsavel) for r in conflitos],
        )

    def concluir(sala: str, inicio: str, fim: str, responsavel: str, origem: str | None = None) -> ReservaOut:
        return saida(agenda.reservar(sala, inicio, fim, responsavel, origem))

    def saida(reserva: Reserva) -> ReservaOut:
        return ReservaOut(
            reserva=reserva.id,
            sala=reserva.sala,
            inicio=reserva.inicio,
            fim=reserva.fim,
            responsavel=reserva.responsavel,
            politica=agenda.versao_politica,
        )

    def perguntar(
        pedido: dict[str, str], alternativas: list[str], ctx: Context, nonce: str | None = None
    ) -> InputRequiredResult:
        """End this round asking the client to pick an alternative; the whole request travels in the state."""
        if not alternativas:
            raise ToolError(ERRO_SEM_ALTERNATIVAS)
        exigir_elicitation_em_form(ctx)
        esquema = {
            "type": "object",
            "properties": {
                "sala": {
                    "type": "string",
                    "title": "Sala",
                    "description": "Sala alternativa escolhida",
                    "enum": alternativas,
                }
            },
            "required": ["sala"],
        }
        # The nonce names this request across rounds, so a replayed accept cannot book twice.
        estado = {
            "pedido": pedido,
            "alternativas": alternativas,
            "chave": CHAVE_ESCOLHA,
            "nonce": nonce or secrets.token_hex(16),
        }
        return InputRequiredResult(
            input_requests={
                CHAVE_ESCOLHA: ElicitRequest(params=ElicitRequestFormParams(message=PERGUNTA, requested_schema=esquema))
            },
            # Plaintext here; the SDK request-state boundary seals it on the way out.
            request_state=json.dumps(estado),
        )

    def retomar(estado: dict[str, Any], ctx: Context) -> ReservaOut | InputRequiredResult:
        """Finish a request rebuilt from the verified state; the re-sent arguments are never used."""
        pedido, alternativas, nonce = estado["pedido"], estado["alternativas"], estado["nonce"]
        resposta = (ctx.input_responses or {}).get(estado["chave"])
        if not isinstance(resposta, ElicitResult):
            return perguntar(pedido, alternativas, ctx, nonce)
        if resposta.action in MOTIVOS_DE_RECUSA:
            return ReservaOut(reservado=False, motivo=MOTIVOS_DE_RECUSA[resposta.action])
        ja_reservada = agenda.reserva_da_origem(nonce)
        if ja_reservada is not None:
            return saida(ja_reservada)
        escolhida = (resposta.content or {}).get("sala")
        if escolhida not in alternativas:
            return perguntar(pedido, alternativas, ctx, nonce)
        intervalo = validar(escolhida, pedido["inicio"], pedido["fim"])
        if agenda.conflitos(escolhida, intervalo):
            return perguntar(pedido, agenda.alternativas(pedido["sala"], intervalo), ctx, nonce)
        return concluir(escolhida, pedido["inicio"], pedido["fim"], pedido["responsavel"], nonce)

    @mcp.tool(description="Reserva uma sala. Se o intervalo estiver ocupado, pergunta qual alternativa usar.")
    def reservar_sala(
        sala: str, inicio: str, fim: str, responsavel: str, ctx: Context
    ) -> ReservaOut | InputRequiredResult:
        if ctx.request_state is not None:
            return retomar(json.loads(ctx.request_state), ctx)
        intervalo = validar(sala, inicio, fim)
        if agenda.conflitos(sala, intervalo):
            pedido = {"sala": sala, "inicio": inicio, "fim": fim, "responsavel": responsavel}
            return perguntar(pedido, agenda.alternativas(sala, intervalo), ctx)
        return concluir(sala, inicio, fim, responsavel)

    @mcp.resource(URI_POLITICA, name="politica-de-uso", description="Politica de uso das salas.", mime_type="text/markdown")
    def politica() -> str:
        return agenda.politica

    return mcp


def exigir_elicitation_em_form(ctx: Context) -> None:
    """Refuse with -32021 a client that did not declare form-mode elicitation in this request."""
    capacidades = ctx.client_capabilities
    elicitation = capacidades.elicitation if capacidades is not None else None
    if elicitation is not None and elicitation.form is not None:
        return
    exigidas = ClientCapabilities(elicitation=ElicitationCapability(form=FormElicitationCapability()))
    raise MCPError(
        code=MISSING_REQUIRED_CLIENT_CAPABILITY,
        message="O cliente nao declarou a capability de elicitation em form mode exigida por reservar_sala",
        data=MissingRequiredClientCapabilityErrorData(required_capabilities=exigidas).model_dump(
            by_alias=True, mode="json", exclude_none=True
        ),
    )


def criar_app(agenda: Agenda | None = None, seguranca: RequestStateSecurity | None = None) -> ASGIApp:
    """Stateless JSON Streamable HTTP app at `/mcp`, wrapped by the stderr request log."""
    servidor = criar_servidor(agenda or Agenda.carregar(), seguranca)
    app = servidor.streamable_http_app(streamable_http_path="/mcp", stateless_http=True, json_response=True)
    return RegistroDeRequests(app)
