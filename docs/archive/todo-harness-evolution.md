# TODO: SOCC Harness Evolution

**Criado em:** 2026-03-30  
**Atualizado em:** 2026-03-31  
**Fontes:** 
- PRD `prd-harness-evolution.md`
- Claude Code Port Analysis `claude-code-port-analysis.md`

---

## Status Legend

| Símbolo | Significado |
|---------|-------------|
| 🔴 | **P0** - Crítico, bloqueia outras tarefas |
| 🟡 | **P1** - Importante, mas não bloqueante |
| 🟢 | **P2** - Nice to have |
| ⬜ | **TODO** - A fazer |
| 🔄 | **WIP** - Em progresso |
| ✅ | **DONE** - Concluído |
| ❌ | **BLOCKED** - Bloqueado |
| 🆕 | **NEW** - Nova task do Claude Code Port |

---

## Fase 1: Foundation (v0.2.0)

### 🔴 P0: Tool Registry

#### ✅ TASK-001: Refatorar tools.py para tools_registry.py

- **Arquivo:** `socc/core/tools_registry.py`
- **Descrição:** Criar sistema de registro dinâmico de tools
- **Acceptance Criteria:**
  - [x] `TOOL_REGISTRY` como dict mutável
  - [x] `register_tool()` funcional
  - [x] `invoke_tool()` com validação de parâmetros
  - [x] `list_tools()` retorna lista ordenada
  - [x] Tests: 100% coverage em tools_registry.py
- **Dependências:** Nenhuma
- **Estimativa:** 4h

#### ✅ TASK-002: Implementar tool spec e validation

- **Arquivo:** `socc/core/tools_registry.py`
- **Descrição:** Criar dataclasses para especificação de tools
- **Acceptance Criteria:**
  - [x] `ToolSpec` dataclass com name, description, parameters, handler
  - [x] `ParamSpec` para definição de parâmetros
  - [x] `ToolResult` para retorno padronizado
  - [x] Validação de tipos em runtime
  - [x] Tests: Validação de parâmetros obrigatórios/opcionais
- **Dependências:** TASK-001
- **Estimativa:** 3h

#### ✅ TASK-003: Mover tools existentes para novo formato

- **Arquivos:** `socc/core/tools.py`
- **Descrição:** Migrar extract_iocs, defang, decode_base64 para novo registry
- **Acceptance Criteria:**
  - [x] `extract_iocs` registrado no novo formato
  - [x] `defang` registrado no novo formato
  - [x] `decode_base64` registrado no novo formato
  - [x] Backward compatibility com imports antigos
  - [x] Tests: Todos os tests existentes passam
- **Dependências:** TASK-002
- **Estimativa:** 2h

#### ✅ TASK-004: Adicionar tools de sistema (read, write)

- **Arquivo:** `socc/tools/file.py`
- **Descrição:** Implementar tools de arquivo inspirados no pi
- **Acceptance Criteria:**
  - [x] `read` - lê arquivo com offset/limit
  - [x] `write` - escreve/cria arquivo
  - [x] `edit` - edita com find/replace
  - [x] Sandbox: apenas dentro de cwd ou paths permitidos
  - [x] Tests: Leitura/escrita em temp_dir
- **Dependências:** TASK-002
- **Estimativa:** 4h

#### ✅ TASK-005: Adicionar tool bash

- **Arquivo:** `socc/tools/shell.py`
- **Descrição:** Executar comandos shell com segurança
- **Acceptance Criteria:**
  - [x] `bash` tool executando comandos
  - [x] Timeout configurável (default: 30s)
  - [x] Whitelist de comandos perigosos (rm -rf, etc)
  - [x] Redação de secrets na saída
  - [x] Tests: Comandos básicos, timeout, bloqueios
- **Dependências:** TASK-002
- **Estimativa:** 3h

---

### 🔴 P0: Context Budget Manager

#### ✅ TASK-038: Criar módulo context_budget.py

- **Arquivo:** `socc/core/context_budget.py`
- **Descrição:** Gerenciador de orçamento de contexto baseado na janela do modelo
- **Acceptance Criteria:**
  - [x] `ContextBudgetManager` com perfis por modelo
  - [x] `estimate_tokens()` com heurística ~4 chars/token
  - [x] `compute_budget()` calcula orçamento por seção
  - [x] Prioridade de seções configurável
  - [x] Truncagem inteligente por prioridade
  - [x] Tests: cobertura dos cenários principais
- **Dependências:** Nenhuma
- **Estimativa:** 4h

#### ✅ TASK-039: Integrar budget no chat_service

- **Arquivo:** `soc_copilot/modules/chat_service.py`
- **Descrição:** Usar budget manager para truncar prompt antes de enviar ao LLM
- **Acceptance Criteria:**
  - [x] `_build_system_prompt` usa budget para limitar seções
  - [x] References são filtradas por relevância quando orçamento apertado
  - [x] Skill content truncada quando excede budget
  - [x] Histórico compactado quando necessário
  - [x] Métricas de uso de contexto no log
- **Dependências:** TASK-038
- **Estimativa:** 3h

#### ✅ TASK-040: Integrar budget no build_prompt_context

- **Arquivo:** `soc_copilot/modules/soc_copilot_loader.py`
- **Descrição:** Passar modelo ativo para o loader ajustar contexto carregado
- **Acceptance Criteria:**
  - [x] `build_prompt_context()` aceita parâmetro `model_name`
  - [x] References filtradas por relevância ao input
  - [x] Skill content truncada se necessário
  - [x] Métrica de tokens estimados por seção
- **Dependências:** TASK-038
- **Estimativa:** 2h

---

### 🔴 P0: Contracts v2.0

#### ✅ TASK-006: Atualizar contracts.py para v2.0

- **Arquivo:** `socc/core/contracts.py`
- **Descrição:** Adicionar novos campos mantendo backward compatibility
- **Acceptance Criteria:**
  - [x] `CONTRACT_VERSION = "2.0"`
  - [x] `AnalysisEnvelope` com fields: tool_calls, reasoning_trace
  - [x] `ChatResponseEnvelope` com fields: tool_calls, thinking
  - [x] `ToolExecutionContract` atualizado
  - [x] Método `to_v1_dict()` para backward compatibility
  - [ ] Tests: Serialização v1 e v2
- **Dependências:** TASK-001
- **Estimativa:** 3h

---

### 🟡 P1: CLI Interativo

#### ✅ TASK-007: Criar módulo cli/repl.py

- **Arquivo:** `socc/cli/chat_interactive.py`
- **Descrição:** TUI full-screen com prompt_toolkit
- **Acceptance Criteria:**
  - [x] Loop REPL funcional
  - [x] Histórico de comandos
  - [x] Suporte a @arquivo para injetar contexto
  - [x] Ctrl+C graceful exit
  - [x] Streaming em tempo real
- **Dependências:** Nenhuma
- **Estimativa:** 6h

#### 🔄 TASK-008: Adicionar flag --continue e --resume

- **Arquivo:** `socc/cli/main.py`
- **Descrição:** Permitir retomar sessões anteriores via CLI
- **Acceptance Criteria:**
  - [ ] `socc chat --continue` retoma última sessão
  - [ ] `socc chat --resume` lista sessões para selecionar
  - [ ] `socc chat --resume <id>` retoma sessão específica
  - [ ] Mensagem clara indicando sessão retomada
- **Dependências:** TASK-007
- **Estimativa:** 3h

#### ⬜ TASK-009: Implementar comando `socc sessions`

- **Arquivo:** `socc/cli/main.py`
- **Descrição:** Subparser `sessions` para gerenciar sessões
- **Acceptance Criteria:**
  - [ ] `socc sessions list` lista com título, data, nº mensagens
  - [ ] `socc sessions show <id>` exibe conversa completa
  - [ ] `socc sessions delete <id>` remove sessão
  - [ ] `socc sessions export <id> --format markdown` exporta
- **Dependências:** TASK-008
- **Estimativa:** 4h

---

### 🟢 P2: Tests e Docs Phase 1

#### ✅ TASK-010: Criar test fixtures para tools

- **Arquivo:** `tests/test_tools_registry.py`
- **Descrição:** Testes do tool registry
- **Status:** Existente e passando
- **Estimativa:** 2h

#### ⬜ TASK-011: Documentação inicial de tools

- **Arquivo:** `docs/tools-reference.md`
- **Descrição:** Documentação de referência das tools
- **Acceptance Criteria:**
  - [ ] Lista de todas as tools disponíveis
  - [ ] Descrição, parâmetros, exemplos para cada
  - [ ] Notas de segurança/sandbox
  - [ ] Exemplos de uso via CLI
- **Dependências:** TASK-003, TASK-004, TASK-005
- **Estimativa:** 2h

---

## 🆕 Fase 1.5: Claude Code Port Integration (v0.2.5)

> **Fonte:** `claude-code-port-analysis.md` - Port de instructkr/claude-code
> **Valor:** Aproveitar arquitetura profissional de harness (184 tools, 207 commands)

### 🔴 P0: Harness Base (CC-001 a CC-004)

#### 🆕 ⬜ TASK-CC-001: Setup Harness Base Structure

- **Arquivo:** `socc/core/harness/`
- **Descrição:** Copiar e adaptar estrutura base do Claude Code Port
- **Acceptance Criteria:**
  - [ ] Criar diretório `socc/core/harness/`
  - [ ] Adaptar `models.py` com `SOCTool`, `SOCAgent`, `SOCCommand`
  - [ ] Criar `reference_data/` com snapshots JSON
  - [ ] Tests: Imports funcionando
- **Dependências:** TASK-001, TASK-002
- **Estimativa:** 4h
- **Port Source:** `/home/nilsonpmjr/claude-code/src/models.py`

#### 🆕 ⬜ TASK-CC-002: Port Runtime Core

- **Arquivo:** `socc/core/harness/runtime.py`
- **Descrição:** Implementar `SOCRuntime` baseado em `PortRuntime`
- **Acceptance Criteria:**
  - [ ] `SOCRuntime` class com routing de prompts
  - [ ] `route_prompt()` para SOC-specific matching
  - [ ] Integração com `tools_registry.py` existente
  - [ ] Tests: Routing funciona
- **Dependências:** TASK-CC-001
- **Estimativa:** 6h
- **Port Source:** `/home/nilsonpmjr/claude-code/src/runtime.py`

#### 🆕 ⬜ TASK-CC-003: SOC Tools Snapshot

- **Arquivo:** `socc/core/harness/reference_data/socc_tools_snapshot.json`
- **Descrição:** Criar snapshot de tools SOC
- **Acceptance Criteria:**
  - [ ] Tools existentes: extract_iocs, defang, decode_base64
  - [ ] Placeholders para tools planejadas
  - [ ] JSON Schema validado
  - [ ] Loader funcional
- **Dependências:** TASK-CC-001
- **Estimativa:** 3h
- **Port Source:** `/home/nilsonpmjr/claude-code/src/reference_data/tools_snapshot.json`

#### 🆕 ⬜ TASK-CC-004: SOC Commands Registry

- **Arquivo:** `socc/core/harness/commands.py`
- **Descrição:** Sistema de comandos inspirado no port
- **Acceptance Criteria:**
  - [ ] `register_command()`, `get_command()`, `list_commands()`
  - [ ] `socc_commands_snapshot.json`
  - [ ] Comandos iniciais: `/case`, `/hunt`, `/report`, `/pivot`
  - [ ] Tests: Comandos listados
- **Dependências:** TASK-CC-001
- **Estimativa:** 4h
- **Port Source:** `/home/nilsonpmjr/claude-code/src/commands.py`

---

### 🔴 P0: BashTool Security (CC-005 a CC-007)

> **Crítico para operações SOC seguras**

#### 🆕 ⬜ TASK-CC-005: Port BashTool Security

- **Arquivo:** `socc/tools/bash/security.py`
- **Descrição:** Sistema de validação de comandos perigosos
- **Acceptance Criteria:**
  - [ ] `CommandRisk` enum: SAFE, MODERATE, DESTRUCTIVE, BLOCKED
  - [ ] `validate_command()` analisa risco
  - [ ] `DESTRUCTIVE_COMMANDS` lista configurável
  - [ ] `should_use_sandbox()` decide sandbox
  - [ ] Tests: Comandos bloqueados/permitidos
- **Dependências:** TASK-005
- **Estimativa:** 6h
- **Port Source:** `tools/BashTool/bashSecurity.ts`, `destructiveCommandWarning.ts`

#### 🆕 ⬜ TASK-CC-006: Port BashTool Permissions

- **Arquivo:** `socc/tools/bash/permissions.py`
- **Descrição:** RBAC para comandos shell
- **Acceptance Criteria:**
  - [ ] Roles: `analyst`, `senior_analyst`, `admin`
  - [ ] Permissões por comando/risco
  - [ ] Audit logging de comandos
  - [ ] Tests: Checagem de permissões
- **Dependências:** TASK-CC-005
- **Estimativa:** 4h
- **Port Source:** `tools/BashTool/bashPermissions.ts`

#### 🆕 ⬜ TASK-CC-007: Port BashTool Sandbox

- **Arquivo:** `socc/tools/bash/sandbox.py`
- **Descrição:** Isolamento de comandos perigosos
- **Acceptance Criteria:**
  - [ ] Container/namespace isolation (opcional)
  - [ ] Resource limits (CPU, memory, time)
  - [ ] Network isolation options
  - [ ] Tests: Sandbox funcional
- **Dependências:** TASK-CC-005
- **Estimativa:** 6h
- **Port Source:** `tools/BashTool/shouldUseSandbox.ts`

---

## Fase 2: Core Features (v0.3.0)

### 🔴 P0: Sistema de Plugins

#### ⬜ TASK-012: Criar ExtensionManager

- **Arquivo:** `socc/core/extensions.py`
- **Descrição:** Sistema de carregamento de plugins
- **Acceptance Criteria:**
  - [ ] Descoberta de plugins em ~/.socc/extensions/
  - [ ] Parse de manifest.json
  - [ ] Validação de schema do manifest
  - [ ] Logging de plugins carregados
  - [ ] Tests: Carregamento de plugin de teste
- **Dependências:** TASK-001
- **Estimativa:** 5h

#### ⬜ TASK-013: Implementar hook system para plugins

- **Arquivo:** `socc/core/extensions.py`
- **Descrição:** Sistema de hooks para events
- **Acceptance Criteria:**
  - [ ] Hooks: on_load, on_tool_call, on_chat_start, on_chat_end
  - [ ] Plugins podem registrar handlers
  - [ ] Exception handling graceful
  - [ ] Tests: Plugin com hooks sendo chamado
- **Dependências:** TASK-012
- **Estimativa:** 4h

#### ⬜ TASK-014: Permitir plugins registrem tools

- **Arquivo:** `socc/core/extensions.py`
- **Descrição:** Plugins podem adicionar tools ao registry
- **Acceptance Criteria:**
  - [ ] Plugin pode definir tools em manifest
  - [ ] Tools carregadas automaticamente
  - [ ] Namespacing: `plugin_name.tool_name`
  - [ ] Tests: Plugin com tool customizada
- **Dependências:** TASK-012, TASK-013
- **Estimativa:** 3h

#### ⬜ TASK-015: Permitir plugins registrem skills

- **Arquivo:** `socc/core/extensions.py`
- **Descrição:** Plugins podem adicionar skills customizadas
- **Acceptance Criteria:**
  - [ ] Plugin pode definir skills em manifest
  - [ ] Skills carregadas de `<plugin_dir>/skills/*.md`
  - [ ] Integração com agent_loader existente
  - [ ] Tests: Plugin com skill customizada
- **Dependências:** TASK-012
- **Estimativa:** 3h

---

### 🔴 P0: Memory Manager com RAG

#### ⬜ TASK-016: Criar schema de memória

- **Arquivo:** `socc/core/memory_schema.py`
- **Descrição:** Definir estrutura de dados para memória
- **Acceptance Criteria:**
  - [ ] `MemoryEntry` dataclass
  - [ ] `MemoryMetadata` dataclass
  - [ ] JSON schema para validação
  - [ ] Tests: Validação de entradas
- **Dependências:** Nenhuma
- **Estimativa:** 2h

#### ⬜ TASK-017: Implementar armazenamento JSONL

- **Arquivo:** `socc/core/memory_store.py`
- **Descrição:** Persistência de memória em JSONL
- **Acceptance Criteria:**
  - [ ] `remember(key, value, metadata)` salva entrada
  - [ ] `forget(key)` remove entrada
  - [ ] `list_entries()` lista todas
  - [ ] Append-only para durability
  - [ ] Tests: CRUD de memória
- **Dependências:** TASK-016
- **Estimativa:** 3h

#### ⬜ TASK-018: Integrar embeddings com sentence-transformers

- **Arquivo:** `socc/core/memory_embeddings.py`
- **Descrição:** Gerar embeddings para memórias
- **Acceptance Criteria:**
  - [ ] Cache de modelo em memória
  - [ ] Geração de embeddings para texto
  - [ ] Batch encoding para performance
  - [ ] Configuração de modelo via env
  - [ ] Tests: Embedding generation
- **Dependências:** TASK-017
- **Estimativa:** 4h

#### ⬜ TASK-019: Implementar vector store com sqlite-vec

- **Arquivo:** `socc/core/memory_vectors.py`
- **Descrição:** Busca semântica com sqlite-vec
- **Acceptance Criteria:**
  - [ ] Indexação automática de embeddings
  - [ ] `recall(query, k=5)` retorna resultados relevantes
  - [ ] Filtro por metadata
  - [ ] Cleanup de entradas antigas
  - [ ] Tests: Semantic search
- **Dependências:** TASK-018
- **Estimativa:** 5h

#### ⬜ TASK-020: Integrar memória no chat

- **Arquivo:** `socc/core/chat.py`
- **Descrição:** Usar memória RAG no chat reply
- **Acceptance Criteria:**
  - [ ] Chat consulta memória antes de responder
  - [ ] Contexto relevante anexado ao prompt
  - [ ] Memória atualizada após cada interação
  - [ ] Feature flag para habilitar/desabilitar
  - [ ] Tests: Chat com e sem memória
- **Dependências:** TASK-019
- **Estimativa:** 4h

---

### 🟡 P1: Agent System (do Claude Code Port)

#### 🆕 ⬜ TASK-CC-009: Port AgentTool Fork

- **Arquivo:** `socc/agents/fork.py`
- **Descrição:** Sistema de subagentes especializados
- **Acceptance Criteria:**
  - [ ] `fork_subagent(config)` cria e executa subagent
  - [ ] Passa contexto (case data, findings)
  - [ ] Track de lifecycle do subagent
  - [ ] Tests: Subagent criado e finalizado
- **Dependências:** TASK-CC-002
- **Estimativa:** 6h
- **Port Source:** `tools/AgentTool/forkSubagent.ts`

#### 🆕 ⬜ TASK-CC-010: Port AgentTool Memory

- **Arquivo:** `socc/agents/memory.py`
- **Descrição:** Memória específica de agents
- **Acceptance Criteria:**
  - [ ] `AgentMemory` class
  - [ ] Persistência em `~/.socc/agents/{agent_id}/`
  - [ ] Snapshots de estado
  - [ ] Tests: Save/restore de estado
- **Dependências:** TASK-CC-009
- **Estimativa:** 4h
- **Port Source:** `tools/AgentTool/agentMemory.ts`

#### 🆕 ⬜ TASK-CC-011: Create SOC Analyst Agent

- **Arquivo:** `socc/agents/built_in/soc_analyst.py`
- **Descrição:** Agente generalista para análise SOC
- **Acceptance Criteria:**
  - [ ] Prompt template para análise SOC
  - [ ] Tools: extract_iocs, defang, bash, grep
  - [ ] Testado com cenários reais
  - [ ] Docs: Como usar
- **Dependências:** TASK-CC-009
- **Estimativa:** 4h

#### 🆕 ⬜ TASK-CC-012: Create Incident Response Agent

- **Arquivo:** `socc/agents/built_in/ir_agent.py`
- **Descrição:** Agente especializado em Incident Response
- **Acceptance Criteria:**
  - [ ] Prompt template para IR
  - [ ] Tools: bash, file_read, process_list
  - [ ] Checklist automático de IR
  - [ ] Tests: Fluxo de resposta a incidente
- **Dependências:** TASK-CC-009
- **Estimativa:** 4h

#### 🆕 ⬜ TASK-CC-013: Create Threat Hunt Agent

- **Arquivo:** `socc/agents/built_in/threat_hunt_agent.py`
- **Descrição:** Agente para threat hunting
- **Acceptance Criteria:**
  - [ ] Prompt template hypothesis-driven
  - [ ] Tools: grep, bash, process_list, network
  - [ ] Logging de hunting findings
  - [ ] Tests: Hipóteses geradas
- **Dependências:** TASK-CC-009
- **Estimativa:** 4h

---

### 🟡 P1: Streaming com Tool Calling

#### ⬜ TASK-021: Adicionar eventos de tool_call no streaming

- **Arquivo:** `socc/core/engine.py`
- **Descrição:** Emitir eventos quando tools são chamadas
- **Acceptance Criteria:**
  - [ ] Evento `tool_call` com tool name e args
  - [ ] Evento `tool_result` com resultado
  - [ ] Integração com SSE existente
  - [ ] Frontend mostra progress
  - [ ] Tests: Eventos em ordem correta
- **Dependências:** TASK-001
- **Estimativa:** 4h

#### ⬜ TASK-022: Implementar detecção de need_tool no chat

- **Arquivo:** `socc/core/chat_tools.py`
- **Descrição:** Detectar quando LLM precisa de tool
- **Acceptance Criteria:**
  - [ ] Parser para resposta do LLM
  - [ ] Detecção de tool call tags
  - [ ] Execução automática de tool
  - [ ] Injeção de resultado no prompt
  - [ ] Tests: Vários formatos de tool call
- **Dependências:** TASK-021
- **Estimativa:** 5h

---

### 🟢 P2: Tests e Docs Phase 2

#### ⬜ TASK-023: Criar plugin de exemplo

- **Arquivo:** `examples/plugins/hello_world/`
- **Descrição:** Plugin exemplo para documentação
- **Acceptance Criteria:**
  - [ ] manifest.json completo
  - [ ] tool customizada simples
  - [ ] skill customizada
  - [ ] README com instruções
- **Dependências:** TASK-015
- **Estimativa:** 2h

#### ⬜ TASK-024: Documentação de plugins

- **Arquivo:** `docs/plugins-guide.md`
- **Descrição:** Guia de criação de plugins
- **Acceptance Criteria:**
  - [ ] Estrutura de diretórios
  - [ ] Schema do manifest.json
  - [ ] Como criar tools/skills
  - [ ] Como usar hooks
- **Dependências:** TASK-023
- **Estimativa:** 2h

---

## Fase 3: Polish (v0.4.0)

### 🟡 P1: CLI Enhancements

#### ⬜ TASK-025: Adicionar auto-complete no REPL

- **Arquivo:** `socc/cli/completions.py`
- **Descrição:** Auto-complete para comandos e paths
- **Acceptance Criteria:**
  - [ ] Complete de comandos: socc <TAB>
  - [ ] Complete de flags: socc --<TAB>
  - [ ] Complete de paths: socc @<TAB>
  - [ ] Complete de tools: socc tool <TAB>
- **Dependências:** TASK-007
- **Estimativa:** 4h

#### ⬜ TASK-026: Adicionar rich output no CLI

- **Arquivo:** `socc/cli/output.py`
- **Descrição:** Formatação rica de output com rich
- **Acceptance Criteria:**
  - [ ] Tabelas para results estruturados
  - [ ] Syntax highlighting para código
  - [ ] Progress bars para operações longas
  - [ ] Colors para status
- **Dependências:** TASK-007
- **Estimativa:** 3h

---

### 🟡 P1: SOC Commands (do Claude Code Port)

#### 🆕 ⬜ TASK-CC-014: Implement SOCC CLI

- **Arquivo:** `socc/cli/main.py`
- **Descrição:** CLI completo inspirado no port
- **Acceptance Criteria:**
  - [ ] Subcommands: scan, analyze, report, case
  - [ ] Interactive mode (REPL)
  - [ ] Help text para cada comando
  - [ ] Tests: CLI invocando cada subcommand
- **Dependências:** TASK-CC-004
- **Estimativa:** 8h
- **Port Source:** `/home/nilsonpmjr/claude-code/src/main.py`

#### 🆕 ⬜ TASK-CC-015: Implement /case Command

- **Arquivo:** `socc/commands/case.py`
- **Descrição:** Gerenciamento de cases de incidente
- **Acceptance Criteria:**
  - [ ] `/case create`, `/case load`, `/case close`
  - [ ] Persistência em `~/.socc/cases/`
  - [ ] Metadata: title, severity, status, assignee
  - [ ] Tests: CRUD de cases
- **Dependências:** TASK-CC-014
- **Estimativa:** 6h

#### 🆕 ⬜ TASK-CC-016: Implement /hunt Command

- **Arquivo:** `socc/commands/hunt.py`
- **Descrição:** Threat hunting interativo
- **Acceptance Criteria:**
  - [ ] Hypothesis-driven hunting
  - [ ] Logging de findings
  - [ ] Integration com Threat Hunt Agent
  - [ ] Tests: Hunting session
- **Dependências:** TASK-CC-014, TASK-CC-013
- **Estimativa:** 4h

---

### 🔴 P0: Export de Sessões

#### ⬜ TASK-027: Implementar export HTML

- **Arquivo:** `socc/cli/export.py`
- **Descrição:** Exportar sessão para HTML formatado
- **Acceptance Criteria:**
  - [ ] `socc export <session_id> --format html`
  - [ ] Template HTML responsivo
  - [ ] Syntax highlighting para código
  - [ ] Metadata no header
- **Dependências:** TASK-009
- **Estimativa:** 3h

#### ⬜ TASK-028: Implementar export Markdown

- **Arquivo:** `socc/cli/export.py`
- **Descrição:** Exportar sessão para Markdown
- **Acceptance Criteria:**
  - [ ] `socc export <session_id> --format markdown`
  - [ ] Markdown formatado com código
  - [ ] YAML frontmatter com metadata
- **Dependências:** TASK-009
- **Estimativa:** 2h

---

### 🟢 P2: Benchmark e Performance

#### ⬜ TASK-029: Criar benchmark de tools

- **Arquivo:** `tests/benchmarks/tools_benchmark.py`
- **Descrição:** Benchmark de performance de tools
- **Acceptance Criteria:**
  - [ ] Medir latency de cada tool
  - [ ] Dataset de teste (1000 IOC samples)
  - [ ] Report de P50, P95, P99
- **Dependências:** TASK-003, TASK-004, TASK-005
- **Estimativa:** 3h

#### ⬜ TASK-030: Criar benchmark de memória RAG

- **Arquivo:** `tests/benchmarks/memory_benchmark.py`
- **Descrição:** Benchmark de RAG
- **Acceptance Criteria:**
  - [ ] Ingestão de N documentos
  - [ ] Query latency com diferentes tamanhos
  - [ ] Recall@k metrics
- **Dependências:** TASK-020
- **Estimativa:** 3h

#### ⬜ TASK-031: Otimizar startup time

- **Arquivo:** `socc/cli/main.py`
- **Descrição:** Reduzir tempo de inicialização
- **Acceptance Criteria:**
  - [ ] Medir baseline atual
  - [ ] Lazy loading de módulos
  - [ ] Target: <1s para `socc --help`
- **Dependências:** Nenhuma
- **Estimativa:** 4h

---

## Fase 4: Advanced (v0.5.0)

### 🟡 P1: Multi-Agent Support

#### ⬜ TASK-032: Criar agente registry

- **Arquivo:** `socc/core/agents.py`
- **Descrição:** Sistema para múltiplos agentes
- **Acceptance Criteria:**
  - [ ] `AgentSpec` dataclass
  - [ ] Registry de agentes
  - [ ] Seletor de agente via CLI
  - [ ] Agente default: soc-copilot
- **Dependências:** TASK-001
- **Estimativa:** 4h

#### ⬜ TASK-033: Permitir agentes com tools diferentes

- **Arquivo:** `socc/core/agents.py`
- **Descrição:** Cada agente pode ter tools específicas
- **Acceptance Criteria:**
  - [ ] `tools_whitelist` no AgentSpec
  - [ ] `tools_blacklist` no AgentSpec
  - [ ] Agente só pode usar tools permitidas
  - [ ] Tests: Isolamento entre agentes
- **Dependências:** TASK-032
- **Estimativa:** 3h

---

### 🟢 P2: Workflow Automation

#### ⬜ TASK-034: Criar workflow engine

- **Arquivo:** `socc/core/workflow.py`
- **Descrição:** Sequências automatizadas de ações
- **Acceptance Criteria:**
  - [ ] `Workflow` spec com steps
  - [ ] Steps podem invocar tools
  - [ ] Steps podem invocar LLM
  - [ ] Conditional branching
  - [ ] Error handling e retries
- **Dependências:** TASK-001, TASK-006
- **Estimativa:** 8h

#### ⬜ TASK-035: Workflows predefinidos para SOC

- **Arquivo:** `socc/workflows/`
- **Descrição:** Workflows comuns de triagem
- **Acceptance Criteria:**
  - [ ] Workflow: Phishing Triage
  - [ ] Workflow: Malware Analysis
  - [ ] Workflow: Alert Enrichment
  - [ ] Workflow: IOC Investigation
- **Dependências:** TASK-034
- **Estimativa:** 4h

---

### 🟢 P2: Integrations (do Claude Code Port)

#### 🆕 ⬜ TASK-CC-017: Port Plugin System

- **Arquivo:** `socc/plugins/`
- **Descrição:** Sistema de plugins completo
- **Acceptance Criteria:**
  - [ ] Plugin loader com entry points
  - [ ] Plugin manifest schema
  - [ ] Hot-reload de plugins
  - [ ] Tests: Plugin loading
- **Dependências:** TASK-012
- **Estimativa:** 8h
- **Port Source:** `commands/plugin/`

#### 🆕 ⬜ TASK-CC-018: VirusTotal Plugin

- **Arquivo:** `socc/plugins/virustotal/`
- **Descrição:** Integração VirusTotal
- **Acceptance Criteria:**
  - [ ] Tools: `vt_lookup_hash`, `vt_lookup_url`, `vt_lookup_domain`
  - [ ] API key management
  - [ ] Rate limiting
  - [ ] Tests: Mock API responses
- **Dependências:** TASK-CC-017
- **Estimativa:** 4h

#### 🆕 ⬜ TASK-CC-019: MISP Plugin

- **Arquivo:** `socc/plugins/misp/`
- **Descrição:** Integração MISP
- **Acceptance Criteria:**
  - [ ] Tools: `misp_search`, `misp_add_event`, `misp_add_ioc`
  - [ ] MISP API integration
  - [ ] Attribute type mapping
  - [ ] Tests: Mock MISP server
- **Dependências:** TASK-CC-017
- **Estimativa:** 4h

#### 🆕 ⬜ TASK-CC-020: OpenCTI Plugin

- **Arquivo:** `socc/plugins/opencti/`
- **Descrição:** Integração OpenCTI
- **Acceptance Criteria:**
  - [ ] Tools: `opencti_search`, `opencti_create_indicator`
  - [ ] GraphQL API integration
  - [ ] STIX 2.1 support
  - [ ] Tests: Mock GraphQL
- **Dependências:** TASK-CC-017
- **Estimativa:** 4h

---

### 🟢 P2: External API

#### ⬜ TASK-036: Integração com Shuffle SOAR

- **Arquivo:** `socc/integrations/shuffle.py`
- **Descrição:** Webhook para Shuffle workflows
- **Acceptance Criteria:**
  - [ ] Endpoint para receber webhooks
  - [ ] Parse de payload do Shuffle
  - [ ] Trigger de análise automática
  - [ ] Callback com resultados
- **Dependências:** TASK-034
- **Estimativa:** 6h

#### ⬜ TASK-037: API REST para integração externa

- **Arquivo:** `socc/api/external.py`
- **Descrição:** API REST para integrações
- **Acceptance Criteria:**
  - [ ] POST /analyze
  - [ ] POST /chat
  - [ ] GET /tools
  - [ ] GET /sessions
  - [ ] Auth via API key
- **Dependências:** Nenhuma
- **Estimativa:** 6h

---

## Summary

### Por Fase

| Fase | Tasks | Estimativa |
|------|-------|------------|
| Phase 1 (v0.2.0) | 11 tasks | ~35h |
| Phase 1.5 (v0.2.5) 🆕 | 12 tasks | ~55h |
| Phase 2 (v0.3.0) | 14 tasks | ~47h |
| Phase 3 (v0.4.0) | 10 tasks | ~34h |
| Phase 4 (v0.5.0) | 10 tasks | ~47h |
| **Total** | **57 tasks** | **~218h** |

### Por Prioridade

| Prioridade | Tasks | Estimativa |
|------------|-------|------------|
| P0 (Crítico) | 21 tasks | ~95h |
| P1 (Importante) | 20 tasks | ~80h |
| P2 (Nice to have) | 16 tasks | ~43h |

### Por Fonte

| Fonte | Tasks | Estimativa |
|-------|-------|------------|
| Original TODO | 37 tasks | ~139h |
| Claude Code Port 🆕 | 20 tasks | ~95h |
| **Total** | **57 tasks** | **~218h** |

### Tasks Concluídas

| Task | Status |
|------|--------|
| TASK-001 | ✅ Tool Registry |
| TASK-002 | ✅ Tool Spec/Validation |
| TASK-003 | ✅ Tools Migration |
| TASK-004 | ✅ File Tools |
| TASK-005 | ✅ Bash Tool |
| TASK-006 | ✅ Contracts v2.0 |
| TASK-007 | ✅ CLI REPL |
| TASK-010 | ✅ Test Fixtures |
| TASK-038 | ✅ Context Budget |
| TASK-039 | ✅ Budget Integration |
| TASK-040 | ✅ Budget in Loader |

---

## Prerequisites Checklist

Antes de começar Phase 1.5 (Claude Code Port):

- [x] TASK-001 a TASK-005 completos (Tool Registry)
- [x] TASK-007 completo (CLI básico)
- [ ] Clonar/portar estrutura de `/home/nilsonpmjr/claude-code/src/`

---

## Definition of Done

Para considerar uma task completa:

- [ ] Código implementado
- [ ] Tests unitários passando
- [ ] Coverage >= 80% no novo código
- [ ] Documentação inline (docstrings)
- [ ] Sem warnings de linter
- [ ] PR revisado e aprovado
- [ ] Merged na branch principal

---

## Claude Code Port Reference

| Component | Port Path | SOCC Target |
|-----------|-----------|-------------|
| models.py | `/home/nilsonpmjr/claude-code/src/models.py` | `socc/core/harness/models.py` |
| runtime.py | `/home/nilsonpmjr/claude-code/src/runtime.py` | `socc/core/harness/runtime.py` |
| commands.py | `/home/nilsonpmjr/claude-code/src/commands.py` | `socc/core/harness/commands.py` |
| tools.py | `/home/nilsonpmjr/claude-code/src/tools.py` | `socc/core/harness/tools_loader.py` |
| BashTool/* | `tools/BashTool/` | `socc/tools/bash/` |
| AgentTool/* | `tools/AgentTool/` | `socc/agents/` |

---

**Próximos passos recomendados:**

1. **TASK-CC-001** - Setup Harness Base (foundation para o port)
2. **TASK-CC-005** - BashTool Security (crítico para SOC)
3. **TASK-CC-009** - AgentTool Fork (subagentes)