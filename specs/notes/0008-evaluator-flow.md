# 0008 - Evaluator flow evidence

Run on 2026-10-16 from a fresh clone of `main` (commit 214cdbf) in a temporary folder, Python 3.14.2, following only the README. `pytest`: 104 passed. Validator: 36 passed, exit code 0 (output in the README).

| Step | Check | Observed |
|---|---|---|
| 3 | Agent Card vs `exemplos/wire/07` | identical JSON; `supportedInterfaces` JSONRPC `1.0` at `http://127.0.0.1:7300/a2a`; skill `reservar-sala` |
| 5 | `tools/list` before first `tools/call`; validator trace id in MCP stderr | `tools/list id=101` then `tools/call id=103`, both with `traceparent=00-cf325ea8c1240adad04c0b3b658cfdab-...` (9 lines with that trace id) |
| 6 | Paused reservation: retry id differs | `tools/call id=103` (initial) and `tools/call id=202` (retry), same trace id `4bf92f3577b34da6a3ce929d0e0e4736` |
| 7 | `exemplos/wire/08` after restart | `TASK_STATE_INPUT_REQUIRED`, `alternativas: sala-fusca, sala-mirante` |
| 8 | `escolha=sala-mirante`, then `GetTask` | `TASK_STATE_COMPLETED`, artifact `reserva` with `"sala": "sala-mirante"` and `"politica": "2026-11-01"` |
| 9 | Same request, `escolha=recusar` | paused with `alternativas: sala-fusca` (mirante now taken), then `TASK_STATE_CANCELED` |
| 10 | `sala=sala-inexistente` | `TASK_STATE_FAILED`, `Sala inexistente: sala-inexistente` in status message and history |
| 11 | `exemplos/wire/03`, one character of `requestState` changed | HTTP 400, `-32602 Invalid or expired requestState` |
| 12 | Untouched `requestState`, MCP server restarted before the retry | HTTP 200, reservation `res-0003` in `sala-fusca` |
| 13 | Same call without `elicitation` | HTTP 400, `-32021`, `requiredCapabilities: {"elicitation": {"form": {}}}` |

No `ERROR` or traceback in either process log.
