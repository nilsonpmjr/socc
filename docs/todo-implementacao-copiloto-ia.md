# TODO - Implementacao do Copiloto de IA no SOCC

## Objetivo

Entregar um MVP funcional do copiloto de analise de payloads no SOCC, com chat real ligado a LLM local, resposta estruturada, feedback humano e base pronta para evolucao com RAG, ML e knowledge graph.

Como desdobramento de plataforma, preparar o produto para operar tambem como runtime instalavel com CLI, gateway local para LLM + MCP e preferencia por aceleracao em GPU.

## Premissas

- backend e frontend do SOCC ja existem
- existe uma pagina de chat em desenvolvimento
- o modelo local atual e `qwen2.5:3b`
- o ambiente podera expor um endpoint local de inferencia
- a arquitetura do agente seguira um padrao declarativo inspirado em OpenClaw
- o produto podera evoluir para um pacote instalavel no estilo OpenClaw
- a GPU disponivel deve ser aproveitada de forma prioritaria quando houver backend compativel
- este TODO foi escrito sem inspecao do codigo nesta sessao

## Status verificado em 2026-03-27

- boa parte de `P0`, `P0.5` e `P1` ja estava implementada no repositorio e foi validada nesta sessao
- `P2` passou a expor o contrato oficial `summary/verdict/confidence/iocs/ttps/risk_reasons/recommended_actions/sources`
- feedback do analista agora possui endpoint e persistencia dedicada
- o parser passou a cobrir um catalogo bem mais amplo de aliases JSON de seguranca para detectar usuario, IPs IPv4/IPv6, hostname, server, arquivo, hash, e-mail/auth, DNS/HTTP/TLS, processo, cloud, NAT/fluxo e Kubernetes/container com menos dependencia do modelo
- a analise passou a derivar contextos investigativos determinísticos por família de telemetria, melhorando explicabilidade e priorizacao operacional mesmo sem depender da LLM
- o draft passou a absorver prioridade operacional e contextos investigativos, reduzindo texto genérico na saída final
- o draft passou a variar o recorte analítico por vertical, deixando a saída mais aderente a phishing, endpoint, rede, cloud e Kubernetes
- a priorização passou a sair também como dado estruturado no runtime, export e UI, pronta para fila operacional e integração futura
- o webchat agora possui painel local de configurações inspirado no ClawDBot, com preferências persistidas para tema, streaming, exportação, visibilidade analítica e status do runtime
- o runtime agora possui fundação inicial de base local de conhecimento para RAG, com registry de fontes, política de limpeza/normalização, chunking textual e ingestão/indexação local via CLI
- o runtime agora também executa retrieval lexical inicial sobre a base local de conhecimento e anexa trechos recuperados ao contexto da análise e do chat, com fontes retornadas no payload final
- o runtime passou a ter onboarding e diagnóstico local inspirados no fluxo de instalação do OpenClaw, via `socc onboard` e `socc doctor`
- o runtime agora também possui instalador one-shot local em estilo OpenClaw, com `install.sh` e `install-cli.sh`
- o runtime agora também controla o servidor local em background com `socc service`, aceitando o alias `socc gateway`, incluindo `restart`, e expõe/abre a URL da UI por `socc dashboard`
- a arquitetura atual do chat, templates e rotas web foi documentada, e o fluxo principal já está confirmado como desacoplado do gateway MCP externo
- o gateway de inferência agora separa explicitamente `backend` de `provider`, com catálogo inicial de backends compatíveis (`ollama`, `lmstudio`, `vllm`, `openai-compatible`, `anthropic`) e diagnóstico ampliado no runtime
- os itens abaixo foram atualizados para refletir o estado real observado

## Fase P0 - Fundacao do SOC Copilot

- [x] Criar a pasta declarativa do agente em `.agents/soc-copilot/`
- [x] Criar `SOUL.md` com missao, principios, limites e postura analitica
- [x] Criar `USER.md` com contexto operacional do ambiente SOC
- [x] Criar `AGENTS.md` com regras de coordenacao e uso de playbooks
- [x] Criar `MEMORY.md` com convencoes iniciais e memoria operacional controlada
- [x] Criar `TOOLS.md` com inventario dos modulos e integracoes disponiveis
- [x] Criar `identity.md` com a versao curta da persona para prompt
- [x] Criar `skills.md` com o indice das skills e playbooks ativos
- [x] Criar `schemas/analysis_response.json`
- [x] Criar playbook `skills/payload-triage.md`
- [x] Criar playbook `skills/phishing-analysis.md`
- [x] Criar playbook `skills/malware-behavior.md`
- [x] Criar playbook `skills/suspicious-url.md`
- [ ] Definir politica de versionamento para memoria, playbooks e tools
- [x] Implementar loader no backend para ler essa estrutura
- [x] Definir prioridade entre persona base, playbook, memoria e contexto da sessao

## Entregavel P0

- estrutura inicial do `SOC Copilot` pronta para ser consumida pelo backend

## Fase P0.5 - Empacotamento e runtime instalavel

- [x] Definir a arquitetura alvo do pacote `socc/` com divisao entre `cli`, `core`, `gateway` e `utils`
- [x] Mapear a migracao gradual da estrutura atual `soc_copilot/` e `modules/` para o pacote instalavel
- [x] Criar `pyproject.toml` com entrypoint de CLI
- [x] Definir comandos iniciais da CLI, como `socc init`, `socc chat` e `socc analyze`
- [x] Implementar bootstrap local do ambiente do agente em `~/.socc` ou diretório equivalente
- [x] Separar o motor do agente da interface web para reutilizacao por CLI e automacao
- [x] Criar camada `gateway` para chamadas ao backend de inferencia
- [x] Criar camada `gateway` para integracao com MCP
- [x] Definir contrato interno entre engine, gateway e tools
- [x] Documentar estrategia de distribuicao, instalacao e upgrade do runtime
- [x] Adicionar onboarding guiado inicial via CLI
- [x] Adicionar comando de diagnostico local do runtime
- [x] Criar instalador one-shot no estilo `install.sh`/`install-cli.sh`
- [x] Adicionar controle local de serviço/daemon sem depender de systemd
- [x] Adicionar atalho CLI para dashboard/UI local

## Entregavel P0.5

- base arquitetural pronta para evoluir o SOCC de app web para runtime instalavel reutilizavel

## Fase P1 - Fundacao do chat real

- [x] Mapear a arquitetura atual do backend, templates e rotas do chat
- [x] Confirmar como o MCP atual esta sendo usado e desacoplar o fluxo principal de chat dele, se necessario
- [x] Definir contrato de API para o chat
- [x] Criar endpoint `POST /api/chat`
- [x] Criar endpoint de streaming, se o stack suportar SSE ou WebSocket
- [x] Implementar adaptador para LLM local
- [x] Externalizar configuracoes em `.env`
- [x] Padronizar timeout, temperatura, contexto maximo e nome do modelo
- [x] Criar prompt de sistema especializado para analise SOC
- [x] Carregar no fluxo do chat a persona base do `SOC Copilot`
- [x] Selecionar playbook aplicavel por tipo de entrada
- [x] Implementar validacao basica de entrada
- [x] Registrar logs tecnicos do fluxo de inferencia
- [x] Persistir sessoes e mensagens
- [x] Conectar `chat.html` ao endpoint real
- [x] Exibir estado de carregamento e erros na UI
- [x] Implementar streaming incremental na tela
- [x] Garantir reset de conversa

## Entregavel P1

- chat funcional de ponta a ponta com resposta da LLM local e persona carregada

## Fase P1.5 - Runtime de inferencia e GPU

- [x] Definir backend principal de inferencia local com suporte a GPU
- [x] Mapear opcoes de backend compativeis com gateway local
- [x] Implementar configuracao de device por ambiente
- [x] Priorizar GPU como padrao de execucao quando disponivel
- [x] Implementar fallback controlado para CPU
- [x] Registrar metricas basicas de uso de CPU, uso de GPU, latencia e fallback
- [x] Criar estrategia de limites para evitar sobrecarga de CPU em inferencia continua
- [x] Validar impacto de streaming e concorrencia no consumo de recursos

## Entregavel P1.5

- runtime de inferencia operacional com preferencia por GPU e observabilidade basica de recursos

## Fase P2 - Analise estruturada de payload

- [x] Definir schema JSON oficial da resposta da IA
- [x] Validar resposta da LLM contra schema no backend
- [x] Criar parser ou fallback para respostas malformadas
- [x] Implementar extracao deterministica de IOCs basicos
- [x] Implementar campos `summary`, `verdict`, `confidence`, `iocs`, `ttps`, `risk_reasons`, `recommended_actions`
- [x] Separar fatos observados de inferencias da IA
- [x] Criar mapeamento preliminar para MITRE ATT&CK
- [x] Exibir analise estruturada na UI alem do texto livre
- [x] Permitir copiar ou exportar a analise
- [x] Criar feedback do analista: aprovar, corrigir, rejeitar
- [x] Persistir feedback vinculado a sessao e payload

## Entregavel P2

- analise auditavel e reaproveitavel, com dados estruturados

## Fase P3 - RAG e bases de inteligencia

- [x] Levantar fontes internas disponiveis
- [x] Definir politica de limpeza e normalizacao dos documentos
- [ ] Escolher vetor store local ou compativel com o stack
- [x] Criar pipeline de ingestao e indexacao
- [ ] Definir chunking e estrategia de embeddings
- [ ] Implementar busca semantica por contexto
- [x] Anexar trechos recuperados ao prompt
- [x] Exibir fontes utilizadas na resposta final
- [x] Criar estrategia de versionamento e reindexacao
- [ ] Medir impacto do RAG na qualidade das respostas

## Entregavel P3

- respostas com contexto das bases de inteligencia internas

## Fase P4 - Automacao com n8n

- [ ] Definir eventos de entrada mais valiosos para automacao
- [ ] Criar endpoint para ingestao automatizada de alertas ou payloads
- [ ] Padronizar payload de requisicao e resposta para workflows
- [ ] Criar fluxo n8n para receber evento e chamar o SOCC
- [ ] Criar fluxo n8n para abrir ticket ou registrar caso
- [ ] Criar fluxo n8n para notificacao operacional
- [ ] Criar fluxo n8n para armazenar feedback em base central

## Entregavel P4

- integracao automatizada para operacao e orquestracao

## Fase P5 - Machine learning operacional

- [ ] Definir rotulos e qualidade minima dos dados historicos
- [ ] Criar dataset a partir das analises e feedbacks
- [ ] Selecionar features basicas de payload, IOC e contexto
- [ ] Treinar baseline com algoritmo simples
- [ ] Avaliar metricas de classificacao e ranking
- [ ] Comparar heuristica x LLM x classificador
- [ ] Integrar score do modelo ao fluxo como apoio, nao como decisao final
- [ ] Implementar monitoramento de drift e re-treino

## Entregavel P5

- score de priorizacao e sugestao de verdict baseada em historico

## Fase P6 - Knowledge graph

- [ ] Definir entidades e relacoes do dominio
- [ ] Escolher modelo de armazenamento do grafo
- [ ] Criar pipeline de extracao de entidades e relacoes
- [ ] Popular grafo com dados historicos e novas analises
- [ ] Criar consultas de correlacao uteis para investigacao
- [ ] Exibir correlacoes relevantes na interface

## Entregavel P6

- correlacao avancada entre artefatos, campanhas e ativos

## Tarefas tecnicas transversais

- [ ] Adicionar testes unitarios para adaptador da LLM
- [x] Adicionar testes para schema de resposta
- [x] Adicionar testes de integracao do endpoint de chat
- [x] Adicionar testes para o loader da camada declarativa do agente
- [x] Adicionar observabilidade basica: latencia, erros, taxa de schema valido
- [x] Adicionar observabilidade de recursos: CPU, GPU, memoria e backend de inferencia ativo
- [x] Criar feature flags para ligar e desligar modulos
- [x] Documentar variaveis de ambiente
- [x] Revisar tratamento de dados sensiveis em logs e prompts
- [x] Criar estrategia de fallback quando a LLM estiver indisponivel
- [x] Documentar estrategia de instalacao e bootstrap do runtime local

## Backlog de produto

- [ ] Modo "explicar para N1"
- [ ] Modo "resposta curta" e "resposta detalhada"
- [ ] Upload de arquivos para analise
- [ ] Templates de resposta por tipo de incidente
- [ ] Exportacao para markdown, JSON e ticket
- [ ] Comparacao entre respostas de diferentes modelos locais
- [ ] Biblioteca de prompts por caso de uso
- [ ] Gateway com suporte a multiplos backends locais de inferencia
- [ ] Perfil de tuning para GPU versus CPU por modelo

## Criterios de pronto do MVP

- [x] Usuario consegue conversar com a LLM local pela UI
- [x] Sistema devolve JSON estruturado valido
- [ ] Sistema extrai IOCs basicos com consistencia aceitavel
- [x] Analista consegue registrar feedback
- [ ] Fluxo possui logs e tratamento de erro suficiente para suporte
- [x] Fluxo possui logs e tratamento de erro suficiente para suporte
- [x] Persona, playbooks e ferramentas podem ser carregados a partir da estrutura do `SOC Copilot`

## Ordem recomendada de execucao

1. P0 - fundacao do SOC Copilot
2. P0.5 - empacotamento e runtime instalavel
3. P1 - chat real
4. P1.5 - runtime de inferencia e GPU
5. P2 - analise estruturada
6. P3 - RAG
7. P4 - n8n
8. P5 - ML
9. P6 - knowledge graph
