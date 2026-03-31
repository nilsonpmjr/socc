# TODO: SOCC Harness Evolution

**Criado em:** 2026-03-30  
**Atualizado em:** 2026-03-31  
**Fonte:** PRD `prd-harness-evolution.md`

---

## Status Legend

- 🔴 **P0** - Crítico, bloqueia outras tarefas
- 🟡 **P1** - Importante, mas não bloqueante
- 🟢 **P2** - Nice to have
- ⬜ **TODO** - A fazer
- 🔄 **WIP** - Em progresso
- ✅ **DONE** - Concluído
- ❌ **BLOCKED** - Bloqueado

---

## Phase 1: Foundation (v0.2.0)

### 🔴 P0: Context Budget Manager (Suporte a LLMs de Baixo Contexto)

#### 🔄 TASK-038: Criar módulo context_budget.py
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

#### 🔄 TASK-039: Integrar budget no chat_service
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

#### 🔄 TASK-040: Integrar budget no build_prompt_context
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

### 🔴 P0: Tool Registry

#### ⬜ TASK-001: Refatorar tools.py para tools_registry.py
- **Arquivo:** `socc/core/tools_registry.py`
- **Descrição:** Criar sistema de registro dinâmico de tools
- **Acceptance Criteria:**
  - [ ] `TOOL_REGISTRY` como dict mutável
  - [ ] `register_tool()` funcional
  - [ ] `invoke_tool()` com validação de parâmetros
  - [ ] `list_tools()` retorna lista ordenada
  - [ ] Tests: 100% coverage em tools_registry.py
- **Dependências:** Nenhuma
- **Estimativa:** 4h

#### ⬜ TASK-002: Implementar tool spec e validation
- **Arquivo:** `socc/core/tools_registry.py`
- **Descrição:** Criar dataclasses para especificação de tools
- **Acceptance Criteria:**
  - [ ] `ToolSpec` dataclass com name, description, parameters, handler
  - [ ] `ParamSpec` para definição de parâmetros
  - [ ] `ToolResult` para retorno padronizado
  - [ ] Validação de tipos em runtime
  - [ ] Tests: Validação de parâmetros obrigatórios/opcionais
- **Dependências:** TASK-001
- **Estimativa:** 3h

#### ⬜ TASK-003: Mover tools existentes para novo formato
- **Arquivos:** `socc/tools/ioc.py`, `socc/tools/__init__.py`
- **Descrição:** Migrar extract_iocs, defang, decode_base64 para novo registry
- **Acceptance Criteria:**
  - [ ] `extract_iocs` registrado no novo formato
  - [ ] `defang` registrado no novo formato
  - [ ] `decode_base64` registrado no novo formato
  - [ ] Backward compatibility com imports antigos
  - [ ] Tests: Todos os tests existentes passam
- **Dependências:** TASK-002
- **Estimativa:** 2h

#### ⬜ TASK-004: Adicionar tools de sistema (read, write)
- **Arquivo:** `socc/tools/file.py`
- **Descrição:** Implementar tools de arquivo inspirados no pi
- **Acceptance Criteria:**
  - [ ] `read` - lê arquivo com offset/limit
  - [ ] `write` - escreve/cria arquivo
  - [ ] `edit` - edita com find/replace
  - [ ] Sandbox: apenas dentro de cwd ou paths permitidos
  - [ ] Tests: Leitura/escrita em temp_dir
- **Dependências:** TASK-002
- **Estimativa:** 4h

#### ⬜ TASK-005: Adicionar tool bash
- **Arquivo:** `socc/tools/shell.py`
- **Descrição:** Executar comandos shell com segurança
- **Acceptance Criteria:**
  - [ ] `bash` tool executando comandos
  - [ ] Timeout configurável (default: 30s)
  - [ ] Whitelist de comandos perigosos (rm -rf, etc)
  - [ ] Redação de secrets na saída
  - [ ] Tests: Comandos básicos, timeout, bloqueios
- **Dependências:** TASK-002
- **Estimativa:** 3h

---

### 🔴 P0: Contracts v2.0

#### ⬜ TASK-006: Atualizar contracts.py para v2.0
- **Arquivo:** `socc/core/contracts.py`
- **Descrição:** Adicionar novos campos mantendo backward compatibility
- **Acceptance Criteria:**
  - [ ] `CONTRACT_VERSION = "2.0"`
  - [ ] `AnalysisEnvelope` com fields: tool_calls, reasoning_trace
  - [ ] `ChatResponseEnvelope` com fields: tool_calls, thinking
  - [ ] `ToolExecutionContract` atualizado
  - [ ] Método `to_v1_dict()` para backward compatibility
  - [ ] Tests: Serialização v1 e v2
- **Dependências:** TASK-001
- **Estimativa:** 3h

---

### 🟡 P1: CLI Interativo

#### ⬜ TASK-007: Criar módulo cli/repl.py
- **Arquivo:** `socc/cli/repl.py`
- **Descrição:** Interface REPL interativa usando prompt_toolkit
- **Acceptance Criteria:**
  - [ ] Loop interativo com prompt `socc> `
  - [ ] Histórico de comandos (seta cima/baixo)
  - [ ] Suporte a @arquivo para incluir arquivos
  - [ ] Tratamento de Ctrl+C graceful
  - [ ] Tests: Input/output em modo não-interativo
- **Dependências:** Nenhuma
- **Estimativa:** 5h

#### ⬜ TASK-008: Adicionar flag --continue e --resume
- **Arquivo:** `socc/cli/main.py`
- **Descrição:** Permitir retomar sessões anteriores
- **Acceptance Criteria:**
  - [ ] `socc --continue` retoma última sessão
  - [ ] `socc --resume` lista sessões para selecionar
  - [ ] `socc --resume <id>` retoma sessão específica
  - [ ] Mensagem clara indicando sessão retomada
  - [ ] Tests: Criação, resume, continue
- **Dependências:** TASK-007
- **Estimativa:** 3h

#### ⬜ TASK-009: Implementar comando de sessões
- **Arquivo:** `socc/cli/session_manager.py`
- **Descrição:** Gerenciamento completo de sessões
- **Acceptance Criteria:**
  - [ ] `socc sessions list` lista sessões
  - [ ] `socc sessions show <id>` mostra detalhes
  - [ ] `socc sessions delete <id>` remove sessão
  - [ ] `socc sessions export <id> --format html` exporta
  - [ ] Tests: CRUD de sessões
- **Dependências:** TASK-008
- **Estimativa:** 4h

---

### 🟢 P2: Tests e Docs Phase 1

#### ⬜ TASK-010: Criar test fixtures para tools
- **Arquivo:** `tests/fixtures/tools_fixtures.py`
- **Descrição:** Dados de teste para validar tools
- **Acceptance Criteria:**
  - [ ] Fixtures de IOC: IPs, domains, hashes, URLs
  - [ ] Fixtures de arquivo: sample.txt, sample.json
  - [ ] Fixtures de expected results
  - [ ] Tests parametrizados usando fixtures
- **Dependências:** TASK-003, TASK-004, TASK-005
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

## Phase 2: Core Features (v0.3.0)

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
  - [ ] Plugins podem Registrar handlers
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

### 🟡 P1: Streaming com Tool Calling

#### ⬜ TASK-021: Adicionar eventos de tool_call no streaming
- **Arquivo:** `socc/core/engine.py`
- **Descrição:** Emitir eventos quando tools são chamadas
- **Acceptance Criteria:**
  - [ ] Evento `tool_call` com tool name e args
  - [ ] Evento `tool_result` com resultado
  - [ ] Integração com SSE existente
  - [ ] Frontend (opcional) mostra progress
  - [ ] Tests: Eventos em ordem correta
- **Dependências:** TASK-001
- **Estimativa:** 4h

#### ⬜ TASK-022: Implementar detecção de need_tool no chat
- **Arquivo:** `socc/core/chat_tools.py`
- **Descrição:** Detectar quando LLM precisa de tool
- **Acceptance Criteria:**
  - [ ] Parser para resposta do LLM
  - [ ] Detecção de `<tool_call>` tags ou similar
  - [ ] Execução automática de tool
  - [ ] Injeção de resultado de volta no prompt
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
  - [ ] Testado que carrega corretamente
- **Dependências:** TASK-015
- **Estimativa:** 2h

#### ⬜ TASK-024: Documentação de plugins
- **Arquivo:** `docs/plugins-guide.md`
- **Descrição:** Guia de criação de plugins
- **Acceptance Criteria:**
  - [ ] Estrutura de diretórios
  - [ ] Schema do manifest.json
  - [ ] Como criar tools
  - [ ] Como criar skills
  - [ ] Como usar hooks
  - [ ] Example completo
- **Dependências:** TASK-023
- **Estimativa:** 2h

---

## Phase 3: Polish (v0.4.0)

### 🟡 P1: CLI Enhancements

#### ⬜ TASK-025: Adicionar auto-complete no REPL
- **Arquivo:** `socc/cli/completions.py`
- **Descrição:** Auto-complete para comandos e paths
- **Acceptance Criteria:**
  - [ ] Complete de comandos: socc <TAB>
  - [ ] Complete de flags: socc --<TAB>
  - [ ] Complete de paths: socc @<TAB>
  - [ ] Complete de tools: socc tool <TAB>
  - [ ] Works com prompt_toolkit
- **Dependências:** TASK-007
- **Estimativa:** 4h

#### ⬜ TASK-026: Adicionar rich output no CLI
- **Arquivo:** `socc/cli/output.py`
- **Descrição:** Formatação rica de output com rich
- **Acceptance Criteria:**
  - [ ] Tabelas para results estruturados
  - [ ] Syntax highlighting para código
  - [ ] Progress bars para operações longas
  - [ ] Colors para status (success, error, warning)
  - [ ] Configurável via --no-color
- **Dependências:** TASK-007
- **Estimativa:** 3h

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
  - [ ] Arquivo salvo em ~/.socc/exports/
- **Dependências:** TASK-009
- **Estimativa:** 3h

#### ⬜ TASK-028: Implementar export Markdown
- **Arquivo:** `socc/cli/export.py`
- **Descrição:** Exportar sessão para Markdown
- **Acceptance Criteria:**
  - [ ] `socc export <session_id> --format markdown`
  - [ ] Markdown formatado com código
  - [ ] YAML frontmatter com metadata
  - [ ] Timestamps ISO 8601
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
  - [ ] Comparação com baseline
- **Dependências:** TASK-003, TASK-004, TASK-005
- **Estimativa:** 3h

#### ⬜ TASK-030: Criar benchmark de memória RAG
- **Arquivo:** `tests/benchmarks/memory_benchmark.py`
- **Descrição:** Benchmark de RAG
- **Acceptance Criteria:**
  - [ ] Ingestão de N documentos
  - [ ] Query latency com diferentes tamanhos
  - [ ] Recall@k metrics
  - [ ] Memory usage tracking
- **Dependências:** TASK-020
- **Estimativa:** 3h

#### ⬜ TASK-031: Otimizar startup time
- **Arquivo:** `socc/cli/main.py`
- **Descrição:** Reduzir tempo de inicialização
- **Acceptance Criteria:**
  - [ ] Medir baseline atual
  - [ ] Lazy loading de módulos
  - [ ] Cache de configuração
  - [ ] Target: <1s para `socc --help`
- **Dependências:** Nenhuma
- **Estimativa:** 4h

---

## Phase 4: Advanced (v0.5.0)

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

### 🟢 P2: Integrations

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
| Phase 1 (v0.2.0) | 14 tasks | ~42h |
| Phase 2 (v0.3.0) | 13 tasks | ~44h |
| Phase 3 (v0.4.0) | 7 tasks | ~22h |
| Phase 4 (v0.5.0) | 6 tasks | ~31h |
| **Total** | **40 tasks** | **~139h** |

### Por Prioridade

| Prioridade | Tasks | Estimativa |
|------------|-------|------------|
| P0 (Crítico) | 17 tasks | ~72h |
| P1 (Importante) | 12 tasks | ~40h |
| P2 (Nice to have) | 8 tasks | ~18h |

### Por Componente

| Componente | Tasks | Estimativa |
|------------|-------|------------|
| Tool Registry | 5 | ~16h |
| Contracts | 1 | ~3h |
| CLI/REPL | 5 | ~19h |
| Extensions | 4 | ~15h |
| Memory/RAG | 5 | ~18h |
| Streaming | 2 | ~9h |
| Sessions | 3 | ~9h |
| Export | 2 | ~5h |
| Agents | 2 | ~7h |
| Workflow | 2 | ~12h |
| Integration | 2 | ~12h |
| Tests/Docs | 4 | ~8h |

---

## Prerequisites Checklist

Antes de começar Phase 1, garantir:

- [ ] Python 3.10+ disponível
- [ ] Dependências instadas: `pip install -e .`
- [ ] Ambiente de teste configurado
- [ ] Repo sincronizado com upstream
- [ ] Branch criada: `feature/harness-evolution`

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

**Próximo passo:** Começar com TASK-001 (Tool Registry)