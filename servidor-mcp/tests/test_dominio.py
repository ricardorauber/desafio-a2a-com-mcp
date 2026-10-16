import pytest

from servidor_mcp.dominio import (
    ERRO_DURACAO,
    ERRO_FORA_DA_JANELA,
    ERRO_INTERVALO,
    Agenda,
    ErroDeDominio,
    Reserva,
    Sala,
)


def h(hora: str, dia: str = "2026-11-03", offset: str = "-03:00") -> str:
    return f"{dia}T{hora}:00{offset}"


@pytest.fixture
def agenda() -> Agenda:
    return Agenda.carregar()


def test_loads_starter_data_and_policy_version(agenda):
    assert agenda.versao_politica == "2026-11-01"
    assert {s.id: s.capacidade for s in agenda.salas} == {
        "sala-aquario": 4,
        "sala-porao": 6,
        "sala-garagem": 12,
        "sala-fusca": 12,
        "sala-mirante": 20,
    }
    assert agenda.politica.startswith("versao: 2026-11-01")


@pytest.mark.parametrize(
    ("sala", "inicio", "fim", "mensagem"),
    [
        ("sala-delorean", h("09:00"), h("10:00"), "Sala inexistente: sala-delorean"),
        ("sala-aquario", h("07:00"), h("08:00"), ERRO_FORA_DA_JANELA),
        ("sala-aquario", h("19:00"), h("20:30"), ERRO_FORA_DA_JANELA),
        ("sala-aquario", h("09:00"), h("12:00"), ERRO_DURACAO),
        ("sala-aquario", h("10:00"), h("09:00"), ERRO_INTERVALO),
        ("sala-aquario", h("10:00"), h("10:00"), ERRO_INTERVALO),
        ("sala-aquario", "amanha", h("10:00"), ERRO_INTERVALO),
        ("sala-aquario", "2026-11-03T09:00:00", h("10:00"), ERRO_INTERVALO),
    ],
)
def test_validation_messages(agenda, sala, inicio, fim, mensagem):
    with pytest.raises(ErroDeDominio) as erro:
        agenda.validar(sala, inicio, fim)
    assert str(erro.value) == mensagem


def test_unknown_room_is_reported_before_a_bad_interval(agenda):
    with pytest.raises(ErroDeDominio, match="Sala inexistente: sala-x"):
        agenda.validar("sala-x", h("10:00"), h("09:00"))


def test_window_is_checked_in_sao_paulo_time(agenda):
    # 11:00Z is 08:00 in Sao Paulo, so this is inside the window.
    agenda.validar("sala-aquario", "2026-11-03T11:00:00+00:00", "2026-11-03T12:00:00+00:00")
    with pytest.raises(ErroDeDominio, match="Fora da janela"):
        agenda.validar("sala-aquario", "2026-11-03T10:00:00+00:00", "2026-11-03T11:00:00+00:00")


@pytest.mark.parametrize(
    ("inicio", "fim", "conflita"),
    [
        (h("14:00"), h("15:00"), True),
        (h("14:15"), h("14:45"), True),
        (h("13:30"), h("14:30"), True),
        (h("15:00"), h("16:00"), False),
        (h("13:00"), h("14:00"), False),
        ("2026-11-03T17:30:00+00:00", "2026-11-03T18:30:00+00:00", True),
    ],
)
def test_overlap(agenda, inicio, fim, conflita):
    conflitos = agenda.conflitos("sala-garagem", agenda.validar("sala-garagem", inicio, fim))
    assert bool(conflitos) is conflita
    if conflita:
        assert conflitos == [
            Reserva("res-0001", "sala-garagem", h("14:00"), h("15:00"), "Marty"),
        ]


def test_alternatives_follow_capacity_then_id(agenda):
    intervalo = agenda.validar("sala-garagem", h("14:00"), h("15:00"))
    assert agenda.alternativas("sala-garagem", intervalo) == ["sala-fusca", "sala-mirante"]


def test_alternatives_are_at_most_three_and_exclude_the_requested_room(agenda):
    intervalo = agenda.validar("sala-aquario", h("09:00"), h("10:00"))
    assert agenda.alternativas("sala-aquario", intervalo) == ["sala-porao", "sala-fusca", "sala-garagem"]


def test_alternatives_skip_busy_rooms_and_can_be_empty():
    salas = [Sala("a", "A", 4, ()), Sala("b", "B", 2, ()), Sala("c", "C", 8, ())]
    reservas = [
        Reserva("res-0001", "a", h("09:00"), h("10:00"), "x"),
        Reserva("res-0002", "c", h("09:00"), h("10:00"), "y"),
    ]
    agenda = Agenda(salas, reservas, "versao: 1\n")
    intervalo = agenda.validar("a", h("09:00"), h("10:00"))
    assert agenda.alternativas("a", intervalo) == []
    assert agenda.alternativas("b", intervalo) == []


def test_reservations_get_sequential_ids_and_become_visible(agenda):
    primeira = agenda.reservar("sala-aquario", h("09:00"), h("10:00"), "Doc")
    segunda = agenda.reservar("sala-porao", h("09:00"), h("10:00"), "Doc")
    assert (primeira.id, segunda.id) == ("res-0003", "res-0004")
    intervalo = agenda.validar("sala-aquario", h("09:30"), h("10:30"))
    assert agenda.conflitos("sala-aquario", intervalo) == [primeira]
    with pytest.raises(ValueError):
        agenda.reservar("sala-aquario", h("09:30"), h("10:30"), "Biff")


def test_reservation_in_the_past_is_allowed(agenda):
    reserva = agenda.reservar("sala-aquario", h("09:00", dia="2020-01-01"), h("10:00", dia="2020-01-01"), "Doc")
    assert reserva.id == "res-0003"
