# PRD — SOCC Claude-Code Harness Parity

**Versao:** 1.0  
**Data:** 2026-04-01  
**Status:** Draft para implementacao  
**Escopo:** paridade funcional de harness com o repositorio local `claude-code` e incorporacao da superficie TUI/REPL referenciada por ele  
**Relacionados:** `prd-harness-evolution.md`, `prd-harness-wiring.md`, `todo-claude-code-integration.md`, `todo-harness-wiring.md`, `ui-spec-claude-code-like-tui.md`

---

## 1. Executive Summary

- **Problem Statement:** O SOCC ja possui pecas de harness, mas elas nao sao o centro do runtime. O roteamento, o inventario de commands/tools, o fork de subagentes e a TUI ainda operam de forma parcial ou desacoplada do modelo aplicado no `claude-code`.
- **Proposed Solution:** Reestruturar o SOCC para que o harness seja a camada principal de execucao, com inventario carregado por snapshot, roteamento consistente, subagentes com isolamento real, e uma TUI/REPL orientada a sessao e slash-commands inspirada na superficie que o `claude-code` referencia.
- **Success Criteria:**
  - `socc` expor comandos de inventario equivalentes a `commands`, `tools`, `route`, `show-command`, `show-tool`, `agents` e `session`.
  - `SOCRuntime` carregar e consultar snapshots de agentes, comandos e tools sem depender de registracao hardcoded para introspeccao.
- `fork_subagent` aplicar whitelist/blacklist de ferramentas e registrar `tool_calls`, `reasoning_trace`, timeout e fallback.
- A TUI iniciar em menos de 1 segundo em ambiente local sem plugins remotos ativos.
- O fluxo `python -m pytest -q` e um smoke test de CLI/TUI passarem sem depender de import hacks ou `PYTHONPATH` manual.
- O desenho de sessao contemplar retomada local e um futuro modo remoto com `session bridge` e `remote bridge` explicitamente modelados.
- A TUI adotar uma linguagem visual densa e operacional alinhada ao spec em `ui-spec-claude-code-like-tui.md`.

---

## 2. User Experience & Functionality

### User Personas

- **Analista SOC:** quer operar casos e hunts numa interface terminal-first sem sair do fluxo de investigacao.
- **Engenheiro de seguranca:** quer um harness previsivel, introspectavel e extensivel por snapshots, plugins e ferramentas.
- **Maintainer do runtime:** quer reduzir divergencia entre docs e codigo, e provar paridade por testes e comandos de inspeccao.

### User Stories

**US-01 — Harness como entrypoint principal**  
As a maintainer, I want the runtime to boot around the harness so that tool, command, agent, and routing behavior all come from one source of truth.

**Acceptance Criteria**

- `startup()` inicializa snapshots, registries, plugins e politicas do runtime numa ordem deterministica.
- O chat CLI e o TUI usam o harness para slash-commands, introspeccao e roteamento.
- O runtime expoe contagens e listas de commands, tools e agents ativos.

**US-02 — Inventario consultavel estilo claude-code**  
As an engineer, I want to inspect commands and tools through CLI inventory commands so that I can understand and validate the harness surface quickly.

**Acceptance Criteria**

- `socc commands --limit N --query X` lista comandos do snapshot e do runtime.
- `socc tools --limit N --query X` lista tools do snapshot e do runtime.
- `socc route "<prompt>"` retorna matches ordenados por score e kind.
- `socc show-command <name>` e `socc show-tool <name>` mostram metadados detalhados.

**US-03 — Subagentes com contrato real**  
As a senior analyst, I want forked subagents to run with explicit tool boundaries and lifecycle tracking so that results are trustworthy and debuggable.

**Acceptance Criteria**

- `fork_subagent` recusa tools fora da whitelist e respeita blacklist.
- O loop do subagente registra `tool_calls`, estado, timeout, fallback e conclusao.
- `block=False` retorna handle imediatamente e `block=True` aguarda ate estado terminal.
- O runtime consegue listar subagentes ativos e concluídos recentes.

**US-04 — TUI/REPL de investigacao**  
As an analyst, I want a terminal UI with session awareness and slash-commands so that I can investigate, pivot, and resume work without alternar entre modos desconectados.

**Acceptance Criteria**

- A TUI mostra historico, input, sessao, backend/modelo e estado de processamento.
- A TUI oferece autocomplete de slash-commands e comandos de sessao.
- `/session`, `/new`, `/resume`, `/agents`, `/tools`, `/case`, `/hunt` funcionam sem sair da TUI.
- A TUI exibe eventos de fase e chamadas de ferramenta quando presentes.
- A TUI adota top chrome, transcript pane, sidebar compacta, composer destacado e footer operacional.
- A TUI fica visualmente mais proxima da densidade e hierarquia percebidas no Claude Code do que da interface atual do SOCC.

### Non-Goals

- Nao perseguir copia literal do Claude Code nem compatibilidade 1:1 com arquivos TypeScript arquivados.
- Nao migrar a interface web para TUI nem remover o frontend web existente nesta fase.
- Nao aumentar arbitrariamente o numero de tools para imitar os 184 itens do repo de referencia sem necessidade funcional no dominio SOC.
- Nao introduzir novas dependencias pesadas de UI terminal sem justificar manutencao, portabilidade e testes.

### Decisoes Confirmadas

- O alvo de TUI deve contemplar terminal local e tambem um futuro modo remoto orientado a `session bridge`.
- A paridade desejada deve cobrir o harness, a experiencia de REPL/TUI, a superficie de sessao e a `remote bridge` referenciada no snapshot do `claude-code`.

---

## 3. AI System Requirements

### Tool Requirements

- O runtime deve distinguir entre `inventory metadata` e `live registry`.
- Cada tool precisa expor nome, descricao, categoria, risco, schema de parametros e origem.
- Tools destrutivas ou potencialmente sensiveis precisam continuar passando pelas politicas de seguranca de `bash/security`, `permissions` e `sandbox`.
- O harness deve conseguir listar tanto tools vivas quanto tools conhecidas por snapshot ainda nao implementadas, com status claro.

### Evaluation Strategy

- Benchmark de roteamento com prompts curtos e compostos, validando ranking de `tool`, `command` e `agent`.
- Testes de subagente cobrindo whitelist, blacklist, timeout, fallback, chamada de tool e chamada de LLM.
- Smoke tests da TUI/CLI cobrindo startup, slash-commands, historico de sessao e introspeccao.
- Teste de empacotamento para garantir que `pytest` e `python -m pytest` funcionem no checkout sem ajustes manuais.

---

## 4. Technical Specifications

### Architecture Overview

O novo fluxo alvo deve ser:

```text
socc CLI / TUI
  -> startup()
    -> carregar ambiente
    -> carregar snapshots de commands/tools/agents
    -> registrar runtime live e plugins
    -> publicar estado do harness
  -> command surface
    -> inventory commands
    -> slash-commands operacionais
  -> routing surface
    -> route_prompt()
    -> dispatch_command()
    -> invoke_tool()
    -> fork_subagent()
  -> chat/analysis surface
    -> engine/chat usando harness para introspeccao e eventos
```

### Integration Points

- `socc/core/harness/runtime.py`
- `socc/core/harness/commands.py`
- `socc/core/tools_registry.py`
- `socc/agents/fork.py`
- `socc/cli/main.py`
- `socc/cli/chat_interactive.py`
- `socc/cli/startup.py`
- `socc/core/chat.py`
- `soc_copilot/modules/chat_service.py`

### Claude-Code Reference Surface

O repositorio local `/home/nilsonpmjr/claude-code` deve ser usado como referencia de padrao, com o seguinte recorte:

- **Implementado no port Python:** inventario de commands/tools e roteamento em `src/main.py`, `src/runtime.py`, `src/tools.py`.
- **Mencionado, mas nao implementado de forma interativa no port Python:** `src/replLauncher.py` deixa explicito que o REPL ainda nao e interativo.
- **Superficie de TUI/REPL referenciada no snapshot do arquivo exposto:** `screens/REPL.tsx`, `ink.ts`, `interactiveHelpers.tsx`, `bridge/replBridge.ts`, `commands/session/session.tsx`.
- **Superficie remota/sessao referenciada no snapshot do arquivo exposto:** `remote/RemoteSessionManager.ts`, `remote/SessionsWebSocket.ts`, `bridge/codeSessionApi.ts`, `bridge/createSession.ts`, `bridge/initReplBridge.ts`, `bridge/replBridgeHandle.ts`.

Decisao para o SOCC:

- A meta de TUI nao deve copiar o `claude-code` Python port atual, porque ele ainda nao entrega uma TUI interativa real.
- A meta deve usar o `claude-code` como referencia de superficie e taxonomia de recursos, e o SOCC atual como base de implementacao do terminal.
- A superficie de sessao e bridge remoto entra no escopo arquitetural, mesmo que sua entrega seja faseada depois da paridade local.

### Security & Privacy

- Nenhuma mudanca deve enfraquecer guardas existentes de shell, logs ou auditoria de prompt.
- Subagentes nao podem ganhar acesso implicito a tools fora do contrato declarado.
- Inventario de tools e commands precisa diferenciar metadados de disponibilidade real para nao induzir execucao insegura.

---

## 5. Risks & Roadmap

### Technical Risks

- **Doc drift:** o repositorio ja tem docs marcadas como `DONE` que nao refletem a realidade atual.
- **Falsa paridade:** snapshots podem dar impressao de cobertura maior do que a superficie executavel real.
- **Regressoes de startup:** centralizar o harness pode quebrar fluxo legado de chat se feito sem smoke tests.
- **TUI parcial:** adicionar comandos de sessao e introspeccao sem um modelo consistente de sessao pode gerar UX inconsistente.

### Phased Rollout

**MVP — Harness Core Parity**

- tornar snapshots de commands/tools/agents parte do runtime
- expor comandos de inventario na CLI
- corrigir empacotamento e testes de import
- alinhar docs com estado real

**v1.1 — Execution Parity**

- reimplementar `fork_subagent` com contrato real de ferramentas
- integrar roteamento do harness ao fluxo de chat/analysis
- expor listagem de subagentes, status e traces

**v1.2 — TUI/Session Parity**

- consolidar TUI como REPL principal
- adicionar comandos de sessao e resume
- exibir eventos de fase, tool call e status do runtime na interface
- aplicar a UI spec `ui-spec-claude-code-like-tui.md`

**v2.0 — Remote Bridge Parity**

- introduzir `session bridge` para modo remoto
- definir contrato de `remote bridge`, ciclo de sessao remota e transporte
- avaliar `RemoteSessionManager`, websocket de sessoes e `repl bridge handle`
- avaliar plugins/session memory mais proximos da taxonomia do snapshot de referencia
