# Review Pack — Clean-Room Harness Rewrite

**Data:** 2026-04-03  
**Status:** pronto para revisão

---

## Escopo entregue

### Workstream 1 — Inventory e bootstrap

Arquivos centrais:

- `socc/core/harness/runtime.py`
- `socc/core/harness/models.py`
- `socc/core/harness/__init__.py`
- `socc/cli/startup.py`
- `socc/cli/main.py`
- `socc/cli/commands/__init__.py`

Entregas:

- merge live+snapshot para tools/commands/agents
- CLI de inventory e introspecção
- roteamento com prioridade para itens implementados
- bootstrap determinístico para CLI/TUI/chat interativo

### Workstream 2 — Contrato de subagentes

Arquivos centrais:

- `socc/agents/fork.py`

Entregas:

- policy explícita de tools
- lifecycle observável
- `tool_calls`, `reasoning_trace`, `error_kind`
- listagem pública de subagentes

### Workstream 3 — Session parity

Arquivos centrais:

- `socc/core/storage.py`
- `soc_copilot/modules/persistence.py`
- `socc/core/engine.py`
- `socc/cli/main.py`
- `socc/cli/chat_interactive.py`

Entregas:

- `session list/show/resume`
- resumo consolidado de sessão
- reidratação de transcript na TUI
- `/resume` e `/session` operacionais

### Workstream 4 — TUI / REPL parity

Arquivos centrais:

- `socc/cli/chat_interactive.py`
- `soc_copilot/modules/chat_service.py`
- `socc/core/engine.py`

Entregas:

- slash surface alinhada à harness
- help local + harness
- eventos de `phase`, `tool_call`, `tool_result`
- layout mais denso e operacional

### Workstream 5 — Runtime/task/bridge modeling

Arquivos centrais:

- `socc/core/task_state.py`
- `socc/core/session_bridge.py`
- `docs/boundary-clean-room-harness-runtime.md`
- `docs/task-lifecycle-clean-room-harness.md`
- `docs/session-bridge-clean-room-harness.md`

Entregas:

- separação entre session state e task state
- integração mínima de task state ao engine/subagentes
- contrato inicial de session bridge remoto
- estratégia inicial de transporte, auth e degradação

---

## Evidências de verificação

Comandos executados com sucesso:

- `python -m pytest -q`
- `python -m compileall socc tests`
- `python scripts/checks/check_runtime_bootstrap.py`
- `python scripts/checks/check_runtime_migration_map.py`
- `python scripts/checks/check_contracts_cli.py`
- `python scripts/checks/check_cli_interactive.py`

Cobertura focada adicionada:

- `tests/test_harness_inventory_cli.py`
- `tests/test_harness_entrypoints_cli.py`
- `tests/test_runtime_contract_compat.py`
- `tests/test_session_resume_cli.py`
- `tests/test_tui_runtime_events.py`
- `tests/test_task_state_runtime.py`
- `tests/test_session_bridge_contract.py`

---

## Riscos remanescentes

- `task_state` e `session_bridge` ainda são in-memory; não persistem entre processos
- bridge remoto está modelado, mas sem transporte real implementado
- task lifecycle ainda não possui árvore, retries ou scheduler
- a camada web ainda não consome o contrato de bridge remoto

---

## Lacunas fora do escopo desta entrega

- websocket/session bridge real
- sincronização de transcript remoto
- remote attach/resume funcional fim a fim
- persistência de task state
- observabilidade histórica por task

---

## Recomendação de revisão

Priorizar revisão nesta ordem:

1. `socc/core/harness/runtime.py`
2. `socc/core/engine.py`
3. `socc/cli/chat_interactive.py`
4. `socc/agents/fork.py`
5. docs de boundary/task/bridge
