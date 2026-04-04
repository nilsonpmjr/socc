# PRD — Clean-Room Rewrite da Harness do SOCC

**Versão:** 1.1  
**Data:** 2026-04-03  
**Status:** Pronto para revisão  
**Fonte primária de referência:** `/home/nilsonpmjr/Documentos/claude-code-analysis`  
**Alvo da reimplementação:** `/home/nilsonpmjr/.gemini/antigravity/scratch/socc`  
**Relacionados:** `prd-claude-code-harness-parity.md`, `todo-clean-room-harness-rewrite.md`, `todo-claude-code-harness-parity.md`, `ui-spec-claude-code-like-tui.md`

---

## 1. Executive Summary

- **Problem Statement:** A harness atual do SOCC ainda é parcial, distribuída entre registries, startup, chat/TUI e flows legados. Isso gera doc drift, bootstrap inconsistente, superfície de inventário incompleta e um executor de subagentes sem contrato forte.
- **Proposed Solution:** Reescrever a harness do SOCC em Python como uma clean-room rewrite orientada pela superfície funcional, arquitetural e de fluxo observada em `/home/nilsonpmjr/Documentos/claude-code-analysis`, usando esse repositório como fonte de referência e o SOCC apenas como alvo de migração.
- **Success Criteria:**
  - `socc` expõe uma superfície de inventário e introspecção consistente com a fonte de referência: `commands`, `tools`, `route`, `show-command`, `show-tool`, `agents` e `session`.
  - `SOCRuntime` unifica metadata de snapshot e runtime vivo sem depender de registros hardcoded para introspecção.
  - `fork_subagent()` aplica política explícita de tools, registra `tool_calls`, `reasoning_trace`, `timeout`, `tool_error`, `llm_error` e fallback determinístico.
  - `pytest -q` e `python -m pytest -q` executam em checkout limpo sem `PYTHONPATH` manual.
  - `socc tui` e `chat --interactive` passam a depender do mesmo bootstrap determinístico da harness.
  - A evolução para session parity e remote/session bridge fica desenhada explicitamente, mesmo que a entrega continue faseada.

### Contexto da Reescrita

- Esta iniciativa não é uma “adaptação” do SOCC atual para parecer com o material de referência.
- Esta iniciativa é uma reimplementação clean-room em Python cuja fonte funcional é `/home/nilsonpmjr/Documentos/claude-code-analysis`.
- O SOCC legado é útil como repositório de integração, domínio SOC, tools e compatibilidade existente, mas não como source of truth de arquitetura quando houver conflito com a superfície-alvo.

### Decisão de Interpretação

- Quando houver conflito entre a organização do SOCC legado e a superfície/fluxo observados em `/home/nilsonpmjr/Documentos/claude-code-analysis`, a referência vence.
- Quando a referência expuser conceitos não entregues no SOCC atual, o plano deve modelar esses conceitos explicitamente como backlog ou fase futura, em vez de omiti-los.
- Quando a referência contiver implementação específica demais ou acoplada ao ecossistema TypeScript, a clean-room rewrite deve preservar comportamento, taxonomia e interfaces, não a forma literal do código.

---

## 2. Problem Framing

### Situação Atual no SOCC

- Inventário de tools, commands e agents ainda não é totalmente centralizado.
- Snapshots existem, mas parte deles não participa do runtime real.
- O bootstrap do runtime já foi melhorado, porém o desenho geral ainda não cobre toda a sessão/TUI/remote surface prevista.
- O executor de subagentes já avançou, mas ainda precisa convergir com uma visão maior de tasks, sessão, runtime events e UX operacional.
- A documentação histórica mistura fases antigas, wiring parcial e metas mais ambiciosas, o que dificulta saber qual documento realmente governa o trabalho.

### Situação Observada na Fonte de Referência

- A fonte em `/home/nilsonpmjr/Documentos/claude-code-analysis` expõe uma superfície muito mais ampla de:
  - entrypoints de CLI
  - registry de comandos
  - processamento de slash-commands
  - orchestration de tools
  - task lifecycle
  - state/session management
  - REPL/TUI
  - flows remotos e bridge/session APIs
- O valor principal da fonte não é “copiar módulos”, mas revelar a topologia do sistema e a forma correta de separar:
  - bootstrap
  - inventory
  - execution
  - session state
  - UI integration
  - remote/session bridge

### Por Que Fazer Agora

- Sem essa reestruturação, o SOCC segue com risco alto de:
  - doc drift
  - regressões de startup
  - divergência entre inventário e execução real
  - UX de TUI parcial
  - impossibilidade de evoluir com segurança para session resume e remote bridge

---

## 3. User Experience & Functionality

### User Personas

- **Analista SOC:** quer operar em terminal-first, com slash-commands, sessões e pivôs de investigação sem alternar entre modos desconectados.
- **Maintainer do runtime:** quer uma harness previsível, introspectável, testável e organizada em torno de uma fonte de verdade clara.
- **Engenheiro de segurança:** quer ferramentas e subagentes com contrato forte, risco explícito e capacidade de auditoria/debug.
- **Autor de integração/plugin:** quer saber o que é inventory metadata, o que é runtime vivo, e como conectar novas ferramentas sem quebrar a superfície principal.

### User Stories

**US-01 — Harness como entrypoint principal**  
As a maintainer, I want the runtime to boot around the harness so that command, tool, agent, and routing behavior come from one coherent source.

**Acceptance Criteria**

- `startup()` executa em ordem determinística.
- TUI, chat interativo e CLI de inventário usam a mesma camada de runtime.
- O runtime expõe contagens e listas consistentes para tools, commands e agents.

**US-02 — Inventário consultável e honesto**  
As an engineer, I want to inspect command/tool/agent inventory so that I can distinguish what is live, planned, and unavailable.

**Acceptance Criteria**

- `socc commands --limit N --query X`
- `socc tools --limit N --query X`
- `socc agents --limit N --query X`
- `socc route "<prompt>" --limit N`
- `socc show-command <name>`
- `socc show-tool <name>`
- Itens planejados aparecem como `planned`, nunca como executáveis.

**US-03 — Subagentes com contrato operacional real**  
As a senior analyst, I want subagents to run with explicit tool boundaries, lifecycle state, and tool traces so that I can trust and debug their outcomes.

**Acceptance Criteria**

- whitelist/blacklist aplicadas em toda execução
- `tool_calls` registrados
- `reasoning_trace` preservado
- `block=True` e `block=False` suportados
- timeout e falhas diferenciadas por tipo
- listagem de subagentes ativos e recentes disponível ao runtime

**US-04 — Session parity local**  
As an analyst, I want to list, inspect, resume, and continue sessions so that the TUI behaves like an operational workspace instead of a transient prompt box.

**Acceptance Criteria**

- `socc session list`
- `socc session show <id>`
- `socc session resume <id>` ou equivalente
- TUI expõe `/session`, `/new` e `/resume`
- estado da sessão atual é visível e útil

**US-05 — TUI/REPL alinhada à superfície da fonte**  
As an analyst, I want the TUI to expose slash-commands, session context, and runtime activity in a dense operational layout.

**Acceptance Criteria**

- autocomplete completo de slash-commands
- transcript, composer, sidebar e footer operacionais
- eventos de phase/tool execution no transcript quando existirem
- bootstrap local sem depender de plugins remotos ativos

### Non-Goals

- Não copiar literalmente o código da fonte de referência.
- Não perseguir compatibilidade 1:1 com o ecossistema TypeScript.
- Não substituir a interface web do SOCC nesta fase.
- Não aumentar artificialmente o número de tools para espelhar a fonte.
- Não usar o SOCC legado como fonte primária de arquitetura quando ele divergir da superfície-alvo.

### Decisões Confirmadas

- `/home/nilsonpmjr/Documentos/claude-code-analysis` é a fonte primária.
- O SOCC é o alvo da reimplementação clean-room.
- A entrega é faseada: inventory/boot/subagents primeiro, session/TUI depois, bridge remoto por último.

---

## 4. Reference Interpretation

### Mapeamento de Superfícies Observadas na Fonte

As seguintes áreas em `/home/nilsonpmjr/Documentos/claude-code-analysis` são tratadas como referência de desenho:

- **CLI entrypoints**
  - `src/entrypoints/cli.tsx`
  - `src/main.tsx`
- **Command surface**
  - `src/commands.ts`
  - `src/utils/processUserInput/processUserInput.ts`
  - `src/utils/processUserInput/processSlashCommand.tsx`
- **Runtime / session loop**
  - `src/query.ts`
  - `src/screens/REPL.tsx`
  - `src/state/AppStateStore.ts`
- **Tools and orchestration**
  - `src/tools.ts`
  - `src/services/tools/toolExecution.ts`
  - `src/services/tools/toolOrchestration.ts`
- **Tasks**
  - `src/Task.ts`
  - `src/tasks/types.ts`
  - `src/utils/task/framework.ts`
- **Remote/session bridge**
  - `src/remote/RemoteSessionManager.ts`
  - `src/remote/SessionsWebSocket.ts`
  - `src/entrypoints/mcp.ts`

### Interpretação Correta da Fonte

- A fonte define a superfície, não o texto da implementação.
- Conceitos como command registry, task lifecycle, tool orchestration, session state e remote bridge devem ser traduzidos para Python idiomático.
- A clean-room rewrite deve preservar:
  - comportamento observável
  - fronteiras de responsabilidade
  - taxonomia dos recursos
  - forma de introspecção e execução
- A clean-room rewrite não deve preservar:
  - nomes internos desnecessários
  - acoplamentos específicos de build/JSX/Ink
  - peculiaridades do runtime TypeScript que não agreguem valor ao SOCC

---

## 5. AI System Requirements

### Tool Requirements

- `tools_registry` permanece como fonte viva de execução.
- Snapshots JSON permanecem como catálogo de referência para itens planejados.
- Cada tool precisa expor:
  - nome
  - descrição
  - categoria
  - risco
  - origem
  - disponibilidade real
- Tools destrutivas ou sensíveis devem continuar cobertas por guardas de segurança existentes.

### Agent Requirements

- Agents precisam expor metadata suficiente para:
  - specialty
  - tool policy
  - timeout
  - max steps
  - source (`snapshot`, `live`, `live+snapshot`)
- O runtime precisa distinguir agent inventory de agent execution state.

### Session Requirements

- Sessões precisam ser endereçáveis por CLI e TUI.
- O modelo de sessão deve acomodar:
  - listagem
  - inspeção
  - retomada local
  - futura extensão para modo remoto

### Evaluation Strategy

- Testes unitários para merge de inventário.
- Testes unitários para ranking de roteamento.
- Testes de subprocesso para CLI de inventário.
- Testes de subagentes cobrindo policy, fallback e lifecycle.
- Smoke tests para `socc tui` e `chat --interactive`.
- Verificações para `pytest -q` e `python -m pytest -q`.

---

## 6. Technical Specifications

### Architecture Overview

Fluxo alvo:

```text
socc CLI / TUI
  -> startup()
    -> load environment
    -> import live tools
    -> register built-in commands
    -> register built-in agents
    -> register plugins
    -> bootstrap SOCRuntime
    -> expose merged inventory + runtime state
  -> command surface
    -> inventory commands
    -> slash-commands operacionais
    -> session commands
  -> routing surface
    -> route_prompt()
    -> dispatch_command()
    -> invoke_tool()
    -> fork_subagent()
  -> session surface
    -> list/show/resume
    -> TUI state
    -> persisted chat history
  -> future remote surface
    -> session bridge
    -> remote attach/resume
```

### Runtime Boundaries

- `socc/core/harness/runtime.py`
  - merge de snapshot + live registry
  - listagens e busca
  - roteamento
  - detalhamento de inventory records
- `socc/core/harness/models.py`
  - contratos de inventory, command, agent e agent result
- `socc/cli/startup.py`
  - bootstrap determinístico
- `socc/cli/main.py`
  - superfície externa de CLI
- `socc/agents/fork.py`
  - execução contratual de subagentes
- `socc/core/storage.py`
  - persistência de sessões exposta ao runtime

### Current Implementation Status

- Já entregue:
  - merge de inventory live/snapshot
  - CLI de inventário
  - bootstrap determinístico para `tui` e chat interativo
  - `fork_subagent()` com `tool_calls`, `reasoning_trace`, `error_kind`
  - correção de empacotamento para pytest sem `PYTHONPATH`
- Ainda pendente:
  - `session resume`
  - session-aware TUI parity completa
  - exibição de runtime/tool events no transcript
  - modelagem de task lifecycle mais próxima da fonte
  - `session bridge` / remote parity
- Entregue nesta iteração:
  - `session list/show/resume`
  - TUI session-aware com `/resume` e resumo operacional
  - runtime events (`phase` / `tool_call` / `tool_result`) no transcript
  - modelagem mínima de `task state`
  - contrato inicial de `session bridge`

### Integration Points

- `socc/core/harness/runtime.py`
- `socc/core/harness/models.py`
- `socc/core/harness/commands.py`
- `socc/core/tools_registry.py`
- `socc/agents/fork.py`
- `socc/cli/startup.py`
- `socc/cli/main.py`
- `socc/cli/chat_interactive.py`
- `socc/core/storage.py`
- `socc/core/chat.py`
- `socc/core/engine.py`
- `soc_copilot/modules/chat_service.py`

### Packaging and Build Expectations

- `socc` deve continuar importável por:
  - `pytest -q`
  - `python -m pytest -q`
  - `python -m socc.cli.main ...`
- Mudanças não devem introduzir dependências novas sem pedido explícito.

### Security & Privacy

- Nenhuma mudança pode enfraquecer guardas de shell/file tools.
- Inventory records precisam distinguir claramente metadata e disponibilidade real.
- Subagentes não podem receber tools fora da policy resolvida.
- Sessões e traces não devem induzir execução insegura de itens apenas planejados.

---

## 7. Verification & Acceptance

### Verificação Mínima por Fase

- **Inventory phase**
  - listagem de commands/tools/agents
  - `show-command` e `show-tool`
  - `route`
- **Subagent phase**
  - whitelist/blacklist
  - tool traces
  - timeout
  - fallback
- **Packaging phase**
  - `pytest -q`
  - `python -m pytest -q`
- **Session phase**
  - `session list`
  - `session show`
  - `session resume`
- **TUI phase**
  - slash autocomplete
  - runtime/session state visível
  - event rendering

### Definição de Concluído

Uma fase só é considerada concluída quando:

- o comportamento alvo está implementado
- a verificação correspondente foi executada
- não há regressão conhecida sem registro explícito
- PRD e TODO refletem o estado real

---

## 8. Risks & Roadmap

### Technical Risks

- **Doc drift:** documentos antigos podem contradizer o estado atual.
- **False parity:** snapshots podem sugerir cobertura além do executável real.
- **Bootstrap regressions:** centralizar o runtime pode quebrar caminhos legados.
- **Session gaps:** sessão parcial pode gerar UX inconsistente.
- **Source inversion:** interpretar o SOCC como fonte e a referência como derivado reintroduz erro de direção no projeto.
- **Scope creep:** tentar entregar remote parity cedo demais pode atrasar session/TUI local.

### Phased Rollout

**MVP — Harness Core Rewrite**

- inventário unificado
- CLI de introspecção
- bootstrap determinístico
- packaging parity

**v1.1 — Execution Rewrite**

- executor de subagentes robusto
- traces e lifecycle
- integração com runtime principal

**v1.2 — Session Rewrite**

- `session list/show/resume`
- alinhamento de chat/TUI com sessão persistida
- preparação para task/state model mais rico

**v1.3 — TUI Rewrite**

- autocomplete completo
- runtime events no transcript
- layout operacional mais próximo da fonte

**v2.0 — Remote Bridge Rewrite**

- `session bridge`
- attach/resume remoto
- contratos explícitos de transporte e estado remoto

### Open Decisions

- Critério principal de sucesso ainda precisa ser confirmado entre:
  - paridade de comportamento
  - paridade de CLI/TUI
  - paridade arquitetural ampliada
- Restrição principal ainda precisa ser confirmada entre:
  - sem novas dependências
  - sem quebrar CLI atual
  - foco apenas em core harness no curto prazo
