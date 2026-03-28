# Gap Analysis: OpenClaw CLI vs SOCC CLI

**Data:** 2026-03-28
**Objetivo:** Identificar gaps entre a experiencia interativa do OpenClaw e o SOCC, com mapeamento direto de comportamentos a trazer para o CLI do SOCC.

---

## 1. Resumo dos Gaps

| Area | OpenClaw | SOCC Hoje | Gap |
|------|----------|-----------|-----|
| Onboarding wizard | Multi-step interativo (25+ opcoes de auth, deteccao automatica) | `socc onboard` chama `bootstrap_runtime()` + `doctor` sem prompts | **CRITICO** |
| Configuracao de providers | Wizard com selecao de provider, teste de conexao, fallback chain | `.env` manual, sem wizard | **CRITICO** |
| Auth/Login de cloud | OAuth flow (OpenAI), API key entry com masking, SecretRef | Nenhum — usuario edita `.env` na mao | **CRITICO** |
| Base de conhecimento | Workspace git com `MEMORY.md`, `SOUL.md`, `USER.md`, daily memory | `~/.socc/intel/` com `sources.json` mas sem wizard de configuracao | **ALTO** |
| Model management | `models list/set/fallbacks add`, profiles Fast/Balanced/Deep | Deteccao existe em `llm_gateway.py` mas sem selecao interativa | **ALTO** |
| Config management | `config get/set/unset/validate` + JSON schema | `update_env_assignment()` basico, sem CLI de config | **ALTO** |
| Agent management | `agents list/add/bind/set-identity`, multiple agents | `list_available_agents()` existe mas sem CLI para gerenciar | **MEDIO** |
| Health checks guiados | `--skip-health`, probe integrado no onboard | `socc doctor` existe mas nao e interativo | **MEDIO** |
| Shell completions | Bash/Zsh/Fish/PowerShell geradas automaticamente | Nenhuma | **BAIXO** |
| Config audit trail | `config-audit.jsonl` com hash chain | Nenhum | **BAIXO** |
| Daemon install | `--skip-daemon`, `--no-install-daemon` com service runtime choice | `install.sh` instala mas sem wizard | **BAIXO** |

---

## 2. Mapeamento Detalhado: O Que Trazer do OpenClaw

### 2.1 Wizard de Onboarding (`socc onboard`)

**OpenClaw faz:**
```
openclaw onboard [--flow quickstart|advanced|manual]
  1. Auth provider selection (25+ opcoes)
  2. API key/token entry (mascarado)
  3. Gateway port/auth/bind
  4. Channel setup (WhatsApp QR, Telegram, Discord)
  5. Workspace directory selection
  6. Agent identity setup
  7. Skills installation
  8. Search provider config
  9. Health checks
  10. Daemon install
```

**Traduzido para o SOCC — fluxo proposto:**
```
socc onboard [--flow rapido|completo|manual]

  Etapa 1: Runtime Home
  ┌─────────────────────────────────────────────────┐
  │ Onde deseja instalar o runtime do SOCC?          │
  │ > ~/.socc (padrao)                               │
  │   /opt/socc                                      │
  │   Outro caminho...                               │
  │                                                  │
  │ [Runtime existente detectado em ~/.socc]          │
  │ Deseja reaproveitar? (S/n)                       │
  └─────────────────────────────────────────────────┘

  Etapa 2: Base Local de Conhecimento
  ┌─────────────────────────────────────────────────┐
  │ Aponte a pasta da sua base local de conhecimento │
  │ (SOPs, playbooks, regras, modelos de nota):      │
  │                                                  │
  │ Caminho: /home/user/Documentos/Alertas           │
  │                                                  │
  │ Tipo de fonte:                                   │
  │ > document_set (pasta de documentos)             │
  │   case_notes (notas de caso)                     │
  │                                                  │
  │ Nivel de confianca:                              │
  │ > internal (documentacao interna do time)        │
  │   curated_external (fonte externa curada)        │
  │                                                  │
  │ Tags (separadas por virgula): sop,playbook       │
  │                                                  │
  │ Indexar agora? (S/n)                             │
  └─────────────────────────────────────────────────┘

  Etapa 3: Backend de Inferencia
  ┌─────────────────────────────────────────────────┐
  │ Qual backend de inferencia deseja usar?          │
  │                                                  │
  │ Backends locais detectados:                      │
  │   ✓ Ollama em http://localhost:11434             │
  │   ✗ LM Studio nao encontrado                    │
  │   ✗ vLLM nao encontrado                         │
  │                                                  │
  │ > ollama (Local - recomendado, GPU detectada)    │
  │   lmstudio (Local)                               │
  │   vllm (Local)                                   │
  │   openai-compatible (Local ou remoto)            │
  │   anthropic (Nuvem)                              │
  │   auto (detectar melhor disponivel)              │
  └─────────────────────────────────────────────────┘

  Etapa 4: Selecao de Modelos
  ┌─────────────────────────────────────────────────┐
  │ Modelos instalados no Ollama:                    │
  │   1. qwen3.5:9b (9.2 GB)                        │
  │   2. llama3.2:3b (2.1 GB)                       │
  │   3. qwen3:4b (3.8 GB)                          │
  │                                                  │
  │ Perfil Fast (rapido, triagem):                   │
  │ > llama3.2:3b                                    │
  │                                                  │
  │ Perfil Balanced (equilibrado, analise):          │
  │ > qwen3.5:9b                                     │
  │                                                  │
  │ Perfil Deep (profundo, drafts complexos):        │
  │ > qwen3.5:9b                                     │
  │                                                  │
  │ GPU detectada: NVIDIA RTX 3060 (12GB)            │
  │ Device preferido: gpu (S/n)                      │
  └─────────────────────────────────────────────────┘

  Etapa 5: Providers de Nuvem (opcional)
  ┌─────────────────────────────────────────────────┐
  │ Deseja configurar um provider de nuvem como      │
  │ fallback? (s/N)                                  │
  │                                                  │
  │ Provider:                                        │
  │ > anthropic                                      │
  │   openai-compatible                              │
  │   Pular                                          │
  │                                                  │
  │ API Key Anthropic: ****************************  │
  │ Modelo: claude-haiku-4-5-20251001 (padrao)       │
  │                                                  │
  │ Testar conexao? (S/n)                            │
  │ ✓ Conexao OK — modelo disponivel                 │
  └─────────────────────────────────────────────────┘

  Etapa 6: Threat Intelligence (opcional)
  ┌─────────────────────────────────────────────────┐
  │ Deseja integrar com Threat Intelligence Tool?    │
  │ (s/N)                                            │
  │                                                  │
  │ URL da API TI: http://localhost:8000             │
  │ Usuario: admin                                   │
  │ Senha: ********                                  │
  │                                                  │
  │ Testar conexao? (S/n)                            │
  │ ✓ Conexao OK                                     │
  └─────────────────────────────────────────────────┘

  Etapa 7: Vantage API (opcional)
  ┌─────────────────────────────────────────────────┐
  │ Deseja integrar com Vantage API?                 │
  │ (s/N)                                            │
  │                                                  │
  │ URL base: https://vantage.example.com            │
  │ Metodo de auth:                                  │
  │ > Bearer Token                                   │
  │   API Key                                        │
  │                                                  │
  │ Token: ****************************              │
  │ Verificar TLS? (S/n)                             │
  │                                                  │
  │ Modulos disponiveis:                             │
  │ [x] incident-summary                             │
  │ [x] threat-context                               │
  │ [ ] asset-enrichment                             │
  │ [ ] user-behavior                                │
  │                                                  │
  │ Testar conexao? (S/n)                            │
  │ ✓ Conexao OK — 2 modulos ativos                  │
  └─────────────────────────────────────────────────┘

  Etapa 8: Agente Ativo
  ┌─────────────────────────────────────────────────┐
  │ Agentes disponiveis:                             │
  │ > soc-copilot (analise SOC, classificacao,       │
  │   triage, drafts)                                │
  │                                                  │
  │ Skills do agente soc-copilot:                    │
  │   ✓ payload-triage                               │
  │   ✓ phishing-analysis                            │
  │   ✓ suspicious-url                               │
  │   ✓ malware-behavior                             │
  │   ✓ soc-generalist                               │
  └─────────────────────────────────────────────────┘

  Etapa 9: Pasta de Saida
  ┌─────────────────────────────────────────────────┐
  │ Onde salvar notas e drafts gerados?              │
  │ Caminho: ~/Documentos/Alertas/Notas_Geradas     │
  │                                                  │
  │ [Pasta criada com sucesso]                       │
  └─────────────────────────────────────────────────┘

  Etapa 10: Feature Flags
  ┌─────────────────────────────────────────────────┐
  │ Funcionalidades ativas (todas ON por padrao):    │
  │ [x] Analyze API                                  │
  │ [x] Draft API                                    │
  │ [x] Chat API + Streaming                         │
  │ [x] Feedback API                                 │
  │ [x] Export API                                   │
  │ [x] Threat Intel                                 │
  │ [x] Runtime API                                  │
  │                                                  │
  │ Alterar algum? (s/N)                             │
  └─────────────────────────────────────────────────┘

  Etapa 11: Seguranca e Observabilidade
  ┌─────────────────────────────────────────────────┐
  │ Redacao de dados sensiveis em logs? (S/n)        │
  │ Auditoria de prompts? (s/N)                      │
  └─────────────────────────────────────────────────┘

  Etapa 12: Revisao e Confirmacao
  ┌─────────────────────────────────────────────────┐
  │ === Resumo da Configuracao ===                   │
  │                                                  │
  │ Runtime:     ~/.socc                             │
  │ Backend:     ollama (GPU)                        │
  │ Modelo Fast: llama3.2:3b                         │
  │ Modelo Bal.: qwen3.5:9b                          │
  │ Modelo Deep: qwen3.5:9b                          │
  │ Fallback:    anthropic/claude-haiku-4-5           │
  │ TI:          http://localhost:8000 ✓              │
  │ Vantage:     desabilitado                        │
  │ KB:          /home/user/.../Alertas (42 docs)    │
  │ Agente:      soc-copilot                         │
  │ Saida:       ~/Documentos/.../Notas_Geradas      │
  │ Redacao:     ativada                             │
  │                                                  │
  │ Salvar configuracao? (S/n)                       │
  │ ✓ Configuracao salva em ~/.socc/.env             │
  │                                                  │
  │ Iniciar servico agora? (S/n)                     │
  │ ✓ Servico iniciado na porta 8080                 │
  │                                                  │
  │ Abrir dashboard? (S/n)                           │
  │ ✓ Abrindo http://localhost:8080                  │
  └─────────────────────────────────────────────────┘
```

---

### 2.2 Gestao de Providers e Auth

**OpenClaw faz:**
- `openclaw onboard --auth-choice token|oauth|setup-token|...`
- `openclaw models auth` — gerencia auth profiles por provider
- OAuth flow completo com refresh tokens e expiry
- SecretRef: armazena referencia a env var em vez do token real
- Multiplos profiles por provider (ex: `anthropic:manual`, `anthropic:claude-code`)

**Gap no SOCC:**
- Zero gestao de credenciais alem de `.env`
- Sem teste de validade de API key
- Sem suporte a OAuth
- Sem SecretRef (token sempre em plaintext no `.env`)

**O que trazer:**

| Comportamento OpenClaw | Equivalente SOCC |
|------------------------|------------------|
| `--auth-choice token` | `socc onboard` Etapa 5: entry de API key com masking |
| `--auth-choice oauth` | Nao se aplica (SOCC nao usa OAuth de provider) |
| SecretRef (env var ref) | `socc configure auth --secret-ref ANTHROPIC_API_KEY` — armazena nome da env var em vez do valor |
| Token expiry tracking | `socc doctor` alertar se token Anthropic retorna 401 |
| Multiple auth profiles | Nao necessario — SOCC tem 1 profile por provider |
| `models auth` | `socc configure provider anthropic --test` |

**Novo subcomando proposto:**
```
socc configure provider <nome>
  --api-key        Configura API key (input mascarado)
  --url            Configura URL base
  --model          Configura modelo padrao
  --test           Testa conexao com o provider
  --secret-ref     Armazena referencia a env var em vez do valor
  --remove         Remove configuracao do provider
```

---

### 2.3 Base Local de Conhecimento

**OpenClaw faz:**
- Workspace git com `MEMORY.md`, `SOUL.md`, `USER.md`
- Daily memory em `memory/YYYY-MM-DD.md`
- Long-term memory curada em `MEMORY.md`
- `openclaw memory status/search/index`
- SQLite para indice de memoria

**SOCC ja tem:**
- `~/.socc/intel/` com `sources.json`, index JSONL, chunking RAG
- `socc intel add/list/reindex/search` (CLI parcialmente implementado)
- Agent workspace com `SOUL.md`, `USER.md`, etc.

**Gaps reais:**
1. **Wizard de configuracao de KB** — usuario precisa saber executar `socc intel add --path /caminho --kind document_set` manualmente
2. **Sem prompt interativo** para apontar pasta de conhecimento
3. **Sem deteccao automatica** de pastas candidatas (ex: detectar `~/Documentos/Alertas` se existir)
4. **Sem preview de indexacao** antes de confirmar

**O que trazer:**
```
socc onboard (Etapa 2):
  - Prompt: "Aponte a pasta da sua base local de conhecimento"
  - Deteccao automatica de candidatos:
    - $ALERTAS_ROOT se definido
    - ~/Documentos/Alertas se existir
    - ~/Documents/SOC se existir
  - Preview: "42 arquivos encontrados (.md, .txt, .json)"
  - Confirmacao: "Indexar agora? (S/n)"
  - Progresso: "Indexando... 42/42 documentos (256 chunks)"

socc intel add --interactive:
  - Mesmo wizard, disponivel fora do onboard
  - Suporte a adicionar multiplas fontes
```

---

### 2.4 Gestao de Modelos

**OpenClaw faz:**
```
openclaw models list          # lista modelos de todos os providers
openclaw models set <model>   # define modelo padrao
openclaw models fallbacks add # adiciona modelo de fallback
```
- Profiles com custos por token (input/output/cache)
- Metadata: context window, max tokens, capabilities (reasoning, image input)
- Auto-discovery de modelos do Ollama

**SOCC ja tem:**
- `llm_gateway.py` com `list_backend_models()` que consulta Ollama tags
- Profiles `SOCC_OLLAMA_FAST_MODEL`, `SOCC_OLLAMA_BALANCED_MODEL`, `SOCC_OLLAMA_DEEP_MODEL`
- `probe_inference_backend()` e `warmup_backend_model()`
- `socc runtime --probe` mostra modelos disponiveis

**Gaps reais:**
1. **Sem selecao interativa** de modelos durante onboard
2. **Sem mapeamento assistido** de modelos para profiles Fast/Balanced/Deep
3. **Sem `socc models` como subcomando dedicado**
4. **Sem fallback chain configuravel** via CLI

**O que trazer:**
```
socc models list                     # lista modelos de todos os backends ativos
socc models set --fast <model>       # define modelo do perfil Fast
socc models set --balanced <model>   # define modelo do perfil Balanced
socc models set --deep <model>       # define modelo do perfil Deep
socc models fallback add <provider/model>   # adiciona fallback
socc models fallback list                   # lista chain de fallback
socc models test [model]                    # testa inferencia com prompt de smoke test
```

---

### 2.5 Gestao de Configuracao

**OpenClaw faz:**
```
openclaw config get <path>       # le valor
openclaw config set <path> <val> # escreve valor
openclaw config unset <path>     # remove valor
openclaw config file             # mostra caminho do arquivo
openclaw config validate         # valida integridade
```
- JSON Schema para validacao
- Config audit trail (`config-audit.jsonl`)
- Config health monitoring (`config-health.json`)
- Backup automatico (`openclaw.json.bak*`)

**SOCC ja tem:**
- `update_env_assignment()` para escrita em `.env`
- `socc.json` manifesto (gerado no bootstrap)
- `socc doctor` lê e reporta config

**Gaps reais:**
1. **Sem `socc config` como subcomando** — todo ajuste exige editar `.env`
2. **Sem validacao de configuracao** — valores invalidos sao aceitos silenciosamente
3. **Sem backup antes de escrita** — `update_env_assignment()` sobrescreve sem backup
4. **Sem audit trail** de mudancas de configuracao

**O que trazer:**
```
socc configure show                 # mostra todas as configuracoes ativas (redacted)
socc configure set <KEY> <VALUE>    # escreve em ~/.socc/.env com backup
socc configure unset <KEY>          # remove variavel
socc configure validate             # valida valores contra schema
socc configure export               # exporta configuracao (redacted) para compartilhar
socc configure import <file>        # importa configuracao de outro ambiente
```

Extras:
- Backup automatico de `.env` antes de cada escrita (`~/.socc/.env.bak.YYYYMMDD-HHMMSS`)
- Validacao de tipos (URL, inteiro, booleano, path existente) antes de salvar
- Log de auditoria em `~/.socc/logs/config-audit.jsonl`

---

### 2.6 Shell Completions

**OpenClaw faz:**
- Gera completions para Bash, Zsh, Fish, PowerShell automaticamente no install
- Armazena em `~/.openclaw/completions/`

**SOCC nao tem:** Nenhuma shell completion.

**O que trazer:**
```
socc completions install [--shell bash|zsh|fish]
socc completions generate [--shell bash|zsh|fish]
```
- Detectar shell do usuario automaticamente
- Gerar completions com argparse + `argcomplete` ou `shtab`
- Instalar no `~/.bashrc` / `~/.zshrc` com guarda de idempotencia

---

## 3. Prioridades de Implementacao

### P0 — Fundacao (pre-requisito para tudo)

| Item | Descricao | Estimativa |
|------|-----------|------------|
| `prompt_runtime` | Modulo de prompts interativos (ask, confirm, select, secret, checklist, summary) | Modulo novo |
| TTY detection | `sys.stdin.isatty()` + `--no-interactive` flag | Poucas linhas |
| `.env` backup | Backup antes de cada escrita de `update_env_assignment()` | Poucas linhas |

### P1 — Onboarding Wizard

| Item | Descricao |
|------|-----------|
| Etapa 1: Runtime Home | Confirmar/escolher `~/.socc` |
| Etapa 2: Knowledge Base | Apontar pasta, detectar candidatos, indexar |
| Etapa 3: Backend | Detectar backends, selecionar, testar |
| Etapa 4: Modelos | Listar modelos, mapear profiles |
| Etapa 5: Cloud Providers | API key entry mascarado, teste de conexao |
| Etapa 6: TI | URL, credenciais, teste |
| Etapa 7: Vantage | URL, auth, modulos |
| Etapa 8: Agente | Selecionar agente ativo |
| Etapa 9: Saida | Pasta de notas geradas |
| Etapa 10: Feature Flags | Checklist de features |
| Etapa 11: Seguranca | Redacao, audit |
| Etapa 12: Resumo | Review, salvar, iniciar, abrir |

### P2 — Subcomandos de Gestao

| Item | Descricao |
|------|-----------|
| `socc configure` | show, set, unset, validate, export, import |
| `socc models` | list, set, fallback, test |
| `socc configure provider` | add, test, remove providers |

### P3 — Doctor Interativo + Completions

| Item | Descricao |
|------|-----------|
| `socc doctor --interactive` | Checklist visual, expand, fix inline |
| `socc completions` | Generate e install para Bash/Zsh |

---

## 4. Modulo `prompt_runtime` — Especificacao

Modulo central reutilizavel para interacao no terminal, inspirado no OpenClaw mas sem dependencias pesadas de TUI.

### Interface proposta

```python
# socc/cli/prompt_runtime.py

def is_interactive() -> bool:
    """Retorna True se stdin e TTY e nao ha flag --no-interactive."""

def ask(prompt: str, default: str = "", validate: Callable = None) -> str:
    """Pergunta aberta com validacao opcional."""

def ask_secret(prompt: str) -> str:
    """Input mascarado para senhas e tokens (getpass)."""

def confirm(prompt: str, default: bool = True) -> bool:
    """Sim/Nao com default."""

def select(prompt: str, options: list[str], default: int = 0) -> str:
    """Selecao unica de lista numerada."""

def checklist(prompt: str, options: list[str], defaults: list[bool] = None) -> list[str]:
    """Selecao multipla com [x]/[ ]."""

def ask_path(prompt: str, default: str = "", must_exist: bool = False) -> Path:
    """Input de caminho com validacao de existencia e expansao de ~."""

def summary(title: str, items: dict[str, str]) -> None:
    """Imprime resumo formatado antes de confirmar."""

def step(number: int, total: int, title: str) -> None:
    """Imprime cabecalho de etapa: [3/12] Selecao de Modelos"""

def success(msg: str) -> None:
    """Imprime mensagem de sucesso com checkmark."""

def warning(msg: str) -> None:
    """Imprime aviso."""

def error(msg: str) -> None:
    """Imprime erro."""

def skip(msg: str) -> None:
    """Imprime indicacao de etapa pulada."""
```

### Regras de comportamento

1. Se `not is_interactive()`: todas as funcoes retornam o default silenciosamente
2. `ask_secret` usa `getpass.getpass()` — nunca ecoa o valor
3. `select` aceita numero ou texto parcial como resposta
4. `ask_path` expande `~` e valida existencia se `must_exist=True`
5. `summary` redige valores que contenham `KEY`, `TOKEN`, `PASS`, `SECRET`
6. Todas as funcoes suportam `Ctrl+C` para abort limpo com mensagem

---

## 5. Mapeamento OpenClaw → SOCC: Cheat Sheet

| OpenClaw | SOCC Equivalente | Status |
|----------|------------------|--------|
| `openclaw setup` | `socc init` | Existe |
| `openclaw onboard` | `socc onboard` | Existe (sem wizard) |
| `openclaw onboard --flow quickstart` | `socc onboard --flow rapido` | **Criar** |
| `openclaw onboard --flow advanced` | `socc onboard --flow completo` | **Criar** |
| `openclaw configure` | `socc configure` | **Criar** |
| `openclaw config get/set` | `socc configure show/set` | **Criar** |
| `openclaw config validate` | `socc configure validate` | **Criar** |
| `openclaw models list` | `socc models list` | **Criar** |
| `openclaw models set` | `socc models set --fast/--balanced/--deep` | **Criar** |
| `openclaw models fallbacks add` | `socc models fallback add` | **Criar** |
| `openclaw models auth` | `socc configure provider` | **Criar** |
| `openclaw agents list` | `socc agent list` | Parcial |
| `openclaw agents add` | N/A (SOCC tem agente fixo) | N/A |
| `openclaw agents set-identity` | N/A (identidade via `identity.md`) | N/A |
| `openclaw doctor` | `socc doctor` | Existe (nao interativo) |
| `openclaw service start/stop` | `socc service start/stop` | Existe |
| `openclaw qr` (WhatsApp) | N/A (SOCC nao tem canais) | N/A |
| `openclaw memory status` | `socc intel list` | Existe |
| `openclaw memory search` | `socc intel search` | Existe |
| `openclaw memory index` | `socc intel reindex` | Existe |
| `openclaw skills install` | N/A (skills embarcados no agente) | N/A |
| Shell completions | `socc completions install` | **Criar** |
| Config audit trail | `~/.socc/logs/config-audit.jsonl` | **Criar** |
| `.env` backup on write | `~/.socc/.env.bak.*` | **Criar** |

---

## 6. Decisoes Arquiteturais

### O que NAO trazer do OpenClaw

| Item | Razao |
|------|-------|
| OAuth flow (OpenAI Codex) | SOCC usa apenas API keys, sem necessidade de OAuth |
| Channels (WhatsApp, Telegram, Discord) | SOCC e runtime local, sem canais de mensageria |
| Device pairing (Ed25519) | SOCC nao tem modelo multi-device |
| Gateway com auth token | SOCC roda localmente sem autenticacao (a adicionar, mas separadamente) |
| Multiple agents com bindings | SOCC tem 1 agente ativo, sem roteamento por canal |
| JSON Schema para config | `.env` e suficiente; validacao pode ser programatica |
| Tailscale integration | SOCC e local-first; exposicao de rede e fora de escopo |
| `openclaw.json` (config central JSON) | Manter `.env` + `socc.json` manifesto, mas com validacao |
| Scheduled jobs (`cron/jobs.json`) | Fora do escopo atual |
| Canvas/Control UI | SOCC ja tem dashboard web proprio |

### O que adaptar

| OpenClaw | Adaptacao SOCC |
|----------|---------------|
| 25+ opcoes de auth provider | 5 opcoes: ollama, lmstudio, vllm, openai-compatible, anthropic |
| Profiles de custo por token | Nao necessario (foco em local) |
| Multiple workspaces | Single workspace `~/.socc/workspace/soc-copilot` |
| `--skip-*` flags granulares | `--flow rapido` (pula opcionais) vs `--flow completo` |
| Config backup com hash chain | Backup simples com timestamp |

---

## 7. Criterios de Aceite

### Wizard de Onboarding
- [ ] Usuario novo completa `socc onboard` do zero ao dashboard sem editar `.env`
- [ ] Todas as etapas tem default seguro e opcao de pular
- [ ] Secrets nunca aparecem em tela, log ou resumo
- [ ] `socc onboard --json` continua funcionando sem prompts
- [ ] `socc onboard --flow rapido` completa em <= 5 interacoes
- [ ] Configuracao persiste corretamente em `~/.socc/.env`
- [ ] Backup de `.env` criado antes de qualquer escrita

### Subcomandos de Gestao
- [ ] `socc configure show` exibe todas as configs ativas com valores redacted
- [ ] `socc configure set KEY VALUE` escreve no `.env` com backup e validacao
- [ ] `socc models list` mostra modelos de todos os backends ativos
- [ ] `socc models set --fast MODEL` persiste no `.env`
- [ ] `socc configure provider anthropic --test` valida a API key

### Doctor Interativo
- [ ] `socc doctor` em TTY exibe checklist navegavel
- [ ] Categorias expansiveis sob demanda
- [ ] Recomendacoes acionaveis com comando sugerido
- [ ] `socc doctor --json` continua retornando payload completo

---

## 8. Proximos Passos

1. **Implementar `socc/cli/prompt_runtime.py`** — modulo de prompts interativos (Secao 4)
2. **Refatorar `socc onboard`** para usar wizard com as 12 etapas (Secao 2.1)
3. **Adicionar `socc configure`** com show/set/unset/validate (Secao 2.5)
4. **Adicionar `socc models`** com list/set/fallback/test (Secao 2.4)
5. **Adicionar backup de `.env`** em `update_env_assignment()` (Secao 2.5)
6. **Adicionar `socc completions`** com generate/install (Secao 2.6)
7. **Refatorar `socc doctor`** para modo interativo com checklist (P3)
