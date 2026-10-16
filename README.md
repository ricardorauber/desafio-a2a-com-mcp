# A Ponte: um agente A2A com MCP por dentro

Entrega do desafio da Hill Valley Tech: um **servidor MCP** (Streamable HTTP, revisão `2026-07-28`) que expõe as salas de reunião, e um **agente** que é host MCP por dentro e servidor A2A v1.0 (binding JSON-RPC) por fora. A peça central é a ponte entre o `input_required` do MRTR e o `TASK_STATE_INPUT_REQUIRED` da Task.

```
cliente A2A ──SendMessage/GetTask──▶ agente (7300, /a2a) ──tools/list · resources/read · tools/call──▶ servidor MCP (7301, /mcp)
                                       host MCP + Tasks                                                  salas, política, MRTR
```

Stack: Python 3.10+, SDK oficial `mcp==2.3.0` (nos dois processos), `a2a-sdk[http-server]==1.2.2`, `uvicorn==0.54.0`. Versões travadas nos `pyproject.toml` e em `requirements.lock`. Sem LLM: o agente interpreta um formato fixo e decide por regra.

```
servidor-mcp/servidor_mcp/   dominio.py (regras), servidor.py (tools, resource, MRTR), seguranca.py, log.py
agente/agente_a2a/           host_mcp.py (cliente MCP), executor.py (máquina de estados), ponte.py, app.py, cartao.py
specs/  adrs/                especificações (SDD) e decisões registradas
```

## Como rodar

Pré-requisito: Python 3.10 ou superior. Se o `python3` da máquina for mais antigo, use o executável de uma versão nova (por exemplo `python3.12`) no lugar dele.

**Instalação**, a partir de um clone limpo:

```bash
git clone https://github.com/ricardorauber/desafio-a2a-com-mcp.git
cd desafio-a2a-com-mcp
python3 -m venv .venv
source .venv/bin/activate
pip install -c requirements.lock -e "./servidor-mcp[test]" -e "./agente[test]"
```

**Terminal 1, servidor MCP.** A chave de integridade do `requestState` vem só da variável `REQUEST_STATE_SECRET` (mínimo de 32 bytes). Gere uma chave sua e exporte; nunca a coloque no repositório:

```bash
source .venv/bin/activate
export REQUEST_STATE_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
python -m servidor_mcp
```

Sem a variável, com menos de 32 bytes ou, se for hexadecimal, com menos de 64 caracteres (32 bytes de aleatoriedade), o servidor se recusa a subir e explica como gerar a chave. O stderr deste terminal é o log de requests: uma linha por request, com `method`, `id`, `name`, `traceparent` e status HTTP. Para o teste de restart, pare com `Ctrl+C` e rode `python -m servidor_mcp` de novo **no mesmo terminal**: a variável exportada continua valendo, e um `requestState` emitido antes do restart continua válido.

**Terminal 2, agente:**

```bash
source .venv/bin/activate
python -m agente_a2a
```

**Terminal 3, validador** (com os dois processos recém-iniciados):

```bash
python3 validador/validar.py --agente http://localhost:7300 --mcp http://localhost:7301
```

Portas e URLs têm padrão e podem ser trocadas por variável de ambiente: `MCP_PORT` (7301), `AGENT_PORT` (7300), `MCP_URL` (`http://127.0.0.1:7301/mcp`) e `AGENT_PUBLIC_URL` (`http://127.0.0.1:7300`, usada no Agent Card). A lista está em `.env.example`.

**Testes unitários** (104, incluindo integração com o servidor MCP real em segundo plano):

```bash
pytest
```

### Fluxo manual

As reservas criadas pelo validador mudam as alternativas oferecidas depois. Antes de percorrer o fluxo manual, reinicie os dois processos.

```bash
curl -s http://localhost:7300/.well-known/agent-card.json

# pedido de sala ocupada: a Task para em TASK_STATE_INPUT_REQUIRED com "alternativas: sala-fusca, sala-mirante"
python3 -c "import json; print(json.dumps(json.load(open('exemplos/wire/08-a2a-send-message.json'))['request']['body']))" > /tmp/pedido.json
curl -s -X POST http://localhost:7300/a2a -H 'Content-Type: application/json' \
  -H 'traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01' -d @/tmp/pedido.json

# continuação com o id da Task devolvida acima (troque <TASK_ID>)
curl -s -X POST http://localhost:7300/a2a -H 'Content-Type: application/json' -d '{"jsonrpc":"2.0","id":2,"method":"SendMessage","params":{"message":{"messageId":"msg-2","role":"ROLE_USER","parts":[{"text":"escolha=sala-mirante"}],"taskId":"<TASK_ID>"}}}'
curl -s -X POST http://localhost:7300/a2a -H 'Content-Type: application/json' -d '{"jsonrpc":"2.0","id":3,"method":"GetTask","params":{"id":"<TASK_ID>"}}'
```

Para recusar, a continuação leva `escolha=recusar` e a Task termina em `TASK_STATE_CANCELED`. Um pedido com `sala=sala-inexistente` termina em `TASK_STATE_FAILED`, com `Sala inexistente: sala-inexistente` na mensagem de status e no `history`.

## Onde a ponte acontece

O pedido chega ao agente em `ExecutorDeReservas._iniciar` ([agente/agente_a2a/executor.py](agente/agente_a2a/executor.py)), que chama `HostMCP.reservar` ([agente/agente_a2a/host_mcp.py](agente/agente_a2a/host_mcp.py)). O host faz `tools/list`, lê `politica://uso` e emite o `tools/call` com `allow_input_required=True`, para enxergar o `input_required` cru em vez de deixar um callback do SDK responder sozinho. A função `classificar` transforma esse resultado em `Pausada(chave, alternativas, request_state)`. **O `input_required` do MCP vira `TASK_STATE_INPUT_REQUIRED` em `ExecutorDeReservas._encerrar`, no ramo `isinstance(resultado, Pausada)`.** Ali o `requestState` é guardado em `Pausas` ([agente/agente_a2a/ponte.py](agente/agente_a2a/ponte.py)), ligado ao `task_id` junto com a chave da elicitation, as alternativas, os argumentos originais e o trace-id da Task, e a Task é interrompida com a mensagem `alternativas: ...`. **O `requestState` volta para o servidor em `ExecutorDeReservas._continuar`**: a resposta `escolha=<id>` ou `escolha=recusar` vira um `ElicitResult` (`accept` ou `decline`), e `HostMCP.retomar` → `_chamar` repete o mesmo `tools/call` com um id de JSON-RPC novo, `inputResponses` na mesma chave e o `requestState` ecoado byte a byte. Do lado do servidor, `reservar_sala` ([servidor-mcp/servidor_mcp/servidor.py](servidor-mcp/servidor_mcp/servidor.py)) termina a primeira rodada em `perguntar` e conclui o retry em `retomar`, reconstruindo o pedido a partir do estado verificado.

## Decisões técnicas

- **Proteção do `requestState`.** A tool devolve o estado em texto claro, com o pedido original (sala, início, fim, responsável), as alternativas oferecidas e a chave da elicitation. O `RequestStateBoundary` do SDK sela esse texto na saída e verifica cada eco na entrada, com AES-256-GCM e chave derivada por HKDF de `REQUEST_STATE_SECRET` ([seguranca.py](servidor-mcp/servidor_mcp/seguranca.py)). O envelope selado carrega a expiração, a audiência (`central-de-salas`) e um vínculo com o método, o nome da tool e o digest dos argumentos. Um caractere trocado, outra chave, um token expirado ou argumentos diferentes no retry são recusados com `-32602` (`Invalid or expired requestState`) antes de a tool rodar. Mesmo assim, a tool só usa os valores selados. O servidor não guarda nada entre as rodadas, por isso o retry funciona depois de um restart com a mesma chave. Cada pausa sela também um nonce: repetir um retry aceito devolve a mesma reserva em vez de criar outra (ADR 0005, spec 0009). Assinar era obrigatório e cifrar era opcional; aqui o estado é cifrado e autenticado (ADR 0003).
- **Validade.** 10 minutos (TTL de 600 s), dentro da faixa de 5 a 30 minutos.
- **Elicitation e capability.** A pergunta é um `elicitation/create` em `mode: form`, na chave `escolha_de_sala`, com `requestedSchema` plano e `enum` na ordem da regra. Sem `elicitation.form` declarado no `_meta` do próprio request, a resposta é `-32021` com `data.requiredCapabilities` e HTTP 400. `{"elicitation": {}}` puro também é recusado, porque o que se exige é form mode.
- **Estado das Tasks.** Fica na memória do agente: as Tasks no `InMemoryTaskStore` do `a2a-sdk`, e o estado pausado (o `requestState` opaco e os dados para retomar) em `Pausas`, por `task_id`. O estado pausado é descartado quando a Task chega a um estado terminal e nunca aparece no card, nos artifacts, nas mensagens nem nos logs. Cada continuação é reivindicada de forma atômica antes do executor rodar. Uma segunda continuação simultânea da mesma Task, ou uma continuação de Task que não está em `TASK_STATE_INPUT_REQUIRED`, é recusada com erro. Um `CancelTask` que chega durante uma continuação espera ela terminar, para que o retry ao MCP e o desfecho da Task fiquem coerentes. As reservas também são só em memória, no servidor MCP.
- **Trace context.** O agente lê o header `traceparent` do `SendMessage` que abre a Task e usa o mesmo trace-id, com um span-id novo, no `_meta.traceparent` de todos os requests MCP daquela Task, inclusive no retry. Sem header válido, gera um trace-id novo para a Task.
- **Sessão.** Nenhuma. Cada request MCP leva `protocolVersion`, `clientInfo` e `clientCapabilities` no `_meta`, e os headers `MCP-Protocol-Version`, `Mcp-Method` e `Mcp-Name` espelhados pelo transporte do SDK.

### Limitações do SDK encontradas, com a evidência

1. **Capability de elicitation (`mcp` 2.3.0).** `ClientSession._build_capabilities` (`mcp/client/session.py`) só anuncia elicitation quando existe um `elicitation_callback`, e então anuncia `{"form": {}, "url": {}}`. Não há parâmetro público para escolher os modos. O agente precisa de exatamente `{"elicitation": {"form": {}}}` e de nenhum callback, para que a pergunta volte ao cliente A2A. A saída foi estreitar a capability em um único ponto, `capacidades_so_formulario` (ADR 0004).
2. **Erro de conexão derruba o cliente MCP (`mcp` 2.3.0).** Uma falha de conexão num POST sobe dentro do task group do transporte (`mcp/client/streamable_http.py`, `_run_request_post`) e encerra o `Client` inteiro. Por isso o host abre um `Client` por operação: com a versão fixada não há handshake, e uma queda do servidor MCP vira `TASK_STATE_FAILED` (`Servidor MCP indisponivel`) em vez de derrubar o agente. Também por isso cada operação começa com o seu `tools/list`: sem o cache de schemas preenchido, `validate_tool_result` refaria a listagem sozinho, sem o `traceparent`. Os ids de JSON-RPC partem de um bloco por operação (101, 102, 103 / 201, 202), únicos no log (ADR 0007).
3. **`a2a-sdk` 1.2.2** (ADR 0005):
   - Sem o header `A2A-Version`, o request é tratado como 0.3 e recusado com `-32009`. O validador não manda esse header, então o padrão passa a ser `1.0`.
   - Uma continuação sem `contextId` ganharia um `contextId` novo. O agente herda o da Task.
   - A mensagem de status só entra no `history` quando chega a próxima mensagem do usuário. O agente normaliza o `history` no store e na resposta do `SendMessage`, como no `exemplos/wire/08`.
   - Para recusar uma Task terminal, o SDK cria uma task ativa e deixa o despachante de eventos dela pendente. O agente recusa antes, com o mesmo `-32004`.
   - `CancelTask` sempre interrompe o produtor em execução, e marca a Task como FAILED se o executor recusar. Por isso o `cancel` do agente nunca recusa: ele espera a continuação em andamento terminar.
4. **Capabilities do servidor (`mcp` 2.3.0).** O `MCPServer` sempre registra `prompts/list`, que devolve lista vazia, e por isso anuncia `prompts`. `subscribe` e `listChanged` são desligados com `subscriptions=False`, já que subscriptions estão fora de escopo.
5. **Nome do pacote.** O pacote do agente se chama `agente_a2a` porque, rodando da raiz, a pasta `agente/` do starter seria importada como namespace package e esconderia um pacote `agente` (ADR 0006).

## Saída do validador

Última execução, com os dois processos recém-iniciados a partir de um clone limpo:

```
trace-id desta execucao: cf325ea8c1240adad04c0b3b658cfdab
procure esse valor no stderr do servidor MCP para conferir a propagacao do traceparent.

PASS 01 tools/list traz as tres tools
PASS 02 toda tool tem inputSchema de objeto
PASS 03 listar_salas devolve structuredContent e o mesmo JSON em texto
PASS 04 _meta sem protocolVersion devolve -32602 e HTTP 400
PASS 05 _meta sem clientCapabilities devolve -32602 e HTTP 400
PASS 06 tool inexistente e recusada, por -32602 ou por isError
PASS 07 resources/read de politica://uso devolve a politica
PASS 08 resources/read de URI inexistente devolve -32602
PASS 09 sala inexistente devolve isError com a mensagem exata
PASS 10 fora da janela devolve isError com a mensagem exata
PASS 11 duracao acima de 2h devolve isError com a mensagem exata
PASS 12 intervalo invertido devolve isError com a mensagem exata
PASS 13 conflito devolve input_required com inputRequests e requestState
PASS 14 a elicitation e form mode e oferece as alternativas na ordem certa
PASS 15 conflito sem a capability elicitation devolve -32021 e HTTP 400
PASS 16 retry com inputResponses e requestState conclui a reserva
PASS 17 requestState adulterado e rejeitado com -32602
PASS 18 argumentos adulterados no retry nao tomam efeito
PASS 19 recusa conclui sem reservar e sem isError
PASS 20 conflito sem alternativa possivel devolve isError com a mensagem exata

PASS 21 agent card responde 200 no well-known com JSON
PASS 22 o card declara a interface JSON-RPC com url e versao 1.0
PASS 23 o card declara a skill reservar-sala
PASS 24 SendMessage com sala livre conclui a Task
PASS 25 o artifact chama reserva e traz a versao da politica
PASS 26 GetTask devolve id, contextId e estado corrente
PASS 27 SendMessage com sala ocupada pausa a Task
PASS 28 a Task pausada lista as alternativas na ordem certa
PASS 29 escolha fora do enum mantem a Task pausada
PASS 30 a continuacao conclui a Task na sala escolhida
PASS 31 SendMessage em Task terminal e recusado
PASS 32 a recusa termina a Task em CANCELED
PASS 33 duas Tasks pausadas ao mesmo tempo concluem cada uma com a sua reserva
PASS 34 nenhuma resposta A2A carrega o requestState
PASS 35 sala inexistente termina a Task em FAILED com a mensagem da tool
PASS 36 o agente e deterministico: o mesmo pedido produz a mesma pausa

resumo: 36 passaram, 0 falharam, de 36 verificacoes

$ echo $?
0
```
