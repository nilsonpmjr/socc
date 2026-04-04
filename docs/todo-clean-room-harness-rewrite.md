# TODO — Clean-Room Harness Rewrite

**PRD pai:** `prd-clean-room-harness-rewrite.md`  
**Fonte primária:** `/home/nilsonpmjr/Documentos/claude-code-analysis`  
**Alvo da reimplementação:** `/home/nilsonpmjr/.gemini/antigravity/scratch/socc`  
**Objetivo:** reimplementar a harness do SOCC em Python tomando a fonte acima como source of truth funcional e arquitetural.

---

## Legenda

| Símbolo | Significado |
|---|---|
| ⬜ | TODO |
| 🔄 | WIP |
| ✅ | DONE |
| ❌ | BLOCKED |

---

## Fase 0 — Direção da Reescrita

### CR-000: fixar a interpretação correta da fonte
**Prioridade:** P0  
**Status:** ✅ DONE

**Acceptance Criteria**

- [x] O PRD declara explicitamente `/home/nilsonpmjr/Documentos/claude-code-analysis` como fonte primária.
- [x] O SOCC legado é tratado como alvo de migração.
- [x] O risco de inverter a direção da reescrita está documentado.

### CR-001: alinhar docs com o estado real
**Prioridade:** P1  
**Status:** ✅ DONE

**Acceptance Criteria**

- [x] Criar PRD específico para a clean-room rewrite
- [x] Criar TODO específico para a clean-room rewrite
- [x] Cruzar PRD/TODO novo com docs antigas e marcar superseded onde necessário
- [x] Remover ambiguidades entre “parity” e “clean-room rewrite”

---

## Fase 1 — Inventário e Runtime Core

### CR-101: carregar snapshots no runtime
**Prioridade:** P0  
**Status:** ✅ DONE

**Acceptance Criteria**

- [x] `SOCRuntime` carrega snapshots de tools
- [x] `SOCRuntime` carrega snapshots de commands
- [x] `SOCRuntime` carrega snapshots de agents
- [x] Bootstrap é idempotente

### CR-102: unificar snapshot inventory e live registry
**Prioridade:** P0  
**Status:** ✅ DONE

**Acceptance Criteria**

- [x] Commands têm estado `implemented` ou `planned`
- [x] Tools têm estado `implemented` ou `planned`
- [x] Agents têm estado `implemented` ou `planned`
- [x] Inventory records distinguem `source`
- [x] O runtime prioriza itens vivos em relação aos apenas planejados

### CR-103: expor a superfície de inventário na CLI
**Prioridade:** P0  
**Status:** ✅ DONE

**Acceptance Criteria**

- [x] `socc commands --limit --query`
- [x] `socc tools --limit --query`
- [x] `socc agents --limit --query`
- [x] `socc route "<prompt>" --limit`
- [x] `socc show-command <name>`
- [x] `socc show-tool <name>`

### CR-104: enriquecer detalhes de inventário
**Prioridade:** P1  
**Status:** ✅ DONE

**Acceptance Criteria**

- [x] `show-command` exibe aliases, argumentos, status, source e hidden state
- [x] `show-tool` exibe tags, categoria, risco, source e auth/timeout quando aplicável
- [x] `agents` expõe specialty, source e policy de tools quando solicitado
- [x] queries têm ordenação previsível para empates

### CR-105: alinhar roteamento com a superfície da fonte
**Prioridade:** P1  
**Status:** ✅ DONE

**Acceptance Criteria**

- [x] `route_prompt()` considera commands, tools e agents
- [x] itens vivos ganham preferência em empates
- [x] score leva em conta aliases e argumentos de forma mais robusta
- [x] testes cobrem conflitos entre live item e snapshot-only item
- [x] `route` fica pronto para futura integração com session/task context

---

## Fase 2 — Bootstrap e Entry Points

### CR-201: tornar o bootstrap determinístico
**Prioridade:** P0  
**Status:** ✅ DONE

**Acceptance Criteria**

- [x] ordem de bootstrap definida
- [x] tools vivos importados antes da consolidação do runtime
- [x] commands built-in registrados antes do merge final
- [x] agents built-in registrados antes do merge final
- [x] plugins registrados antes do bootstrap final do runtime

### CR-202: alinhar `chat --interactive` e `tui`
**Prioridade:** P0  
**Status:** ✅ DONE

**Acceptance Criteria**

- [x] `chat --interactive` usa bootstrap bloqueante da harness
- [x] `socc tui` usa bootstrap bloqueante da harness
- [x] TUI deixa de iniciar com registries vazios

### CR-203: validar entrypoints do runtime
**Prioridade:** P1  
**Status:** ✅ DONE

**Acceptance Criteria**

- [x] smoke test dedicado para `socc tui`
- [x] smoke test dedicado para `socc chat --interactive`
- [x] validação de comportamento quando plugins remotos estiverem ausentes
- [x] medição de startup local para a meta de < 1s

---

## Fase 3 — Contrato de Subagentes

### CR-301: reimplementar `fork_subagent` com contrato forte
**Prioridade:** P0  
**Status:** ✅ DONE

**Acceptance Criteria**

- [x] policy de tools resolvida explicitamente
- [x] whitelist aplicada
- [x] blacklist aplicada
- [x] `tool_calls` registrados
- [x] `reasoning_trace` registrado
- [x] `error_kind` registrado
- [x] `block=False` mantém lifecycle observável

### CR-302: endurecer semântica de falha
**Prioridade:** P1  
**Status:** ✅ DONE

**Acceptance Criteria**

- [x] diferenciar `tool_error`
- [x] diferenciar `llm_error`
- [x] diferenciar `timeout`
- [x] diferenciar falha de runtime interno
- [x] expor elapsed time, summary e policy resolvida numa listagem pública

### CR-303: expor estado de subagentes na CLI/runtime
**Prioridade:** P1  
**Status:** ✅ DONE

**Acceptance Criteria**

- [x] comando para listar subagentes ativos/recentes
- [x] payload inclui status, elapsed time e resumo
- [x] payload inclui `error_kind` quando aplicável
- [x] smoke test cobre `pending -> running -> completed|failed|timeout`

---

## Fase 4 — Empacotamento e Regressão

### CR-401: remover dependência de `PYTHONPATH` manual
**Prioridade:** P0  
**Status:** ✅ DONE

**Acceptance Criteria**

- [x] `pytest -q`
- [x] `python -m pytest -q`
- [x] `python -m socc.cli.main ...`
- [x] cobertura nova para CLI de inventário

### CR-402: manter a suíte de harness saudável
**Prioridade:** P0  
**Status:** ✅ DONE

**Acceptance Criteria**

- [x] `tests/test_harness_wiring.py`
- [x] `tests/test_harness_inventory_cli.py`
- [x] compileall em `socc` e `tests`

### CR-403: validar checks amplos do repositório
**Prioridade:** P1  
**Status:** ✅ DONE

**Acceptance Criteria**

- [x] rodar `scripts/checks/check_runtime_bootstrap.py`
- [x] rodar `scripts/checks/check_runtime_migration_map.py`
- [x] rodar `scripts/checks/check_contracts_cli.py`
- [x] rodar `scripts/checks/check_cli_interactive.py`
- [x] registrar diferenças residuais entre falhas já conhecidas e regressões novas

---

## Fase 5 — Session Parity

### CR-501: expor leitura de sessões persistidas
**Prioridade:** P0  
**Status:** ✅ DONE

**Acceptance Criteria**

- [x] `socc session list`
- [x] `socc session show <id>`
- [x] integração com `socc.core.storage`

### CR-502: adicionar retomada de sessão
**Prioridade:** P1  
**Status:** ✅ DONE

**Acceptance Criteria**

- [x] `socc session resume <id>` ou equivalente
- [x] `chat --session-id` alinhado à semântica de resume
- [x] `/resume` ou fluxo equivalente na TUI
- [x] testes cobrindo criação, listagem e retomada

### CR-503: consolidar session model
**Prioridade:** P1  
**Status:** ✅ DONE

**Acceptance Criteria**

- [x] payload de sessão atual expõe dados úteis para TUI
- [x] resumo da sessão atual não depende de lógica espalhada
- [x] session state acomoda expansão para remote bridge

---

## Fase 6 — TUI / REPL Parity

### CR-601: alinhar slash surface da TUI com a harness
**Prioridade:** P1  
**Status:** ✅ DONE

**Acceptance Criteria**

- [x] autocomplete reflete toda a superfície do harness
- [x] comandos locais e comandos do registry convivem sem ambiguidade
- [x] `/help` diferencia ajuda local e ajuda de harness quando necessário

### CR-602: exibir runtime events no transcript
**Prioridade:** P1  
**Status:** ✅ DONE

**Acceptance Criteria**

- [x] tool execution aparece como evento visual distinto
- [x] phase/progress aparece como evento visual distinto
- [x] fallback limpo quando backend não suportar eventos ricos

### CR-603: aproximar layout da fonte
**Prioridade:** P2  
**Status:** ✅ DONE

**Acceptance Criteria**

- [x] session pane mais informativa
- [x] footer operacional
- [x] transcript/composer/sidebar com densidade mais próxima da fonte
- [x] sem dependência nova pesada sem justificativa

---

## Fase 7 — Tasks e Runtime State

### CR-701: modelar task lifecycle inspirado na fonte
**Prioridade:** P2  
**Status:** ✅ DONE

**Acceptance Criteria**

- [x] identificar o mínimo de `task state` necessário no SOCC
- [x] separar task state de session state
- [x] preparar integração com subagentes e runtime events

### CR-702: definir limites entre harness, engine e chat service
**Prioridade:** P2  
**Status:** ✅ DONE

**Acceptance Criteria**

- [x] commands/tools routing não bypassa a harness
- [x] engine/chat usam a surface correta para introspecção
- [x] boundary doc explicita responsabilidades entre runtime, engine, TUI e web

---

## Fase 8 — Remote / Session Bridge

### CR-801: modelar `session bridge`
**Prioridade:** P2  
**Status:** ✅ DONE

**Acceptance Criteria**

- [x] estados de sessão remota definidos
- [x] contrato local para create/attach/resume/close
- [x] interface inicial de bridge documentada

### CR-802: definir estratégia de transporte e degradação
**Prioridade:** P2  
**Status:** ✅ DONE

**Acceptance Criteria**

- [x] transporte inicial escolhido
- [x] autenticação e autorização documentadas
- [x] degradação graciosa quando backend remoto estiver indisponível
- [x] testes de comportamento degradado planejados

---

## Fase 9 — Encerramento e Higiene

### CR-901: alinhar PRD/TODO com o estado real ao fim de cada fase
**Prioridade:** P1  
**Status:** ✅ DONE

**Acceptance Criteria**

- [x] registrar fases concluídas no TODO
- [x] marcar explicitamente o que continua WIP
- [x] remover falsas marcações de `DONE` em docs antigas

### CR-902: preparar entrega para revisão
**Prioridade:** P1  
**Status:** ✅ DONE

**Acceptance Criteria**

- [x] changed files mapeados por workstream
- [x] verification evidence resumida
- [x] riscos remanescentes registrados
- [x] lacunas fora do escopo explicitadas

---

## Estado pós-entrega

**Pronto para revisão**

Continua propositalmente fora do escopo/WIP para iterações futuras:

- transporte remoto real (`http+ws`) do session bridge
- attach/resume remoto fim a fim
- persistência de `task_state`
- observabilidade histórica por task
- integração web com o contrato de bridge remoto
