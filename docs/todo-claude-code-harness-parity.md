# TODO — SOCC Claude-Code Harness Parity

> **Status:** superseded por `docs/todo-clean-room-harness-rewrite.md`.
> Este TODO não governa mais a execução principal; use-o apenas como histórico do plano anterior.
> Os status/checklists abaixo podem divergir do estado real atual e não devem ser usados para aceite.

**PRD pai:** `prd-claude-code-harness-parity.md`  
**Data:** 2026-04-01  
**Status geral:** Draft executavel  
**Objetivo:** transformar o harness do SOCC na superficie principal de runtime, introspeccao e TUI
**UI spec:** `ui-spec-claude-code-like-tui.md`

---

## Legenda

| Simbolo | Significado |
|---|---|
| ⬜ | TODO |
| 🔄 | WIP |
| ✅ | DONE |
| ❌ | BLOCKED |

---

## Fase 0 — Alinhamento e limpeza documental

### PAR-000: congelar o alvo de paridade
**Prioridade:** P0  
**Status:** ⬜ TODO

**Acceptance Criteria**

- [ ] Registrar que o alvo inclui harness, TUI local, superficie de sessao e um futuro modo remoto com `session bridge`.
- [ ] Declarar que o `claude-code` Python port e referencia de inventario e taxonomia, nao de TUI executavel pronta.
- [ ] Marcar docs antigas de harness como superseded ou legacy para evitar leitura equivocada.

**Arquivos**

- `docs/prd-harness-evolution.md`
- `docs/prd-harness-wiring.md`
- `docs/todo-claude-code-integration.md`
- `docs/todo-harness-wiring.md`

---

## Fase 1 — Inventory parity do harness

### PAR-101: carregar snapshots de tools e commands no runtime
**Prioridade:** P0  
**Status:** ⬜ TODO

**Acceptance Criteria**

- [ ] `SOCRuntime.bootstrap()` carregar `socc_tools_snapshot.json`, `socc_commands_snapshot.json` e `socc_agents_snapshot.json`.
- [ ] Runtime expor listagens separadas para `inventory` e `live registry`.
- [ ] Snapshot entries exibirem status claro: `implemented`, `planned`, `unavailable` ou equivalente.

**Arquivos**

- `socc/core/harness/runtime.py`
- `socc/core/harness/reference_data/socc_tools_snapshot.json`
- `socc/core/harness/reference_data/socc_commands_snapshot.json`
- `socc/core/harness/reference_data/socc_agents_snapshot.json`

### PAR-102: criar superficie CLI de inventario
**Prioridade:** P0  
**Status:** ⬜ TODO

**Acceptance Criteria**

- [ ] `socc commands --limit --query`
- [ ] `socc tools --limit --query`
- [ ] `socc route "<prompt>" --limit`
- [ ] `socc show-command <name>`
- [ ] `socc show-tool <name>`
- [ ] saida consistente e testada por subprocess

**Arquivos**

- `socc/cli/main.py`
- `tests/`

### PAR-103: alinhar roteamento com inventario e runtime vivo
**Prioridade:** P1  
**Status:** ⬜ TODO

**Acceptance Criteria**

- [ ] `route_prompt()` combinar matches de tool, command e agent com score previsivel.
- [ ] Matches priorizarem itens ativos quando houver empate com snapshot nao implementado.
- [ ] Testes cobrirem prompts curtos, compostos e conflitantes.

**Arquivos**

- `socc/core/harness/runtime.py`
- `tests/test_harness_wiring.py`

---

## Fase 2 — Execution parity do harness

### PAR-201: transformar `fork_subagent` em executor contratual
**Prioridade:** P0  
**Status:** ⬜ TODO

**Acceptance Criteria**

- [ ] aplicar `tools_whitelist` e `tools_blacklist` em toda a execucao
- [ ] registrar `tool_calls` em `AgentResult`
- [ ] respeitar `max_steps` e `timeout_seconds`
- [ ] manter fallback deterministico quando LLM indisponivel
- [ ] diferenciar erro de ferramenta, erro de LLM e timeout

**Arquivos**

- `socc/agents/fork.py`
- `socc/core/harness/models.py`
- `tests/test_harness_wiring.py`

### PAR-202: integrar harness ao fluxo principal de chat
**Prioridade:** P0  
**Status:** ⬜ TODO

**Acceptance Criteria**

- [ ] slash-commands no chat/TUI delegam ao `COMMAND_REGISTRY`
- [ ] introspeccao de tools/agents usa o runtime do harness
- [ ] eventos de ferramenta e fase ficam disponiveis para exibicao
- [ ] engine e chat nao bypassam o harness quando a acao for de command/tool routing

**Arquivos**

- `socc/cli/chat_interactive.py`
- `socc/core/engine.py`
- `socc/core/chat.py`
- `soc_copilot/modules/chat_service.py`

### PAR-203: expor estado de subagentes e runtime
**Prioridade:** P1  
**Status:** ⬜ TODO

**Acceptance Criteria**

- [ ] comando ou API para listar subagentes ativos/recentes
- [ ] payload incluir status, elapsed time e resumo
- [ ] smoke test cobrindo ciclo `pending -> running -> completed|failed|timeout`

**Arquivos**

- `socc/agents/fork.py`
- `socc/cli/main.py`
- `tests/`

---

## Fase 3 — TUI and session parity

### PAR-301: consolidar a TUI como REPL principal do runtime
**Prioridade:** P0  
**Status:** ⬜ TODO

**Acceptance Criteria**

- [ ] startup do TUI < 1s sem plugins remotos ativos
- [ ] historico, status bar, input e busy state preservados
- [ ] slash autocomplete combinar comandos built-in e comandos do harness
- [ ] `/help`, `/tools`, `/agents`, `/case`, `/hunt` funcionarem dentro da TUI
- [ ] layout alinhado ao spec: top chrome, transcript pane, sidebar compacta, composer e footer operacional
- [ ] linguagem visual mais proxima de Claude Code do que da TUI atual

**Arquivos**

- `socc/cli/chat_interactive.py`
- `socc/cli/startup.py`

### PAR-302: introduzir comandos de sessao no estilo da superficie de referencia
**Prioridade:** P1  
**Status:** ⬜ TODO

**Acceptance Criteria**

- [ ] definir contrato para `session list`, `session show`, `session resume` ou equivalente
- [ ] `/session` exibir informacoes uteis da sessao atual
- [ ] `--resume` ou `--continue` terem comportamento consistente no CLI
- [ ] testes cobrirem criacao, listagem e retomada de sessao

**Arquivos**

- `socc/cli/main.py`
- `socc/cli/chat_interactive.py`
- `socc/core/storage.py`
- `tests/`

### PAR-303: mostrar eventos de fase e tool execution na TUI
**Prioridade:** P1  
**Status:** ⬜ TODO

**Acceptance Criteria**

- [ ] streaming mostrar eventos `phase` e `tool_call` quando existirem
- [ ] UI diferenciar mensagem final, progresso e resultados de tool
- [ ] manter fallback limpo quando backend nao suportar streaming rico

**Arquivos**

- `socc/cli/chat_interactive.py`
- `socc/core/engine.py`
- `soc_copilot/modules/chat_service.py`

---

## Fase 4 — Remote bridge parity

### PAR-401: definir contrato de sessao remota e remote bridge
**Prioridade:** P1  
**Status:** ⬜ TODO

**Acceptance Criteria**

- [ ] descrever estados da sessao remota: criada, conectando, ativa, pausada, encerrada, erro
- [ ] definir API local para `create_session`, `attach_session`, `resume_session`, `close_session`
- [ ] definir interface de `repl bridge` entre TUI e backend remoto
- [ ] documentar transporte inicial e estrategia de autenticacao

**Arquivos**

- `docs/`
- `socc/cli/`
- `socc/core/`

### PAR-402: implementar base de `RemoteSessionManager`
**Prioridade:** P1  
**Status:** ⬜ TODO

**Acceptance Criteria**

- [ ] camada isolada para gerenciar sessoes remotas sem quebrar sessoes locais
- [ ] persistencia minima de metadados de sessao remota
- [ ] adaptadores para futura conexao websocket ou transporte equivalente
- [ ] smoke tests cobrindo criar, anexar e encerrar sessao remota simulada

**Arquivos**

- `socc/core/storage.py`
- `socc/core/`
- `tests/`

### PAR-403: integrar TUI ao bridge remoto
**Prioridade:** P2  
**Status:** ⬜ TODO

**Acceptance Criteria**

- [ ] TUI permitir alternar entre sessao local e remota
- [ ] status bar indicar modo remoto e identificador da sessao conectada
- [ ] comandos de sessao funcionarem em ambos os modos ou falharem de forma explicita
- [ ] degradacao limpa quando transporte remoto nao estiver disponivel

**Arquivos**

- `socc/cli/chat_interactive.py`
- `socc/cli/main.py`
- `tests/`

---

## Fase 5 — Packaging, quality and rollout

### PAR-501: corrigir o modo de execucao dos testes
**Prioridade:** P0  
**Status:** ⬜ TODO

**Acceptance Criteria**

- [ ] `pytest -q` funcionar no checkout limpo
- [ ] `python -m pytest -q` continuar funcionando
- [ ] documentar a estrategia adotada

**Arquivos**

- `pyproject.toml`
- `tests/`

### PAR-502: criar suite de verificacao de paridade
**Prioridade:** P0  
**Status:** ⬜ TODO

**Acceptance Criteria**

- [ ] subprocess tests para `socc commands`, `socc tools`, `socc route`
- [ ] testes de `fork_subagent` cobrindo contrato real
- [ ] smoke tests de TUI/CLI cobrindo slash-commands principais
- [ ] testes de startup com plugins configurados e nao configurados

**Arquivos**

- `tests/test_harness_wiring.py`
- `tests/`

### PAR-503: rollout controlado e documentado
**Prioridade:** P1  
**Status:** ⬜ TODO

**Acceptance Criteria**

- [ ] definir flags ou guard rails para ativar a nova superficie sem quebrar o fluxo atual
- [ ] atualizar README e docs operacionais quando a implementacao estiver pronta
- [ ] registrar riscos remanescentes e gaps conhecidos

**Arquivos**

- `README.md`
- `docs/`

---

## Sequencia recomendada

1. `PAR-000`
2. `PAR-101`
3. `PAR-102`
4. `PAR-103`
5. `PAR-201`
6. `PAR-202`
7. `PAR-501`
8. `PAR-502`
9. `PAR-301`
10. `PAR-302`
11. `PAR-303`
12. `PAR-203`
13. `PAR-401`
14. `PAR-402`
15. `PAR-403`
16. `PAR-503`

---

## Verificacao minima da fase MVP

```bash
python -m pytest -q
pytest -q

socc commands --limit 10
socc tools --limit 10
socc route "review mcp tool and incident agent" --limit 10
socc show-command agents
socc show-tool bash
```
