# 0002 - Room domain for the MCP server

## Goal
Give the MCP server one small, pure domain module that loads the starter data and applies the usage policy, the conflict check and the alternatives rule, so the tools only translate protocol.

## Scope
- In: `servidor-mcp/servidor_mcp/dominio.py` — loading `dados/salas.json`, `dados/reservas.json` and `dados/politica-de-uso.md`; validation; conflict detection; alternatives; in-memory reservation store with id generation.
- Out: MCP tools, resources, transport and MRTR (0003, 0004). No ORM, no database, no service layer.

## Requirements
- R1: The module SHALL load rooms, initial reservations and the policy text from `dados/` resolved relative to the repository root (not to the current working directory), and SHALL extract the policy version from its first line `versao: <valor>`.
- R2: The module SHALL validate a request `(sala, inicio, fim)` in this order and raise a domain error carrying the exact message:
  1. room not in `salas.json` → `Sala inexistente: <id informado>`;
  2. `inicio` or `fim` not parseable as ISO 8601 with offset → `Intervalo invalido: fim deve ser posterior a inicio`;
  3. `fim <= inicio` → `Intervalo invalido: fim deve ser posterior a inicio`;
  4. `inicio` or `fim`, converted to São Paulo time (`-03:00`), outside 08:00–20:00 (start before 08:00, end after 20:00, or start and end on different local days) → `Fora da janela de uso: a politica permite reservas entre 08:00 e 20:00`;
  5. duration over 2 hours → `Duracao acima do limite: a politica permite no maximo 2 horas`.
- R3: Two intervals SHALL conflict when `inicio_a < fim_b and inicio_b < fim_a` (touching ends do not conflict), compared as absolute instants.
- R4: The module SHALL return, for a room and an interval, the list of conflicting reservations with `id`, `inicio`, `fim` and `responsavel`.
- R5: The alternatives for a conflicting request SHALL be the rooms, other than the requested one, free in that interval with capacity greater than or equal to the requested room's, at most three, sorted by capacity ascending and, on ties, by `id` alphabetically.
- R6: Creating a reservation SHALL assign the next id `res-NNNN` (4 digits, continuing after the highest id loaded from `reservas.json`), store it in memory and make it visible to every later query of the same process. No rule SHALL depend on today's date.
- R7: The store SHALL NOT persist anything to disk.

## Acceptance criteria
- [ ] AC1: The loaded policy version is `2026-11-01` and the five rooms load with their capacities. (R1)
- [ ] AC2: Each of the four validation messages is produced, with the exact text, for `sala-delorean`; 07:00–08:00; 09:00–12:00; 10:00–09:00. (R2)
- [ ] AC3: `sala-garagem` 14:00–15:00 on 2026-11-03 conflicts with `res-0001`; 15:00–16:00 does not. (R3, R4)
- [ ] AC4: Alternatives for `sala-garagem` 14:00–15:00 are `["sala-fusca", "sala-mirante"]`; for `sala-aquario` with every room taken except two larger ones they are sorted by capacity then id; never more than three. (R5)
- [ ] AC5: A created reservation gets `res-0003`, the next one `res-0004`, and both show up as conflicts afterwards. (R6)
- [ ] AC6: A reservation in the past (e.g. 2020-01-01) is accepted. (R6)

## Unit tests
- T1: data loading and policy version extraction (AC1).
- T2: one test per validation message, plus validation order (unknown room wins over a bad interval) (AC2).
- T3: overlap edge cases — touching, contained, identical, different offsets for the same instant (AC3).
- T4: alternatives ordering, capacity filter, max three, excludes requested room, empty when nothing fits (AC4).
- T5: id sequence and in-memory visibility (AC5).
- T6: past date accepted (AC6).
