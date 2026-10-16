import json

import pytest
from google.protobuf.json_format import MessageToDict

from agente_a2a.cartao import criar_cartao
from agente_a2a.pedido import PEDIDO_INVALIDO, interpretar_pedido

EXEMPLO = json.load(open("exemplos/wire/07-a2a-agent-card.json"))["response"]["body"]


def test_card_matches_the_v1_example():
    cartao = MessageToDict(criar_cartao("http://127.0.0.1:7300"))
    assert cartao == EXEMPLO
    assert "securitySchemes" not in cartao


def test_card_uses_the_public_url():
    cartao = criar_cartao("http://agente.local:9000/")
    assert cartao.supported_interfaces[0].url == "http://agente.local:9000/a2a"


def test_valid_request_and_name_with_spaces():
    assert interpretar_pedido(
        "reservar sala=sala-porao inicio=2026-11-03T09:00:00-03:00 fim=2026-11-03T10:00:00-03:00 responsavel=Emmett Brown"
    ) == {
        "sala": "sala-porao",
        "inicio": "2026-11-03T09:00:00-03:00",
        "fim": "2026-11-03T10:00:00-03:00",
        "responsavel": "Emmett Brown",
    }


@pytest.mark.parametrize(
    "texto",
    [
        "reservar sala=sala-porao inicio=2026-11-03T09:00:00-03:00 fim=2026-11-03T10:00:00-03:00",
        "por favor reservar sala=sala-porao inicio=a fim=b responsavel=Doc",
        "reservar a sala-porao amanha",
        "escolha=sala-fusca",
        "",
    ],
)
def test_malformed_requests(texto):
    assert interpretar_pedido(texto) is None


def test_invalid_request_message():
    assert PEDIDO_INVALIDO == "Pedido invalido: use reservar sala=<id> inicio=<iso8601> fim=<iso8601> responsavel=<nome>"
