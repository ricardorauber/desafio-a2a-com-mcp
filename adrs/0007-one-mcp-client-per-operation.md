# 0007 - Open one SDK MCP client per host operation

- Date: 2026-10-16
- Spec: 0005-agent-mcp-host
- Status: accepted

## Context
Spec 0005 allowed one long-lived `Client`. With `mcp` 2.3.0, a connection error in any POST is raised inside the Streamable HTTP transport's task group (`mcp/client/streamable_http.py`, `_run_request_post`), which tears the whole client down and propagates to whoever entered it; a long-lived client entered in the app lifespan would take the agent down when the MCP server restarts. Also, `ClientSession.validate_tool_result` re-lists tools on its own (without the caller's `_meta`, so without `traceparent`) when the output-schema cache is empty.

## Options considered
- A: Long-lived client in a supervised background task, recreated after a failure — more moving parts.
- B: A fresh client per host operation (initial reservation, retry) — no handshake is needed with the protocol pinned to `2026-07-28`, and failures stay local.

## Decision
B, following the standing instruction to take the recommended option. Every operation starts with its own `tools/list` (carrying the Task's `traceparent`), which also primes the schema cache so the SDK never re-lists without trace context.

## Consequences
JSON-RPC ids restart per client: the initial `tools/call` of a Task is id 3 (after `tools/list` and `resources/read`) and its retry is id 2 (after `tools/list`), so they always differ; requests are told apart in the MCP log by their trace id.
