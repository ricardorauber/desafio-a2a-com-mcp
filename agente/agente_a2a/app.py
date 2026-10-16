"""Starlette app of the agent: Agent Card, JSON-RPC endpoint and in-memory Tasks."""

from __future__ import annotations

from typing import Any

from a2a.server.agent_execution import RequestContext, SimpleRequestContextBuilder
from a2a.server.context import ServerCallContext
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import DefaultServerCallContextBuilder, create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore, TaskStore
from a2a.types import Task
from starlette.applications import Starlette
from starlette.requests import Request

from agente_a2a.cartao import CAMINHO_A2A, criar_cartao
from agente_a2a.executor import ExecutorDeReservas
from agente_a2a.host_mcp import HostMCP

VERSAO_A2A = "1.0"


class ContextoComVersaoPadrao(DefaultServerCallContextBuilder):
    """Treat a request without `A2A-Version` as 1.0 (the SDK would assume 0.3 and refuse it)."""

    def build(self, request: Request) -> ServerCallContext:
        contexto = super().build(request)
        contexto.state.setdefault("headers", {}).setdefault("a2a-version", VERSAO_A2A)
        return contexto


class ContinuacaoHerdaContexto(SimpleRequestContextBuilder):
    """A continuation that names only the `taskId` keeps the Task's `contextId`."""

    def __init__(self, tarefas: TaskStore) -> None:
        super().__init__(should_populate_referred_tasks=False, task_store=tarefas)
        self._tarefas = tarefas

    async def build(self, context: ServerCallContext, params: Any = None, task_id: str | None = None,
                    context_id: str | None = None, task: Task | None = None) -> RequestContext:
        if params is not None and task_id and not context_id:
            existente = task or await self._tarefas.get(task_id, context)
            if existente is not None:
                context_id = existente.context_id
                params.message.context_id = context_id
        return await super().build(context, params, task_id, context_id, task)


class TarefasComHistoricoCompleto(InMemoryTaskStore):
    """Keep every status message in the Task history exactly once.

    The SDK only moves the status message into `history` when the next user
    message arrives, so a final message would otherwise never reach it.
    """

    async def save(self, task: Task, context: ServerCallContext) -> None:
        copia = Task()
        copia.CopyFrom(task)
        vistos: set[str] = set()
        mensagens = []
        for mensagem in copia.history:
            if mensagem.message_id not in vistos:
                vistos.add(mensagem.message_id)
                mensagens.append(mensagem)
        if copia.status.HasField("message") and copia.status.message.message_id not in vistos:
            mensagens.append(copia.status.message)
        del copia.history[:]
        copia.history.extend(mensagens)
        await super().save(copia, context)


def criar_app(host: HostMCP, url_publica: str) -> Starlette:
    cartao = criar_cartao(url_publica)
    tarefas = TarefasComHistoricoCompleto()
    tratador = DefaultRequestHandler(
        agent_executor=ExecutorDeReservas(host),
        task_store=tarefas,
        agent_card=cartao,
        request_context_builder=ContinuacaoHerdaContexto(tarefas),
    )
    rotas = create_agent_card_routes(cartao) + create_jsonrpc_routes(
        tratador, rpc_url=CAMINHO_A2A, context_builder=ContextoComVersaoPadrao()
    )
    return Starlette(routes=rotas)
