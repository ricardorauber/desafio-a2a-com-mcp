# 0005 - Agent as MCP host

## Goal
Give the agent an MCP client layer that talks to the MCP server over HTTP like a real client — runtime discovery, policy read, raw view of `input_required`, retry with a new id — and propagates the trace context, without any room business rule.

## Scope
- In: `agente/agente_a2a/trace.py` (W3C `traceparent` parsing and child span generation), `agente/agente_a2a/host_mcp.py` (a long-lived SDK `Client` wrapper and the result types the A2A layer consumes).
- Out: A2A server and Task handling (0006), the bridge between both (0007).

## Requirements
- R1: The agent SHALL use the official `mcp` SDK `Client` over Streamable HTTP pinned to protocol `2026-07-28` (no `server/discover` probe), connecting to `MCP_URL` (default `http://127.0.0.1:7301/mcp`), with `clientInfo` `agente-central-de-salas` / `1.0.0` and response caching disabled. One client object MAY be kept alive for the whole process.
- R2: Every MCP request emitted by the agent SHALL carry in `_meta` the protocol version, the client info and `io.modelcontextprotocol/clientCapabilities` exactly `{"elicitation": {"form": {}}}`, and the headers `MCP-Protocol-Version`, `Mcp-Method` and, for `tools/call` and `resources/read`, `Mcp-Name` (mirrored by the SDK transport). Because the SDK advertises `url` too whenever an elicitation callback exists, the agent SHALL narrow the advertised capability to form mode in one documented place; no elicitation callback SHALL ever answer a question on its own.
- R3: The agent SHALL discover the tools with `tools/list` before its first `tools/call` of each Task and SHALL NOT hold a hardcoded tool list; WHEN `reservar_sala` is not among the discovered tools the operation SHALL fail with `Ferramenta reservar_sala nao encontrada no servidor MCP`.
- R4: The agent SHALL read the resource `politica://uso` and extract the version from the first line `versao: <valor>`.
- R5: The agent SHALL call `reservar_sala` with `allow_input_required=True` and classify the outcome as exactly one of:
  - `Concluida(structured_content)` — `complete`, no `isError`, `reservado: true`;
  - `Recusada(motivo)` — `complete`, no `isError`, `reservado: false`;
  - `Pausada(chave, alternativas, request_state)` — `input_required` with one `elicitation/create` in form mode; `alternativas` is the `enum` (or the single `const`) of `requestedSchema.properties.sala`, in received order; `request_state` is kept as the exact opaque string;
  - `FalhaFerramenta(texto)` — `isError: true`, with the text blocks joined unchanged;
  - `FalhaProtocolo(texto)` — a JSON-RPC error (`Erro MCP <code>: <message>`) or an unreachable server (`Servidor MCP indisponivel`).
- R6: The retry SHALL re-send the same `tools/call` (same name and the same original arguments) with a new JSON-RPC id, `inputResponses` keyed by exactly the key received in `inputRequests`, and the `requestState` echoed byte for byte. A choice becomes `{"action": "accept", "content": {"sala": <id>}}`; a refusal becomes `{"action": "decline"}`.
- R7: The agent SHALL NOT open, decode, interpret or rebuild `request_state`, and SHALL NOT log it.
- R8: WHEN the caller provides a trace id, every MCP request of that operation SHALL carry `_meta.traceparent` `00-<same trace-id>-<new 16-hex span-id>-01`; WHEN the inbound `traceparent` is absent or malformed, a new random trace id SHALL be generated for the Task.

## Acceptance criteria
- [ ] AC1: Against the running MCP server, the server's stderr shows `tools/list` before the first `tools/call` issued by the host, all with the same trace id. (R3, R8)
- [ ] AC2: The captured request bodies show `clientCapabilities` equal to `{"elicitation": {"form": {}}}` and the mirrored headers. (R2)
- [ ] AC3: A conflicting reservation returns `Pausada` with key `escolha_de_sala` and alternatives `["sala-fusca", "sala-mirante"]`; the retry with `sala-fusca` returns `Concluida` and its JSON-RPC id differs from the first call's. (R5, R6)
- [ ] AC4: `sala-delorean` returns `FalhaFerramenta` whose text contains `Sala inexistente: sala-delorean`. (R5)
- [ ] AC5: The policy version read is `2026-11-01`. (R4)

## Unit tests
- T1: `traceparent` parsing — valid header keeps the trace id; invalid/absent generates a new one; child span ids are 16 hex chars and differ per call (R8).
- T2: outcome classification from canned SDK results for each of the five variants, including `const` with a single alternative (R5).
- T3: the narrowed capability serializes to `{"elicitation": {"form": {}}}` (R2).
- T4: version extraction from the policy text (R4).
- T5: integration with the MCP server app in a background uvicorn on a free port: discovery order, pause, retry with a new id, failure text (AC1, AC3, AC4).
