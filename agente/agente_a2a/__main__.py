import argparse
import logging
import os
import sys

import uvicorn

from agente_a2a.app import criar_app
from agente_a2a.host_mcp import HostMCP

PORTA_PADRAO = 7300
MCP_PADRAO = "http://127.0.0.1:7301/mcp"


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m agente_a2a",
        description="Agente A2A da Central de Salas (JSON-RPC em /a2a, host MCP por dentro).",
    )
    parser.parse_args()
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    for ruidoso in ("httpx", "httpx2", "mcp.client"):
        logging.getLogger(ruidoso).setLevel(logging.WARNING)
    porta = int(os.environ.get("AGENT_PORT", PORTA_PADRAO))
    url_publica = os.environ.get("AGENT_PUBLIC_URL", f"http://127.0.0.1:{porta}")
    host = HostMCP(os.environ.get("MCP_URL", MCP_PADRAO))
    uvicorn.run(criar_app(host, url_publica), host="127.0.0.1", port=porta, log_config=None, access_log=False)


if __name__ == "__main__":
    main()
