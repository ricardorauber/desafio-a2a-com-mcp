import json
import logging

import pytest

from apoio_mcp import h, texto
from servidor_mcp.dominio import ERRO_DURACAO, ERRO_FORA_DA_JANELA, ERRO_INTERVALO

TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"


def test_tools_list_has_three_tools_with_object_schemas(mcp):
    status, resposta = mcp.chamar("tools/list")
    assert status == 200
    tools = {t["name"]: t for t in resposta["result"]["tools"]}
    assert set(tools) == {"listar_salas", "consultar_disponibilidade", "reservar_sala"}
    assert all(t["inputSchema"]["type"] == "object" for t in tools.values())
    assert tools["listar_salas"]["outputSchema"]["required"] == ["salas"]
    assert set(tools["reservar_sala"]["inputSchema"]["required"]) == {"sala", "inicio", "fim", "responsavel"}
    assert {"reserva", "reservado", "sala", "inicio", "fim", "responsavel", "politica", "motivo"} <= set(
        tools["reservar_sala"]["outputSchema"]["properties"]
    )


def test_listar_salas_structured_content_matches_text_block(mcp):
    _, resposta = mcp.ferramenta("listar_salas", {})
    resultado = resposta["result"]
    assert json.loads(texto(resultado)) == resultado["structuredContent"]
    assert [s["id"] for s in resultado["structuredContent"]["salas"]][0] == "sala-aquario"


@pytest.mark.parametrize("omitir", ["protocolVersion", "clientCapabilities"])
def test_missing_meta_field_is_rejected(mcp, omitir):
    status, resposta = mcp.ferramenta("listar_salas", {}, omitir=omitir)
    assert status == 400
    assert resposta["error"]["code"] == -32602


@pytest.mark.parametrize(
    ("inicio", "fim", "mensagem"),
    [(h("07:00"), h("08:00"), ERRO_FORA_DA_JANELA), (h("09:00"), h("12:00"), ERRO_DURACAO), (h("10:00"), h("09:00"), ERRO_INTERVALO)],
)
def test_consultar_disponibilidade_policy_errors(mcp, inicio, fim, mensagem):
    _, resposta = mcp.ferramenta("consultar_disponibilidade", {"sala": "sala-aquario", "inicio": inicio, "fim": fim})
    assert resposta["result"]["isError"] is True
    assert mensagem in texto(resposta["result"])


def test_consultar_disponibilidade_unknown_room_and_conflicts(mcp):
    _, resposta = mcp.ferramenta("consultar_disponibilidade", {"sala": "sala-delorean", "inicio": h("09:00"), "fim": h("10:00")})
    assert "Sala inexistente: sala-delorean" in texto(resposta["result"])
    _, resposta = mcp.ferramenta("consultar_disponibilidade", {"sala": "sala-garagem", "inicio": h("14:30"), "fim": h("15:30")})
    dados = resposta["result"]["structuredContent"]
    assert dados["livre"] is False
    assert [c["id"] for c in dados["conflitos"]] == ["res-0001"]
    assert json.loads(texto(resposta["result"])) == dados


def test_unknown_tool_is_refused(mcp):
    _, resposta = mcp.ferramenta("voar_delorean", {})
    assert resposta.get("error", {}).get("code") == -32602 or resposta["result"]["isError"] is True


def test_policy_resource_and_unknown_uri(mcp):
    _, resposta = mcp.chamar("resources/read", {"uri": "politica://uso"}, nome="politica://uso")
    conteudo = resposta["result"]["contents"][0]
    assert conteudo["mimeType"] == "text/markdown"
    assert conteudo["text"].startswith("versao: 2026-11-01")
    status, resposta = mcp.chamar("resources/read", {"uri": "politica://nada"}, nome="politica://nada")
    assert resposta["error"]["code"] == -32602
    assert status == 400


def test_request_log_has_method_id_traceparent_and_status(mcp, caplog):
    with caplog.at_level(logging.INFO, logger="servidor_mcp.requests"):
        mcp.chamar("tools/list", traceparent=TRACEPARENT)
        mcp.ferramenta("listar_salas", {}, omitir="protocolVersion")
    linhas = [r.getMessage() for r in caplog.records if r.name == "servidor_mcp.requests"]
    assert len(linhas) == 2
    assert "method=tools/list" in linhas[0] and f"traceparent={TRACEPARENT}" in linhas[0] and "status=200" in linhas[0]
    assert "method=tools/call" in linhas[1] and "id=" in linhas[1] and "status=400" in linhas[1]


def test_reservar_sala_free_interval(mcp):
    _, resposta = mcp.ferramenta(
        "reservar_sala", {"sala": "sala-aquario", "inicio": h("09:00"), "fim": h("10:00"), "responsavel": "Doc"}
    )
    dados = resposta["result"]["structuredContent"]
    assert dados["reservado"] is True
    assert (dados["reserva"], dados["sala"], dados["politica"], dados["responsavel"]) == (
        "res-0003",
        "sala-aquario",
        "2026-11-01",
        "Doc",
    )
