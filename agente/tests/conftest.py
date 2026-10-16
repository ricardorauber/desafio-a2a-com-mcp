import pytest
from starlette.testclient import TestClient

from apoio_agente import ClienteA2A, HostFalso
from agente_a2a.app import criar_app


@pytest.fixture
def a2a_com():
    clientes = []

    def fabricar(*resultados):
        host = HostFalso(*resultados)
        http = TestClient(criar_app(host, "http://127.0.0.1:7300"))
        clientes.append(http)
        return ClienteA2A(http.__enter__()), host

    yield fabricar
    for http in clientes:
        http.__exit__(None, None, None)
