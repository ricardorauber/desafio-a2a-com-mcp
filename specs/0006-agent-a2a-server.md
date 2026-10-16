# 0006 - Agent as A2A server

## Goal
Expose the room booking capability as an A2A v1.0 agent (JSON-RPC binding) with a public Agent Card, `SendMessage` and `GetTask`, and a Task state machine that ends in `COMPLETED` or `FAILED` for requests that need no choice.

## Scope
- In: `agente/agente_a2a/cartao.py` (Agent Card), `agente/agente_a2a/pedido.py` (parsing of the fixed request text), `agente/agente_a2a/executor.py` (the `AgentExecutor`), `agente/agente_a2a/app.py` (Starlette app, request handler, task store, call-context builder), `agente/agente_a2a/__main__.py` (uvicorn startup).
- Out: pausing and resuming Tasks (0007), streaming, push notifications, authentication.

## Requirements
- R1: `GET /.well-known/agent-card.json` SHALL return HTTP 200 with the v1.0 card: name `Central de Salas`, description `Reserva salas de reuniao da Hill Valley Tech.`, provider `Hill Valley Tech` / `https://hillvalley.example`, version `1.0.0`, `supportedInterfaces` `[{"url": "<AGENT_PUBLIC_URL>/a2a", "protocolBinding": "JSONRPC", "protocolVersion": "1.0"}]`, capabilities `streaming`, `pushNotifications` and `extendedAgentCard` all `false`, default input/output modes `text/plain`, and one skill `reservar-sala` (name, description, tags, modes and example as in `exemplos/wire/07-a2a-agent-card.json`). No `securitySchemes`.
- R2: The JSON-RPC endpoint `/a2a` on port `AGENT_PORT` (default `7300`) SHALL accept `SendMessage` and `GetTask` using the official `a2a-sdk` request handler and an in-memory task store; requests without an `A2A-Version` header SHALL be treated as version `1.0`.
- R3: A `SendMessage` without `taskId` SHALL open a new Task with its own `id` and `contextId`; a continuation with `taskId` and no `contextId` SHALL keep the Task's `contextId`.
- R4: The Task SHALL pass through `TASK_STATE_SUBMITTED` and `TASK_STATE_WORKING` before any other state, `SendMessage` SHALL answer only when the Task is terminal or interrupted, and `GetTask` SHALL return the current `id`, `contextId`, status, history and artifacts at any time.
- R5: The first message SHALL match exactly `reservar sala=<id> inicio=<iso8601> fim=<iso8601> responsavel=<nome>` (the name may contain spaces); otherwise the Task SHALL end `TASK_STATE_FAILED` with the message `Pedido invalido: use reservar sala=<id> inicio=<iso8601> fim=<iso8601> responsavel=<nome>`. The agent SHALL NOT validate rooms, times or policy itself.
- R6: WHEN the host returns `Concluida`, the Task SHALL get one artifact named `reserva` whose single text part is the JSON object `{"reserva","sala","inicio","fim","responsavel","politica"}` built from the tool's `structuredContent` with `politica` set to the version the agent read from `politica://uso`, and SHALL end `TASK_STATE_COMPLETED` with the agent message `Reserva <reserva> confirmada na <sala>.`
- R7: WHEN the host returns `FalhaFerramenta` or `FalhaProtocolo`, the Task SHALL end `TASK_STATE_FAILED` with an agent message whose text is exactly the host's text.
- R8: The final agent status message of a Task SHALL also be present in the Task `history` (each message once).
- R9: A `SendMessage` referencing a Task in a terminal state SHALL be refused with a JSON-RPC error and SHALL NOT change the Task.
- R10: The executor SHALL be deterministic: the same request against the same server state produces the same states and texts. No LLM SHALL be used.

## Acceptance criteria
- [ ] AC1: `curl http://localhost:7300/.well-known/agent-card.json` matches the interface, protocol version and skill of `exemplos/wire/07-a2a-agent-card.json`; validator checks 21-23 pass. (R1)
- [ ] AC2: Validator checks 24-26 and 35 pass. (R2-R7)
- [ ] AC3: A Task's state sequence recorded by the store is `SUBMITTED → WORKING → COMPLETED` for a free room. (R4)
- [ ] AC4: `SendMessage` on a completed Task returns a JSON-RPC `error` and `GetTask` still shows `COMPLETED`. (R9)
- [ ] AC5: The FAILED Task for `sala-inexistente` shows `Sala inexistente: sala-inexistente` in `status.message` and in `history`. (R7, R8)
- [ ] AC6: A malformed request ends `FAILED` with the `Pedido invalido` message. (R5)

## Unit tests
- T1: card fields and JSON serialization (AC1).
- T2: request parsing — valid, name with spaces, missing field, extra text (AC6).
- T3: executor with a fake host for `Concluida`, `FalhaFerramenta`, `FalhaProtocolo` — states, messages, artifact JSON (AC2, AC3, AC5).
- T4: JSON-RPC app with a fake host: `SendMessage` without `A2A-Version`, `GetTask`, terminal-state refusal, history contains the final message once (AC2, AC4, AC5).
