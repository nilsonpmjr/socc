# SOCC Harness Evolution - Implementation Detail

> **Versão:** 1.0
> **Data:** 2026-03-31
> **Fonte Principal:** Claude Code Python Port (`/home/nilsonpmjr/claude-code/`)

---

## Visão Geral da Implementação

### Estrutura Final do SOCC após Integração

```
socc/
├── core/
│   ├── harness/              # 🆕 Baseado no Claude Code Port
│   │   ├── __init__.py
│   │   ├── models.py        # Dataclasses: SOCTool, SOCAgent, SOCCommand
│   │   ├── runtime.py       # SOCRuntime: routing, invocation
│   │   ├── commands.py      # Command registry
│   │   ├── tools_loader.py  # Tools loader (snapshots JSON)
│   │   └── reference_data/
│   │       ├── socc_tools_snapshot.json
│   │       ├── socc_commands_snapshot.json
│   │       └── socc_agents_snapshot.json
│   ├── tools_registry.py    # ✅ Já existe (TASK-001)
│   ├── contracts.py         # ✅ Já existe (TASK-006)
│   ├── context_budget.py    # ✅ Já existe (TASK-038)
│   └── extensions.py        # 🆕 Plugin system (TASK-012)
│
├── tools/
│   ├── file.py              # ✅ Já existe (read, write, edit)
│   ├── shell.py             # ✅ Já existe (bash)
│   ├── bash/                # 🆕 BashTool Security do Port
│   │   ├── __init__.py
│   │   ├── security.py      # CommandRisk, validate_command()
│   │   ├── permissions.py   # RBAC, audit logging
│   │   └── sandbox.py       # Isolation, resource limits
│   └── soc/                 # ✅ Tools SOC específicas
│       ├── ioc_extractor.py # extract_iocs
│       ├── defang.py        # defang URLs
│       └── decode.py        # decode_base64
│
├── agents/                  # 🆕 AgentTool do Port
│   ├── __init__.py
│   ├── fork.py              # fork_subagent()
│   ├── memory.py            # AgentMemory, snapshots
│   └── built_in/
│       ├── __init__.py
│       ├── soc_analyst.py   # General-purpose SOC agent
│       ├── ir_agent.py      # Incident Response agent
│       ├── threat_hunt.py   # Threat Hunting agent
│       └── malware_analyst.py # Malware Analysis agent
│
├── commands/                # 🆕 Commands do Port
│   ├── __init__.py
│   ├── case.py              # /case management
│   ├── hunt.py              # /hunt interactive
│   ├── report.py            # /report generation
│   └── pivot.py             # /pivot operations
│
├── plugins/                 # 🆕 Plugin System
│   ├── __init__.py
│   ├── virustotal/          # VT integration
│   ├── misp/                # MISP integration
│   └── opencti/             # OpenCTI integration
│
├── cli/
│   ├── main.py              # CLI entrypoint
│   ├── chat_interactive.py  # ✅ TUI REPL
│   ├── session_manager.py   # 🆕 Sessions
│   └── export.py            # 🆕 Export HTML/MD
│
└── integrations/
    ├── shuffle.py           # Shuffle SOAR webhook
    └── api.py               # REST API
```

---

## FASE 1: Foundation (TASK-CC-001 a TASK-CC-004)

### TASK-CC-001: Harness Base Structure

#### Implementação Detalhada

**Arquivo:** `socc/core/harness/models.py`

```python
"""
Dataclasses base para o SOCC Harness.
Baseado em: /home/nilsonpmjr/claude-code/src/models.py
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Any

# ============================================================================
# Enums
# ============================================================================

class ToolCategory(Enum):
    """Categorias de tools SOC."""
    IOC = "ioc"                    # Indicators of Compromise
    MALWARE = "malware"            # Malware analysis
    THREAT_INTEL = "threat_intel"  # Threat Intelligence
    NETWORK = "network"            # Network operations
    FILE = "file"                  # File operations
    SHELL = "shell"                 # Shell commands
    UTILITY = "utility"            # General utilities
    PLUGIN = "plugin"              # Plugin-provided

class RiskLevel(Enum):
    """Níveis de risco para tools/commands."""
    LOW = "low"           # Always safe
    MEDIUM = "medium"     # Requires logging
    HIGH = "high"         # Requires approval
    CRITICAL = "critical" # Blocked by default

class AgentSpecialty(Enum):
    """Especialidades de agentes SOC."""
    GENERAL = "general"           # General-purpose analyst
    IR = "incident_response"      # Incident Response
    TI = "threat_intel"           # Threat Intelligence
    HUNT = "threat_hunt"          # Threat Hunting
    MALWARE = "malware_analysis"  # Malware Analysis
    FORENSICS = "forensics"       # Digital Forensics

# ============================================================================
# Tool Specification
# ============================================================================

@dataclass(frozen=True)
class SOCToolSpec:
    """Especificação completa de uma tool SOC."""
    name: str                                    # Unique identifier
    description: str                             # Human-readable description
    handler: Callable                            # Python callable
    category: ToolCategory = ToolCategory.UTILITY
    risk_level: RiskLevel = RiskLevel.LOW
    parameters: dict[str, ParamSpec] = field(default_factory=dict)
    aliases: list[str] = field(default_factory=list)
    permissions_required: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    
    def to_json_schema(self) -> dict:
        """Gera JSON Schema para OpenAI function calling."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    name: spec.to_json_schema() 
                    for name, spec in self.parameters.items()
                },
                "required": [n for n, s in self.parameters.items() if s.required]
            }
        }

@dataclass
class ParamSpec:
    """Especificação de parâmetro de tool."""
    type: str = "string"
    description: str = ""
    required: bool = True
    default: Any = None
    enum: list[str] | None = None
    items: dict | None = None    # For arrays
    min_value: int | float | None = None
    max_value: int | float | None = None
    
    def to_json_schema(self) -> dict:
        schema = {"type": self.type, "description": self.description}
        if self.enum:
            schema["enum"] = self.enum
        if self.items:
            schema["items"] = self.items
        if self.min_value is not None:
            schema["minimum"] = self.min_value
        if self.max_value is not None:
            schema["maximum"] = self.max_value
        return schema

# ============================================================================
# Agent Specification
# ============================================================================

@dataclass
class SOCAgentSpec:
    """Especificação de um agente SOC."""
    name: str                                    # Agent identifier
    specialty: AgentSpecialty                    # Specialty area
    description: str                             # Description
    prompt_template: str                         # System prompt template
    tools_whitelist: list[str] = field(default_factory=list)  # Empty = all allowed
    tools_blacklist: list[str] = field(default_factory=list)  # Always blocked
    max_steps: int = 10                          # Max reasoning steps
    timeout_seconds: int = 300                  # Max execution time
    metadata: dict = field(default_factory=dict)
    
    def can_use_tool(self, tool_name: str) -> bool:
        """Check if agent can use a specific tool."""
        if tool_name in self.tools_blacklist:
            return False
        if not self.tools_whitelist:
            return True
        return tool_name in self.tools_whitelist

# ============================================================================
# Command Specification  
# ============================================================================

@dataclass
class SOCCommand:
    """Especificação de um comando CLI."""
    name: str                                    # Command name (e.g., "/case")
    description: str                             # Help text
    handler: Callable                            # Handler function
    aliases: list[str] = field(default_factory=list)  # Alternative names
    permissions: list[str] = field(default_factory=list)  # Required permissions
    arguments: list[CommandArg] = field(default_factory=list)
    
@dataclass
class CommandArg:
    """Argumento de comando CLI."""
    name: str
    type: str = "string"
    required: bool = False
    default: Any = None
    help: str = ""

# ============================================================================
# Result Types
# ============================================================================

@dataclass
class ToolResult:
    """Resultado de execução de tool."""
    ok: bool
    output: Any | None = None
    error: str | None = None
    metadata: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        if self.ok:
            return {"ok": True, "output": self.output, **self.metadata}
        return {"ok": False, "error": self.error}

@dataclass  
class AgentResult:
    """Resultado de execução de agente."""
    ok: bool
    agent_name: str
    conclusion: str                             # Agent's final conclusion
    findings: list[str] = field(default_factory=list)  # Key findings
    tool_calls: list[ToolResult] = field(default_factory=list)
    reasoning_trace: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0
```

---

### TASK-CC-002: Runtime Core

#### Implementação Detalhada

**Arquivo:** `socc/core/harness/runtime.py`

```python
"""
Runtime principal do SOCC Harness.
Baseado em: /home/nilsonpmjr/claude-code/src/runtime.py
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import json
import time
from typing import Any

from .models import (
    SOCToolSpec, SOCAgentSpec, SOCCommand, ToolResult, AgentResult,
    ToolCategory, RiskLevel
)

# ============================================================================
# Routing
# ============================================================================

@dataclass(frozen=True)
class RoutedMatch:
    """Match resultado de routing."""
    kind: str          # "tool", "agent", "command"
    name: str          # Identifier
    score: int         # Relevance score
    source_hint: str   # Where found

class SOCRuntime:
    """Runtime principal do SOCC Harness."""
    
    def __init__(self):
        # Registries
        self._tools: dict[str, SOCToolSpec] = {}
        self._agents: dict[str, SOCAgentSpec] = {}
        self._commands: dict[str, SOCCommand] = {}
        
        # Load from snapshots
        self._load_tools_snapshot()
        self._load_agents_snapshot()
        self._load_commands_snapshot()
    
    # ------------------------------------------------------------------------
    # Tool Operations
    # ------------------------------------------------------------------------
    
    def register_tool(self, spec: SOCToolSpec) -> None:
        """Register a tool."""
        self._tools[spec.name] = spec
        for alias in spec.aliases:
            self._tools[alias] = spec
    
    def get_tool(self, name: str) -> SOCToolSpec | None:
        """Get a tool by name."""
        return self._tools.get(name)
    
    def list_tools(
        self, 
        category: ToolCategory | None = None,
        risk_level: RiskLevel | None = None
    ) -> list[SOCToolSpec]:
        """List tools, optionally filtered."""
        tools = list(self._tools.values())
        if category:
            tools = [t for t in tools if t.category == category]
        if risk_level:
            tools = [t for t in tools if t.risk_level == risk_level]
        return tools
    
    def invoke_tool(
        self, 
        name: str, 
        args: dict[str, Any],
        check_permissions: bool = True
    ) -> ToolResult:
        """Invoke a tool with validation."""
        tool = self.get_tool(name)
        if not tool:
            return ToolResult(ok=False, error=f"Tool not found: {name}")
        
        # Validate parameters
        validated = self._validate_params(tool, args)
        if not validated["ok"]:
            return ToolResult(ok=False, error=validated["error"])
        
        # Check risk level
        if check_permissions and tool.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            # TODO: Implement permission check
            pass
        
        # Execute
        try:
            start = time.time()
            result = tool.handler(**validated["args"])
            elapsed = time.time() - start
            
            return ToolResult(
                ok=True, 
                output=result,
                metadata={"elapsed_seconds": elapsed, "tool": name}
            )
        except Exception as e:
            return ToolResult(ok=False, error=str(e))
    
    # ------------------------------------------------------------------------
    # Agent Operations
    # ------------------------------------------------------------------------
    
    def register_agent(self, spec: SOCAgentSpec) -> None:
        """Register an agent."""
        self._agents[spec.name] = spec
    
    def get_agent(self, name: str) -> SOCAgentSpec | None:
        """Get an agent by name."""
        return self._agents.get(name)
    
    def list_agents(self) -> list[SOCAgentSpec]:
        """List all agents."""
        return list(self._agents.values())
    
    # ------------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------------
    
    def route_prompt(self, prompt: str, limit: int = 5) -> list[RoutedMatch]:
        """Route a prompt to relevant tools/agents/commands.
        
        Baseado em PortRuntime.route_prompt() do Claude Code Port.
        """
        tokens = self._tokenize_prompt(prompt)
        
        matches: list[RoutedMatch] = []
        
        # Score tools
        for name, tool in self._tools.items():
            score = self._score_match(tokens, [name, tool.description])
            if score > 0:
                matches.append(RoutedMatch(
                    kind="tool", 
                    name=name, 
                    score=score,
                    source_hint=tool.category.value
                ))
        
        # Score agents
        for name, agent in self._agents.items():
            score = self._score_match(tokens, [name, agent.description, agent.specialty.value])
            if score > 0:
                matches.append(RoutedMatch(
                    kind="agent",
                    name=name,
                    score=score,
                    source_hint=agent.specialty.value
                ))
        
        # Sort and return top matches
        matches.sort(key=lambda m: (-m.score, m.name))
        return matches[:limit]
    
    # ------------------------------------------------------------------------
    # Private Methods
    # ------------------------------------------------------------------------
    
    def _tokenize_prompt(self, prompt: str) -> set[str]:
        """Extract search tokens from prompt."""
        # Simple tokenization
        tokens = prompt.lower().replace('/', ' ').replace('-', ' ').split()
        return {t for t in tokens if len(t) > 2}
    
    def _score_match(self, tokens: set[str], haystacks: list[str]) -> int:
        """Score how well tokens match haystacks."""
        score = 0
        for token in tokens:
            for hay in haystacks:
                if token in hay.lower():
                    score += 1
        return score
    
    def _validate_params(self, tool: SOCToolSpec, args: dict) -> dict:
        """Validate tool parameters."""
        validated = {}
        
        for name, spec in tool.parameters.items():
            if spec.required and name not in args:
                return {"ok": False, "error": f"Missing required parameter: {name}"}
            
            if name in args:
                # Type coercion
                value = args[name]
                # TODO: Add type validation
                validated[name] = value
            elif spec.default is not None:
                validated[name] = spec.default
        
        return {"ok": True, "args": validated}
    
    def _load_tools_snapshot(self):
        """Load tools from snapshot JSON."""
        snapshot_path = Path(__file__).parent / "reference_data" / "socc_tools_snapshot.json"
        if snapshot_path.exists():
            data = json.loads(snapshot_path.read_text())
            # Register placeholder entries
            for entry in data:
                # Tools are registered separately with handlers
                pass
    
    def _load_agents_snapshot(self):
        """Load agents from snapshot JSON."""
        snapshot_path = Path(__file__).parent / "reference_data" / "socc_agents_snapshot.json"
        if snapshot_path.exists():
            data = json.loads(snapshot_path.read_text())
            for entry in data:
                spec = SOCAgentSpec(
                    name=entry["name"],
                    specialty=AgentSpecialty(entry.get("specialty", "general")),
                    description=entry["description"],
                    prompt_template=entry.get("prompt_template", ""),
                    tools_whitelist=entry.get("tools_whitelist", []),
                    tools_blacklist=entry.get("tools_blacklist", []),
                )
                self.register_agent(spec)
    
    def _load_commands_snapshot(self):
        """Load commands from snapshot JSON."""
        snapshot_path = Path(__file__).parent / "reference_data" / "socc_commands_snapshot.json"
        if snapshot_path.exists():
            data = json.loads(snapshot_path.read_text())
            for entry in data:
                # Commands registered separately with handlers
                pass


# Global runtime instance
RUNTIME = SOCRuntime()
```

---

### TASK-CC-003: Tools Snapshot

**Arquivo:** `socc/core/harness/reference_data/socc_tools_snapshot.json`

```json
[
  {
    "name": "extract_iocs",
    "description": "Extract Indicators of Compromise (IPs, domains, URLs, hashes) from text",
    "category": "ioc",
    "risk_level": "low",
    "parameters": {
      "text": {"type": "string", "description": "Text to extract IOCs from", "required": true},
      "types": {"type": "array", "description": "IOC types to extract", "required": false, "default": ["ip", "domain", "url", "hash"]}
    },
    "tags": ["ioc", "extraction", "analysis"]
  },
  {
    "name": "defang",
    "description": "Defang URLs and indicators by replacing dangerous characters",
    "category": "utility",
    "risk_level": "low",
    "parameters": {
      "text": {"type": "string", "description": "Text containing URLs/indicators to defang", "required": true}
    },
    "tags": ["defang", "sanitize", "safe"]
  },
  {
    "name": "decode_base64",
    "description": "Decode base64 encoded strings",
    "category": "utility",
    "risk_level": "low",
    "parameters": {
      "value": {"type": "string", "description": "Base64 encoded string", "required": true}
    },
    "tags": ["decode", "base64", "analysis"]
  },
  {
    "name": "read",
    "description": "Read file contents with optional offset and limit",
    "category": "file",
    "risk_level": "low",
    "parameters": {
      "path": {"type": "string", "description": "File path to read", "required": true},
      "offset": {"type": "integer", "description": "Line to start reading from", "required": false, "default": 1},
      "limit": {"type": "integer", "description": "Maximum lines to read", "required": false}
    },
    "permissions_required": ["file.read"],
    "tags": ["file", "read"]
  },
  {
    "name": "write",
    "description": "Write content to a file",
    "category": "file",
    "risk_level": "medium",
    "parameters": {
      "path": {"type": "string", "description": "File path to write", "required": true},
      "content": {"type": "string", "description": "Content to write", "required": true}
    },
    "permissions_required": ["file.write"],
    "tags": ["file", "write"]
  },
  {
    "name": "bash",
    "description": "Execute shell commands with security validation",
    "category": "shell",
    "risk_level": "high",
    "parameters": {
      "command": {"type": "string", "description": "Command to execute", "required": true},
      "timeout": {"type": "integer", "description": "Timeout in seconds", "required": false, "default": 30}
    },
    "permissions_required": ["shell.execute"],
    "tags": ["shell", "command", "execute"]
  },
  {
    "name": "vt_lookup_hash",
    "description": "Lookup file hash in VirusTotal",
    "category": "threat_intel",
    "risk_level": "low",
    "parameters": {
      "hash": {"type": "string", "description": "File hash (MD5, SHA1, SHA256)", "required": true}
    },
    "tags": ["virustotal", "lookup", "malware"]
  },
  {
    "name": "misp_search",
    "description": "Search for indicators in MISP",
    "category": "threat_intel",
    "risk_level": "low",
    "parameters": {
      "value": {"type": "string", "description": "Value to search", "required": true},
      "type": {"type": "string", "description": "Attribute type", "required": false}
    },
    "tags": ["misp", "search", "threat_intel"]
  }
]
```

---

## FASE 2: BashTool Security (TASK-CC-005 a TASK-CC-007)

### TASK-CC-005: BashTool Security

**Arquivo:** `socc/tools/bash/security.py`

```python
"""
Security validation for shell commands.
Baseado em: tools/BashTool/bashSecurity.ts, destructiveCommandWarning.ts
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import re
import shlex

class CommandRisk(Enum):
    """Risk levels for shell commands."""
    SAFE = "safe"              # Always safe
    MODERATE = "moderate"      # Generally safe, may have side effects
    DESTRUCTIVE = "destructive"  # Modifies system state
    BLOCKED = "blocked"        # Always blocked

# Destructive commands that modify system state
DESTRUCTIVE_PATTERNS = [
    # File system
    r"\brm\s+-rf\b",
    r"\brm\s+.*-f.*-r\b",
    r"\bdd\s+if=",
    r"\bmkfs\b",
    r"\bfdisk\b",
    r"\bformat\b",
    
    # System
    r"\bshutdown\b",
    r"\breboot\b",
    r"\binit\s+[06]\b",
    r"\bsystemctl\s+(stop|disable|mask)\b",
    
    # Network
    r"\biptables\s+-F\b",
    r"\bifconfig\s+.*down\b",
    r"\bip\s+link\s+set\s+.*down\b",
    
    # Process
    r"\bkill\s+-9\s+1\b",
    r"\bkillall\s+.*init\b",
    
    # Windows equivalents
    r"\bdel\s+/s\b",
    r"\bformat\s+c:",
    r"\bshutdown\s+/s\b",
]

# Commands that require explicit approval
HIGH_RISK_PATTERNS = [
    r"\bsudo\b",
    r"\bsu\b",
    r"\bchmod\s+[0-7]{3,4}\b",
    r"\bchown\b",
    r"\bcurl\b.*\|\s*\bbash\b",
    r"\bwget\b.*\|\s*\bbash\b",
    r"\beval\b",
]

# Commands that are generally safe
SAFE_PATTERNS = [
    r"\bls\b",
    r"\bcat\b",
    r"\bgrep\b",
    r"\bhead\b",
    r"\btail\b",
    r"\bwc\b",
    r"\bfind\b.*-type\f",
    r"\becho\b",
    r"\bwhich\b",
    r"\bwhoami\b",
    r"\bpwd\b",
]

@dataclass
class CommandAnalysis:
    """Result of command security analysis."""
    risk: CommandRisk
    reason: str
    matched_patterns: list[str]
    sanitized_command: str | None = None
    requires_approval: bool = False

def analyze_command(command: str) -> CommandAnalysis:
    """Analyze a shell command for security risks."""
    command = command.strip()
    
    if not command:
        return CommandAnalysis(
            risk=CommandRisk.SAFE,
            reason="Empty command",
            matched_patterns=[]
        )
    
    # Check blocked patterns first
    for pattern in DESTRUCTIVE_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return CommandAnalysis(
                risk=CommandRisk.BLOCKED,
                reason=f"Matches destructive pattern: {pattern}",
                matched_patterns=[pattern],
                requires_approval=False  # Cannot be approved
            )
    
    # Check high-risk patterns
    matched_high = []
    for pattern in HIGH_RISK_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            matched_high.append(pattern)
    
    if matched_high:
        return CommandAnalysis(
            risk=CommandRisk.DESTRUCTIVE,
            reason="High-risk command requires approval",
            matched_patterns=matched_high,
            requires_approval=True
        )
    
    # Check if safe patterns match the whole command
    for pattern in SAFE_PATTERNS:
        if re.match(f"^{pattern}", command, re.IGNORECASE):
            return CommandAnalysis(
                risk=CommandRisk.SAFE,
                reason="Matches safe pattern",
                matched_patterns=[pattern],
                requires_approval=False
            )
    
    # Default to moderate
    return CommandAnalysis(
        risk=CommandRisk.MODERATE,
        reason="Unknown command, treated as moderate risk",
        matched_patterns=[],
        requires_approval=False
    )

def should_use_sandbox(command: str, context: dict | None = None) -> bool:
    """Decide if command should run in sandbox.
    
    Args:
        command: Shell command to analyze
        context: Additional context (user role, case sensitivity, etc)
    
    Returns:
        True if sandbox is recommended
    """
    analysis = analyze_command(command)
    
    # Always sandbox destructive commands
    if analysis.risk == CommandRisk.DESTRUCTIVE:
        return True
    
    # Never sandbox blocked commands (they won't run at all)
    if analysis.risk == CommandRisk.BLOCKED:
        return False
    
    # Check context
    context = context or {}
    
    # Sandbox if user role requires it
    user_role = context.get("role", "analyst")
    if user_role == "analyst" and analysis.risk != CommandRisk.SAFE:
        return True
    
    # Check if handling sensitive case
    if context.get("sensitive_case"):
        return True
    
    return False

def redact_secrets(output: str) -> str:
    """Redact potential secrets from command output."""
    patterns = [
        # API keys
        (r"(api[_-]?key['\"]?\s*[:=]\s*['\"]?)[\w\-]{20,}", r"\1[REDACTED]"),
        # Passwords
        (r"(password['\"]?\s*[:=]\s*['\"]?)[^\s'\"]+", r"\1[REDACTED]"),
        # Tokens
        (r"(token['\"]?\s*[:=]\s*['\"]?)[\w\-\.]{20,}", r"\1[REDACTED]"),
        # AWS keys
        (r"AKIA[A-Z0-9]{16}", r"[REDACTED_AWS_KEY]"),
        # Private keys
        (r"-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----[\s\S]*?-----END", r"[PRIVATE KEY REDACTED]"),
    ]
    
    result = output
    for pattern, replacement in patterns:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    
    return result
```

---

## FASE 3: Agent System (TASK-CC-009 a TASK-CC-013)

### TASK-CC-009: AgentTool Fork

**Arquivo:** `socc/agents/fork.py`

```python
"""
Subagent forking system.
Baseado em: tools/AgentTool/forkSubagent.ts
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable
import uuid
import time
import threading
from pathlib import Path

from socc.core.harness.runtime import RUNTIME, ToolResult
from socc.core.harness.models import SOCAgentSpec, AgentResult

@dataclass
class SubagentConfig:
    """Configuration for forking a subagent."""
    name: str                                    # Subagent identifier
    specialty: str                               # Agent specialty
    task: str                                    # Task description
    context: dict[str, Any] = field(default_factory=dict)  # Context to pass
    tools: list[str] = field(default_factory=list)          # Tools to allow
    max_steps: int = 10                         # Max reasoning steps
    timeout_seconds: int = 300                 # Max execution time
    parent_agent_id: str | None = None         # Parent agent (for nesting)

@dataclass
class SubagentHandle:
    """Handle to a running/completed subagent."""
    id: str                                      # Unique ID
    name: str                                    # Config name
    status: str                                  # "running", "completed", "failed", "timeout"
    result: AgentResult | None = None           # Final result
    started_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    
    @property
    def elapsed_seconds(self) -> float:
        if self.completed_at:
            return self.completed_at - self.started_at
        return time.time() - self.started_at

# Active subagents registry
_active_subagents: dict[str, SubagentHandle] = {}
_subagent_lock = threading.Lock()

def fork_subagent(config: SubagentConfig) -> SubagentHandle:
    """Create and start a subagent.
    
    This creates a specialized agent to handle a specific task.
    The subagent inherits context from the parent and has access
    to a restricted set of tools.
    
    Args:
        config: Subagent configuration
    
    Returns:
        Handle to the subagent for tracking
    """
    handle = SubagentHandle(
        id=str(uuid.uuid4())[:8],
        name=config.name,
        status="running"
    )
    
    with _subagent_lock:
        _active_subagents[handle.id] = handle
    
    # Start subagent in background thread
    thread = threading.Thread(
        target=_run_subagent,
        args=(handle, config),
        daemon=True
    )
    thread.start()
    
    # Wait for completion or timeout
    thread.join(timeout=config.timeout_seconds)
    
    if thread.is_alive():
        handle.status = "timeout"
        handle.completed_at = time.time()
    
    return handle

def _run_subagent(handle: SubagentHandle, config: SubagentConfig) -> None:
    """Execute subagent task (internal)."""
    try:
        # Get agent spec
        agent_spec = RUNTIME.get_agent(config.specialty)
        if not agent_spec:
            handle.status = "failed"
            handle.result = AgentResult(
                ok=False,
                agent_name=config.specialty,
                conclusion=f"Agent not found: {config.specialty}"
            )
            handle.completed_at = time.time()
            return
        
        # Build prompt with context
        prompt = _build_subagent_prompt(agent_spec, config)
        
        # Execute agent reasoning loop
        result = _execute_agent_loop(agent_spec, config, prompt)
        
        handle.result = result
        handle.status = "completed" if result.ok else "failed"
        
    except Exception as e:
        handle.status = "failed"
        handle.result = AgentResult(
            ok=False,
            agent_name=config.specialty,
            conclusion=f"Error: {str(e)}"
        )
    
    finally:
        handle.completed_at = time.time()

def _build_subagent_prompt(spec: SOCAgentSpec, config: SubagentConfig) -> str:
    """Build prompt for subagent."""
    parts = [
        f"# Task: {config.task}",
        "",
        f"## Agent: {spec.name}",
        f"Specialty: {spec.specialty.value}",
        "",
        "## Context:",
    ]
    
    for key, value in config.context.items():
        parts.append(f"- {key}: {value}")
    
    parts.extend([
        "",
        "## Available Tools:",
        ", ".join(config.tools) if config.tools else "<all>",
        "",
        "Please analyze and provide your conclusion.",
    ])
    
    return "\n".join(parts)

def _execute_agent_loop(
    spec: SOCAgentSpec, 
    config: SubagentConfig, 
    prompt: str
) -> AgentResult:
    """Execute agent's reasoning loop (simplified version)."""
    findings = []
    tool_calls = []
    reasoning = []
    
    # TODO: Integrate with actual LLM
    # For now, return placeholder
    return AgentResult(
        ok=True,
        agent_name=spec.name,
        conclusion="Analysis complete (placeholder)",
        findings=findings,
        tool_calls=tool_calls,
        reasoning_trace=reasoning,
        elapsed_seconds=0.0
    )

def list_active_subagents() -> list[SubagentHandle]:
    """List all active subagents."""
    with _subagent_lock:
        return [h for h in _active_subagents.values() if h.status == "running"]

def get_subagent(subagent_id: str) -> SubagentHandle | None:
    """Get a subagent by ID."""
    with _subagent_lock:
        return _active_subagents.get(subagent_id)
```

---

### TASK-CC-011 a CC-013: Built-in Agents

**Arquivo:** `socc/agents/built_in/soc_analyst.py`

```python
"""
SOC Analyst Agent - General-purpose security analyst.
"""
from socc.core.harness.models import SOCAgentSpec, AgentSpecialty

SOC_ANALYST_PROMPT = """
You are a SOC Analyst Agent, a general-purpose security analyst.

## Your Role
Analyze security incidents, triage alerts, and investigate suspicious activity.

## Available Analysis Types
- Phishing analysis and URL inspection
- Malware indicators extraction
- Log analysis and correlation
- Threat intelligence lookup
- Incident timeline construction

## Methodology
1. **Triage**: Assess severity and impact
2. **Enrichment**: Gather additional context
3. **Analysis**: Examine evidence and correlate
4. **Conclusion**: Provide findings and recommendations

## Output Format
When complete, provide:
- **Severity**: Critical/High/Medium/Low
- **Summary**: One-sentence summary
- **Findings**: Bullet list of key findings
- **Recommendations**: Action items for response
- **IOCs**: Extracted indicators (if any)
"""

SOC_ANALYST_SPEC = SOCAgentSpec(
    name="soc_analyst",
    specialty=AgentSpecialty.GENERAL,
    description="General-purpose SOC analyst for alert triage and investigation",
    prompt_template=SOC_ANALYST_PROMPT,
    tools_whitelist=[
        "extract_iocs", "defang", "decode_base64",
        "read", "grep", "bash",
        "vt_lookup_hash", "misp_search"
    ],
    tools_blacklist=[],
    max_steps=15,
    timeout_seconds=600
)
```

**Arquivo:** `socc/agents/built_in/ir_agent.py`

```python
"""
Incident Response Agent - Specialized in IR procedures.
"""
from socc.core.harness.models import SOCAgentSpec, AgentSpecialty

IR_AGENT_PROMPT = """
You are an Incident Response Agent, specialized in handling security incidents.

## Your Role
Coordinate incident response activities, maintain chain of custody, and ensure proper procedures.

## IR Workflow
1. **Preparation**: Verify scope and authorization
2. **Identification**: Confirm incident and assess impact
3. **Containment**: Isolate affected systems
4. **Eradication**: Remove threat and vulnerabilities
5. **Recovery**: Restore systems and operations
6. **Lessons Learned**: Document findings

## Key Tasks
- Create incident timeline
- Identify scope of compromise
- Preserve evidence
- Recommend containment actions
- Document all activities

## Checklist
Before declaring incident contained:
- [ ] All affected systems identified
- [ ] Attacker access removed
- [ ] Lateral movement blocked
- [ ] Evidence preserved
- [ ] Stakeholders notified
"""

IR_AGENT_SPEC = SOCAgentSpec(
    name="ir_agent",
    specialty=AgentSpecialty.IR,
    description="Incident Response specialist for handling security incidents",
    prompt_template=IR_AGENT_PROMPT,
    tools_whitelist=[
        "read", "grep", "bash",
        "extract_iocs", "defang"
    ],
    tools_blacklist=[],  # Can use all allowed tools
    max_steps=20,
    timeout_seconds=1800  # 30 min for complex IR
)
```

---

## FASE 4: Commands (TASK-CC-014 a TASK-CC-016)

### TASK-CC-015: /case Command

**Arquivo:** `socc/commands/case.py`

```python
"""
Case management command.
"""
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import json
import uuid

@dataclass
class Case:
    """Security incident case."""
    id: str
    title: str
    severity: str = "medium"  # low, medium, high, critical
    status: str = "open"       # open, investigating, contained, closed
    assignee: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    findings: list[str] = field(default_factory=list)
    iocs: list[str] = field(default_factory=list)
    timeline: list[dict] = field(default_factory=list)
    notes: str = ""

class CaseManager:
    """Manage security cases."""
    
    def __init__(self, cases_dir: Path | None = None):
        self.cases_dir = cases_dir or Path.home() / ".socc" / "cases"
        self.cases_dir.mkdir(parents=True, exist_ok=True)
    
    def create(self, title: str, severity: str = "medium") -> Case:
        """Create a new case."""
        case = Case(
            id=str(uuid.uuid4())[:8],
            title=title,
            severity=severity
        )
        self._save(case)
        return case
    
    def load(self, case_id: str) -> Case | None:
        """Load an existing case."""
        case_file = self.cases_dir / f"{case_id}.json"
        if not case_file.exists():
            return None
        
        data = json.loads(case_file.read_text())
        return Case(**data)
    
    def list(self, status: str | None = None) -> list[Case]:
        """List cases, optionally filtered by status."""
        cases = []
        for case_file in self.cases_dir.glob("*.json"):
            case = self.load(case_file.stem)
            if case and (status is None or case.status == status):
                cases.append(case)
        return sorted(cases, key=lambda c: c.updated_at, reverse=True)
    
    def close(self, case_id: str) -> Case | None:
        """Close a case."""
        case = self.load(case_id)
        if case:
            case.status = "closed"
            case.updated_at = datetime.utcnow()
            self._save(case)
        return case
    
    def _save(self, case: Case) -> None:
        """Save case to disk."""
        case_file = self.cases_dir / f"{case.id}.json"
        case_file.write_text(json.dumps({
            "id": case.id,
            "title": case.title,
            "severity": case.severity,
            "status": case.status,
            "assignee": case.assignee,
            "created_at": case.created_at.isoformat(),
            "updated_at": case.updated_at.isoformat(),
            "findings": case.findings,
            "iocs": case.iocs,
            "timeline": case.timeline,
            "notes": case.notes
        }, indent=2))

# Command handler
def handle_case_command(args: list[str], context: dict) -> str:
    """Handle /case command."""
    manager = CaseManager()
    
    if not args or args[0] == "list":
        cases = manager.list()
        if not cases:
            return "No cases found."
        
        lines = ["# Cases", ""]
        for case in cases:
            status_emoji = {"open": "🔴", "investigating": "🟡", "contained": "🟢", "closed": "⬜"}
            lines.append(f"{status_emoji.get(case.status, '⚪')} [{case.id}] {case.title} ({case.severity})")
        return "\n".join(lines)
    
    if args[0] == "create":
        title = " ".join(args[1:]) if len(args) > 1 else "Untitled Case"
        case = manager.create(title)
        return f"Created case [{case.id}]: {case.title}"
    
    if args[0] == "load" and len(args) > 1:
        case = manager.load(args[1])
        if not case:
            return f"Case {args[1]} not found."
        
        lines = [
            f"# Case [{case.id}]: {case.title}",
            f"**Severity:** {case.severity}",
            f"**Status:** {case.status}",
            f"**Created:** {case.created_at}",
            "",
            "## Findings",
            *[f"- {f}" for f in case.findings] if case.findings else ["No findings yet"],
            "",
            "## IOCs",
            *[f"- {i}" for i in case.iocs] if case.iocs else ["No IOCs yet"],
        ]
        return "\n".join(lines)
    
    if args[0] == "close" and len(args) > 1:
        case = manager.close(args[1])
        if case:
            return f"Closed case [{case.id}]"
        return f"Case {args[1]} not found."
    
    return "Usage: /case [list|create <title>|load <id>|close <id>]"
```

---

## Summary

### Arquivos que Serão Criados/Modificados

| Arquivo | Tipo | Descrição |
|---------|------|-----------|
| `socc/core/harness/__init__.py` | 🆕 | Package init |
| `socc/core/harness/models.py` | 🆕 | Dataclasses base |
| `socc/core/harness/runtime.py` | 🆕 | Runtime principal |
| `socc/core/harness/commands.py` | 🆕 | Command registry |
| `socc/core/harness/reference_data/socc_tools_snapshot.json` | 🆕 | Tools catalog |
| `socc/core/harness/reference_data/socc_agents_snapshot.json` | 🆕 | Agents catalog |
| `socc/core/harness/reference_data/socc_commands_snapshot.json` | 🆕 | Commands catalog |
| `socc/tools/bash/__init__.py` | 🆕 | Package init |
| `socc/tools/bash/security.py` | 🆕 | Command validation |
| `socc/tools/bash/permissions.py` | 🆕 | RBAC |
| `socc/tools/bash/sandbox.py` | 🆕 | Sandbox execution |
| `socc/agents/__init__.py` | 🆕 | Package init |
| `socc/agents/fork.py` | 🆕 | Subagent forking |
| `socc/agents/memory.py` | 🆕 | Agent memory |
| `socc/agents/built_in/__init__.py` | 🆕 | Package init |
| `socc/agents/built_in/soc_analyst.py` | 🆕 | General analyst |
| `socc/agents/built_in/ir_agent.py` | 🆕 | IR specialist |
| `socc/agents/built_in/threat_hunt.py` | 🆕 | Threat hunter |
| `socc/commands/__init__.py` | 🆕 | Package init |
| `socc/commands/case.py` | 🆕 | Case management |
| `socc/commands/hunt.py` | 🆕 | Threat hunting |
| `socc/plugins/__init__.py` | 🆕 | Plugin system |

### Contagem

- **Arquivos novos:** ~22 arquivos
- **Arquivos Python:** ~18 arquivos
- **Arquivos JSON:** ~3 arquivos
- **Linhas estimadas:** ~2500 linhas

### Dependências Necessárias

```toml
# pyproject.toml
[project]
dependencies = [
    # Existing
    "pyyaml>=6.0",
    "pydantic>=2.0",
    
    # New for harness
    "prompt-toolkit>=3.0",      # REPL
    "rich>=13.0",               # Rich output
    "sentence-transformers>=2.0",  # Embeddings (optional)
]
```