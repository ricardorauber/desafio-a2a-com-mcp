"""Task state machine of the agent: A2A outside, MCP host inside."""

from __future__ import annotations

import json
import logging

from a2a.helpers.proto_helpers import new_task_from_user_message
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import Part
from a2a.utils.errors import UnsupportedOperationError
from mcp_types import ElicitResult

from agente_a2a.host_mcp import Concluida, FalhaFerramenta, FalhaProtocolo, HostMCP, Pausada, Recusada, Resultado
from agente_a2a.pedido import PEDIDO_INVALIDO, interpretar_pedido
from agente_a2a.ponte import RECUSAR, Pausas, TarefaPausada, interpretar_escolha, linha_de_alternativas
from agente_a2a.trace import trace_id_de

logger = logging.getLogger(__name__)

NOME_DO_ARTIFACT = "reserva"
RESERVA_RECUSADA = "Reserva recusada."
CAMPOS_DO_ARTIFACT = ("reserva", "sala", "inicio", "fim", "responsavel")


def conteudo_do_artifact(resultado: Concluida) -> str:
    reserva = {campo: resultado.dados.get(campo) for campo in CAMPOS_DO_ARTIFACT}
    reserva["politica"] = resultado.politica
    return json.dumps(reserva, ensure_ascii=False)


def _traceparent(context: RequestContext) -> str | None:
    estado = context.call_context.state if context.call_context is not None else {}
    return (estado.get("headers") or {}).get("traceparent")


class ExecutorDeReservas(AgentExecutor):
    def __init__(self, host: HostMCP, pausas: Pausas | None = None) -> None:
        self._host = host
        self._pausas = pausas or Pausas()

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        tarefa = TaskUpdater(event_queue, context.task_id, context.context_id)
        if context.current_task is None:
            await event_queue.enqueue_event(new_task_from_user_message(context.message))
            await self._iniciar(context, tarefa)
            return
        try:
            await self._continuar(context, tarefa)
        finally:
            # Claimed by the request-context builder before this continuation started.
            self._pausas.liberar(context.task_id)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Called by the SDK only while work is running for the Task (a paused Task is closed by the SDK itself).

        Waiting for the running continuation keeps its MCP retry and the Task
        outcome consistent; the SDK then stops the producer and marks the Task
        CANCELED unless it already reached a terminal state.
        """
        await self._pausas.aguardar(context.task_id)
        self._pausas.descartar(context.task_id)

    async def _iniciar(self, context: RequestContext, tarefa: TaskUpdater) -> None:
        await tarefa.start_work()
        pedido = interpretar_pedido(context.get_user_input())
        if pedido is None:
            await self._falhar(tarefa, PEDIDO_INVALIDO)
            return
        trace_id = trace_id_de(_traceparent(context))
        logger.info("task=%s trace_id=%s reservar_sala sala=%s", context.task_id, trace_id, pedido["sala"])
        resultado = await self._host.reservar(pedido, trace_id)
        await self._encerrar(tarefa, resultado, pedido, trace_id)

    async def _continuar(self, context: RequestContext, tarefa: TaskUpdater) -> None:
        """The bridge back: an A2A answer becomes the MCP retry of the paused request."""
        pausa = self._pausas.obter(context.task_id)
        if pausa is None:
            raise UnsupportedOperationError(message=f"Task {context.task_id} is not waiting for input")
        escolha = interpretar_escolha(context.get_user_input())
        if escolha == RECUSAR:
            resposta = ElicitResult(action="decline")
        elif escolha in pausa.alternativas:
            resposta = ElicitResult(action="accept", content={"sala": escolha})
        else:
            await tarefa.requires_input(tarefa.new_agent_message([Part(text=linha_de_alternativas(pausa.alternativas))]))
            return
        await tarefa.start_work()
        logger.info("task=%s trace_id=%s retry reservar_sala acao=%s", context.task_id, pausa.trace_id, resposta.action)
        resultado = await self._host.retomar(
            pausa.argumentos, pausa.chave, resposta, pausa.request_state, pausa.politica, pausa.trace_id
        )
        await self._encerrar(tarefa, resultado, pausa.argumentos, pausa.trace_id)

    async def _encerrar(self, tarefa: TaskUpdater, resultado: Resultado, argumentos: dict[str, str], trace_id: str) -> None:
        if isinstance(resultado, Pausada):
            # The bridge: MCP input_required becomes an interrupted A2A Task, and the
            # opaque requestState stays here, bound to this Task, never sent out.
            self._pausas.guardar(
                tarefa.task_id,
                TarefaPausada(
                    argumentos=argumentos,
                    chave=resultado.chave,
                    alternativas=resultado.alternativas,
                    trace_id=trace_id,
                    politica=resultado.politica,
                    request_state=resultado.request_state,
                ),
            )
            await tarefa.requires_input(tarefa.new_agent_message([Part(text=linha_de_alternativas(resultado.alternativas))]))
            return
        self._pausas.descartar(tarefa.task_id)
        if isinstance(resultado, Concluida):
            await tarefa.add_artifact([Part(text=conteudo_do_artifact(resultado))], name=NOME_DO_ARTIFACT)
            confirmacao = f"Reserva {resultado.dados.get('reserva')} confirmada na {resultado.dados.get('sala')}."
            await tarefa.complete(tarefa.new_agent_message([Part(text=confirmacao)]))
        elif isinstance(resultado, Recusada):
            await tarefa.cancel(tarefa.new_agent_message([Part(text=RESERVA_RECUSADA)]))
        else:
            await self._falhar(tarefa, resultado.texto)

    @staticmethod
    async def _falhar(tarefa: TaskUpdater, texto: str) -> None:
        await tarefa.failed(tarefa.new_agent_message([Part(text=texto)]))
