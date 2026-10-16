"""Integrity key of the sealed `requestState`, read only from the environment."""

from __future__ import annotations

import os

from mcp.server.request_state import RequestStateSecurity

VARIAVEL = "REQUEST_STATE_SECRET"
TAMANHO_MINIMO = 32
VALIDADE_SEGUNDOS = 600.0

ORIENTACAO = (
    f"{VARIAVEL} ausente ou com menos de {TAMANHO_MINIMO} bytes. Gere uma chave com\n"
    '  python3 -c "import secrets; print(secrets.token_hex(32))"\n'
    f"e exporte antes de subir o servidor: export {VARIAVEL}=<valor gerado>"
)


class SegredoInvalido(Exception):
    pass


def seguranca_do_ambiente(ambiente: dict[str, str] | None = None) -> RequestStateSecurity:
    """AES-256-GCM sealing (SDK) with the key from `REQUEST_STATE_SECRET` and a 10-minute TTL."""
    segredo = (os.environ if ambiente is None else ambiente).get(VARIAVEL, "")
    if len(segredo.encode()) < TAMANHO_MINIMO:
        raise SegredoInvalido(ORIENTACAO)
    return RequestStateSecurity(keys=[segredo], ttl=VALIDADE_SEGUNDOS)
