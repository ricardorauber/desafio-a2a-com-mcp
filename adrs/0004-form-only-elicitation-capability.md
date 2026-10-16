# 0004 - Narrow the agent's elicitation capability to form mode

- Date: 2026-10-16
- Spec: 0005
- Status: accepted

## Context
The statement requires every MCP request of the agent to declare `{"elicitation": {"form": {}}}`. In `mcp` 2.3.0, `ClientSession._build_capabilities` advertises `{"form": {}, "url": {}}` whenever an `elicitation_callback` is set, and advertises nothing without one; there is no public parameter to choose the modes (evidence: `mcp/client/session.py`, `_build_capabilities`). The agent must not answer elicitations through a callback anyway, because the question has to reach the A2A client.

## Options considered
- A: Accept `form` + `url` (declares a mode the agent cannot honor).
- B: Write a custom HTTP MCP client (reimplements header mirroring and `_meta` stamping).
- C: Keep the SDK `Client`, and override only the capability builder in one small subclass that returns form-only elicitation.

## Decision
C, documented in the README as an SDK limitation with the evidence above.

## Consequences
The override touches a private method of a pinned SDK version; an SDK upgrade must re-check it (covered by a unit test asserting the serialized capability).
