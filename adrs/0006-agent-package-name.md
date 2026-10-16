# 0006 - Name the agent's Python package `agente_a2a`

- Date: 2026-10-16
- Spec: 0001-project-setup
- Status: accepted

## Context
Spec 0001 named the agent package `agente/agente/` with entry point `python -m agente`. The processes are started from the repository root, where the top-level folder `agente/` (no `__init__.py`, required by the starter structure) is picked up by Python as a namespace package named `agente` and shadows the installed package: `import agente` resolved to the folder and `python -m agente` did not run the real entry point.

## Options considered
- A: Keep the name and require `pip install --config-settings editable_mode=compat` — fragile, an extra flag the evaluator must not forget.
- B: Rename the inner package to `agente_a2a` (entry point `python -m agente_a2a`) — no collision with the folder.

## Decision
B, following the standing instruction to take the recommended option ("Pode ir sempre pelas recomendações" — "you can always go with the recommendations").

## Consequences
Specs 0001, 0005, 0006 and 0007 refer to `agente/agente_a2a/` and `python -m agente_a2a`; the folder `agente/` stays as the starter requires.
