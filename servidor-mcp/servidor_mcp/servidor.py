"""MCP server of the room booking domain (Streamable HTTP, revision 2026-07-28)."""

from __future__ import annotations

from pydantic import BaseModel
from starlette.types import ASGIApp

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.request_state import RequestStateSecurity

from servidor_mcp.dominio import Agenda, ErroDeDominio
from servidor_mcp.log import RegistroDeRequests

NOME = "central-de-salas"
VERSAO = "1.0.0"
URI_POLITICA = "politica://uso"


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
    mcp = MCPServer(NOME, version=VERSAO, request_state_security=seguranca)

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

    @mcp.tool(description="Reserva uma sala. Se o intervalo estiver ocupado, pergunta qual alternativa usar.")
    def reservar_sala(sala: str, inicio: str, fim: str, responsavel: str) -> ReservaOut:
        validar(sala, inicio, fim)
        reserva = agenda.reservar(sala, inicio, fim, responsavel)
        return ReservaOut(
            reserva=reserva.id,
            sala=reserva.sala,
            inicio=reserva.inicio,
            fim=reserva.fim,
            responsavel=reserva.responsavel,
            politica=agenda.versao_politica,
        )

    @mcp.resource(URI_POLITICA, name="politica-de-uso", description="Politica de uso das salas.", mime_type="text/markdown")
    def politica() -> str:
        return agenda.politica

    return mcp


def criar_app(agenda: Agenda | None = None, seguranca: RequestStateSecurity | None = None) -> ASGIApp:
    """Stateless JSON Streamable HTTP app at `/mcp`, wrapped by the stderr request log."""
    servidor = criar_servidor(agenda or Agenda.carregar(), seguranca)
    app = servidor.streamable_http_app(streamable_http_path="/mcp", stateless_http=True, json_response=True)
    return RegistroDeRequests(app)
