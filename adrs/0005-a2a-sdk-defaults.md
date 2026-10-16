# 0005 - a2a-sdk defaults: version header, context id and history

- Date: 2026-10-16
- Spec: 0006
- Status: accepted

## Context
Spikes with `a2a-sdk` 1.2.2 showed three behaviors that conflict with the validator and the statement:
1. A request without the `A2A-Version` header is treated as 0.3 and rejected with `-32009`; the validator sends no such header.
2. A continuation with `taskId` and no `contextId` gets a newly generated context id on the stored message and on the reply.
3. The final status message only enters `history` when a later user message arrives, but the statement asks for the failure message to be visible in the history.

## Decision
1. A call-context builder (subclass of `DefaultServerCallContextBuilder`) defaults the header to `1.0`.
2. A request-context builder inherits the Task's `contextId` when the continuation omits it.
3. A task store wrapper appends the current status message to `history` when it is not already there (deduplicated by `messageId`).

## Consequences
All three are small, local adapters around public extension points; the README lists them as SDK findings.
