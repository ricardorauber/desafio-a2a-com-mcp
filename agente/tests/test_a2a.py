import json

from apoio_agente import estado, mensagem, tarefa
from agente_a2a.host_mcp import Concluida, FalhaFerramenta, FalhaProtocolo

PEDIDO = "reservar sala=sala-porao inicio=2026-11-03T09:00:00-03:00 fim=2026-11-03T10:00:00-03:00 responsavel=Doc"
TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
RESERVA = {
    "reserva": "res-0003",
    "reservado": True,
    "sala": "sala-porao",
    "inicio": "2026-11-03T09:00:00-03:00",
    "fim": "2026-11-03T10:00:00-03:00",
    "responsavel": "Doc",
    "politica": "2026-11-01",
    "motivo": None,
}


def test_free_room_completes_with_the_reserva_artifact(a2a_com):
    a2a, host = a2a_com(Concluida(RESERVA, "2026-11-01"))
    resposta = a2a.enviar(PEDIDO, traceparent=TRACEPARENT)
    t = tarefa(resposta)
    assert estado(resposta) == "TASK_STATE_COMPLETED"
    assert t["id"] and t["contextId"]
    assert mensagem(resposta) == "Reserva res-0003 confirmada na sala-porao."
    [artifact] = t["artifacts"]
    assert artifact["name"] == "reserva"
    assert json.loads(artifact["parts"][0]["text"]) == {
        "reserva": "res-0003",
        "sala": "sala-porao",
        "inicio": "2026-11-03T09:00:00-03:00",
        "fim": "2026-11-03T10:00:00-03:00",
        "responsavel": "Doc",
        "politica": "2026-11-01",
    }
    [(_, (argumentos, trace_id))] = host.chamadas
    assert argumentos == {k: RESERVA[k] for k in ("sala", "inicio", "fim", "responsavel")}
    assert trace_id == "4bf92f3577b34da6a3ce929d0e0e4736"


def test_get_task_reflects_the_current_state(a2a_com):
    a2a, _ = a2a_com(Concluida(RESERVA, "2026-11-01"))
    t = tarefa(a2a.enviar(PEDIDO))
    obtida = tarefa(a2a.obter(t["id"]))
    assert (obtida["id"], obtida["contextId"], obtida["status"]["state"]) == (t["id"], t["contextId"], "TASK_STATE_COMPLETED")
    assert obtida["artifacts"][0]["name"] == "reserva"


def test_tool_and_protocol_failures_end_failed_with_the_text_in_history(a2a_com):
    texto = "Error executing tool reservar_sala: Sala inexistente: sala-inexistente"
    a2a, _ = a2a_com(FalhaFerramenta(texto), FalhaProtocolo("Servidor MCP indisponivel"))
    for esperado in (texto, "Servidor MCP indisponivel"):
        resposta = a2a.enviar(PEDIDO)
        assert estado(resposta) == "TASK_STATE_FAILED"
        assert mensagem(resposta) == esperado
        assert [p["text"] for m in tarefa(resposta)["history"] for p in m["parts"]].count(esperado) == 1
        historico = tarefa(a2a.obter(tarefa(resposta)["id"]))["history"]
        textos = [p["text"] for m in historico for p in m["parts"]]
        assert textos.count(esperado) == 1
        assert [m["role"] for m in historico] == ["ROLE_USER", "ROLE_AGENT"]


def test_malformed_request_fails_without_calling_mcp(a2a_com):
    a2a, host = a2a_com()
    resposta = a2a.enviar("reservar a sala-porao amanha")
    assert estado(resposta) == "TASK_STATE_FAILED"
    assert mensagem(resposta).startswith("Pedido invalido: use reservar sala=<id>")
    assert host.chamadas == []


def test_terminal_task_refuses_new_messages(a2a_com):
    a2a, host = a2a_com(Concluida(RESERVA, "2026-11-01"))
    t = tarefa(a2a.enviar(PEDIDO))
    resposta = a2a.enviar("escolha=sala-fusca", task_id=t["id"])
    assert "error" in resposta
    assert tarefa(a2a.obter(t["id"]))["status"]["state"] == "TASK_STATE_COMPLETED"
    assert len(host.chamadas) == 1


def test_state_sequence_is_submitted_working_completed(a2a_com, monkeypatch):
    from agente_a2a.app import TarefasComHistoricoCompleto

    vistos = []
    original = TarefasComHistoricoCompleto.save

    async def registrar(self, task, context):
        vistos.append(task.status.state)
        await original(self, task, context)

    monkeypatch.setattr(TarefasComHistoricoCompleto, "save", registrar)
    a2a, _ = a2a_com(Concluida(RESERVA, "2026-11-01"))
    a2a.enviar(PEDIDO)
    from a2a.types import TaskState

    nomes = [TaskState.Name(s) for s in vistos]
    unicos = [s for i, s in enumerate(nomes) if i == 0 or s != nomes[i - 1]]
    assert unicos == ["TASK_STATE_SUBMITTED", "TASK_STATE_WORKING", "TASK_STATE_COMPLETED"]
