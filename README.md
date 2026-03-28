# socc

Projeto local de apoio a triagem SOC, parsing de payloads, enriquecimento de IOCs e geração controlada de alertas e notas operacionais.

Perfil local atual recomendado: `Ollama` com `qwen3.5:9b`, priorizando `GPU`.

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

## Instalação e execução via npm

Para usar o SOCC em fluxo npm-first, no estilo do OpenClaw:

```bash
npm install -g .
socc setup
socc doctor --probe
socc serve
```

No checkout local, você também pode usar scripts npm sem instalar globalmente:

```bash
npm run setup
npm run doctor
npm run serve
```

O wrapper npm delega para a CLI Python existente, prepara `~/.socc/venv` quando necessário e preserva os mesmos comandos operacionais (`socc dashboard`, `socc gateway restart`, `socc runtime`, etc.).

No layout npm/global, o modelo agora fica mais próximo do OpenClaw:

- `~/.socc/` guarda apenas estado do usuário: `.env`, `workspace/`, sessões, logs, cache, MCP e base local de conhecimento
- a alma do agente é seedada em `~/.socc/workspace/soc-copilot`
- código Python, templates HTML e assets continuam no pacote instalado
- o manifesto `~/.socc/socc.json` registra `installation_layout=package` e o `package_root`

No fluxo de desenvolvimento via checkout, o layout continua `checkout`, com links locais para o repositório quando isso fizer sentido.

Para respostas mais rápidas no chat, o runtime agora suporta perfis de resposta:

```bash
socc chat --response-mode fast --message "Resuma este alerta"
socc chat --response-mode balanced --message "Analise este log"
socc chat --response-mode deep --message "Aprofunde hipóteses e próximos passos"
```

Na UI, o mesmo controle aparece como `Fast | Balanced | Deep`.
No perfil atual recomendado:

- `Fast` usa `llama3.2:3b`
- `Balanced` usa `qwen3.5:9b`
- `Deep` usa `qwen3.5:9b`

Se quiser trocar isso, ajuste `SOCC_OLLAMA_FAST_MODEL`, `SOCC_OLLAMA_BALANCED_MODEL` e `SOCC_OLLAMA_DEEP_MODEL` em `~/.socc/.env`.

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
socc vantage status
socc vantage modules
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
- o parser agora também usa um catálogo ampliado de aliases de telemetria de segurança para JSONs de EDR/NDR/plataformas de eventos/IAM/cloud/Kubernetes, incluindo IPv4/IPv6, hostname, server, arquivo, hash, e-mail/auth, DNS/HTTP/TLS, processo, cloud e container
- a extração de IOCs agora também normaliza artefatos defangados (`hxxp`, `[.]`), estabiliza caixa de domínio/hash/URL e reduz duplicidade entre parser, TI e contrato estruturado
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
- a integração com Vantage API já possui catálogo inicial de módulos, contrato de autenticação por ambiente, comandos de inspeção via `socc vantage` e enriquecimento automático orientado a IOC/artefato
- a análise e o export agora também podem carregar `operational_payload` estruturado, pronto para reaproveito operacional em alerta, encerramento e documentação técnica
- a exportação operacional agora suporta `JSON`, `Markdown` e `Ticket`, tanto no chat quanto na interface legada
- o chat e a interface legada agora também mostram esse `operational_payload`, incluindo ação de cópia direta do bloco estruturado
- os drafts e o `operational_payload` agora diferenciam a rota operacional por classificação, destacando abertura de alerta, encerramento administrativo, correção de detecção, encerramento benigno e tratativa de telemetria
- o chat agora preserva melhor o último artefato estruturado da sessão em mensagens referenciais e evita cair em triagem binária só por menção solta a `payload`
- eventos M365 `HygieneTenantEvents` agora recebem leitura determinística inicial, reduzindo explicações inventadas quando faltam fontes de grounding

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
- ollama tuning: `SOCC_OLLAMA_KEEP_ALIVE`, `SOCC_OLLAMA_FAST_MODEL`, `SOCC_OLLAMA_BALANCED_MODEL`, `SOCC_OLLAMA_DEEP_MODEL`
- feature flags: `SOCC_FEATURE_ANALYZE_API`, `SOCC_FEATURE_DRAFT_API`, `SOCC_FEATURE_CHAT_API`, `SOCC_FEATURE_CHAT_STREAMING`, `SOCC_FEATURE_FEEDBACK_API`, `SOCC_FEATURE_EXPORT_API`, `SOCC_FEATURE_THREAT_INTEL`, `SOCC_FEATURE_RUNTIME_API`
- segurança/observabilidade: `SOCC_LOG_REDACTION_ENABLED`, `SOCC_PROMPT_AUDIT_ENABLED`, `SOCC_PROMPT_PREVIEW_CHARS`
- Vantage API: `SOCC_VANTAGE_ENABLED`, `SOCC_VANTAGE_BASE_URL`, `SOCC_VANTAGE_BEARER_TOKEN`, `SOCC_VANTAGE_API_KEY`, `SOCC_VANTAGE_TIMEOUT`, `SOCC_VANTAGE_VERIFY_TLS`, `SOCC_VANTAGE_ENABLED_MODULES`
  Ajustes de contexto automático: `SOCC_VANTAGE_CONTEXT_MAX_MODULES`, `SOCC_VANTAGE_CONTEXT_CHARS`, `SOCC_VANTAGE_QUERY_LIMIT`

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

## Vantage API

O runtime agora possui uma camada inicial para integração com a API do Vantage em [vantage_api.py](/home/nilsonpmjr/.gemini/antigravity/scratch/socc/socc/gateway/vantage_api.py), com catálogo inicial de módulos úteis ao SOC:

- `dashboard`
- `feed`
- `recon`
- `watchlist`
- `hunting`
- `exposure`
- `users`
- `admin`

Comandos iniciais:

- `socc vantage status`
- `socc vantage modules`
- `socc vantage probe --module feed`

O runtime agora já tenta enriquecer automaticamente chat e análise com contexto do Vantage quando a integração estiver habilitada. Esse enriquecimento é fail-open: se a API falhar, o SOCC continua respondendo sem interromper o fluxo principal.
Quando houver artefatos claros no caso, como `CVE`, `hash`, `IP`, `domínio`, `URL`, `hostname` ou `usuário`, o cliente do Vantage também monta consultas mais direcionadas por módulo para trazer contexto mais útil ao analista.

No webchat, esse uso agora também fica visível:

- o `Control Center` mostra o estado da integração e os módulos do Vantage mapeados
- respostas e cards analíticos exibem quando módulos do Vantage contribuíram para o contexto
- o `Control Center` também permite ligar/desligar o enriquecimento automático e escolher quais módulos entram no contexto

## Saída operacional estruturada

O runtime agora gera um bloco `operational_payload` junto da análise estruturada, com:

- `title`, `classification`, `disposition`, `summary` e `verdict`
- `priority` com `level`, `score`, `rank` e família principal
- `recommended_actions`, `risk_reasons`, `iocs` e `evidence`
- `sources` e resumo do contexto vindo do Vantage

Esse bloco já entra no export `JSON` e também aparece no export `Markdown`, facilitando reaproveito em nota de encerramento, alerta ou integração futura com outras ferramentas.

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
- o seed atual de `.env` já sai alinhado para `SOCC_INFERENCE_BACKEND=ollama`, `SOCC_INFERENCE_DEVICE=gpu` e `OLLAMA_MODEL=qwen3.5:9b`
- no layout npm, o runtime home não recebe cópia do projeto; ele recebe só o estado local e o workspace do agente, enquanto o pacote instalado continua sendo a origem de código/templates/assets

## Streaming do chat

- `POST /api/chat/stream` expõe SSE para a interface de chat
- perguntas livres recebem deltas incrementais quando o backend Ollama está ativo
- payloads enviam eventos de fase (`detect`, `parse`, `ti`, `analysis`, `draft`) antes do card final

## Preferências da UI

- o `chat.html` agora expõe um painel local de configurações inspirado no fluxo configurável do ClawDBot
- o webchat agora também possui um `Control Center` inspirado no OpenClaw para runtime, agente ativo, base local de conhecimento, sessões e diagnóstico
- a interface permite alternar manualmente entre agentes disponíveis do workspace/runtime sem editar variáveis de ambiente à mão
- o chat agora também oferece perfis `Fast`, `Balanced` e `Deep`, que ajustam tamanho de contexto, profundidade de resposta e parâmetros do Ollama para equilibrar latência e qualidade
- o `Control Center` agora também lista modelos detectados no backend, permite escolher os modelos de `Fast`, `Balanced` e `Deep` pela UI e executar warm-up manual do perfil selecionado
- as preferências ficam em `localStorage` e cobrem tema, densidade dos cards, visibilidade de contexto/trilha/contrato oficial, preferência por SSE, classificação e cliente padrão, ordenação de sessões e formato padrão de exportação
- o painel também consulta `GET /api/runtime/status` para mostrar provider, modelo, device e features ativas diretamente na interface

## Base local de conhecimento

- o runtime agora possui uma fundação inicial de RAG em `~/.socc/intel`, com registry de fontes, pasta de documentos normalizados e índice local em `JSONL`
- o comando `socc intel add-source` registra acervos internos ou curados para ingestão futura
- o comando `socc intel ingest` normaliza texto, aplica chunking por parágrafo e grava um índice auditável sem depender ainda de vetor store
- a política inicial de limpeza/normalização e o modelo mínimo de fonte ficam seedados no workspace do agente em `references/knowledge-ingestion-policy.md` e `references/intelligence-source-registry.md`
- nesta etapa o índice ainda é textual; embeddings e busca semântica entram no próximo corte de P3
