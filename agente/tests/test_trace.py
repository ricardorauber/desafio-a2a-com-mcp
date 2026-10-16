import re

from agente_a2a.trace import trace_id_de, traceparent_filho

VALIDO = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"


def test_valid_header_keeps_trace_id():
    assert trace_id_de(VALIDO) == "4bf92f3577b34da6a3ce929d0e0e4736"


def test_absent_or_malformed_header_gets_a_new_trace_id():
    gerados = {trace_id_de(None), trace_id_de("lixo"), trace_id_de("00-" + "0" * 32 + "-00f067aa0ba902b7-01")}
    assert len(gerados) == 3
    assert all(re.fullmatch(r"[0-9a-f]{32}", t) for t in gerados)


def test_child_spans_are_new_and_keep_the_trace():
    a, b = traceparent_filho("4bf92f3577b34da6a3ce929d0e0e4736"), traceparent_filho("4bf92f3577b34da6a3ce929d0e0e4736")
    assert a != b
    for filho in (a, b):
        versao, trace, span, flags = filho.split("-")
        assert (versao, trace, flags) == ("00", "4bf92f3577b34da6a3ce929d0e0e4736", "01")
        assert re.fullmatch(r"[0-9a-f]{16}", span)
