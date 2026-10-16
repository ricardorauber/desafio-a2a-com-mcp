import pytest
from a2a.server.context import ServerCallContext
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import Message, Part, Role, SendMessageRequest, Task, TaskState, TaskStatus
from a2a.utils.errors import UnsupportedOperationError

from apoio_agente import estado, tarefa
from agente_a2a.app import ContinuacaoHerdaContexto
from agente_a2a.host_mcp import Concluida, FalhaFerramenta, Pausada
from agente_a2a.ponte import Pausas, TarefaPausada

PEDIDO = "reservar sala=sala-garagem inicio=2026-11-03T14:00:00-03:00 fim=2026-11-03T15:00:00-03:00 responsavel=Marty"
PAUSA = Pausada("escolha_de_sala", ("sala-fusca",), "2026-11-01", "v1.ESTADO")


def test_cancel_of_a_paused_task(a2a_com):
    pausas = Pausas()
    a2a, host = a2a_com(PAUSA, pausas=pausas)
    task_id = tarefa(a2a.enviar(PEDIDO))["id"]
    assert pausas.obter(task_id) is not None
    resposta = a2a.rpc("CancelTask", {"id": task_id})
    assert estado(resposta) == "TASK_STATE_CANCELED"
    assert "error" in a2a.enviar("escolha=sala-fusca", task_id=task_id)
    assert len(host.chamadas) == 1
    assert pausas.obter(task_id) is None


async def test_cancel_waits_for_the_running_continuation():
    import asyncio

    from agente_a2a.executor import ExecutorDeReservas

    pausas = Pausas()
    pausas.guardar("t1", TarefaPausada({}, "k", ("sala-fusca",), "trace", "v", "v1.ESTADO"))
    assert pausas.reivindicar("t1")
    ordem = []

    async def continuacao():
        await asyncio.sleep(0.02)
        ordem.append("continuacao terminou")
        pausas.liberar("t1")

    class Contexto:
        task_id = "t1"

    async def cancelar():
        await ExecutorDeReservas(host=None, pausas=pausas).cancel(Contexto(), None)
        ordem.append("cancel voltou")

    await asyncio.gather(continuacao(), cancelar())
    assert ordem == ["continuacao terminou", "cancel voltou"]
    assert pausas.obter("t1") is None


def test_cancel_of_a_completed_task_is_refused(a2a_com):
    a2a, _ = a2a_com(Concluida({"reserva": "res-0003", "sala": "sala-garagem"}, "2026-11-01"))
    task_id = tarefa(a2a.enviar(PEDIDO))["id"]
    assert "error" in a2a.rpc("CancelTask", {"id": task_id})
    assert tarefa(a2a.obter(task_id))["status"]["state"] == "TASK_STATE_COMPLETED"


async def test_continuation_of_a_working_task_is_refused():
    tarefas = InMemoryTaskStore()
    contexto = ServerCallContext()
    await tarefas.save(Task(id="t1", context_id="c1", status=TaskStatus(state=TaskState.TASK_STATE_WORKING)), contexto)
    mensagem = Message(message_id="m1", role=Role.ROLE_USER, parts=[Part(text="escolha=sala-fusca")], task_id="t1")
    with pytest.raises(UnsupportedOperationError, match="not waiting for input"):
        await ContinuacaoHerdaContexto(tarefas, Pausas()).build(contexto, SendMessageRequest(message=mensagem), task_id="t1")


async def test_second_continuation_of_a_claimed_task_is_refused():
    tarefas, pausas = InMemoryTaskStore(), Pausas()
    contexto = ServerCallContext()
    await tarefas.save(Task(id="t1", context_id="c1", status=TaskStatus(state=TaskState.TASK_STATE_INPUT_REQUIRED)), contexto)
    pausas.guardar("t1", TarefaPausada({}, "k", ("sala-fusca",), "trace", "v", "v1.ESTADO"))
    construtor = ContinuacaoHerdaContexto(tarefas, pausas)

    def pedido(n):
        mensagem = Message(message_id=f"m{n}", role=Role.ROLE_USER, parts=[Part(text="escolha=sala-fusca")], task_id="t1")
        return SendMessageRequest(message=mensagem)

    contexto_da_tarefa = await construtor.build(contexto, pedido(1), task_id="t1")
    assert contexto_da_tarefa.context_id == "c1"
    with pytest.raises(UnsupportedOperationError, match="not waiting for input"):
        await construtor.build(contexto, pedido(2), task_id="t1")


def test_locks_and_pauses_are_released(a2a_com):
    pausas = Pausas()
    a2a, _ = a2a_com(FalhaFerramenta("x"), PAUSA, Concluida({"reserva": "res-0003", "sala": "sala-fusca"}, "2026-11-01"), pausas=pausas)
    a2a.enviar("pedido torto")
    a2a.enviar(PEDIDO)
    pausada = tarefa(a2a.enviar(PEDIDO))["id"]
    assert set(pausas._pausadas) == {pausada}
    a2a.enviar("escolha=sala-fusca", task_id=pausada)
    assert pausas._pausadas == {} and pausas._em_andamento == {}
