import pytest
from starlette.testclient import TestClient

from apoio_mcp import ClienteMCP
from servidor_mcp.servidor import criar_app


@pytest.fixture
def mcp():
    with TestClient(criar_app(), base_url="http://127.0.0.1:7301") as http:
        yield ClienteMCP(http)
