# 0003 - Python stack, and MRTR driven by the tool body

- Date: 2026-10-16
- Spec: 0001, 0003, 0004
- Status: accepted

## Context
Both official SDKs are allowed. The wire examples were captured with the Python SDK. The Python `mcp` 2.3.0 SDK offers two MRTR styles: `Resolve(...)`/`Elicit` resolvers (the question is re-derived each round, the request state carries only the recorded answers) or a tool that returns `InputRequiredResult` itself and reads `ctx.input_responses`/`ctx.request_state` on the retry. Either way, the SDK's `RequestStateBoundary` seals the state (AES-256-GCM, TTL, audience, binding to method, tool name and argument digest).

## Options considered
- A: Resolvers — less code; the original request is not inside the state, so after a restart the alternatives are recomputed rather than read back.
- B: Tool body returns `InputRequiredResult` with the full request (room, interval, owner, alternatives, key) as plaintext state, sealed by the SDK boundary.

## Decision
B. The statement requires the state to carry everything needed to rebuild the request and the retry to use sealed values; option B makes both literal while still using the SDK utility for integrity. The capability check (`-32021`) is raised by the tool before returning the elicitation, with the same error shape the SDK resolvers use. Stack: Python 3.10+, `mcp==2.3.0`, `a2a-sdk[http-server]==1.2.2`, `uvicorn==0.54.0`.

## Consequences
The tool owns a small amount of round logic (accept/decline/cancel/out-of-enum). Divergent retry arguments are rejected by the SDK binding (`-32602`) before the handler runs.
