"""The fixed request format the agent accepts (no natural language, no LLM)."""

from __future__ import annotations

import re

FORMATO = "reservar sala=<id> inicio=<iso8601> fim=<iso8601> responsavel=<nome>"
PEDIDO_INVALIDO = f"Pedido invalido: use {FORMATO}"

_PEDIDO = re.compile(r"^reservar sala=(\S+) inicio=(\S+) fim=(\S+) responsavel=(\S.*)$")


def interpretar_pedido(texto: str) -> dict[str, str] | None:
    """`reservar_sala` arguments taken verbatim from the text, or None when it does not match."""
    encontrado = _PEDIDO.match(texto.strip())
    if encontrado is None:
        return None
    sala, inicio, fim, responsavel = encontrado.groups()
    return {"sala": sala, "inicio": inicio, "fim": fim, "responsavel": responsavel.strip()}
