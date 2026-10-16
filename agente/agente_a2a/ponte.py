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
    """Per-Task paused state, plus a claim so only one continuation acts on a Task at a time.

    Claims are taken synchronously on the event loop, so check-and-claim is atomic.
    """

    def __init__(self) -> None:
        self._pausadas: dict[str, TarefaPausada] = {}
        self._em_andamento: dict[str, asyncio.Event] = {}

    def reivindicar(self, task_id: str) -> bool:
        if task_id in self._em_andamento:
            return False
        self._em_andamento[task_id] = asyncio.Event()
        return True

    def liberar(self, task_id: str) -> None:
        fim = self._em_andamento.pop(task_id, None)
        if fim is not None:
            fim.set()

    async def aguardar(self, task_id: str) -> None:
        """Wait for the continuation of this Task that is running, if any."""
        fim = self._em_andamento.get(task_id)
        if fim is not None:
            await fim.wait()

    def guardar(self, task_id: str, pausa: TarefaPausada) -> None:
        self._pausadas[task_id] = pausa

    def obter(self, task_id: str) -> TarefaPausada | None:
        return self._pausadas.get(task_id)

    def descartar(self, task_id: str) -> None:
        self._pausadas.pop(task_id, None)
