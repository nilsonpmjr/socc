# socc

Projeto local de apoio a triagem SOC, parsing de payloads, enriquecimento de IOCs e geração controlada de alertas e notas operacionais.

## Escopo atual

- parsing de entradas em texto, JSON e CSV
- normalização de campos e IOCs
- integração local de Threat Intelligence
- análise estruturada pré-draft
- geração controlada de saídas operacionais
- interface local para análise, revisão, cópia e salvamento
- base inicial para runtime instalável com CLI, gateway e MCP

## Estrutura principal

- `soc_copilot/`: aplicação web atual e módulos do MVP
- `socc/`: pacote instalável com `cli`, `core`, `gateway` e `utils`
- `tests/`: suíte de regressão e casos extremos
- `run.py`: entrypoint compatível com o MVP atual
- `pyproject.toml`: configuração do pacote instalável e do binário `socc`

## Instalação em modo editável

```bash
pip install -e .
```

## Instalação one-shot local

```bash
./install.sh
```

Ou, se quiser o nome mais próximo do fluxo do OpenClaw:

```bash
./install-cli.sh
```

Esse fluxo cria `~/.socc/venv`, instala o pacote, escreve o launcher em `~/.socc/bin/socc`, expõe o checkout atual em `~/.socc/project` e executa `socc onboard`.
O launcher e o runtime agora também respeitam `SOCC_HOME`, para isolar a instalação em outro diretório quando necessário.
Se o shim em `~/.local/bin/socc` não puder ser criado, use diretamente `~/.socc/bin/socc`.

## Comandos principais

```bash
socc onboard
socc doctor --probe
socc service start
socc gateway restart
socc service restart
socc dashboard --open
socc init
socc chat --message "Resumo técnico do caso"
socc runtime
socc serve
socc analyze --file caminho/do/payload.txt --json
```

Compatibilidade com o fluxo atual:

```bash
python run.py
```

Ao subir a aplicação web, a rota `/` agora abre a interface de chat por padrão. A interface antiga de análise continua disponível em `/legacy`.

## Direção arquitetural

O pacote `socc` foi adicionado como camada de runtime para aproximar o projeto de um modelo instalável estilo agent/runtime:

- `socc.cli`: comandos locais como `init`, `serve` e `analyze`
- `socc.core`: wrappers para engine, memória, prompts, contratos e ferramentas
- `socc.gateway`: preparação para execução LLM local/remota e integração MCP
- `socc.utils`: carregamento de configuração e parsing utilitário

O projeto continua usando variáveis locais definidas em `.env`, com possibilidade de bootstrap de `~/.socc/.env` via `socc init`.

## Migração gradual

O caminho de migração agora está formalizado em [migracao-runtime-socc.md](/home/nilsonpmjr/.gemini/antigravity/scratch/socc/docs/migracao-runtime-socc.md). A regra prática passa a ser:

- código novo deve importar `socc.core.*` e `socc.gateway.*`
- `soc_copilot.modules.*` permanece como implementação legada por trás dessas fachadas
- `soc_copilot.main` segue como cliente web do runtime até a extração completa
- a maior parte dos fluxos web de análise/chat já foi redirecionada para essas fachadas
- a preparação inicial do payload também já passa por `socc.core.engine`
- `analyze` e `draft` da camada web já delegam sua orquestração principal ao `engine`
- a validação e preparação de entrada de `analyze` e `draft` também já passam por helpers do `engine`
- o payload do chat também já fecha sua análise estruturada pelo `engine`
- o chat síncrono, o stream SSE e os payloads de runtime/benchmark também já passam pelo `engine`
- `feedback`, `export` e `chat` também já normalizam seus corpos JSON via helpers do `engine`
- export, feedback, save e histórico também já passam por helpers do runtime
- os helpers residuais de SSE/detecção também já foram extraídos do `main.py`
- o parser agora também usa um catálogo ampliado de aliases de telemetria de segurança para JSONs de EDR/NDR/SIEM/IAM/cloud/Kubernetes, incluindo IPv4/IPv6, hostname, server, arquivo, hash, e-mail/auth, DNS/HTTP/TLS, processo, cloud e container
- o runtime agora também deriva contextos investigativos por família de telemetria, como phishing, pressão de autenticação, canal web/TLS, persistência, exfiltração, cloud e Kubernetes
- o draft final agora usa esses contextos para destacar prioridade operacional e recomendações mais específicas por caso
- o draft também passou a variar o recorte analítico e os detalhes exibidos por vertical, diferenciando melhor casos de e-mail, endpoint, rede, cloud e Kubernetes
- a análise agora também expõe priorização estruturada (`score`, `level`, `rank`, `primary_family`, `reasons`) no runtime, export e UI

O mapa atual do backend/templates do chat está documentado em [chat-arquitetura-atual.md](/home/nilsonpmjr/.gemini/antigravity/scratch/socc/docs/chat-arquitetura-atual.md). Esse documento também registra que o fluxo principal do chat web já não depende do gateway MCP externo; o uso atual de MCP ficou restrito à análise semi-LLM com ferramentas locais em estilo tool-calling.

## Runtime autocontido

O `socc init` agora prepara um runtime mais próximo do modelo do OpenClaw:

- cria `~/.socc/workspace/soc-copilot` com uma cópia inicial da camada declarativa do agente
- grava `~/.socc/socc.json` com caminhos e variáveis-chave do runtime
- mantém `~/.socc/.env` como ponto principal de override local
- permite apontar outro workspace com `SOCC_AGENT_HOME=/caminho/do/agente`

Na ausência de override, o loader tenta esta ordem:

1. `SOCC_AGENT_HOME`
2. `~/.socc/workspace/soc-copilot`
3. `.agents/soc-copilot` no repositório

O fluxo local agora também pode começar por:

- `socc onboard`: bootstrap + validação inicial do runtime
- `socc doctor`: diagnóstico local de paths, manifesto, knowledge base e backend de inferência
- `socc service start|stop|restart|status`: controle do servidor web em background com PID/log local
  Alias compatível: `socc gateway ...`
- `socc dashboard` e `socc dashboard --open`: devolvem ou tentam abrir a URL local da interface com base no serviço atual
- a base local de conhecimento já suporta retrieval lexical inicial, anexando trechos recuperados ao contexto do chat e da análise estruturada

## Contrato interno do runtime

O pacote `socc.core` agora expõe um contrato interno explícito para desacoplar motor, gateway e tools:

- `AnalysisEnvelope`: retorno canônico de `socc analyze` e do engine analítico
- `ChatResponseEnvelope`: retorno canônico de `socc chat`
- `GatewayRequestContract` e `GatewayResponseContract`: metadados mínimos do backend de inferência
- `ToolExecutionContract`: resultado padronizado para ferramentas locais e futuras integrações MCP

Todos esses envelopes carregam `contract_version`, o que facilita evolução gradual sem acoplar a web ao formato interno exato.

## CLI de chat

- `socc chat --message "..."` envia uma mensagem única ao runtime
- `socc chat --stream --message "..."` mostra deltas incrementais quando o backend suportar streaming
- `socc chat` sem argumentos abre um REPL simples e reaproveita a mesma sessão ao longo da conversa
- `socc chat --json` retorna o envelope canônico com `runtime`, `gateway`, `skill` e `session_id`

## Variáveis de ambiente

Principais grupos documentados em `.env.example`:

- runtime: `SOCC_AGENT_HOME`
- base local de conhecimento: `SOCC_RAG_CHUNK_CHARS`, `SOCC_RAG_CHUNK_OVERLAP`, `SOCC_RAG_MAX_FILE_BYTES`
- aplicação: `SOC_PORT`, `OUTPUT_DIR`, `ALERTAS_ROOT`, `MAX_TI_IOCS`
- TI: `TI_API_BASE_URL`, `TI_API_USER`, `TI_API_PASS`, `THREAT_INTEL_API_KEY`, `THREAT_CHECK_SCRIPT`
- LLM: `LLM_ENABLED`, `LLM_PROVIDER`, `LLM_TIMEOUT`, `OLLAMA_URL`, `OLLAMA_MODEL`, `ANTHROPIC_API_KEY`, `LLM_MODEL`
- runtime local: `SOCC_INFERENCE_BACKEND`, `SOCC_BACKEND_PRIORITY`, `SOCC_INFERENCE_DEVICE`, `SOCC_LLM_FALLBACK_PROVIDER`, `SOCC_CPU_GUARD_ENABLED`, `SOCC_CPU_GUARD_LOAD`, `SOCC_MAX_CONCURRENT_LLM`, `SOCC_LMSTUDIO_URL`, `SOCC_LMSTUDIO_MODEL`, `SOCC_VLLM_URL`, `SOCC_VLLM_MODEL`, `SOCC_OPENAI_COMPAT_URL`, `SOCC_OPENAI_COMPAT_MODEL`, `SOCC_LOCAL_MODEL_DEFAULT`
- feature flags: `SOCC_FEATURE_ANALYZE_API`, `SOCC_FEATURE_DRAFT_API`, `SOCC_FEATURE_CHAT_API`, `SOCC_FEATURE_CHAT_STREAMING`, `SOCC_FEATURE_FEEDBACK_API`, `SOCC_FEATURE_EXPORT_API`, `SOCC_FEATURE_THREAT_INTEL`, `SOCC_FEATURE_RUNTIME_API`
- segurança/observabilidade: `SOCC_LOG_REDACTION_ENABLED`, `SOCC_PROMPT_AUDIT_ENABLED`, `SOCC_PROMPT_PREVIEW_CHARS`

As feature flags permitem rollout controlado do runtime/plugin sem remover código:

- desligar `SOCC_FEATURE_CHAT_STREAMING` faz a UI cair para `POST /api/chat`
- desligar `SOCC_FEATURE_THREAT_INTEL` mantém a análise ativa, mas sem enriquecimento TI
- desligar endpoints específicos retorna `503` com o nome da feature bloqueada

Backends atualmente mapeados no runtime:

- `ollama`: padrão local atual, bom para workstation e streaming
- `lmstudio`: opção desktop OpenAI-compatible para testes e comparação de modelos
- `vllm`: opção local orientada a throughput/GPU
- `openai-compatible`: gateway genérico para endpoints compatíveis com OpenAI
- `anthropic`: fallback remoto

`socc runtime` e `socc doctor` agora mostram o backend selecionado, a origem da decisão, capacidades do backend e o catálogo compatível conhecido pelo runtime.

## Segurança operacional

- logs técnicos do runtime passam por redação por padrão, mascarando IPs, emails, URLs, hashes e segredos
- a auditoria de prompts é opcional e desligada por padrão; quando ligada, grava apenas fingerprint, tamanho e preview redigido
- `GET /api/runtime/status` e `socc runtime` agora mostram também métricas da pipeline analítica, taxa de schema válido e estado dos controles de segurança

## Observabilidade de runtime

- `socc runtime` mostra provider, modelo, device preferido, fallback configurado e métricas recentes
- `socc runtime --probe` testa conectividade com o backend configurado
- `socc runtime --benchmark --probe` executa benchmark leve de concorrência e inclui a sonda do backend
- `GET /api/runtime/status` expõe status do runtime, snapshot básico de CPU/GPU e métricas agregadas
- `GET /api/runtime/benchmark` expõe benchmark leve de concorrência e o status do streaming SSE do chat
- o runtime tenta priorizar GPU automaticamente quando disponível e aplica guarda simples de CPU/concorrência para evitar sobrecarga local

## Distribuição e upgrade

- `pip install -e .` mantém o runtime instalável localmente durante a evolução do projeto
- `./install.sh` e `./install-cli.sh` funcionam como instaladores one-shot locais em estilo próximo ao OpenClaw
- `socc init` prepara `~/.socc` com `.env`, manifesto e workspace seedado
- `socc init --force` regrava manifesto, `.env.example` e arquivos seedados do runtime quando for preciso atualizar a base local
- o seed do workspace preserva customizações existentes e só adiciona arquivos ausentes quando não há `--force`
- o runtime agora também grava arquivos de serviço em `~/.socc/logs`, incluindo PID, metadata e logs stdout/stderr do `serve`

## Streaming do chat

- `POST /api/chat/stream` expõe SSE para a interface de chat
- perguntas livres recebem deltas incrementais quando o backend Ollama está ativo
- payloads enviam eventos de fase (`detect`, `parse`, `ti`, `analysis`, `draft`) antes do card final

## Preferências da UI

- o `chat.html` agora expõe um painel local de configurações inspirado no fluxo configurável do ClawDBot
- as preferências ficam em `localStorage` e cobrem tema, densidade dos cards, visibilidade de contexto/trilha/contrato oficial, preferência por SSE, classificação e cliente padrão, ordenação de sessões e formato padrão de exportação
- o painel também consulta `GET /api/runtime/status` para mostrar provider, modelo, device e features ativas diretamente na interface

## Base local de conhecimento

- o runtime agora possui uma fundação inicial de RAG em `~/.socc/intel`, com registry de fontes, pasta de documentos normalizados e índice local em `JSONL`
- o comando `socc intel add-source` registra acervos internos ou curados para ingestão futura
- o comando `socc intel ingest` normaliza texto, aplica chunking por parágrafo e grava um índice auditável sem depender ainda de vetor store
- a política inicial de limpeza/normalização e o modelo mínimo de fonte ficam seedados no workspace do agente em `references/knowledge-ingestion-policy.md` e `references/intelligence-source-registry.md`
- nesta etapa o índice ainda é textual; embeddings e busca semântica entram no próximo corte de P3
