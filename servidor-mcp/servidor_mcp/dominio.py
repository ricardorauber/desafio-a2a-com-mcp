"""Room domain: starter data, usage policy, conflicts and alternatives.

Everything lives in memory. Reservations created while the process runs are
visible to later queries and are lost on restart, by design.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

DADOS = Path(__file__).resolve().parents[2] / "dados"
FUSO_SAO_PAULO = timezone(timedelta(hours=-3))
ABERTURA = time(8, 0)
FECHAMENTO = time(20, 0)
DURACAO_MAXIMA = timedelta(hours=2)
MAXIMO_ALTERNATIVAS = 3

ERRO_SALA_INEXISTENTE = "Sala inexistente: {sala}"
ERRO_FORA_DA_JANELA = "Fora da janela de uso: a politica permite reservas entre 08:00 e 20:00"
ERRO_DURACAO = "Duracao acima do limite: a politica permite no maximo 2 horas"
ERRO_INTERVALO = "Intervalo invalido: fim deve ser posterior a inicio"
ERRO_SEM_ALTERNATIVAS = "Sem alternativas disponiveis no intervalo"


class ErroDeDominio(Exception):
    """A request that the usage policy refuses; the message is user-facing."""


@dataclass(frozen=True)
class Sala:
    id: str
    nome: str
    capacidade: int
    recursos: tuple[str, ...]


@dataclass(frozen=True)
class Reserva:
    id: str
    sala: str
    inicio: str
    fim: str
    responsavel: str


@dataclass(frozen=True)
class Intervalo:
    inicio: datetime
    fim: datetime

    def sobrepoe(self, outro: Intervalo) -> bool:
        return self.inicio < outro.fim and outro.inicio < self.fim


def _instante(valor: str) -> datetime:
    try:
        instante = datetime.fromisoformat(valor)
    except (TypeError, ValueError):
        raise ErroDeDominio(ERRO_INTERVALO) from None
    if instante.tzinfo is None:
        raise ErroDeDominio(ERRO_INTERVALO)
    return instante


def _dentro_da_janela(intervalo: Intervalo) -> bool:
    inicio = intervalo.inicio.astimezone(FUSO_SAO_PAULO)
    fim = intervalo.fim.astimezone(FUSO_SAO_PAULO)
    return inicio.date() == fim.date() and inicio.time() >= ABERTURA and fim.time() <= FECHAMENTO


def versao_da_politica(texto: str) -> str:
    primeira = texto.splitlines()[0] if texto else ""
    chave, _, valor = primeira.partition(":")
    if chave.strip() != "versao" or not valor.strip():
        raise ValueError("a primeira linha da politica deve ser 'versao: <valor>'")
    return valor.strip()


class Agenda:
    """Rooms, reservations and the usage policy of one server process."""

    def __init__(self, salas: list[Sala], reservas: list[Reserva], politica: str) -> None:
        self._salas = {sala.id: sala for sala in salas}
        self._reservas = list(reservas)
        self.politica = politica
        self.versao_politica = versao_da_politica(politica)
        numeros = [int(r.id.removeprefix("res-")) for r in reservas if r.id.removeprefix("res-").isdigit()]
        self._proximo = max(numeros, default=0) + 1

    @classmethod
    def carregar(cls, dados: Path = DADOS) -> Agenda:
        salas = [
            Sala(s["id"], s["nome"], s["capacidade"], tuple(s["recursos"]))
            for s in json.loads((dados / "salas.json").read_text(encoding="utf-8"))
        ]
        reservas = [
            Reserva(r["id"], r["sala"], r["inicio"], r["fim"], r["responsavel"])
            for r in json.loads((dados / "reservas.json").read_text(encoding="utf-8"))
        ]
        politica = (dados / "politica-de-uso.md").read_text(encoding="utf-8")
        return cls(salas, reservas, politica)

    @property
    def salas(self) -> list[Sala]:
        return list(self._salas.values())

    def validar(self, sala: str, inicio: str, fim: str) -> Intervalo:
        """Return the parsed interval, or raise `ErroDeDominio` with the policy message."""
        if sala not in self._salas:
            raise ErroDeDominio(ERRO_SALA_INEXISTENTE.format(sala=sala))
        intervalo = Intervalo(_instante(inicio), _instante(fim))
        if intervalo.fim <= intervalo.inicio:
            raise ErroDeDominio(ERRO_INTERVALO)
        if not _dentro_da_janela(intervalo):
            raise ErroDeDominio(ERRO_FORA_DA_JANELA)
        if intervalo.fim - intervalo.inicio > DURACAO_MAXIMA:
            raise ErroDeDominio(ERRO_DURACAO)
        return intervalo

    def conflitos(self, sala: str, intervalo: Intervalo) -> list[Reserva]:
        return [
            r
            for r in self._reservas
            if r.sala == sala and intervalo.sobrepoe(Intervalo(_instante(r.inicio), _instante(r.fim)))
        ]

    def alternativas(self, sala: str, intervalo: Intervalo) -> list[str]:
        """Free rooms at least as large as `sala`, by capacity then id, at most three."""
        minimo = self._salas[sala].capacidade
        candidatas = sorted(
            (s for s in self._salas.values() if s.id != sala and s.capacidade >= minimo),
            key=lambda s: (s.capacidade, s.id),
        )
        livres = [s.id for s in candidatas if not self.conflitos(s.id, intervalo)]
        return livres[:MAXIMO_ALTERNATIVAS]

    def reservar(self, sala: str, inicio: str, fim: str, responsavel: str) -> Reserva:
        """Create a reservation for a valid, free interval."""
        intervalo = self.validar(sala, inicio, fim)
        if self.conflitos(sala, intervalo):
            raise ValueError(f"{sala} is not free in the requested interval")
        reserva = Reserva(f"res-{self._proximo:04d}", sala, inicio, fim, responsavel)
        self._proximo += 1
        self._reservas.append(reserva)
        return reserva
