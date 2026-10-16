"""Starlette app of the agent: Agent Card, JSON-RPC endpoint and in-memory Tasks."""

from __future__ import annotations

from typing import Any

from a2a.server.agent_execution import RequestContext, SimpleRequestContextBuilder
from a2a.server.context import ServerCallContext
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import DefaultServerCallContextBuilder, create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore, TaskStore
from a2a.server.agent_execution.active_task import TERMINAL_TASK_STATES
from a2a.types import Task, TaskState
from a2a.utils.errors import UnsupportedOperationError
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
    """Continuations: refuse a terminal Task up front, and keep the Task's `contextId`.

    The SDK also refuses terminal Tasks, but only after spinning up an active
    task whose event dispatcher is then left pending; checking here, before
    that, gives the same -32004 error without the leak.
    """

    def __init__(self, tarefas: TaskStore) -> None:
        super().__init__(should_populate_referred_tasks=False, task_store=tarefas)
        self._tarefas = tarefas

    async def build(self, context: ServerCallContext, params: Any = None, task_id: str | None = None,
                    context_id: str | None = None, task: Task | None = None) -> RequestContext:
        existente = (task or await self._tarefas.get(task_id, context)) if task_id else None
        if existente is not None and existente.status.state in TERMINAL_TASK_STATES:
            estado = TaskState.Name(existente.status.state)
            raise UnsupportedOperationError(message=f"Task {task_id} is in terminal state: {estado}")
        if params is not None and existente is not None and not context_id:
            context_id = existente.context_id
            params.message.context_id = context_id
        return await super().build(context, params, task_id, context_id, task)


def com_historico_completo(task: Task) -> Task:
    """Copy of `task` whose history holds every message once, the current status message included.

    The SDK only moves the status message into `history` when the next user
    message arrives, so a final message would otherwise never reach it.
    """
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
    return copia


class TarefasComHistoricoCompleto(InMemoryTaskStore):
    async def save(self, task: Task, context: ServerCallContext) -> None:
        await super().save(com_historico_completo(task), context)


class TratadorComHistoricoCompleto(DefaultRequestHandler):
    """`SendMessage` answers with the same history `GetTask` will show."""

    async def on_message_send(self, params: Any, context: ServerCallContext) -> Any:
        resultado = await super().on_message_send(params, context)
        return com_historico_completo(resultado) if isinstance(resultado, Task) else resultado


def criar_app(host: HostMCP, url_publica: str) -> Starlette:
    cartao = criar_cartao(url_publica)
    tarefas = TarefasComHistoricoCompleto()
    tratador = TratadorComHistoricoCompleto(
        agent_executor=ExecutorDeReservas(host),
        task_store=tarefas,
        agent_card=cartao,
        request_context_builder=ContinuacaoHerdaContexto(tarefas),
    )
    rotas = create_agent_card_routes(cartao) + create_jsonrpc_routes(
        tratador, rpc_url=CAMINHO_A2A, context_builder=ContextoComVersaoPadrao()
    )
    return Starlette(routes=rotas)
