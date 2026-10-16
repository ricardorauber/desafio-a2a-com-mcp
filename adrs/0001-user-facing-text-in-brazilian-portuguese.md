# 0001 - User-facing text in Brazilian Portuguese, code and specs in English

- Date: 2026-10-16
- Spec: all
- Status: accepted

## Context
The challenge statement, the data, the validator and the exact error messages are in Brazilian Portuguese (without accents in the protocol messages). The SDD artifacts follow the convention of the previous MBA challenges.

## Decision
README, tool descriptions, agent messages and startup errors are in Brazilian Portuguese; protocol messages copy the statement byte for byte. Specs, ADRs, code identifiers that are not domain terms, and commit messages are in English. Domain terms (`sala`, `reserva`, `politica`) keep the statement's names.

## Consequences
Wire strings can be compared against the statement without translation; engineering artifacts stay consistent with the other challenges.
