# TODO: Claude Code Port Integration

> **Parent PRD:** `prd-harness-evolution.md`
> **Análise:** `claude-code-port-analysis.md`
> **Fonte:** `/home/nilsonpmjr/claude-code/` (instructkr/claude-code)

---

## Sprint 1: Foundation (Week 1-2)

### TASK-CC-001: Setup Harness Base Structure
**Priority:** P0 | **Estimate:** 4h | **Status:** ✅ DONE

**Acceptance Criteria:**
- [ ] Criar `socc/core/harness/` directory
- [ ] Copiar `models.py` do port como base
- [ ] Adaptar `Subsystem`, `PortingModule`, `PortingBacklog` para contexto SOC
- [ ] Testes unitários passando

**Implementation Notes:**
```python
# socc/core/harness/models.py
@dataclass(frozen=True)
class SOCTool:
    name: str
    category: ToolCategory  # IOC, MALWARE, THREAT_INTEL, etc
    risk_level: RiskLevel
    handler: Callable
    
@dataclass(frozen=True)
class SOCAgent:
    name: str
    specialty: str  # "ir", "threat_intel", "malware", "hunt"
    tools: list[str]
    prompt_template: str
```

---

### TASK-CC-002: Port Runtime Core
**Priority:** P0 | **Estimate:** 6h | **Status:** ✅ DONE

**Acceptance Criteria:**
- [ ] Criar `socc/core/harness/runtime.py`
- [ ] Implementar `SOCRuntime` class baseado em `PortRuntime`
- [ ] Adicionar `route_prompt()` para SOC-specific routing
- [ ] Integrar com `tools_registry.py` existente

**Implementation Notes:**
```python
# socc/core/harness/runtime.py
class SOCRuntime:
    def __init__(self):
        self.tool_registry = TOOL_REGISTRY
        self.agent_registry = {}
        self.command_registry = {}
    
    def route_prompt(self, prompt: str) -> RoutedMatch:
        """Route prompts to appropriate tools/agents."""
        # Similar to PortRuntime.route_prompt but SOC-aware
        pass
    
    def invoke_tool(self, name: str, args: dict) -> ToolResult:
        """Invoke a tool with validation."""
        pass
```

---

### TASK-CC-003: SOC Tools Snapshot
**Priority:** P1 | **Estimate:** 3h | **Status:** ✅ DONE

**Acceptance Criteria:**
- [ ] Criar `socc/core/harness/reference_data/socc_tools_snapshot.json`
- [ ] Incluir tools existentes: `extract_iocs`, `defang`, `decode_base64`
- [ ] Adicionar placeholders para tools planejadas
- [ ] JSON Schema validado

**Reference Data Format:**
```json
[
  {
    "name": "extract_iocs",
    "source_hint": "socc/core/tools.py",
    "responsibility": "Extract IOCs (IPs, domains, hashes, URLs)",
    "category": "ioc",
    "risk_level": "low"
  },
  {
    "name": "defang",
    "source_hint": "socc/core/tools.py",
    "responsibility": "Defang URLs and indicators",
    "category": "utility",
    "risk_level": "low"
  }
]
```

---

### TASK-CC-004: SOC Commands Registry
**Priority:** P1 | **Estimate:** 4h | **Status:** ✅ DONE

**Acceptance Criteria:**
- [ ] Criar `socc/core/harness/commands.py`
- [ ] Implementar `register_command()`, `get_command()`, `list_commands()`
- [ ] Criar `socc_commands_snapshot.json`
- [ ] Comandos iniciais: `/case`, `/hunt`, `/report`, `/pivot`

**Commands Structure:**
```python
# socc/core/harness/commands.py
@dataclass(frozen=True)
class SOCCommand:
    name: str
    description: str
    handler: Callable
    aliases: list[str]
    permissions: list[str]
    
COMMAND_REGISTRY: dict[str, SOCCommand] = {}

def register_command(cmd: SOCCommand) -> None: ...
def get_command(name: str) -> SOCCommand | None: ...
def list_commands() -> list[str]: ...
```

---

## Sprint 2: Security Tools (Week 3-4)

### TASK-CC-005: Port BashTool Security
**Priority:** P0 | **Estimate:** 6h | **Status:** ✅ DONE

**Acceptance Criteria:**
- [ ] Criar `socc/tools/bash/security.py`
- [ ] Implementar validação de comandos perigosos
- [ ] Lista de comandos bloqueados/customizáveis
- [ ] Integração com `bashSecurity.ts` concepts

**Port from:**
```typescript
// tools/BashTool/bashSecurity.ts
- destructiveCommandWarning.ts → destructive_commands list
- pathValidation.ts → validate_path()
- readOnlyValidation.ts → ReadOnlyMode
- shouldUseSandbox.ts → SandboxDecision
```

**Implementation:**
```python
# socc/tools/bash/security.py
from enum import Enum
from dataclasses import dataclass

class CommandRisk(Enum):
    SAFE = "safe"
    MODERATE = "moderate"
    DESTRUCTIVE = "destructive"
    BLOCKED = "blocked"

DESTRUCTIVE_COMMANDS = {
    "rm -rf", "dd", "mkfs", "fdisk", "format",
    "shutdown", "reboot", "init", "systemctl",
    # Add Windows equivalents
    "del /s", "format c:", "shutdown /s"
}

def validate_command(cmd: str) -> CommandRisk:
    """Analyze command risk level."""
    pass

def should_use_sandbox(cmd: str, context: dict) -> bool:
    """Decide if command needs sandboxing."""
    pass
```

---

### TASK-CC-006: Port BashTool Permissions
**Priority:** P0 | **Estimate:** 4h | **Status:** ✅ DONE

**Acceptance Criteria:**
- [ ] Criar `socc/tools/bash/permissions.py`
- [ ] Implementar RBAC para comandos
- [ ] Roles: `analyst`, `senior_analyst`, `admin`
- [ ] Audit logging de comandos executados

---

### TASK-CC-007: Port BashTool Sandbox
**Priority:** P1 | **Estimate:** 6h | **Status:** ✅ DONE

**Acceptance Criteria:**
- [ ] Criar `socc/tools/bash/sandbox.py`
- [ ] Implementar containers/namespace isolation
- [ ] Resource limits (CPU, memory, time)
- [ ] Network isolation options

---

### TASK-CC-008: Integrate Existing Tools
**Priority:** P0 | **Estimate:** 2h | **Status:** ✅ DONE

**Acceptance Criteria:**
- [ ] Mover `extract_iocs`, `defang`, `decode_base64` para novo schema
- [ ] Atualizar `tools_registry.py` para usar `ToolSpec` do port
- [ ] Testes existentes passando

---

## Sprint 3: Agent System (Week 5-6)

### TASK-CC-009: Port AgentTool Fork
**Priority:** P0 | **Estimate:** 6h | **Status:** ✅ DONE

**Acceptance Criteria:**
- [ ] Criar `socc/agents/fork.py`
- [ ] Implementar `fork_subagent()` function
- [ ] Passar contexto (case data, findings) para subagent
- [ ] Track subagent lifecycle

**Port from:**
```typescript
// tools/AgentTool/forkSubagent.ts
export async function forkSubagent(config: ForkConfig): Promise<SubagentHandle>
```

**Implementation:**
```python
# socc/agents/fork.py
from dataclasses import dataclass
from typing import Callable, Any

@dataclass
class SubagentConfig:
    name: str
    specialty: str
    tools: list[str]
    context: dict[str, Any]
    max_steps: int = 10
    
@dataclass
class SubagentHandle:
    id: str
    name: str
    status: str  # "running", "completed", "failed"
    result: Any | None
    
def fork_subagent(config: SubagentConfig) -> SubagentHandle:
    """Create and run a specialized subagent."""
    pass
```

---

### TASK-CC-010: Port AgentTool Memory
**Priority:** P0 | **Estimate:** 4h | **Status:** ✅ DONE

**Acceptance Criteria:**
- [ ] Criar `socc/agents/memory.py`
- [ ] Implementar `AgentMemory` class
- [ ] Persistência em `~/.socc/agents/{agent_id}/`
- [ ] Snapshots de estado

**Port from:**
```typescript
// tools/AgentTool/agentMemory.ts
// tools/AgentTool/agentMemorySnapshot.ts
```

---

### TASK-CC-011: Create SOC Analyst Agent
**Priority:** P0 | **Estimate:** 4h | **Status:** ✅ DONE

**Acceptance Criteria:**
- [ ] Criar `socc/agents/built_in/soc_analyst.py`
- [ ] Prompt template para análise SOC
- [ ] Tools: `extract_iocs`, `defang`, `bash`, `grep`
- [ ] Testado com cenários reais

---

### TASK-CC-012: Create Incident Response Agent
**Priority:** P1 | **Estimate:** 4h | **Status:** ✅ DONE

**Acceptance Criteria:**
- [ ] Criar `socc/agents/built_in/ir_agent.py`
- [ ] Prompt template para Incident Response
- [ ] Tools: `bash`, `file_read`, `process_list`
- [ ] Checklist automático de IR

---

### TASK-CC-013: Create Threat Hunt Agent
**Priority:** P1 | **Estimate:** 4h | **Status:** ✅ DONE

**Acceptance Criteria:**
- [ ] Criar `socc/agents/built_in/threat_hunt_agent.py`
- [ ] Prompt template para Threat Hunting
- [ ] Tools: `grep`, `bash`, `process_list`, `network_connections`
- [ ] Hypothesis-driven hunting

---

## Sprint 4: CLI & Commands (Week 7-8)

### TASK-CC-014: Implement SOCC CLI
**Priority:** P0 | **Estimate:** 8h | **Status:** ✅ DONE

**Acceptance Criteria:**
- [ ] Criar `socc/cli/main.py`
- [ ] Usar argparse como port main.py
- [ ] Subcommands: `scan`, `analyze`, `report`, `case`
- [ ] Interactive mode (REPL)

**CLI Structure:**
```python
# socc/cli/main.py
def build_parser():
    parser = argparse.ArgumentParser('socc')
    subparsers = parser.add_subparsers(dest='command')
    
    # Scan commands
    scan_parser = subparsers.add_parser('scan')
    scan_parser.add_argument('--target', required=True)
    scan_parser.add_argument('--type', choices=['ioc', 'malware', 'vuln'])
    
    # Case commands
    case_parser = subparsers.add_parser('case')
    case_parser.add_argument('--create')
    case_parser.add_argument('--load')
    case_parser.add_argument('--close')
    
    # Agent commands
    agent_parser = subparsers.add_parser('agent')
    agent_parser.add_argument('--run', choices=['soc_analyst', 'ir', 'hunt'])
    
    return parser
```

---

### TASK-CC-015: Implement /case Command
**Priority:** P0 | **Estimate:** 6h | **Status:** ✅ DONE

**Acceptance Criteria:**
- [ ] Comando `/case` funcional no REPL
- [ ] Criar, carregar, fechar cases
- [ ] Persistência em `~/.socc/cases/`
- [ ] Metadata: title, severity, status, assignee

---

### TASK-CC-016: Implement /hunt Command
**Priority:** P1 | **Estimate:** 4h | **Status:** ✅ DONE

**Acceptance Criteria:**
- [ ] Comando `/hunt` funcional
- [ ] Hypothesis-driven hunting
- [ ] Logging de findings
- [ ] Integration com Threat Hunt Agent

---

## Sprint 5: Plugins & Integrations (Week 9-10)

### TASK-CC-017: Port Plugin System
**Priority:** P0 | **Estimate:** 8h | **Status:** ✅ DONE

**Acceptance Criteria:**
- [ ] Criar `socc/plugins/` structure
- [ ] Plugin loader com entry points
- [ ] Plugin manifest schema
- [ ] Hot-reload de plugins

**Port from:**
```typescript
// commands/plugin/ (17 files)
```

---

### TASK-CC-018: VirusTotal Plugin
**Priority:** P1 | **Estimate:** 4h | **Status:** ✅ DONE

**Acceptance Criteria:**
- [ ] Criar `socc/plugins/virustotal/`
- [ ] Tools: `vt_lookup_hash`, `vt_lookup_url`, `vt_lookup_domain`
- [ ] API key management
- [ ] Rate limiting

---

### TASK-CC-019: MISP Plugin
**Priority:** P1 | **Estimate:** 4h | **Status:** ✅ DONE

**Acceptance Criteria:**
- [ ] Criar `socc/plugins/misp/`
- [ ] Tools: `misp_search`, `misp_add_event`, `misp_add_ioc`
- [ ] MISP API integration
- [ ] Attribute type mapping

---

### TASK-CC-020: OpenCTI Plugin
**Priority:** P2 | **Estimate:** 4h | **Status:** ✅ DONE

**Acceptance Criteria:**
- [ ] Criar `socc/plugins/opencti/`
- [ ] Tools: `opencti_search`, `opencti_create_indicator`
- [ ] GraphQL API integration
- [ ] STIX 2.1 support

---

## Summary

| Sprint | Tasks | Priority | Estimate | Status |
|--------|-------|----------|----------|--------|
| 1 | CC-001 a CC-004 | Foundation | 17h | ✅ DONE |
| 2 | CC-005 a CC-008 | Security Tools | 18h | ✅ DONE |
| 3 | CC-009 a CC-013 | Agent System | 22h | ✅ DONE |
| 4 | CC-014 a CC-016 | CLI & Commands | 18h | ✅ DONE |
| 5 | CC-017 a CC-020 | Plugins | 20h | ✅ DONE |
| **Total** | **20 tasks** | | **95h** | **✅ COMPLETO** |

---

## Blocked By

- [x] TASK-001 (Tool Registry) - DONE
- [x] TASK-002 (Contracts v2.0) - DONE
- [x] TASK-003 (Interactive CLI) - DONE

---

## Notes

- Priorizar BashTool security (CC-005 a CC-007) para segurança operacional
- AgentTool fork/memory (CC-009, CC-010) são críticos para workflows complexos
- Plugins podem ser desenvolvidos em paralelo após plugin system (CC-017)