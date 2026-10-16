import argparse
import logging
import os
import sys

import uvicorn

from servidor_mcp.seguranca import SegredoInvalido, seguranca_do_ambiente
from servidor_mcp.servidor import criar_app

PORTA_PADRAO = 7301


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m servidor_mcp",
        description="Servidor MCP da Central de Salas (Streamable HTTP em /mcp).",
    )
    parser.parse_args()
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        seguranca = seguranca_do_ambiente()
    except SegredoInvalido as erro:
        print(f"erro: {erro}", file=sys.stderr)
        sys.exit(2)
    porta = int(os.environ.get("MCP_PORT", PORTA_PADRAO))
    uvicorn.run(criar_app(seguranca=seguranca), host="127.0.0.1", port=porta, log_config=None, access_log=False)


if __name__ == "__main__":
    main()
