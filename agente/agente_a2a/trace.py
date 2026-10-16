"""W3C trace context: keep the caller's trace id, mint a new span per MCP request."""

from __future__ import annotations

import re
import secrets

_TRACEPARENT = re.compile(r"^[0-9a-f]{2}-([0-9a-f]{32})-([0-9a-f]{16})-[0-9a-f]{2}$")
_INVALIDO = "0" * 32


def trace_id_de(traceparent: str | None) -> str:
    """Trace id of an inbound `traceparent`, or a new random one when absent or malformed."""
    encontrado = _TRACEPARENT.match((traceparent or "").strip().lower())
    if encontrado and encontrado.group(1) != _INVALIDO and encontrado.group(2) != "0" * 16:
        return encontrado.group(1)
    return secrets.token_hex(16)


def traceparent_filho(trace_id: str) -> str:
    return f"00-{trace_id}-{secrets.token_hex(8)}-01"
