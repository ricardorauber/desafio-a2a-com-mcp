# 0004 - MRTR cycle of `reservar_sala`

## Goal
When the requested room is taken, `reservar_sala` finishes its response asking for a choice (`input_required` with a form elicitation and a sealed `requestState`) and completes on the client's retry, without any server-side memory between rounds.

## Scope
- In: the conflict branch of `reservar_sala`, the sealed request state (`RequestStateSecurity` from the SDK), the retry handling, the capability check, startup checks of `REQUEST_STATE_SECRET`.
- Out: the agent side of the cycle (0005, 0007).

## Requirements
- R1: The server SHALL never call the client mid-execution: the conflict branch SHALL return an SDK `InputRequiredResult` (`resultType: input_required`).
- R2: WHEN the requested interval is valid but conflicts and at least one alternative exists (0002, R5), `reservar_sala` SHALL return `inputRequests` with exactly one entry, key `escolha_de_sala`, whose value is an `elicitation/create` request in `mode: form` with message `A sala pedida esta ocupada nesse intervalo. Escolha uma alternativa.` and a flat `requestedSchema` `{"type":"object","properties":{"sala":{"type":"string","title":"Sala","description":"Sala alternativa escolhida","enum":[<alternativas na ordem da regra>]}},"required":["sala"]}`.
- R3: WHEN the request conflicts and no alternative exists, the tool SHALL return `isError: true` with `Sem alternativas disponiveis no intervalo` and no elicitation.
- R4: WHEN an elicitation is needed and the request's `clientCapabilities` does not declare `elicitation.form`, the server SHALL answer JSON-RPC `-32021` with `data.requiredCapabilities = {"elicitation": {"form": {}}}` and HTTP `400`.
- R5: The plaintext request state SHALL carry everything needed to finish the request: `sala`, `inicio`, `fim`, `responsavel`, the offered `alternativas` and the elicitation key. The server SHALL keep nothing in memory between `input_required` and the retry.
- R6: The request state SHALL be sealed by the SDK's `RequestStateSecurity` (AES-256-GCM, key derived from `REQUEST_STATE_SECRET`, audience = server name) with a TTL of 600 seconds; the SDK also binds the token to the tool name and the original arguments.
- R7: `REQUEST_STATE_SECRET` SHALL come only from the environment; WHEN it is missing or shorter than 32 bytes, the server SHALL refuse to start with a Brazilian Portuguese message on stderr that explains how to generate it, and exit with a non-zero code. No secret SHALL exist in the code or the repository.
- R8: WHEN a retry carries a tampered, foreign or expired `requestState`, the server SHALL answer JSON-RPC `-32602` (the SDK's `Invalid or expired requestState`) and create nothing. WHEN the retry's arguments differ from the sealed ones, the SDK binding SHALL reject it with `-32602`; the handler SHALL in any case use only the sealed values.
- R9: On a retry, the handler SHALL read `inputResponses` and `requestState` from `params`, rebuild the request from the sealed state, and:
  - `action: accept` with `content.sala` in the sealed `alternativas` → re-validate that room for the sealed interval; if free, create the reservation for the chosen room with the sealed interval and `responsavel` and return it as in 0003 R9; if it became taken, recompute alternatives and return a new `input_required` (or the R3 error when none is left);
  - `action: accept` with a room outside the sealed `alternativas`, or no answer for the key → return the original `input_required` again with the same alternatives;
  - `action: decline` or `cancel` → return a `complete` result without `isError`, with `structuredContent` `reservado: false` and `motivo: "recusado"` (decline) or `motivo: "cancelado"` (cancel), and create nothing.
- R10: The retry SHALL succeed after the server process restarts, as long as the same `REQUEST_STATE_SECRET` is used and the token has not expired.

## Acceptance criteria
- [ ] AC1: Validator checks 13-20 pass. (R1-R4, R8, R9)
- [ ] AC2: `sala-garagem` 14:00–15:00 on 2026-11-03 yields `input_required` with one `escolha_de_sala` entry, `mode: form` and enum `["sala-fusca", "sala-mirante"]`. (R2)
- [ ] AC3: Changing one character of the `requestState` gives `-32602`. (R8)
- [ ] AC4: Restarting the server between `input_required` and the retry still completes the reservation. (R10)
- [ ] AC5: Starting without `REQUEST_STATE_SECRET`, or with a 16-byte value, exits non-zero with the guidance message. (R7)
- [ ] AC6: `grep -rn "REQUEST_STATE_SECRET" servidor-mcp` shows only environment reads, docs and tests that generate a random value. (R7)
- [ ] AC7: `decline` returns `reservado: false`, `motivo: "recusado"`, no `isError`, and the room stays free. (R9)

## Unit tests
- T1: conflict returns the exact elicitation shape and enum order (AC2).
- T2: no alternatives returns the exact `isError` message (R3).
- T3: empty capabilities and `{"elicitation": {"url": {}}}` both give `-32021`, HTTP 400 and `requiredCapabilities` (R4).
- T4: accept retry creates the reservation in the chosen room with the sealed interval (R9).
- T5: tampered token and expired token (TTL patched) give `-32602` (AC3).
- T6: retry with different arguments is rejected and creates nothing (R8).
- T7: decline and cancel (AC7).
- T8: choice outside the enum re-asks; chosen room taken meanwhile re-asks with new alternatives (R9).
- T9: a token minted by one app instance is accepted by a fresh instance with the same secret (AC4).
- T10: startup refuses a missing or short secret (AC5).
