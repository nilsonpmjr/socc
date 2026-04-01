# Claude Code Python Port - Análise para SOCC Integration

> **Fonte:** `/home/nilsonpmjr/claude-code/` - Clean-room Python rewrite by Sigrid Jin (instructkr)
> **Data:** 2025-03-31
> **Objetivo:** Avaliar uso como base para o SOCC Harness

---

## 1. Visão Geral do Port

### 1.1 Origem
- **Autor:** Sigrid Jin (@instructkr) - Citado no WSJ (25B tokens usados em 2025)
- **Método:** Clean-room rewrite de TypeScript para Python
- **Ferramenta:** oh-my-codex (OmX) - Workflow orchestration sobre Codex
- **Licença:** Copyleft (ver essay sobre legalidade vs legitimidade)

### 1.2 Métricas
| Métrica | Valor |
|---------|-------|
| Total Python files | 54 |
| Tools catalogados | 184 |
| Commands catalogados | 207 |
| Subsystems | 30 |
| Reference data | JSON snapshots |

---

## 2. Arquitetura do Harness

### 2.1 Estrutura de Diretórios
```
src/
├── main.py              # CLI entrypoint (argparse)
├── models.py            # Dataclasses (Subsystem, PortingModule, PortingBacklog)
├── commands.py          # Command registry + snapshot loader
├── tools.py             # Tool registry + snapshot loader
├── runtime.py           # PortRuntime (prompt routing)
├── port_manifest.py     # Workspace manifest generation
├── query_engine.py      # Summary rendering
├── reference_data/      # JSON snapshots
│   ├── tools_snapshot.json
│   ├── commands_snapshot.json
│   └── subsystems/
│       ├── assistant.json
│       ├── cli.json
│       ├── hooks.json
│       └── ... (30 subsystems)
└── [30 subsystem directories]/
```

### 2.2 Principais Tools (por módulo)

| Tool | Arquivos | Descrição | Relevância SOC |
|------|----------|-----------|----------------|
| **AgentTool** | 20 | Sistema de subagentes | ⭐⭐⭐⭐⭐ |
| **BashTool** | 18 | Execução shell + segurança | ⭐⭐⭐⭐⭐ |
| **PowerShellTool** | 14 | Execução PowerShell | ⭐⭐⭐ |
| **FileEditTool** | 6 | Edição de arquivos | ⭐⭐⭐⭐ |
| **LSPTool** | 6 | Language Server | ⭐⭐ |
| **WebFetchTool** | 5 | HTTP requests | ⭐⭐⭐⭐ |
| **MCPTool** | 4 | Model Context Protocol | ⭐⭐⭐⭐⭐ |
| **SkillTool** | 4 | Sistema de skills | ⭐⭐⭐⭐⭐ |
| **GrepTool** | 3 | Search em arquivos | ⭐⭐⭐⭐ |
| **GlobTool** | 3 | File globbing | ⭐⭐⭐ |

### 2.3 Principais Commands (por funcionalidade)

| Command | Arquivos | Descrição | Relevância SOC |
|---------|----------|-----------|----------------|
| **plugin** | 17 | Sistema de plugins | ⭐⭐⭐⭐⭐ |
| **agents** | 2 | Gerenciamento de agentes | ⭐⭐⭐⭐⭐ |
| **mcp** | 4 | Model Context Protocol | ⭐⭐⭐⭐⭐ |
| **config** | 2 | Configuração | ⭐⭐⭐⭐ |
| **hooks** | 2 | Hooks system | ⭐⭐⭐⭐⭐ |
| **memory** | 2 | Gerenciamento de memória | ⭐⭐⭐⭐⭐ |
| **permissions** | 2 | Sistema de permissões | ⭐⭐⭐⭐⭐ |
| **doctor** | 2 | Diagnóstico | ⭐⭐⭐ |
| **review** | 4 | Code review | ⭐⭐⭐ |

---

## 3. Componentes de Alta Relevância para SOCC

### 3.1 BashTool (18 arquivos)
```
tools/BashTool/
├── BashTool.tsx           # Main component
├── bashCommandHelpers.ts  # Command parsing
├── bashPermissions.ts    # Permission system ⭐
├── bashSecurity.ts       # Security validation ⭐
├── commandSemantics.ts   # Semantic analysis
├── destructiveCommandWarning.ts  # Destructive ops ⭐
├── modeValidation.ts     # Mode checks
├── pathValidation.ts     # Path sanitization ⭐
├── readOnlyValidation.ts # Read-only mode
├── sedEditParser.ts      # Sed parsing
├── sedValidation.ts      # Sed validation
├── shouldUseSandbox.ts   # Sandbox decision ⭐
└── utils.ts
```

**Apliquível para SOCC:**
- `bashSecurity.ts` → Validação de comandos para SOC analysts
- `bashPermissions.ts` → RBAC para ferramentas de segurança
- `destructiveCommandWarning.ts` → Alertas para comandos perigosos
- `shouldUseSandbox.ts` → Sandbox para análise de malware

### 3.2 AgentTool (20 arquivos)
```
tools/AgentTool/
├── AgentTool.tsx
├── agentColorManager.ts
├── agentDisplay.ts
├── agentMemory.ts          # Agent memory ⭐
├── agentMemorySnapshot.ts  # State snapshots ⭐
├── agentToolUtils.ts
├── built-in/
│   ├── claudeCodeGuideAgent.ts
│   ├── exploreAgent.ts     # Exploration ⭐
│   ├── generalPurposeAgent.ts
│   ├── planAgent.ts        # Planning ⭐
│   ├── verificationAgent.ts  # Verification ⭐
│   └── statuslineSetup.ts
├── builtInAgents.ts
├── constants.ts
├── forkSubagent.ts         # Subagent forking ⭐
├── loadAgentsDir.ts        # Agent loading ⭐
├── prompt.ts
├── resumeAgent.ts          # Agent resumption ⭐
└── runAgent.ts             # Agent execution ⭐
```

**Aplicável para SOCC:**
- `forkSubagent.ts` → Criar subagentes especializados (IR, Threat Intel, etc)
- `agentMemory.ts` → Context retention em investigações longas
- `verificationAgent.ts` → Verificação de findings
- `loadAgentsDir.ts` → Carregar agentes SOC customizados

### 3.3 SkillTool (4 arquivos)
```
tools/SkillTool/
└── ... (prompt, execution, etc)
```

**Aplicável para SOCC:**
- Skills de análise de malware
- Skills de threat intelligence
- Skills de incident response

---

## 4. Proposta de Integração SOCC

### 4.1 Estrutura Proposta
```
socc/
├── core/
│   ├── harness/              # ← Baseado em claude-code/src
│   │   ├── __init__.py
│   │   ├── runtime.py        # Runtime principal
│   │   ├── commands.py       # Command registry
│   │   ├── tools.py          # Tool registry
│   │   └── models.py         # Dataclasses
│   ├── tools_registry.py     # ← Já implementado
│   ├── contracts.py          # ← Existente
│   └── engine.py             # ← Existente
├── tools/                    # ← Baseado em claude-code/tools
│   ├── bash/                 # BashTool adaptado
│   │   ├── security.py       # bashSecurity.ts
│   │   ├── permissions.py    # bashPermissions.ts
│   │   └── sandbox.py        # shouldUseSandbox.ts
│   ├── agent/                # AgentTool adaptado
│   │   ├── fork.py           # forkSubagent.ts
│   │   ├── memory.py         # agentMemory.ts
│   │   └── run.py            # runAgent.ts
│   └── soc/                  # ← Tools específicas SOC
│       ├── ioc_extractor.py  # ← Já existe (extract_iocs)
│       ├── defang.py         # ← Já existe
│       ├── vt_lookup.py      # VirusTotal
│       ├── mitre_attack.py   # MITRE ATT&CK
│       └── yara_scan.py      # YARA scanning
├── agents/                   # ← Baseado em AgentTool/built-in
│   ├── ir_agent.py           # Incident Response
│   ├── ti_agent.py           # Threat Intelligence
│   ├── malware_agent.py      # Malware Analysis
│   └── hunt_agent.py         # Threat Hunting
├── commands/                 # ← Baseado em claude-code/commands
│   ├── case.py               # Case management
│   ├── hunt.py               # Threat hunting
│   ├── report.py             # Report generation
│   └── pivot.py              # Pivot operations
└── plugins/                  # ← Baseado em plugin command
    ├── virustotal/
    ├── misp/
    └── opencti/
```

### 4.2 Comandos SOC Propostos
Adaptando commands do Claude Code:

| Claude Code | SOCC Equivalent | Descrição |
|-------------|-----------------|-----------|
| `/agents` | `/socc agents` | Gerenciar agentes SOC |
| `/memory` | `/socc case` | Case memory/context |
| `/hooks` | `/socc triggers` | Automation triggers |
| `/permissions` | `/socc rbac` | Role-based access |
| `/doctor` | `/socc check` | Environment check |
| `/review` | `/socc review` | Peer review de findings |
| `/plugins` | `/socc integrations` | Plugin management |
| `/config` | `/socc config` | Configuration |

### 4.3 Agents SOC Propostos
Baseado em AgentTool/built-in:

| Claude Agent | SOCC Agent | Função |
|--------------|------------|--------|
| `generalPurposeAgent` | `SOCAnalystAgent` | Análise geral |
| `exploreAgent` | `ThreatHuntAgent` | Threat hunting |
| `planAgent` | `IncidentResponseAgent` | IR planning |
| `verificationAgent` | `QualityAssuranceAgent` | Finding verification |

---

## 5. Roadmap de Integração

### Fase 1: Foundation (Sprint 1-2)
- [ ] Copiar estrutura base (`models.py`, `runtime.py`)
- [ ] Adaptar `tools_registry.py` para usar padrão do port
- [ ] Implementar `commands_registry.py`
- [ ] Setup `reference_data/` com tools SOC

### Fase 2: Core Tools (Sprint 3-4)
- [ ] Portar `BashTool/security.py`
- [ ] Portar `BashTool/permissions.py`
- [ ] Portar `BashTool/sandbox.py`
- [ ] Integrar com tools existentes (`extract_iocs`, `defang`)

### Fase 3: Agents (Sprint 5-6)
- [ ] Portar `AgentTool/fork.py`
- [ ] Portar `AgentTool/memory.py`
- [ ] Criar `SOCAnalystAgent`
- [ ] Criar `IncidentResponseAgent`

### Fase 4: Commands (Sprint 7-8)
- [ ] Implementar `/socc` CLI
- [ ] Adaptar commands para contexto SOC
- [ ] Integrar com case management

### Fase 5: Plugins (Sprint 9-10)
- [ ] Portar plugin system
- [ ] Criar plugins: VirusTotal, MISP, OpenCTI
- [ ] Documentar API de plugins

---

## 6. Riscos e Considerações

### 6.1 Legais
- **Status:** Clean-room rewrite (não copia código proprietário)
- **Licença do port:** Copyleft
- **Ação recomendada:** Manviar attribution e link para essay

### 6.2 Técnicos
- **Gap:** Port é "metadata-first" (snapshots JSON), não runtime completo
- **MITIGAÇÃO:** Usar como blueprint, implementar runtime real
- **Dependency:** Port não tem dependências externas pesadas

### 6.3 Compatibilidade
- **Python:** Port é Python 3.10+ (dataclasses, type hints)
- **SOCC:** Já usa Python 3.10+
- **Compatível:** ✅

---

## 7. Próximos Passos Imediatos

1. **Clonar estrutura:** `cp -r /home/nilsonpmjr/claude-code/src/socc/core/harness`
2. **Mapear tools:** Criar `socc_tools_snapshot.json`
3. **Adaptar runtime:** Modificar `runtime.py` para contexto SOC
4. **Testar integração:** Rodar testes existentes do SOCC

---

## 8. Referências

- **Repositório:** `github.com/instructkr/claude-code`
- **Essay:** "Is legal the same as legitimate: AI reimplementation and the erosion of copyleft"
- **WSJ Article:** "The Trillion Dollar Race to Automate Our Entire Lives" (Mar 21, 2026)
- **oh-my-codex:** `github.com/Yeachan-Heo/oh-my-codex`

---

## Apêndice A: Lista Completa de Tools

```
AgentTool (20)          BashTool (18)          PowerShellTool (14)
FileEditTool (6)        LSPTool (6)             BriefTool (5)
ConfigTool (5)          FileReadTool (5)        ScheduleCronTool (5)
WebFetchTool (5)        EnterPlanModeTool (4)   EnterWorktreeTool (4)
ExitPlanModeTool (4)    ExitWorktreeTool (4)    MCPTool (4)
NotebookEditTool (4)    SendMessageTool (4)     SkillTool (4)
TeamCreateTool (4)      TeamDeleteTool (4)      FileWriteTool (3)
GlobTool (3)            GrepTool (3)            ListMcpResourcesTool (3)
ReadMcpResourceTool (3) RemoteTriggerTool (3)   TaskCreateTool (3)
TaskGetTool (3)         TaskListTool (3)        TaskStopTool (3)
TaskUpdateTool (3)      TodoWriteTool (3)       ToolSearchTool (3)
WebSearchTool (3)       AskUserQuestionTool (2) REPLTool (2)
TaskOutputTool (2)      McpAuthTool (1)         SleepTool (1)
SyntheticOutputTool (1)
```

## Apêndice B: Lista Completa de Subsystems

```
assistant     bootstrap     bridge        buddy         cli
components    constants     coordinator   entrypoints   hooks
keybindings   memdir        migrations    moreright     native_ts
outputStyles  plugins       remote        schemas       screens
server        services      skills        state         types
upstreamproxy utils         vim           voice
```