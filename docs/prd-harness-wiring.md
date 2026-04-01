# PRD — Harness Wiring: Conectar o Motor ao Cockpit

**Versão:** 1.0  
**Data:** 2026-04-01  
**Status:** Aprovado para implementação  
**Relacionado:** `prd-harness-evolution.md`, `todo-claude-code-integration.md`

---

## 1. Executive Summary

### Problem Statement
O SOCC possui um harness completo (`SOCRuntime`, `CommandRegistry`, `PluginSystem`, agentes built-in) implementado e testado em isolamento, mas **nenhum ponto de entrada o usa**. O `chat_interactive.py` não conhece o harness; o `main.py` não faz bootstrap do runtime; os comandos `/case` e `/hunt` chegam ao TUI mas caem em `"Comando desconhecido"`.

### Proposed Solution
Quatro cirurgias pontuais que conectam as camadas já prontas sem reescrever nada:
1. **Startup hook** — `RUNTIME.bootstrap()` + agentes + plugins na inicialização
2. **Dispatch bridge** — roteamento de `/commands` no TUI via `COMMAND_REGISTRY`
3. **LLM bridge no `fork_subagent`** — substituir o stub por chamada real ao `llm_gateway`
4. **Limpeza de duplicatas** — remover `socc/commands/` (órfão), manter `socc/cli/commands/`

### Success Criteria
| Critério | Medida |
|---|---|
| `/case create Test` no TUI cria um case real | `~/.socc/cases/*.json` existe |
| `/hunt start "lateral movement"` inicia uma sessão | `~/.socc/hunts/*.json` existe |
| `/tools` lista todas as tools registradas | ≥ 5 tools na saída |
| `/agents` lista os 3 agentes built-in | soc_analyst, ir_agent, threat_hunt |
| `fork_subagent` retorna findings via LLM real | `result.ok=True`, `findings` não vazio |
| Plugins carregados quando env vars presentes | `vt_lookup_hash` em `list_tools()` |

---

## 2. User Experience & Functionality

### User Personas
- **Analista SOC** — usa o TUI diariamente para triagem; quer `/case` e `/hunt` funcionando
- **Analista Sênior** — orquestra subagentes; quer `fork_subagent` com resultado real do LLM
- **Admin** — configura integrações; quer plugins carregados automaticamente se a env var existe

### User Stories

**US-01 — Slash-commands no TUI**
> Como analista, quero digitar `/case create Phishing-2026-04` no chat e ter o case criado, para não precisar de outra ferramenta para gestão de incidentes.

**AC:**
- `/case`, `/hunt`, `/tools`, `/agents`, `/help` roteados para o `COMMAND_REGISTRY`
- Resposta exibida no histórico do TUI em ≤ 200ms (operações locais)
- Comandos desconhecidos mostram `/help` resumido ao invés de mensagem genérica
- Tab-completion no TUI lista os comandos disponíveis

**US-02 — Bootstrap automático**
> Como analista, quero que ao abrir o chat os agentes e ferramentas estejam prontos, sem configuração manual.

**AC:**
- `RUNTIME.bootstrap()` chamado uma vez no `socc chat`
- Agentes `soc_analyst`, `ir_agent`, `threat_hunt` registrados no RUNTIME
- Plugins com env vars presentes registrados automaticamente
- Plugins sem env vars ignorados silenciosamente (sem crash, sem warnings ruidosos)

**US-03 — Subagente com resultado real**
> Como analista sênior, quero invocar um subagente de threat intel que use o LLM para sintetizar os findings, não um stub hardcoded.

**AC:**
- `fork_subagent(config)` chama o `llm_gateway` com o prompt do agente
- Resultado inclui `findings` derivados da resposta do LLM
- Timeout e fallback determinístico quando LLM indisponível
- `block=False` retorna handle imediatamente; `block=True` aguarda

### Non-Goals
- **Não** vamos reimplementar o TUI (apenas conectar dispatch)
- **Não** vamos adicionar novas tools ou agentes nesta fase
- **Não** vamos mudar a arquitetura do `llm_gateway` ou `chat_service`
- **Não** vamos implementar `/report` ou `/pivot` (fora do escopo)

---

## 3. Technical Specifications

### 3.1 Componentes afetados

```
socc/cli/main.py              ← adicionar startup() com bootstrap
socc/cli/chat_interactive.py  ← bridge _handle_command → COMMAND_REGISTRY  
socc/agents/fork.py           ← substituir stub por chamada llm_gateway
socc/agents/__init__.py       ← expor register_builtin_agents()
socc/commands/               ← DELETAR (duplicata órfã de socc/cli/commands/)
```

### 3.2 Fluxo de startup

```
socc chat
  └─ main.py: startup()
       ├─ load_environment()
       ├─ RUNTIME.bootstrap()          # carrega agents snapshot
       ├─ register_builtin_commands()  # /case /hunt /tools /agents /help
       ├─ register_builtin_agents()    # SOC_ANALYST_SPEC, IR_AGENT_SPEC, THREAT_HUNT_SPEC
       └─ register_all_plugins(skip_unconfigured=True)  # VT/MISP/OpenCTI se env vars ok
```

### 3.3 Dispatch bridge no TUI

```python
# chat_interactive.py — _handle_command() ao final do bloco de ifs:
result = COMMAND_REGISTRY.dispatch(cmd)
if result.ok:
    self.history.append_line(result.output)
else:
    self.history.append_line(f"⚠ {result.error}")
```

### 3.4 fork_subagent com LLM real

```python
# socc/agents/fork.py — _run_subagent():
# 1. build prompt (já existe)
# 2. chamar llm_gateway via chat_service.generate_chat_reply()
# 3. parsear findings do texto retornado
# 4. fallback determinístico (IOC extraction) se LLM falhar
```

O `fork_subagent` usa o mesmo gateway que o chat — sem novo código de chamada HTTP.

### 3.5 Remoção de socc/commands/ (órfã)

`socc/commands/case.py` e `socc/commands/hunt.py` foram criados antes de `socc/cli/commands/`. A versão em `socc/cli/commands/` é a correta (tem `register()`). Remover a duplicata para evitar confusão.

---

## 4. Security & Constraints

- `register_all_plugins(skip_unconfigured=True)` — plugins sem API key são ignorados, nunca crasham o startup
- `fork_subagent` herda o `inference_guard` do `llm_gateway` — não bypassa CPU guard nem semáforo de concorrência
- Comandos no TUI passam pelo `COMMAND_REGISTRY.dispatch()` que valida permissões via `SOCCommand.permissions`

---

## 5. Risks & Rollout

### Riscos técnicos
| Risco | Mitigação |
|---|---|
| `bootstrap()` lento (plugins demoram) | Executar em thread separada, TUI abre imediatamente |
| `fork_subagent` com LLM pode demorar muito | Timeout configurável, fallback para resultado parcial |
| Quebra de compatibilidade ao deletar `socc/commands/` | Grep no codebase antes de deletar — confirmado sem imports externos |

### Fases
```
MVP (esta sprint):  US-01 + US-02  — dispatch + startup
v1.1 (próxima):     US-03          — fork_subagent com LLM real
```
