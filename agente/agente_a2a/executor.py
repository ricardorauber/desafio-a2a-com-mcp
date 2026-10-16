"""Task state machine of the agent: A2A outside, MCP host inside."""

from __future__ import annotations

import json
import logging

from a2a.helpers.proto_helpers import new_task_from_user_message
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import Part

from agente_a2a.host_mcp import Concluida, FalhaFerramenta, FalhaProtocolo, HostMCP, Resultado
from agente_a2a.pedido import PEDIDO_INVALIDO, interpretar_pedido
from agente_a2a.trace import trace_id_de

logger = logging.getLogger(__name__)

NOME_DO_ARTIFACT = "reserva"
CAMPOS_DO_ARTIFACT = ("reserva", "sala", "inicio", "fim", "responsavel")


def conteudo_do_artifact(resultado: Concluida) -> str:
    reserva = {campo: resultado.dados.get(campo) for campo in CAMPOS_DO_ARTIFACT}
    reserva["politica"] = resultado.politica
    return json.dumps(reserva, ensure_ascii=False)


def _traceparent(context: RequestContext) -> str | None:
    estado = context.call_context.state if context.call_context is not None else {}
    return (estado.get("headers") or {}).get("traceparent")


class ExecutorDeReservas(AgentExecutor):
    def __init__(self, host: HostMCP) -> None:
        self._host = host

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        if context.current_task is None:
            await event_queue.enqueue_event(new_task_from_user_message(context.message))
        tarefa = TaskUpdater(event_queue, context.task_id, context.context_id)
        await tarefa.start_work()

        pedido = interpretar_pedido(context.get_user_input())
        if pedido is None:
            await self._falhar(tarefa, PEDIDO_INVALIDO)
            return
        trace_id = trace_id_de(_traceparent(context))
        logger.info("task=%s trace_id=%s reservar_sala sala=%s", context.task_id, trace_id, pedido["sala"])
        await self._encerrar(tarefa, await self._host.reservar(pedido, trace_id))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        await TaskUpdater(event_queue, context.task_id, context.context_id).cancel()

    async def _encerrar(self, tarefa: TaskUpdater, resultado: Resultado) -> None:
        if isinstance(resultado, Concluida):
            await tarefa.add_artifact([Part(text=conteudo_do_artifact(resultado))], name=NOME_DO_ARTIFACT)
            confirmacao = f"Reserva {resultado.dados.get('reserva')} confirmada na {resultado.dados.get('sala')}."
            await tarefa.complete(tarefa.new_agent_message([Part(text=confirmacao)]))
        elif isinstance(resultado, (FalhaFerramenta, FalhaProtocolo)):
            await self._falhar(tarefa, resultado.texto)
        else:
            raise NotImplementedError(type(resultado).__name__)

    @staticmethod
    async def _falhar(tarefa: TaskUpdater, texto: str) -> None:
        await tarefa.failed(tarefa.new_agent_message([Part(text=texto)]))
