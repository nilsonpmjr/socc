# TODO — Harness Wiring

**PRD:** `prd-harness-wiring.md`  
**Data:** 2026-04-01  
**Sprint MVP:** TASK-HW-001 a TASK-HW-004  
**Sprint v1.1:** TASK-HW-005

---

## Status Legend
| Símbolo | Significado |
|---|---|
| ⬜ | TODO |
| 🔄 | WIP |
| ✅ | DONE |
| ❌ | BLOCKED |

---

## Sprint MVP — Dispatch + Startup

### TASK-HW-001: Remover `socc/commands/` órfã
**Prioridade:** P0 | **Estimativa:** 15min | **Status:** ✅ DONE

**Por quê primeiro:** evitar confusão entre a versão correta (`socc/cli/commands/`) e a duplicata sem `register()`.

**Acceptance Criteria:**
- [ ] Confirmar que nenhum módulo importa de `socc.commands` (grep)
- [ ] Deletar `socc/commands/case.py`, `socc/commands/hunt.py`, `socc/commands/__init__.py`
- [ ] `python -m pytest` continua 160 passed

**Arquivos:**
```
DELETE socc/commands/case.py
DELETE socc/commands/hunt.py
DELETE socc/commands/__init__.py
```

---

### TASK-HW-002: `register_builtin_agents()` no `socc/agents/__init__.py`
**Prioridade:** P0 | **Estimativa:** 30min | **Status:** ✅ DONE

**Acceptance Criteria:**
- [ ] `socc/agents/__init__.py` expõe `register_builtin_agents()`
- [ ] Função registra `SOC_ANALYST_SPEC`, `IR_AGENT_SPEC`, `THREAT_HUNT_SPEC` no `RUNTIME`
- [ ] Idempotente: segunda chamada não levanta `ValueError`
- [ ] Teste unitário: `RUNTIME.list_agents()` retorna os 3 após chamada

**Implementação:**
```python
# socc/agents/__init__.py
from socc.core.harness.runtime import RUNTIME
from socc.agents.built_in.soc_analyst import SOC_ANALYST_SPEC
from socc.agents.built_in.ir_agent import IR_AGENT_SPEC
from socc.agents.built_in.threat_hunt import THREAT_HUNT_SPEC

def register_builtin_agents() -> None:
    for spec in (SOC_ANALYST_SPEC, IR_AGENT_SPEC, THREAT_HUNT_SPEC):
        try:
            RUNTIME.register_agent(spec)
        except ValueError:
            pass  # já registrado
```

---

### TASK-HW-003: `startup()` no `socc/cli/main.py`
**Prioridade:** P0 | **Estimativa:** 45min | **Status:** ✅ DONE

**Acceptance Criteria:**
- [ ] Função `startup()` criada em `main.py` (ou módulo `socc/cli/startup.py`)
- [ ] Chamada no comando `socc chat` antes de iniciar o TUI
- [ ] Executa em thread separada — TUI abre imediatamente, não bloqueia
- [ ] Log de startup visível com `socc chat --verbose`
- [ ] Ordem garantida: `load_environment` → `bootstrap` → `commands` → `agents` → `plugins`

**Implementação:**
```python
# socc/cli/startup.py
import threading, logging
_logger = logging.getLogger(__name__)

def startup(*, block: bool = False) -> threading.Thread:
    def _run():
        from socc.utils.config_loader import load_environment
        load_environment()
        from socc.core.harness.runtime import RUNTIME
        RUNTIME.bootstrap()
        from socc.cli.commands import register_builtin_commands
        register_builtin_commands()
        from socc.agents import register_builtin_agents
        register_builtin_agents()
        from socc.plugins import register_all_plugins
        register_all_plugins(skip_unconfigured=True)
        _logger.info("SOCC startup complete: %s", repr(RUNTIME))
    t = threading.Thread(target=_run, daemon=True, name="socc-startup")
    t.start()
    if block:
        t.join()
    return t
```

**Arquivo a editar:** `socc/cli/main.py` — no handler do subcomando `chat`:
```python
from socc.cli.startup import startup
startup()   # non-blocking — TUI sobe imediatamente
```

---

### TASK-HW-004: Dispatch bridge no `chat_interactive.py`
**Prioridade:** P0 | **Estimativa:** 1h | **Status:** ✅ DONE

**Acceptance Criteria:**
- [ ] `_handle_command()` roteia para `COMMAND_REGISTRY.dispatch()` ao final do bloco de ifs
- [ ] Resultado `ok=True` → exibe `result.output` no histórico
- [ ] Resultado `ok=False` → exibe `⚠ result.error` em amarelo
- [ ] Tab-completion do TUI lista nomes de comandos do `COMMAND_REGISTRY`
- [ ] Comandos built-ins (`/exit`, `/clear`, `/mode`, etc.) mantidos como estão — não delegados
- [ ] Teste manual: `/case create Teste` cria `~/.socc/cases/*.json`
- [ ] Teste manual: `/tools` lista tools do registry
- [ ] Teste manual: `/agents` lista 3 agentes

**Implementação — ao final de `_handle_command()`:**
```python
# Após todos os ifs de comandos built-in:
from socc.core.harness.commands import COMMAND_REGISTRY
result = COMMAND_REGISTRY.dispatch(cmd)
if result.ok:
    for line in result.output.splitlines():
        self.history.append_line(f"  {line}")
else:
    self.history.append_line(_yellow(f"  ⚠  {result.error}"))
self.history.append_line("")
```

**Tab-completion — na construção do `WordCompleter`:**
```python
from socc.core.harness.commands import COMMAND_REGISTRY
harness_cmds = [f"/{c.name}" for c in COMMAND_REGISTRY.list()]
# Combinar com COMMANDS existente
all_cmds = list(set(COMMANDS + harness_cmds))
```

---

## Sprint v1.1 — fork_subagent com LLM real

### TASK-HW-005: LLM bridge em `fork_subagent`
**Prioridade:** P1 | **Estimativa:** 3h | **Status:** ✅ DONE

**Acceptance Criteria:**
- [ ] `_run_subagent()` chama LLM real via `socc.core.chat.generate_chat_reply()`
- [ ] Prompt construído com `_build_prompt()` existente (sem mudança)
- [ ] Findings extraídos do texto de resposta via heurística de bullet points
- [ ] Fallback determinístico (extração de IOCs) quando LLM retorna erro
- [ ] Timeout: respeita `config.timeout_seconds`
- [ ] Teste: `fork_subagent(SubagentConfig(name="test", specialty="general", task="analise 1.2.3.4", context={"text":"IP malicioso: 1.2.3.4"}))` retorna `result.ok=True` com findings

**Implementação — substituir o bloco placeholder em `_run_subagent()`:**
```python
# Etapa real: chamar LLM
from socc.core.chat import generate_chat_reply
llm_result = generate_chat_reply(
    message=prompt,
    session_id=f"subagent-{handle.id}",
    response_mode="balanced",
)
llm_content = llm_result.get("content", "")

# Extrair findings de bullet points na resposta
import re
findings = re.findall(r"^[\s]*[-*•]\s+(.+)$", llm_content, re.MULTILINE)
if not findings:
    findings = [llm_content[:200]] if llm_content else []

reasoning.append(f"[llm] {len(findings)} findings extraídos")
```

---

## Arquivos por task

| Task | Arquivo principal | Ação |
|---|---|---|
| HW-001 | `socc/commands/` | DELETE |
| HW-002 | `socc/agents/__init__.py` | EDIT |
| HW-003 | `socc/cli/startup.py` | CREATE + edit `main.py` |
| HW-004 | `socc/cli/chat_interactive.py` | EDIT |
| HW-005 | `socc/agents/fork.py` | EDIT |

## Verificação final (pós HW-001..004)

```bash
# Smoke test manual
socc chat
# digitar no TUI:
# /tools        → lista tools
# /agents       → lista 3 agentes
# /case create Phishing-Test
# /case list
# /hunt start "lateral movement hypothesis"
# /hunt status
# Ctrl+D para sair

# Verificar persistência
ls ~/.socc/cases/
ls ~/.socc/hunts/

# Testes automatizados
python -m pytest  # 160+ passed
```
