import json
import secrets
import subprocess
import sys
import time

import pytest
from starlette.testclient import TestClient

from apoio_mcp import ClienteMCP, h, texto
from servidor_mcp.dominio import ERRO_SEM_ALTERNATIVAS, Agenda
from servidor_mcp.seguranca import SegredoInvalido, seguranca_do_ambiente
from servidor_mcp.servidor import CHAVE_ESCOLHA, criar_app

SEGREDO = secrets.token_hex(32)
CONFLITO = {"sala": "sala-garagem", "inicio": h("14:00"), "fim": h("15:00"), "responsavel": "Marty"}


def cliente(agenda=None):
    seguranca = seguranca_do_ambiente({"REQUEST_STATE_SECRET": SEGREDO})
    return TestClient(criar_app(agenda or Agenda.carregar(), seguranca), base_url="http://127.0.0.1:7301")


@pytest.fixture
def mcp():
    with cliente() as http:
        yield ClienteMCP(http)


def pausar(mcp, argumentos=CONFLITO):
    _, resposta = mcp.ferramenta("reservar_sala", argumentos)
    return resposta["result"]


def retomar(mcp, estado, resposta, argumentos=CONFLITO, chave=CHAVE_ESCOLHA):
    params = {"name": "reservar_sala", "arguments": argumentos, "inputResponses": {chave: resposta}, "requestState": estado}
    return mcp.chamar("tools/call", params, nome="reservar_sala")


def aceitar(sala):
    return {"action": "accept", "content": {"sala": sala}}


def test_conflict_returns_form_elicitation_with_ordered_alternatives(mcp):
    resultado = pausar(mcp)
    assert resultado["resultType"] == "input_required"
    assert list(resultado["inputRequests"]) == [CHAVE_ESCOLHA]
    pedido = resultado["inputRequests"][CHAVE_ESCOLHA]
    assert pedido["method"] == "elicitation/create"
    assert pedido["params"]["mode"] == "form"
    assert pedido["params"]["message"] == "A sala pedida esta ocupada nesse intervalo. Escolha uma alternativa."
    esquema = pedido["params"]["requestedSchema"]
    assert esquema["type"] == "object" and esquema["required"] == ["sala"]
    assert esquema["properties"]["sala"]["type"] == "string"
    assert esquema["properties"]["sala"]["enum"] == ["sala-fusca", "sala-mirante"]
    assert resultado["requestState"].startswith("v1.")
    assert "sala-garagem" not in resultado["requestState"]


def test_conflict_without_alternatives_is_a_tool_error(mcp):
    mcp.ferramenta("reservar_sala", {"sala": "sala-mirante", "inicio": h("11:00"), "fim": h("12:00"), "responsavel": "A"})
    _, resposta = mcp.ferramenta("reservar_sala", {"sala": "sala-mirante", "inicio": h("11:00"), "fim": h("12:00"), "responsavel": "B"})
    assert resposta["result"]["isError"] is True
    assert ERRO_SEM_ALTERNATIVAS in texto(resposta["result"])
    assert "inputRequests" not in resposta["result"]


@pytest.mark.parametrize("capacidades", [{}, {"elicitation": {"url": {}}}, {"elicitation": {}}])
def test_missing_form_elicitation_capability(mcp, capacidades):
    status, resposta = mcp.ferramenta("reservar_sala", CONFLITO, capacidades=capacidades)
    assert status == 400
    assert resposta["error"]["code"] == -32021
    assert resposta["error"]["data"]["requiredCapabilities"] == {"elicitation": {"form": {}}}


def test_accept_creates_the_reservation_in_the_chosen_room(mcp):
    estado = pausar(mcp)["requestState"]
    _, resposta = retomar(mcp, estado, aceitar("sala-fusca"))
    resultado = resposta["result"]
    assert resultado["resultType"] == "complete" and not resultado["isError"]
    assert resultado["structuredContent"] == {
        "reserva": "res-0003",
        "reservado": True,
        "sala": "sala-fusca",
        "inicio": h("14:00"),
        "fim": h("15:00"),
        "responsavel": "Marty",
        "politica": "2026-11-01",
        "motivo": None,
    }


def test_tampered_and_expired_state_are_rejected(mcp, monkeypatch):
    estado = pausar(mcp)["requestState"]
    adulterado = estado[:-6] + ("AAAAAA" if not estado.endswith("AAAAAA") else "BBBBBB")
    status, resposta = retomar(mcp, adulterado, aceitar("sala-fusca"))
    assert (status, resposta["error"]["code"]) == (400, -32602)
    agora = time.time()
    monkeypatch.setattr("mcp.server.request_state.time.time", lambda: agora + 601)
    _, resposta = retomar(mcp, estado, aceitar("sala-fusca"))
    assert resposta["error"]["code"] == -32602


def test_retry_with_different_arguments_is_rejected_and_creates_nothing(mcp):
    estado = pausar(mcp)["requestState"]
    outros = {**CONFLITO, "sala": "sala-mirante", "responsavel": "Biff"}
    _, resposta = retomar(mcp, estado, aceitar("sala-fusca"), argumentos=outros)
    assert resposta["error"]["code"] == -32602
    _, livre = mcp.ferramenta("consultar_disponibilidade", {"sala": "sala-fusca", "inicio": h("14:00"), "fim": h("15:00")})
    assert livre["result"]["structuredContent"]["livre"] is True


@pytest.mark.parametrize(("acao", "motivo"), [("decline", "recusado"), ("cancel", "cancelado")])
def test_decline_and_cancel_complete_without_reserving(mcp, acao, motivo):
    estado = pausar(mcp)["requestState"]
    _, resposta = retomar(mcp, estado, {"action": acao})
    resultado = resposta["result"]
    assert resultado["resultType"] == "complete" and not resultado.get("isError")
    assert resultado["structuredContent"]["reservado"] is False
    assert resultado["structuredContent"]["motivo"] == motivo
    _, livre = mcp.ferramenta("consultar_disponibilidade", {"sala": "sala-fusca", "inicio": h("14:00"), "fim": h("15:00")})
    assert livre["result"]["structuredContent"]["livre"] is True


def test_choice_outside_the_offer_asks_again(mcp):
    estado = pausar(mcp)["requestState"]
    _, resposta = retomar(mcp, estado, aceitar("sala-aquario"))
    resultado = resposta["result"]
    assert resultado["resultType"] == "input_required"
    assert resultado["inputRequests"][CHAVE_ESCOLHA]["params"]["requestedSchema"]["properties"]["sala"]["enum"] == [
        "sala-fusca",
        "sala-mirante",
    ]


def test_chosen_room_taken_meanwhile_asks_again_with_new_alternatives(mcp):
    estado = pausar(mcp)["requestState"]
    mcp.ferramenta("reservar_sala", {"sala": "sala-fusca", "inicio": h("14:00"), "fim": h("15:00"), "responsavel": "Biff"})
    _, resposta = retomar(mcp, estado, aceitar("sala-fusca"))
    resultado = resposta["result"]
    assert resultado["resultType"] == "input_required"
    assert resultado["inputRequests"][CHAVE_ESCOLHA]["params"]["requestedSchema"]["properties"]["sala"]["enum"] == [
        "sala-mirante"
    ]


def test_state_survives_a_new_server_instance_with_the_same_secret():
    with cliente() as primeiro:
        estado = pausar(ClienteMCP(primeiro))["requestState"]
    with cliente() as segundo:
        _, resposta = retomar(ClienteMCP(segundo), estado, aceitar("sala-mirante"))
    assert resposta["result"]["structuredContent"]["sala"] == "sala-mirante"


@pytest.mark.parametrize("ambiente", [{}, {"REQUEST_STATE_SECRET": "x" * 16}])
def test_startup_refuses_a_missing_or_short_secret(ambiente):
    with pytest.raises(SegredoInvalido, match="secrets.token_hex"):
        seguranca_do_ambiente(ambiente)
    processo = subprocess.run(
        [sys.executable, "-m", "servidor_mcp"], env={"PATH": "/usr/bin:/bin", **ambiente}, capture_output=True, text=True
    )
    assert processo.returncode != 0
    assert "REQUEST_STATE_SECRET" in processo.stderr


def test_replayed_accept_returns_the_first_reservation(mcp):
    estado = pausar(mcp)["requestState"]
    _, primeira = retomar(mcp, estado, aceitar("sala-fusca"))
    _, repetida = retomar(mcp, estado, aceitar("sala-mirante"))
    assert repetida["result"]["structuredContent"] == primeira["result"]["structuredContent"]
    _, livre = mcp.ferramenta("consultar_disponibilidade", {"sala": "sala-mirante", "inicio": h("14:00"), "fim": h("15:00")})
    assert livre["result"]["structuredContent"]["livre"] is True


@pytest.mark.parametrize(
    ("segredo", "aceito"),
    [(secrets.token_hex(16), False), (secrets.token_hex(32), True), ("a" * 20 + "!", False), ("senha-longa-nao-hex-" * 2, True)],
)
def test_secret_needs_32_bytes_of_randomness(segredo, aceito):
    if aceito:
        seguranca_do_ambiente({"REQUEST_STATE_SECRET": segredo})
    else:
        with pytest.raises(SegredoInvalido):
            seguranca_do_ambiente({"REQUEST_STATE_SECRET": segredo})


def test_discover_does_not_advertise_subscriptions(mcp):
    _, resposta = mcp.chamar("server/discover")
    capacidades = resposta["result"]["capabilities"]
    assert "tools" in capacidades and "resources" in capacidades
    assert not capacidades["resources"].get("subscribe")
    assert not any(c.get("listChanged") for c in capacidades.values() if isinstance(c, dict))
