# 0009 - Hardening from the independent review

## Goal
Close the gaps an independent review found in the built specs 0003-0007: replayed retries, cancel and concurrent continuations racing a retry, a weak-secret loophole, leaked per-Task locks and over-advertised server capabilities.

## Scope
- In: `servidor-mcp/servidor_mcp/servidor.py`, `servidor-mcp/servidor_mcp/dominio.py`, `servidor-mcp/servidor_mcp/seguranca.py`, `agente/agente_a2a/executor.py`, `agente/agente_a2a/app.py`, `agente/agente_a2a/ponte.py` and their tests.
- Out: the trace id of a continuation (spec 0007 R7 keeps the Task's trace id on purpose), README (0008).

## Requirements
- R1: Each `input_required` round SHALL seal a random nonce in the request state. WHEN an accepted retry carries a nonce whose reservation already exists in the running process, the server SHALL return that same reservation as `complete` instead of booking again.
- R2: WHEN `REQUEST_STATE_SECRET` consists only of hexadecimal characters, it SHALL have at least 64 characters (32 decoded bytes); any other value SHALL have at least 32 bytes. Otherwise the server SHALL refuse to start as in 0004 R7.
- R3: The MCP server SHALL NOT advertise `resources.subscribe` or `listChanged` (subscriptions are out of scope); it uses the SDK option that disables `subscriptions/listen`.
- R4: A `CancelTask` of a paused Task SHALL end it `TASK_STATE_CANCELED` and drop its paused state. WHEN a continuation of that Task is already running, the cancel SHALL wait for it to finish, so that the MCP retry it sent is never left half-applied (no reservation without its artifact), and SHALL return the resulting Task. A `CancelTask` of a terminal Task SHALL be refused with a JSON-RPC error and SHALL NOT change it. (The `a2a-sdk` always stops a running producer on cancel and marks the Task FAILED if the executor refuses, so refusing is not an option there.)
- R5: A `SendMessage` with the `taskId` of a Task that is not in `TASK_STATE_INPUT_REQUIRED` (terminal, or still working) SHALL be refused with a JSON-RPC error before the executor runs.
- R6: The per-Task lock and paused state SHALL be released whenever a Task leaves the paused state, including invalid requests and failures.

## Acceptance criteria
- [x] AC1: Replaying one accepted retry (same state, same key, another allowed room) returns the first reservation and creates no second one. (R1)
- [x] AC2: `REQUEST_STATE_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(16))")` is refused; `token_hex(32)` is accepted. (R2)
- [x] AC3: `server/discover` reports `resources.subscribe` and every `listChanged` as false or absent. (R3)
- [x] AC4: `CancelTask` on a paused Task ends it CANCELED and a later continuation is refused; `CancelTask` racing a continuation never leaves a reservation without a COMPLETED Task and artifact; `CancelTask` on a COMPLETED Task returns an error. (R4)
- [x] AC5: A continuation sent while the same Task is WORKING is refused with an error. (R5)
- [x] AC6: After an invalid request and after a completed Task, no lock or paused state remains for them. (R6)
- [x] AC7: Validator still passes 36/36 with fresh processes. (R1-R6)

## Unit tests
- T1: replayed accepted retry returns the same reservation id and books nothing else (AC1).
- T2: secret length rules for hex and non-hex values (AC2).
- T3: discover capabilities without subscribe/listChanged (AC3).
- T4: cancel of a paused Task, of a completed Task, and cancel waiting for a running continuation (AC4).
- T5: builder refuses a continuation for a WORKING Task (AC5).
- T6: lock and pause store are empty after invalid and completed Tasks (AC6).
