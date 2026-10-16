# 0003 - MCP server: transport, logging, read tools and policy resource

## Goal
Serve the room domain as a stateless MCP server over Streamable HTTP (revision `2026-07-28`) with the two read-only tools, the policy resource and per-request stderr logging.

## Scope
- In: `servidor-mcp/servidor_mcp/servidor.py` (the `MCPServer` instance, tools `listar_salas` and `consultar_disponibilidade`, resource `politica://uso`), `servidor-mcp/servidor_mcp/log.py` (request logging ASGI wrapper), `servidor-mcp/servidor_mcp/__main__.py` (uvicorn startup), and a declaration of `reservar_sala` with its input/output schema whose happy path only creates the reservation (no conflict handling yet).
- Out: the MRTR cycle of `reservar_sala` (0004), the agent (0005-0007).

## Requirements
- R1: The server SHALL use the official `mcp` SDK v2 (`MCPServer`, name `central-de-salas`, version `1.0.0`) over Streamable HTTP in stateless JSON mode at the single endpoint `/mcp`, listening on `127.0.0.1` and on the port given by `MCP_PORT` (default `7301`).
- R2: The server SHALL declare the `tools` and `resources` capabilities and SHALL rely on the SDK to reject, with JSON-RPC `-32602` and HTTP `400`, any request whose `_meta` lacks `io.modelcontextprotocol/protocolVersion` or `io.modelcontextprotocol/clientCapabilities`, and with `-32020` any request whose `MCP-Protocol-Version`, `Mcp-Method` or `Mcp-Name` header does not match the body. Nothing SHALL be inferred from earlier requests.
- R3: Every HTTP request reaching `/mcp`, including the ones the SDK rejects, SHALL be logged as one line on stderr with at least the JSON-RPC `method`, the `id` and the `_meta.traceparent` value (or `-` when absent), plus the HTTP status of the response. The deprecated MCP logging feature SHALL NOT be used.
- R4: `listar_salas` SHALL take no arguments and return `{"salas": [...]}` as `structuredContent` conforming to its declared `outputSchema`, plus the same JSON serialized in a text block.
- R5: `consultar_disponibilidade(sala, inicio, fim)` SHALL apply the same validations as the domain (0002, R2) and, when valid, return `structuredContent` `{"sala", "livre", "conflitos": [{"id","inicio","fim","responsavel"}]}` plus the JSON text block.
- R6: Domain validation failures SHALL come back as a `complete` result with `isError: true` and the exact domain message in the text content (an SDK prefix such as `Error executing tool <nome>:` is acceptable).
- R7: A `tools/call` for an unknown tool SHALL be refused (the SDK's `isError: true` result is accepted).
- R8: The resource `politica://uso` SHALL return the content of `dados/politica-de-uso.md` with `mimeType` `text/markdown`; a `resources/read` of an unknown URI SHALL return JSON-RPC `-32602` (never empty `contents`).
- R9: `reservar_sala(sala, inicio, fim, responsavel)` SHALL be listed with an object `inputSchema` and an `outputSchema` with `reserva`, `reservado`, `sala`, `inicio`, `fim`, `responsavel`, `politica` and `motivo`; when the interval is valid and free it SHALL create the reservation and return those fields with `reservado: true` and `politica` equal to the policy version.
- R10: All three tools SHALL have a description in Brazilian Portuguese.

## Acceptance criteria
- [x] AC1: `tools/list` on `http://127.0.0.1:7301/mcp` returns the three tools, each with an `inputSchema` of `type: object`. (R1, R9)
- [x] AC2: Validator checks 01-12 pass. (R2, R4-R8)
- [x] AC3: A request without `_meta` gets HTTP 400 / `-32602` and still produces a stderr line with its method and id. (R2, R3)
- [x] AC4: A request with `_meta.traceparent` produces a stderr line containing that exact value. (R3)
- [x] AC5: `reservar_sala` for `sala-aquario` 09:00–10:00 on 2026-11-03 returns `reservado: true`, `reserva: res-0003`, `politica: 2026-11-01`. (R9)

## Unit tests
- T1: in-process (Starlette test client) `tools/list` returns three tools with object input schemas and the `listar_salas` output schema (AC1).
- T2: `listar_salas` structured content equals the parsed text block (AC2).
- T3: missing `protocolVersion` and missing `clientCapabilities` each give HTTP 400 and `-32602` (AC2, AC3).
- T4: each validation error of `consultar_disponibilidade` carries the exact message with `isError: true` (AC2).
- T5: `politica://uso` content and mime type; unknown URI gives `-32602` (AC2).
- T6: the log wrapper writes method, id, traceparent and status for a valid and for a rejected request (AC3, AC4).
- T7: `reservar_sala` happy path (AC5).
