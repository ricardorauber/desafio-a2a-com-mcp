import json

import pytest
from mcp_types import (
    CallToolResult,
    ClientCapabilities,
    ElicitationCapability,
    ElicitRequest,
    ElicitRequestFormParams,
    ElicitResult,
    InputRequiredResult,
    TextContent,
    UrlElicitationCapability,
)

from apoio_agente import servidor_mcp_em_segundo_plano
from agente_a2a.host_mcp import (
    Concluida,
    FalhaFerramenta,
    FalhaProtocolo,
    HostMCP,
    Pausada,
    Recusada,
    capacidades_so_formulario,
    classificar,
    versao_da_politica,
)

TRACE = "4bf92f3577b34da6a3ce929d0e0e4736"
CONFLITO = {
    "sala": "sala-garagem",
    "inicio": "2026-11-03T14:00:00-03:00",
    "fim": "2026-11-03T15:00:00-03:00",
    "responsavel": "Marty",
}


def pedido(propriedade: dict) -> InputRequiredResult:
    esquema = {"type": "object", "properties": {"sala": {"type": "string", **propriedade}}, "required": ["sala"]}
    return InputRequiredResult(
        input_requests={"k": ElicitRequest(params=ElicitRequestFormParams(message="m", requested_schema=esquema))},
        request_state="opaco",
    )


def test_classification_of_each_outcome():
    assert classificar(CallToolResult(content=[], structured_content={"reservado": True, "sala": "a"}), "v") == Concluida(
        {"reservado": True, "sala": "a"}, "v"
    )
    assert classificar(CallToolResult(content=[], structured_content={"reservado": False, "motivo": "recusado"}), "v") == Recusada(
        "recusado"
    )
    erro = CallToolResult(content=[TextContent(type="text", text="Error executing tool x: Sala inexistente: y")], is_error=True)
    assert classificar(erro, "v") == FalhaFerramenta("Error executing tool x: Sala inexistente: y")
    assert classificar(pedido({"enum": ["b", "a"]}), "v") == Pausada("k", ("b", "a"), "v", "opaco")
    assert classificar(pedido({"const": "a"}), "v") == Pausada("k", ("a",), "v", "opaco")
    assert isinstance(classificar(pedido({}), "v"), FalhaProtocolo)


def test_paused_repr_hides_the_request_state():
    assert "opaco" not in repr(Pausada("k", ("a",), "v", "opaco"))


def test_capability_is_narrowed_to_form_mode():
    sdk = ClientCapabilities(elicitation=ElicitationCapability(form={}, url=UrlElicitationCapability()))
    assert capacidades_so_formulario(sdk).model_dump(by_alias=True, mode="json", exclude_none=True) == {
        "elicitation": {"form": {}}
    }


def test_policy_version_extraction():
    assert versao_da_politica("versao: 2026-11-01\n\n- regra") == "2026-11-01"
    with pytest.raises(ValueError):
        versao_da_politica("sem versao")


async def test_full_cycle_against_the_real_mcp_server():
    with servidor_mcp_em_segundo_plano() as (url, captura):
        host = HostMCP(url)
        pausa = await host.reservar(CONFLITO, TRACE)
        assert isinstance(pausa, Pausada)
        assert (pausa.chave, pausa.alternativas, pausa.politica) == (
            "escolha_de_sala",
            ("sala-fusca", "sala-mirante"),
            "2026-11-01",
        )
        fim = await host.retomar(
            CONFLITO, pausa.chave, ElicitResult(action="accept", content={"sala": "sala-fusca"}), pausa.request_state, pausa.politica, TRACE
        )
        assert isinstance(fim, Concluida) and fim.dados["sala"] == "sala-fusca" and fim.politica == "2026-11-01"
        falha = await host.reservar({**CONFLITO, "sala": "sala-delorean"}, TRACE)
        assert isinstance(falha, FalhaFerramenta) and "Sala inexistente: sala-delorean" in falha.texto

    metodos = [r["body"]["method"] for r in captura.requests]
    assert metodos[:5] == ["tools/list", "resources/read", "tools/call", "tools/list", "tools/call"]
    chamadas = [r for r in captura.requests if r["body"]["method"] == "tools/call"]
    assert chamadas[0]["body"]["id"] != chamadas[1]["body"]["id"]
    assert chamadas[1]["body"]["params"]["requestState"] == pausa.request_state
    assert chamadas[1]["body"]["params"]["inputResponses"] == {
        "escolha_de_sala": {"action": "accept", "content": {"sala": "sala-fusca"}}
    }
    assert chamadas[1]["body"]["params"]["arguments"] == CONFLITO
    for r in captura.requests:
        meta = r["body"]["params"]["_meta"]
        assert meta["io.modelcontextprotocol/clientCapabilities"] == {"elicitation": {"form": {}}}
        assert meta["io.modelcontextprotocol/protocolVersion"] == "2026-07-28"
        assert meta["traceparent"].split("-")[1] == TRACE
        assert r["headers"]["mcp-protocol-version"] == "2026-07-28"
        assert r["headers"]["mcp-method"] == r["body"]["method"]
        if r["body"]["method"] == "tools/call":
            assert r["headers"]["mcp-name"] == "reservar_sala"
        if r["body"]["method"] == "resources/read":
            assert r["headers"]["mcp-name"] == "politica://uso"
    assert len({r["body"]["params"]["_meta"]["traceparent"] for r in captura.requests}) == len(captura.requests)
    assert len({r["body"]["id"] for r in captura.requests}) == len(captura.requests)


async def test_protocol_error_and_unreachable_server():
    with servidor_mcp_em_segundo_plano() as (url, _):
        host = HostMCP(url)
        pausa = await host.reservar(CONFLITO, TRACE)
        adulterado = pausa.request_state[:-4] + "AAAA"
        falha = await host.retomar(
            CONFLITO, pausa.chave, ElicitResult(action="accept", content={"sala": "sala-fusca"}), adulterado, "v", TRACE
        )
        assert isinstance(falha, FalhaProtocolo) and falha.texto.startswith("Erro MCP -32602")
    assert await HostMCP("http://127.0.0.1:9/mcp").reservar(CONFLITO, TRACE) == FalhaProtocolo("Servidor MCP indisponivel")
