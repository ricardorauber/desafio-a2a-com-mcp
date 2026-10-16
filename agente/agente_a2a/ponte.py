"""Paused Tasks: the MCP `requestState` bound to the A2A Task that is waiting for input.

Only protocol data lives here (the original arguments, the elicitation key, the
offered alternatives, the opaque state, the trace id and the policy version).
None of it is ever sent to the A2A client.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field

RECUSAR = "recusar"
_ESCOLHA = re.compile(r"^escolha=(\S+)$")


@dataclass(frozen=True)
class TarefaPausada:
    argumentos: dict[str, str]
    chave: str
    alternativas: tuple[str, ...]
    trace_id: str
    politica: str
    request_state: str = field(repr=False)


def linha_de_alternativas(alternativas: tuple[str, ...]) -> str:
    return "alternativas: " + ", ".join(alternativas)


def interpretar_escolha(texto: str) -> str | None:
    encontrado = _ESCOLHA.match(texto.strip())
    return encontrado.group(1) if encontrado else None


class Pausas:
    """Per-Task paused state, plus one lock per Task so continuations run one at a time."""

    def __init__(self) -> None:
        self._pausadas: dict[str, TarefaPausada] = {}
        self._travas: dict[str, asyncio.Lock] = {}

    def trava(self, task_id: str) -> asyncio.Lock:
        return self._travas.setdefault(task_id, asyncio.Lock())

    def guardar(self, task_id: str, pausa: TarefaPausada) -> None:
        self._pausadas[task_id] = pausa

    def obter(self, task_id: str) -> TarefaPausada | None:
        return self._pausadas.get(task_id)

    def descartar(self, task_id: str) -> None:
        self._pausadas.pop(task_id, None)
        self._travas.pop(task_id, None)
