# 0008 - README, end-to-end verification and delivery

## Goal
Replace the starter README with the delivery documentation, prove the whole flow from a clean clone, and publish it on `main` of the public fork.

## Scope
- In: `README.md` (Brazilian Portuguese), helper scripts at the root (`scripts/`), full validator run, the evaluator's manual flow, push to `main`.
- Out: code changes beyond fixes found by the verification (those go back to the spec they belong to).

## Requirements
- R1: The README SHALL have the four sections `Como rodar`, `Onde a ponte acontece`, `Decisões técnicas` and `Saída do validador`, in Brazilian Portuguese.
- R2: `Como rodar` SHALL give the exact commands, from a clean clone, to create the venv, install with `requirements.lock`, generate and export `REQUEST_STATE_SECRET` with `python3 -c "import secrets; print(secrets.token_hex(32))"` (never a real value), start the MCP server and the agent in two terminals, and run `python3 validador/validar.py --agente http://localhost:7300 --mcp http://localhost:7301`.
- R3: `Onde a ponte acontece` SHALL point (file and function) to where the MCP `input_required` becomes `TASK_STATE_INPUT_REQUIRED` and to where the `requestState` goes back to the server.
- R4: `Decisões técnicas` SHALL state how the `requestState` is protected (SDK AES-256-GCM, key from `REQUEST_STATE_SECRET`, binding to tool and arguments), its 10-minute validity, where Task and paused state live (agent memory), and the SDK limitations found with their evidence (the form-only capability narrowing; the `A2A-Version` default).
- R5: `Saída do validador` SHALL contain the complete output of the last run, with both processes freshly started, in a code block, ending with 36 passes and exit code 0.
- R6: The evaluator flow (steps 3-13 of the statement) SHALL be executed manually and pass, including the restart of the MCP server between `input_required` and retry, and the trace id visible in the MCP stderr.
- R7: The delivery SHALL be on `main` of `ricardorauber/desafio-a2a-com-mcp`, with `dados/`, `validador/` and `exemplos/` unchanged.

## Acceptance criteria
- [x] AC1: Following only the README in a fresh clone in a temporary folder, the validator ends with `resumo: 36 passaram, 0 falharam` and exit code 0. (R2, R5)
- [x] AC2: The README has the four section headings of R1. (R1)
- [x] AC3: The README references existing file paths and function names for the bridge. (R3)
- [x] AC4: Evaluator steps 3-13 pass and their evidence (stderr lines with trace id, distinct retry ids) is recorded in the build notes. (R6)
- [x] AC5: `git diff --stat 263f17e -- dados validador exemplos` is empty on `origin/main`. (R7)

## Unit tests
- T1: none — this spec is verified end to end by AC1-AC5.
