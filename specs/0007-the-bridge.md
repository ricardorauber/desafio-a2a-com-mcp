# 0007 - The bridge: MCP `input_required` ↔ A2A `TASK_STATE_INPUT_REQUIRED`

## Goal
Turn the MCP server's `input_required` into a paused A2A Task, keep the `requestState` bound to that Task inside the agent, and resume the original `tools/call` with a new id when the A2A client answers.

## Scope
- In: `agente/agente/ponte.py` (per-Task paused state store) and the pause/resume branches of `agente/agente/executor.py`.
- Out: room rules (they stay in the MCP server), streaming, cross-Task references.

## Requirements
- R1: WHEN the host returns `Pausada`, the Task SHALL move to `TASK_STATE_INPUT_REQUIRED` with an agent message whose text is exactly `alternativas: <ids separados por ", ">` in the order received, nothing else.
- R2: The agent SHALL keep, per Task id, only the protocol data needed to resume: the original `reservar_sala` arguments, the elicitation key, the offered alternatives, the opaque `request_state`, the Task's trace id and the policy version. This state SHALL live in process memory, SHALL never appear in the card, artifacts, messages, errors or logs returned to or seen by the A2A client, and SHALL be discarded when the Task reaches a terminal state.
- R3: A continuation `SendMessage` with `taskId` of a paused Task SHALL accept exactly `escolha=<valor>`:
  - `<valor>` in the stored alternatives → retry with `accept` and that room;
  - `recusar` → retry with `decline`;
  - anything else (unknown room, other text) → no MCP call; the Task stays `TASK_STATE_INPUT_REQUIRED` and the agent message repeats the same `alternativas:` line.
- R4: The retry SHALL go through the host's retry (0005 R6): a new JSON-RPC id, the same key, the `request_state` echoed unchanged, and the Task's trace id.
- R5: Retry outcomes SHALL map as: `Concluida` → artifact `reserva` and `TASK_STATE_COMPLETED` (0006 R6); `Recusada` → `TASK_STATE_CANCELED` with the message `Reserva recusada.`; `Pausada` (the server re-asked) → `TASK_STATE_INPUT_REQUIRED` with the new alternatives, replacing the stored state; `FalhaFerramenta`/`FalhaProtocolo` → `TASK_STATE_FAILED` (0006 R7).
- R6: Paused state SHALL be isolated per Task: two Tasks paused at the same time SHALL each resume with their own `request_state`, and concurrent continuations of the same Task SHALL be processed one at a time.
- R7: The trace id of a Task SHALL be the one taken when the Task was opened; every MCP request of that Task, including the retry, SHALL use it.

## Acceptance criteria
- [ ] AC1: Validator checks 27-34 and 36 pass. (R1-R6)
- [ ] AC2: The manual flow with `exemplos/wire/08-a2a-send-message.json` pauses with `alternativas: sala-fusca, sala-mirante`; `escolha=sala-mirante` completes with an artifact pointing to `sala-mirante` with `politica`; repeating and answering `escolha=recusar` ends `TASK_STATE_CANCELED`. (R1, R3, R5)
- [ ] AC3: In the MCP server stderr, the two `tools/call` of a paused-then-resumed reservation have different ids and the same trace id. (R4, R7)
- [ ] AC4: No A2A response body contains any prefix of the `requestState`. (R2)

## Unit tests
- T1: pause message format, including a single alternative (R1).
- T2: continuation parsing — valid choice, `recusar`, out-of-enum, malformed (R3).
- T3: executor with a fake host — retry receives the stored key, the untouched `request_state` and the Task trace id; each outcome maps to the right state and message (R4, R5, R7).
- T4: two paused Tasks resume with their own `request_state`; the store is emptied on terminal states (R2, R6).
- T5: no A2A-visible field (status message, history, artifacts) contains the `request_state` (AC4).
