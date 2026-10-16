# 0001 - Project setup and conventions

## Goal
Give both processes (`servidor-mcp/` and `agente/`) a pinned, reproducible Python project skeleton, a shared test setup and the repository conventions every later spec relies on.

## Scope
- In: `servidor-mcp/pyproject.toml`, `agente/pyproject.toml`, empty packages `servidor-mcp/servidor_mcp/` and `agente/agente/` with `__main__.py` stubs, `requirements.lock`, root `pytest.ini`, `.env.example`, `.gitignore` additions, removal of the `.gitkeep` files, the repository conventions below.
- Out: any MCP or A2A behavior (0002-0007), README content (0008).

## Requirements
- R1: The system SHALL target Python 3.10 or newer, and every direct dependency SHALL be pinned to an exact version: in `servidor-mcp/pyproject.toml` `mcp==2.3.0` and `uvicorn==0.54.0`; in `agente/pyproject.toml` `mcp==2.3.0`, `a2a-sdk[http-server]==1.2.2`, `uvicorn==0.54.0` and `httpx==0.28.1`; test extras `pytest` and `pytest-asyncio` pinned in both.
- R2: The system SHALL ship `requirements.lock` at the root with the exact versions of every installed package (direct and transitive) of a fresh environment that installed both projects, so that `pip install -c requirements.lock -e ./servidor-mcp[test] -e ./agente[test]` is reproducible.
- R3: No dependency on any LLM provider SDK (OpenAI, Anthropic, Google GenAI, LangChain or similar) SHALL appear in either `pyproject.toml` or in `requirements.lock`.
- R4: `python -m servidor_mcp` and `python -m agente` SHALL be the entry points of the two processes (stubs in this spec).
- R5: `.env.example` SHALL list `REQUEST_STATE_SECRET=` (empty), `MCP_PORT=7301`, `AGENT_PORT=7300`, `MCP_URL=http://127.0.0.1:7301/mcp` and `AGENT_PUBLIC_URL=http://127.0.0.1:7300`, and `.env` SHALL stay ignored by git.
- R6: `pytest` run from the repository root SHALL discover `servidor-mcp/tests/` and `agente/tests/`.
- R7: The files under `dados/`, `validador/` and `exemplos/` SHALL NOT be modified by this or any later spec.

## Acceptance criteria
- [ ] AC1: In a fresh Python 3.10+ venv, `pip install -c requirements.lock -e ./servidor-mcp[test] -e ./agente[test]` succeeds. (R1, R2)
- [ ] AC2: Every entry in `dependencies` and in the `test` extra of both `pyproject.toml` files uses `==`. (R1)
- [ ] AC3: `grep -iE "openai|anthropic|langchain|google-genai|google-generativeai|litellm" */pyproject.toml requirements.lock` finds nothing. (R3)
- [ ] AC4: `python -m servidor_mcp --help` and `python -m agente --help` exit 0 (stubs). (R4)
- [ ] AC5: `.env.example` has exactly the variables of R5 and `git check-ignore .env` succeeds. (R5)
- [ ] AC6: `pytest` from the root collects the smoke tests of both packages and passes. (R6)
- [ ] AC7: `git diff --stat <starter commit> -- dados validador exemplos` is empty. (R7)

## Unit tests
- T1: `servidor-mcp/tests/test_smoke.py` imports `servidor_mcp` (AC6).
- T2: `agente/tests/test_smoke.py` imports `agente` (AC6).
