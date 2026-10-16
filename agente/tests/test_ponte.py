import asyncio
import json

import pytest
from mcp_types import ElicitResult

from apoio_agente import estado, mensagem, tarefa
from agente_a2a.host_mcp import Concluida, FalhaFerramenta, FalhaProtocolo, Pausada, Recusada
from agente_a2a.ponte import Pausas, TarefaPausada, interpretar_escolha, linha_de_alternativas

PEDIDO = "reservar sala=sala-garagem inicio=2026-11-03T14:00:00-03:00 fim=2026-11-03T15:00:00-03:00 responsavel=Marty"
ARGUMENTOS = {
    "sala": "sala-garagem",
    "inicio": "2026-11-03T14:00:00-03:00",
    "fim": "2026-11-03T15:00:00-03:00",
    "responsavel": "Marty",
}
TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
ESTADO = "v1.SEGREDO-OPACO-DO-SERVIDOR-MCP-0123456789"


def pausa(alternativas=("sala-fusca", "sala-mirante"), estado=ESTADO):
    return Pausada("escolha_de_sala", alternativas, "2026-11-01", estado)


def reserva(sala):
    return Concluida({"reserva": "res-0004", "reservado": True, **ARGUMENTOS, "sala": sala}, "2026-11-01")


def test_pause_line_format():
    assert linha_de_alternativas(("sala-fusca", "sala-mirante")) == "alternativas: sala-fusca, sala-mirante"
    assert linha_de_alternativas(("sala-mirante",)) == "alternativas: sala-mirante"


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [("escolha=sala-fusca", "sala-fusca"), (" escolha=recusar ", "recusar"), ("escolha = sala-fusca", None), ("sala-fusca", None), ("", None)],
)
def test_choice_parsing(texto, esperado):
    assert interpretar_escolha(texto) == esperado


def test_pause_then_accept_completes_with_the_chosen_room(a2a_com):
    a2a, host = a2a_com(pausa(), reserva("sala-mirante"))
    resposta = a2a.enviar(PEDIDO, traceparent=TRACEPARENT)
    assert estado(resposta) == "TASK_STATE_INPUT_REQUIRED"
    assert mensagem(resposta) == "alternativas: sala-fusca, sala-mirante"
    assert [p["text"] for m in tarefa(resposta)["history"] for p in m["parts"]] == [PEDIDO, "alternativas: sala-fusca, sala-mirante"]
    task_id = tarefa(resposta)["id"]
    assert tarefa(a2a.obter(task_id))["status"]["state"] == "TASK_STATE_INPUT_REQUIRED"

    final = a2a.enviar("escolha=sala-mirante", task_id=task_id)
    assert estado(final) == "TASK_STATE_COMPLETED"
    assert json.loads(tarefa(final)["artifacts"][0]["parts"][0]["text"])["sala"] == "sala-mirante"
    textos = [p["text"] for m in tarefa(final)["history"] for p in m["parts"]]
    assert textos == [PEDIDO, "alternativas: sala-fusca, sala-mirante", "escolha=sala-mirante", "Reserva res-0004 confirmada na sala-mirante."]
    assert tarefa(final)["contextId"] == tarefa(resposta)["contextId"]

    (_, (args, trace)), (_, retry) = host.chamadas
    assert args == ARGUMENTOS
    assert retry == (
        ARGUMENTOS,
        "escolha_de_sala",
        ElicitResult(action="accept", content={"sala": "sala-mirante"}),
        ESTADO,
        "2026-11-01",
        "4bf92f3577b34da6a3ce929d0e0e4736",
    )
    assert trace == "4bf92f3577b34da6a3ce929d0e0e4736"


def test_refusal_declines_and_cancels(a2a_com):
    a2a, host = a2a_com(pausa(), Recusada("recusado"))
    task_id = tarefa(a2a.enviar(PEDIDO))["id"]
    final = a2a.enviar("escolha=recusar", task_id=task_id)
    assert estado(final) == "TASK_STATE_CANCELED"
    assert mensagem(final) == "Reserva recusada."
    assert host.chamadas[1][1][2] == ElicitResult(action="decline")


@pytest.mark.parametrize("texto", ["escolha=sala-aquario", "quero a fusca"])
def test_invalid_choice_keeps_the_pause_without_calling_mcp(a2a_com, texto):
    a2a, host = a2a_com(pausa())
    task_id = tarefa(a2a.enviar(PEDIDO))["id"]
    resposta = a2a.enviar(texto, task_id=task_id)
    assert estado(resposta) == "TASK_STATE_INPUT_REQUIRED"
    assert mensagem(resposta) == "alternativas: sala-fusca, sala-mirante"
    assert len(host.chamadas) == 1


def test_server_asking_again_replaces_the_stored_pause(a2a_com):
    novo_estado = "v1.OUTRO-ESTADO"
    a2a, host = a2a_com(pausa(), pausa(("sala-mirante",), novo_estado), reserva("sala-mirante"))
    task_id = tarefa(a2a.enviar(PEDIDO))["id"]
    resposta = a2a.enviar("escolha=sala-fusca", task_id=task_id)
    assert estado(resposta) == "TASK_STATE_INPUT_REQUIRED"
    assert mensagem(resposta) == "alternativas: sala-mirante"
    assert estado(a2a.enviar("escolha=sala-mirante", task_id=task_id)) == "TASK_STATE_COMPLETED"
    assert host.chamadas[2][1][3] == novo_estado


@pytest.mark.parametrize("falha", [FalhaFerramenta("Error executing tool reservar_sala: x"), FalhaProtocolo("Erro MCP -32602: Invalid or expired requestState")])
def test_retry_failures_end_failed(a2a_com, falha):
    a2a, _ = a2a_com(pausa(), falha)
    task_id = tarefa(a2a.enviar(PEDIDO))["id"]
    final = a2a.enviar("escolha=sala-fusca", task_id=task_id)
    assert estado(final) == "TASK_STATE_FAILED"
    assert mensagem(final) == falha.texto


def test_two_paused_tasks_resume_with_their_own_state(a2a_com):
    a2a, host = a2a_com(pausa(estado="v1.ESTADO-A"), pausa(estado="v1.ESTADO-B"), reserva("sala-mirante"), reserva("sala-mirante"))
    a = tarefa(a2a.enviar(PEDIDO))["id"]
    b = tarefa(a2a.enviar(PEDIDO.replace("Marty", "George")))["id"]
    a2a.enviar("escolha=sala-mirante", task_id=b)
    a2a.enviar("escolha=sala-mirante", task_id=a)
    retries = [c for nome, c in host.chamadas if nome == "retomar"]
    assert [(r[0]["responsavel"], r[3]) for r in retries] == [("George", "v1.ESTADO-B"), ("Marty", "v1.ESTADO-A")]


def test_store_is_emptied_on_terminal_states():
    pausas = Pausas()
    pausas.guardar("t", TarefaPausada(ARGUMENTOS, "k", ("a",), "trace", "v", ESTADO))
    assert pausas.obter("t") is not None
    assert ESTADO not in repr(pausas.obter("t"))
    pausas.descartar("t")
    assert pausas.obter("t") is None


async def test_lock_serializes_continuations_of_one_task():
    pausas = Pausas()
    ordem = []

    async def trabalho(n):
        async with pausas.trava("t"):
            ordem.append(("inicio", n))
            await asyncio.sleep(0.01)
            ordem.append(("fim", n))

    await asyncio.gather(trabalho(1), trabalho(2))
    assert ordem == [("inicio", 1), ("fim", 1), ("inicio", 2), ("fim", 2)]


def test_request_state_never_reaches_the_a2a_client(a2a_com):
    a2a, _ = a2a_com(pausa(), Recusada("recusado"))
    task_id = tarefa(a2a.enviar(PEDIDO))["id"]
    a2a.obter(task_id)
    a2a.enviar("escolha=sala-aquario", task_id=task_id)
    a2a.enviar("escolha=recusar", task_id=task_id)
    a2a.obter(task_id)
    assert a2a.corpos and not any(ESTADO[:20] in corpo for corpo in a2a.corpos)
