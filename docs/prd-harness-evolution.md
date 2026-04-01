# PRD: SOCC Harness Evolution

**Versão:** 1.2.0  
**Data:** 2026-03-31  
**Status:** Draft  
**Autor:** Análise comparativa com pi-coding-agent + diagnóstico de prompt bloat
**Integração:** Claude Code Python Port (instructkr/claude-code)

---

## 0. Integration Source

### Claude Code Python Port

Este PRD incorpora a arquitetura do **Claude Code Python Port** por Sigrid Jin (instructkr),
um clean-room rewrite do harness do Claude Code de TypeScript para Python.

> **Repositório:** `/home/nilsonpmjr/claude-code/` (local) | `github.com/instructkr/claude-code`
> **Métricas:** 184 tools | 207 commands | 30 subsystems | 54 Python files
> **Análise Detalhada:** `docs/claude-code-port-analysis.md`

**Componentes a Integrar:**

| Port Component | Source Path | SOCC Target | Prioridade |
|----------------|-------------|-------------|------------|
| `models.py` | `src/models.py` | `socc/core/harness/models.py` | P0 |
| `runtime.py` | `src/runtime.py` | `socc/core/harness/runtime.py` | P0 |
| `commands.py` | `src/commands.py` | `socc/core/harness/commands.py` | P0 |
| `BashTool/security` | `tools/BashTool/*Security*.ts` | `socc/tools/bash/security.py` | P0 |
| `AgentTool/fork` | `tools/AgentTool/forkSubagent.ts` | `socc/agents/fork.py` | P1 |
| `AgentTool/memory` | `tools/AgentTool/agentMemory.ts` | `socc/agents/memory.py` | P1 |
| Plugin System | `commands/plugin/` | `socc/plugins/` | P1 |

---

## 1. Executive Summary

### Problem Statement

O SOCC atual opera como um assistente de triagem SOC com capacidades limitadas de interação: fluxo request-response básico, tools hardcoded, e sem sistema de extensibilidade. Comparado com harnesses modernos como o **pi-coding-agent** e o **Claude Code harness**, o SOCC carece de: sistema de ferramentas dinâmico, CLI interativo, gerenciamento de sessões robusto, e capacidade de extensão via plugins.

### Proposed Solution

Transformar o SOCC de um "script de análise" para um **harness de agente SOC completo**, adotando padrões estabelecidos pelo Claude Code Python Port e adaptando para o domínio de Security Operations. Isso inclui:

1. **Sistema de Tools Dinâmico** - Registry extensível baseado no port (184 tools)
2. **CLI Interativo estilo REPL** - Interface profissional inspirada no Claude Code CLI
3. **Sistema de Plugins** - Extensibilidade via sistema do port (207 commands)
4. **Sistema de Agentes** - Fork de subagentes especializados (IR, TI, Hunt)
5. **BashTool Security** - Validação de comandos, RBAC, sandbox
6. **Memória Persistente com RAG** - Contexto persistente entre sessões
7. **Gerenciamento de Sessões** - Resume, fork, e export de sessões
8. **Context Budget Manager** - Orçamento de contexto por modelo

### Success Criteria

| Métrica | Baseline | Target | Prazo |
|---------|----------|--------|-------|
| Número de tools disponíveis | 3 | 15+ | v0.2.0 |
| Tempo de inicialização CLI | ~3s | <1s | v0.2.0 |
| Capacidade de extensão | 0 plugins | plugins carregáveis | v0.3.0 |
| Latência de memória RAG | N/A | <100ms | v0.3.0 |
| Satisfação do usuário (NPS) | TBD | >50 | v0.4.0 |

---

## 2. User Experience & Functionality

### 2.1 User Personas

**Persona 1: Ana - Analista SOC Sênior**

- Usa SOCC para triagem de alertas 8h/dia
- Precisa de respostas rápidas com contexto
- Frustrada com limitações de ferramentas
- Quer customizar fluxos de análise

**Persona 2: Carlos - Engenheiro de Segurança**

- Integra SOCC com pipelines existentes
- Desenvolve parsers customizados
- Precisa de API estável e extensível
- Quer adicionar funcionalidades sem modificar core

**Persona 3: Equipe de Threat Intel**

- Enriquece IOCs automaticamente
- Precisa de integração com múltiplas fontes
- Quer usar tools específicas do domínio
- Precisa de memória entre sessões

### 2.2 User Stories

#### US-001: Sistema de Tools Dinâmico

```
As an: Analista SOC
I want: Usar diferentes ferramentas dependendo do contexto
So that: Posso executar análises especializadas sem mudar de aplicação

Acceptance Criteria:
- [ ] Registry de tools carregável dinamicamente
- [ ] Tools SOC: extract_iocs, defang, enrich_ioc, query_mitre, http_get
- [ ] Tools de sistema: read, write, edit, bash, grep, find
- [ ] Configuração via ~/.socc/tools.json
- [ ] Fallback gracioso quando tool não disponível
```

#### US-002: CLI Interativo

```
As an: Analista SOC
I want: Interface de linha de comando interativa tipo REPL
So that: Posso ter conversas multi-turno com contexto mantido

Acceptance Criteria:
- [ ] Comando `socc` inicia REPL interativo
- [ ] Histórico de comandos com seta para cima/baixo
- [ ] Auto-complete de comandos e paths
- [ ] Suporte a @arquivo.txt para incluir arquivos
- [ ] Flag --continue para retomar última sessão
- [ ] Flag --resume para selecionar sessão anterior
- [ ] Timeout configurável para comandos longos
```

#### US-003: Sistema de Plugins

```
As an: Engenheiro de Segurança
I want: Criar plugins customizados sem modificar o core
So that: Posso estender funcionalidades para casos específicos

Acceptance Criteria:
- [ ] Diretório ~/.socc/extensions/ para plugins
- [ ] Manifesto JSON com metadados do plugin
- [ ] Hook system para eventos do lifecycle
- [ ] Registro de tools via plugin
- [ ] Registro de skills via plugin
- [ ] Isolamento de dependências por plugin
```

#### US-004: Memória Persistente com RAG

```
As an: Analista SOC
I want: Que o sistema lembre de análises anteriores relevantes
So that: Não preciso repetir contexto em cada sessão

Acceptance Criteria:
- [ ] Armazenamento em ~/.socc/memory/<agent_id>.jsonl
- [ ] Busca semântica via embeddings
- [ ] Recuperação de memórias relevantes por query
- [ ] Limite configurável de contexto recuperado
- [ ] API: memory.remember(key, value), memory.recall(query)
```

#### US-005: Gerenciamento de Sessões

```
As an: Analista SOC
I want: Gerenciar múltiplas sessões de análise
So that: Posso trabalhar em casos diferentes simultaneamente

Acceptance Criteria:
- [ ] Listar sessões com `socc sessions list`
- [ ] Retomar sessão com `socc --resume <id>`
- [ ] Clonar sessão com `socc session fork <id>`
- [ ] Exportar sessão para HTML/Markdown
- [ ] Limite configurável de sessões armazenadas
```

#### US-006: Streaming com Tool Calling

```
As an: Analista SOC
I want: Ver progresso durante análises longas
So that: Sei que o sistema está trabalhando

Acceptance Criteria:
- [ ] SSE para streaming de resposta
- [ ] Eventos de phase: detect, parse, ti, analysis, draft
- [ ] Eventos de tool_call antes da execução
- [ ] Eventos de tool_result após execução
- [ ] Progress bar para análises longas
```

#### US-007: Contratos Versionados

```
As an: Desenvolvedor integrando SOCC
I want: APIs estáveis com versionamento explícito
So that: Alterações não quebram integrações existentes

Acceptance Criteria:
- [ ] contract_version em todos os envelopes
- [ ] Backward compatibility com v1
- [ ] Documentação de mudanças entre versões
- [ ] Migration guide para cada nova versão
- [ ] Deprecation warnings para campos obsoletos
```

#### US-008: Context Budget Manager (Suporte a LLMs de Baixo Contexto)

```
As an: Analista SOC usando modelos locais com janela de contexto limitada
I want: Que o sistema ajuste automaticamente o tamanho do prompt ao modelo ativo
So that: Posso usar modelos como llama3.2:3b (8K) sem estourar contexto

Acceptance Criteria:
- [ ] Estimativa de tokens antes de montar o prompt
- [ ] Budget dinâmico por seção (persona, references, skill, history, KB, payload)
- [ ] Truncagem inteligente por prioridade (payload > skill > history > references > persona)
- [ ] Perfil de contexto por modelo (não apenas por response_mode)
- [ ] Compactação de histórico via resumo quando necessário
- [ ] Métricas de utilização de contexto visíveis no runtime
```

### 2.3 Non-Goals

- **Não é LLM Training**: SOCC continua sendo harness/consumer de LLMs
- **Não é SOAR Completo**: Foco em assistência ao analista, não automação total
- **Não substitui SIEM**: Integra com SIEMs existentes, não compete
- **Não é Chat App**: CLI e API primeiro; UI web é secundária

---

## 3. AI System Requirements

### 3.1 Tool Requirements

O sistema de tools deve suportar:

| Categoria | Tools | Prioridade |
|-----------|-------|------------|
| **IOC Processing** | extract_iocs, defang, decode_base64, enrich_ioc | P0 |
| **File Operations** | read, write, edit | P1 |
| **Shell Operations** | bash | P1 |
| **Search** | grep, find | P2 |
| **Network** | http_get, dns_lookup | P2 |
| **Threat Intel** | query_mitre, query_virustotal, query_otx | P2 |

### 3.2 Evaluation Strategy

**Métricas Quantitativas:**

```python
# Benchmark de tools
benchmark_tools = {
    "extract_iocs": {
        "dataset": "test_fixtures/iocs/*.txt",
        "expected": "test_fixtures/iocs/*.expected.json",
        "metrics": ["precision", "recall", "f1"],
        "target": {"precision": 0.95, "recall": 0.90, "f1": 0.92}
    },
    "memory_recall": {
        "dataset": "test_fixtures/memory/*.jsonl",
        "metrics": ["relevance_score", "latency_ms"],
        "target": {"relevance_score": 0.85, "latency_ms": 100}
    }
}
```

**Métricas Qualitativas:**

- Usabilidade (teste com 5 analistas)
- Documentação completa (>90% coverage)
- Examples e tutorials

### 3.3 Memory & Context Requirements

```yaml
memory_config:
  storage: ~/.socc/memory/
  format: jsonl
  max_entries_per_session: 1000
  embedding_model: sentence-transformers/all-MiniLM-L6-v2
  vector_store: sqlite_vec  # lightweight, local
  retrieval:
    top_k: 5
    min_score: 0.7
  cleanup:
    max_age_days: 90
    max_total_mb: 500
```

---

## 4. Technical Specifications

### 4.1 Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLI Layer                                │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐   │
│  │   REPL   │ │  Batch   │ │  Serve   │ │   Extensions     │   │
│  │  Mode    │ │  Mode    │ │  Mode    │ │   CLI            │   │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────────┬─────────┘   │
│       │            │            │                  │           │
└───────┼────────────┼────────────┼──────────────────┼───────────┘
        │            │            │                  │
┌───────┴────────────┴────────────┴──────────────────┴───────────┐
│                      Core Engine                                │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────────┐   │
│  │   Engine    │ │  Contracts  │ │      Tool Registry      │   │
│  │   (v2.0)    │ │  (v2.0)     │ │                         │   │
│  └─────┬───────┘ └─────────────┘ └─────────────────────────┘   │
│        │                    │                    │              │
│  ┌─────┴────────┐ ┌────────┴────────┐ ┌────────┴────────────┐  │
│  │   Memory     │ │    Prompts      │ │     Extensions      │  │
│  │   Manager    │ │    Templates    │ │     Manager         │  │
│  └──────────────┘ └─────────────────┘ └─────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
        │
┌───────┴───────────────────────────────────────────────────────┐
│                      Gateway Layer                              │
│  ┌───────────────┐ ┌───────────────┐ ┌─────────────────────┐   │
│  │ LLM Gateway   │ │ Threat Intel  │ │    MCP Gateway      │   │
│  │ (Ollama etc)  │ │   Gateway     │ │                     │   │
│  └───────────────┘ └───────────────┘ └─────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
        │
┌───────┴───────────────────────────────────────────────────────┐
│                      Storage Layer                             │
│  ┌───────────┐ ┌───────────────┐ ┌─────────────────────────┐  │
│  │ Sessions  │ │    Memory     │ │     Knowledge Base      │  │
│  │ (SQLite)  │ │   (JSONL)     │ │      (SQLite)           │  │
│  └───────────┘ └───────────────┘ └─────────────────────────┘  │
└───────────────────────────────────────────────────────────────┘
```

### 4.2 Component Specifications

#### 4.2.1 Tool Registry

```python
# socc/core/tools_registry.py

TOOL_REGISTRY: dict[str, ToolSpec] = {}

@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, ParamSpec]
    handler: Callable
    requires_auth: bool = False
    risk_level: str = "low"  # low, medium, high
    category: str = "utility"

def register_tool(spec: ToolSpec) -> None:
    """Registra uma tool no registry global."""
    TOOL_REGISTRY[spec.name] = spec

def invoke_tool(name: str, arguments: dict) -> ToolResult:
    """Invoca uma tool pelo nome com argumentos."""
    spec = TOOL_REGISTRY.get(name)
    if not spec:
        raise ToolNotFoundError(f"Tool '{name}' not found")
    
    # Validar parâmetros
    validate_params(spec.parameters, arguments)
    
    # Verificar permissões
    if spec.requires_auth and not has_auth():
        raise AuthRequiredError(f"Tool '{name}' requires authentication")
    
    # Executar
    return spec.handler(**arguments)
```

#### 4.2.2 Memory Manager

```python
# socc/core/memory_manager.py

class MemoryManager:
    """Gerencia memória persistente com RAG."""
    
    def __init__(self, agent_id: str, config: MemoryConfig):
        self.db_path = config.storage / f"{agent_id}.jsonl"
        self.embeddings = EmbeddingModel(config.embedding_model)
        self.vector_store = SQLiteVec(config.storage / f"{agent_id}.vec")
    
    def remember(
        self, 
        key: str, 
        value: Any, 
        metadata: dict | None = None
    ) -> str:
        """Armazena uma memória."""
        entry = {
            "id": generate_uuid(),
            "key": key,
            "value": value,
            "metadata": metadata or {},
            "embedding": self.embeddings.encode(f"{key}: {value}"),
            "timestamp": utc_now(),
        }
        self._append_entry(entry)
        self.vector_store.insert(entry)
        return entry["id"]
    
    def recall(
        self, 
        query: str, 
        limit: int = 5,
        min_score: float = 0.7
    ) -> list[MemoryEntry]:
        """Recupera memórias relevantes via RAG."""
        query_embedding = self.embeddings.encode(query)
        results = self.vector_store.search(
            query_embedding, 
            k=limit,
            min_score=min_score
        )
        return [self._load_entry(r.id) for r in results]
    
    def forget(
        self, 
        key: str | None = None,
        before: datetime | None = None
    ) -> int:
        """Remove memórias antigas ou específicas."""
        # Implementation
        pass
```

#### 4.2.3 Extension Manager

```python
# socc/core/extensions.py

@dataclass
class ExtensionManifest:
    name: str
    version: str
    description: str
    author: str
    tools: list[str]
    skills: list[str]
    hooks: dict[str, str]  # event -> handler
    dependencies: list[str]

class ExtensionManager:
    """Gerencia plugins carregáveis."""
    
    def __init__(self, extensions_dir: Path):
        self.extensions_dir = extensions_dir
        self.loaded: dict[str, Extension] = {}
    
    def discover(self) -> list[ExtensionManifest]:
        """Descobre extensões disponíveis."""
        manifests = []
        for ext_dir in self.extensions_dir.iterdir():
            manifest_path = ext_dir / "manifest.json"
            if manifest_path.exists():
                manifests.append(parse_manifest(manifest_path))
        return manifests
    
    def load(self, name: str) -> Extension:
        """Carrega uma extensão."""
        ext_dir = self.extensions_dir / name
        manifest = parse_manifest(ext_dir / "manifest.json")
        
        # Carregar tools
        for tool_name in manifest.tools:
            tool_module = import_module(f"{ext_dir}.{tool_name}")
            register_tool(tool_module.get_tool_spec())
        
        # Carregar skills
        for skill_name in manifest.skills:
            skill_path = ext_dir / "skills" / f"{skill_name}.md"
            register_skill(skill_name, skill_path)
        
        # Registrar hooks
        extension = Extension(manifest, ext_dir)
        self.loaded[name] = extension
        
        return extension
```

#### 4.2.4 Session Manager

```python
# socc/cli/session_manager.py

@dataclass
class Session:
    id: str
    created_at: datetime
    updated_at: datetime
    title: str
    messages: list[Message]
    metadata: dict

class SessionManager:
    """Gerencia sessões de conversa."""
    
    def __init__(self, sessions_dir: Path):
        self.sessions_dir = sessions_dir
    
    def create(self, title: str = "") -> Session:
        """Cria uma nova sessão."""
        session = Session(
            id=generate_uuid(),
            created_at=utc_now(),
            updated_at=utc_now(),
            title=title,
            messages=[],
            metadata={}
        )
        self._save(session)
        return session
    
    def list(self, limit: int = 20) -> list[SessionMeta]:
        """Lista sessões existentes."""
        sessions = []
        for session_file in self.sessions_dir.glob("*.jsonl"):
            meta = self._load_meta(session_file)
            sessions.append(meta)
        return sorted(sessions, key=lambda s: s.updated_at, reverse=True)[:limit]
    
    def resume(self, session_id: str | None = None) -> Session:
        """Retoma uma sessão existente."""
        if session_id:
            return self._load(session_id)
        # Retorna a última sessão
        sessions = self.list(limit=1)
        if not sessions:
            return self.create()
        return self._load(sessions[0].id)
    
    def fork(self, session_id: str) -> Session:
        """Cria uma cópia de uma sessão."""
        original = self._load(session_id)
        forked = Session(
            id=generate_uuid(),
            created_at=utc_now(),
            updated_at=utc_now(),
            title=f"Fork of {original.title}",
            messages=original.messages.copy(),
            metadata={"forked_from": session_id}
        )
        self._save(forked)
        return forked
    
    def export(
        self, 
        session_id: str, 
        format: str = "html"
    ) -> Path:
        """Exporta sessão para HTML ou Markdown."""
        session = self._load(session_id)
        if format == "html":
            return self._export_html(session)
        return self._export_markdown(session)
```

### 4.3 Integration Points

```yaml
# ~/.socc/config.yaml

llm:
  backend: ollama
  model: qwen3.5:9b
  endpoint: http://localhost:11434
  
memory:
  enabled: true
  embedding_model: all-MiniLM-L6-v2
  max_entries: 10000
  
extensions:
  auto_load: true
  directories:
    - ~/.socc/extensions
    - ~/.socc/workspace/*/extensions
    
tools:
  enabled:
    - extract_iocs
    - defang
    - read
    - write
    - bash
  risk_limits:
    high: []  # require explicit approval
    medium: []  # log only
    low: ["*"]  # always allowed
    
sessions:
  max_stored: 100
  auto_title: true
  export_format: html
```

#### 4.2.5 Context Budget Manager

```python
# socc/core/context_budget.py

@dataclass
class ContextBudget:
    """Orçamento de tokens por seção do prompt."""
    total_budget: int          # janela de contexto do modelo
    reserved_output: int       # tokens reservados para geração
    available: int             # total_budget - reserved_output
    sections: dict[str, int]   # orçamento por seção

class ContextBudgetManager:
    """Gerencia orçamento de contexto baseado no modelo ativo."""

    # Perfis de janela de contexto por modelo
    MODEL_PROFILES = {
        "llama3.2:3b":   {"context_window": 8192,  "effective": 6000},
        "llama3.2:8b":   {"context_window": 8192,  "effective": 6000},
        "qwen3.5:9b":    {"context_window": 32768, "effective": 28000},
        "qwen3.5:14b":   {"context_window": 32768, "effective": 28000},
        "mistral:7b":    {"context_window": 32768, "effective": 24000},
    }

    # Prioridade de seções (maior = cortado primeiro)
    SECTION_PRIORITY = {
        "payload":     1,   # nunca cortar
        "skill":       2,   # essencial
        "identity":    3,   # persona curta
        "history":     4,   # resumir se necessário
        "knowledge":   5,   # truncar
        "references":  6,   # truncar/omitir
        "memory":      7,   # omitir se apertado
        "vantage":     8,   # omitir se apertado
    }

    def compute_budget(
        self,
        model: str,
        response_mode: str,
        sections: dict[str, str],
    ) -> ContextBudget:
        """Calcula orçamento e trunca seções por prioridade."""
        ...

    def estimate_tokens(self, text: str) -> int:
        """Estimativa rápida: ~4 chars por token (heurística)."""
        return max(1, len(text) // 4)

    def summarize_history(
        self,
        history: list[dict[str, str]],
        max_tokens: int,
    ) -> str:
        """Compacta histórico quando excede orçamento."""
        ...
```

### 4.4 Security & Privacy

| Aspecto | Especificação |
|---------|---------------|
| **Dados Locais** | Todos os dados em ~/.socc/ com permissões 700 |
| **Redação de Logs** | IPs, emails, hashes redigidos automaticamente |
| **API Keys** | Armazenadas encrypted em ~/.socc/credentials/ |
| **Tool Sandbox** | Tools de sistema rodam em sandbox limitado |
| **Rate Limiting** | Máximo 100 tool calls por sessão |
| **Audit Trail** | Todas as chamadas logadas com hash do input |

---

## 5. Risks & Roadmap

### 5.1 Phased Rollout

```
┌─────────────────────────────────────────────────────────────────┐
│ Phase 1: Foundation (v0.2.0) - 2 semanas                        │
├─────────────────────────────────────────────────────────────────┤
│ • Sistema de tools dinâmico                                     │
│ • Refatoração de contracts.py para v2.0                        │
│ • CLI básico com REPL                                           │
│ • Testes unitários para tool registry                           │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│ Phase 2: Core Features (v0.3.0) - 3 semanas                     │
├─────────────────────────────────────────────────────────────────┤
│ • Sistema de plugins/extensões                                  │
│ • Memory manager com RAG                                        │
│ • Session manager completo                                       │
│ • Streaming com tool calling                                    │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│ Phase 3: Polish (v0.4.0) - 2 semanas                            │
├─────────────────────────────────────────────────────────────────┤
│ • Auto-complete no CLI                                          │
│ • Export de sessões (HTML/Markdown)                            │
│ • Documentação completa                                         │
│ • Benchmark de performance                                      │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│ Phase 4: Advanced (v0.5.0) - 3 semanas                         │
├─────────────────────────────────────────────────────────────────┤
│ • Multi-agent support                                           │
│ • Workflow automation                                            │
│ • Integration com SOAR tools (Shuffle, etc)                    │
│ • UI web melhorada                                               │
└─────────────────────────────────────────────────────────────────┘
```

### 5.2 Technical Risks

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Performance de RAG com muitos documentos | Média | Alto | Limitar contexto, usar sqlite-vec otimizado |
| Compatibilidade com Python 3.10 | Baixa | Médio | Testes CI em múltiplas versões |
| Breaking changes em LLM backends | Média | Alto | Abstração via gateway, testes de integração |
| Segurança em tools de sistema | Média | Crítico | Sandbox, whitelist, rate limiting |
| Complexidade de plugins | Alta | Médio | Documentação extensa, examples |

### 5.3 Dependencies

```toml
# pyproject.toml additions

[project.dependencies]
# Existing...
# New for harness evolution:
sqlite-vec = ">=0.1.0"  # Vector store leve
sentence-transformers = ">=2.2.0"  # Embeddings
prompt-toolkit = ">=3.0.0"  # CLI interativo
rich = ">=13.0.0"  # Output formatting
pydantic = ">=2.0.0"  # Schema validation (already have)
```

---

## 6. Appendix

### A. Comparison: SOCC vs Pi

| Feature | SOCC (Current) | Pi | SOCC (Target) |
|---------|----------------|-----|---------------|
| Tools Registry | 3 hardcoded | Dynamic | Dynamic v0.2.0 |
| CLI Mode | Batch only | REPL + Batch | REPL v0.2.0 |
| Plugins | None | Extensions | Extensions v0.3.0 |
| Memory | Session only | Persistent + RAG | RAG v0.3.0 |
| Sessions | Basic | Resume/Fork/Export | Full v0.3.0 |
| Contracts | v1.0 | Simple | v2.0 v0.2.0 |
| Streaming | SSE | SSE + Tool Calls | Tool Calls v0.3.0 |

### B. File Structure After Implementation

```
socc/
├── cli/
│   ├── main.py            # Entry point
│   ├── repl.py            # NEW: Interactive REPL
│   ├── session_manager.py # NEW: Session management
│   ├── completions.py     # NEW: Auto-complete
│   └── ...
├── core/
│   ├── engine.py
│   ├── contracts.py       # Updated: v2.0
│   ├── tools_registry.py  # NEW: Dynamic tools
│   ├── memory_manager.py  # NEW: RAG memory
│   ├── extensions.py      # NEW: Plugin system
│   ├── session_store.py   # NEW: Session persistence
│   └── ...
├── tools/                 # NEW: Tool implementations
│   ├── __init__.py
│   ├── ioc.py            # extract_iocs, defang, etc
│   ├── file.py           # read, write, edit
│   ├── shell.py          # bash, grep, find
│   └── network.py        # http_get, dns_lookup
├── extensions/            # NEW: Built-in extensions
│   └── threat_intel/
│       ├── manifest.json
│       └── plugin.py
└── ...
```

### C. Metrics Dashboard

```yaml
# ~/.socc/metrics.json

{
  "tools": {
    "total_calls": 1523,
    "by_tool": {
      "extract_iocs": 450,
      "read": 320,
      "bash": 280,
      ...
    },
    "avg_latency_ms": 45,
    "error_rate": 0.02
  },
  "memory": {
    "total_entries": 2300,
    "avg_recall_latency_ms": 78,
    "cache_hit_rate": 0.85
  },
  "sessions": {
    "total": 45,
    "avg_messages_per_session": 12,
    "avg_session_duration_min": 8.5
  }
}
```

---

**Documento aprovado por:** _[A definir]_  
**Próxima revisão:** _[A definir]_