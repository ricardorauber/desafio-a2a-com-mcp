# 0005 - a2a-sdk defaults: version header, context id, history and terminal Tasks

- Date: 2026-10-16
- Spec: 0006
- Status: accepted

## Context
Spikes with `a2a-sdk` 1.2.2 showed three behaviors that conflict with the validator and the statement:
1. A request without the `A2A-Version` header is treated as 0.3 and rejected with `-32009`; the validator sends no such header.
2. A continuation with `taskId` and no `contextId` gets a newly generated context id on the stored message and on the reply.
3. The final status message only enters `history` when a later user message arrives, but the statement asks for the failure message to be visible in the history (and `exemplos/wire/08` shows the `alternativas:` message already in the `SendMessage` history).
4. A `SendMessage` on a terminal Task is refused (`-32004`) only after the SDK has created an active task, whose event dispatcher is then left pending (`Task was destroyed but it is pending!` and OpenTelemetry `Failed to detach context` in the log, seen during spec 0007).

## Decision
1. A call-context builder (subclass of `DefaultServerCallContextBuilder`) defaults the header to `1.0`.
2. A request-context builder inherits the Task's `contextId` when the continuation omits it.
3. A task store wrapper and a request handler subclass apply the same normalization to what is stored and to the `SendMessage` result: the current status message is appended to `history` when it is not already there (deduplicated by `messageId`).
4. The request-context builder, which already loads the stored Task, refuses a terminal Task first with the same `-32004` error, before any active task exists.

## Consequences
All four are small, local adapters around public extension points; the README lists them as SDK findings.

## Addendum (spec 0009)
`CancelTask` in `a2a-sdk` 1.2.2 (`ActiveTask.cancel`) always stops a running producer, and marks the Task FAILED when `AgentExecutor.cancel` raises; for a paused Task it writes CANCELED without calling the executor. So the executor's `cancel` never refuses: it waits for a running continuation to finish (its MCP retry and the Task outcome stay consistent), and the task store drops the paused state whenever a Task turns terminal. Continuations are claimed atomically in the request-context builder, so a second concurrent one is refused with `-32004`.
