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

## Fase P0 - Fundacao do SOC Copilot

- [ ] Criar a pasta declarativa do agente em `.agents/soc-copilot/`
- [ ] Criar `SOUL.md` com missao, principios, limites e postura analitica
- [ ] Criar `USER.md` com contexto operacional do ambiente SOC
- [ ] Criar `AGENTS.md` com regras de coordenacao e uso de playbooks
- [ ] Criar `MEMORY.md` com convencoes iniciais e memoria operacional controlada
- [ ] Criar `TOOLS.md` com inventario dos modulos e integracoes disponiveis
- [ ] Criar `identity.md` com a versao curta da persona para prompt
- [ ] Criar `skills.md` com o indice das skills e playbooks ativos
- [ ] Criar `schemas/analysis_response.json`
- [ ] Criar playbook `skills/payload-triage.md`
- [ ] Criar playbook `skills/phishing-analysis.md`
- [ ] Criar playbook `skills/malware-behavior.md`
- [ ] Criar playbook `skills/suspicious-url.md`
- [ ] Definir politica de versionamento para memoria, playbooks e tools
- [ ] Implementar loader no backend para ler essa estrutura
- [ ] Definir prioridade entre persona base, playbook, memoria e contexto da sessao

## Entregavel P0

- estrutura inicial do `SOC Copilot` pronta para ser consumida pelo backend

## Fase P0.5 - Empacotamento e runtime instalavel

- [ ] Definir a arquitetura alvo do pacote `socc/` com divisao entre `cli`, `core`, `gateway` e `utils`
- [ ] Mapear a migracao gradual da estrutura atual `soc_copilot/` e `modules/` para o pacote instalavel
- [ ] Criar `pyproject.toml` com entrypoint de CLI
- [ ] Definir comandos iniciais da CLI, como `socc init`, `socc chat` e `socc analyze`
- [ ] Implementar bootstrap local do ambiente do agente em `~/.socc` ou diretório equivalente
- [ ] Separar o motor do agente da interface web para reutilizacao por CLI e automacao
- [ ] Criar camada `gateway` para chamadas ao backend de inferencia
- [ ] Criar camada `gateway` para integracao com MCP
- [ ] Definir contrato interno entre engine, gateway e tools
- [ ] Documentar estrategia de distribuicao, instalacao e upgrade do runtime

## Entregavel P0.5

- base arquitetural pronta para evoluir o SOCC de app web para runtime instalavel reutilizavel

## Fase P1 - Fundacao do chat real

- [ ] Mapear a arquitetura atual do backend, templates e rotas do chat
- [ ] Confirmar como o MCP atual esta sendo usado e desacoplar o fluxo principal de chat dele, se necessario
- [ ] Definir contrato de API para o chat
- [ ] Criar endpoint `POST /api/chat`
- [ ] Criar endpoint de streaming, se o stack suportar SSE ou WebSocket
- [ ] Implementar adaptador para LLM local
- [ ] Externalizar configuracoes em `.env`
- [ ] Padronizar timeout, temperatura, contexto maximo e nome do modelo
- [ ] Criar prompt de sistema especializado para analise SOC
- [ ] Carregar no fluxo do chat a persona base do `SOC Copilot`
- [ ] Selecionar playbook aplicavel por tipo de entrada
- [ ] Implementar validacao basica de entrada
- [ ] Registrar logs tecnicos do fluxo de inferencia
- [ ] Persistir sessoes e mensagens
- [ ] Conectar `chat.html` ao endpoint real
- [ ] Exibir estado de carregamento e erros na UI
- [ ] Implementar streaming incremental na tela
- [ ] Garantir reset de conversa

## Entregavel P1

- chat funcional de ponta a ponta com resposta da LLM local e persona carregada

## Fase P1.5 - Runtime de inferencia e GPU

- [ ] Definir backend principal de inferencia local com suporte a GPU
- [ ] Mapear opcoes de backend compativeis com gateway local
- [ ] Implementar configuracao de device por ambiente
- [ ] Priorizar GPU como padrao de execucao quando disponivel
- [ ] Implementar fallback controlado para CPU
- [ ] Registrar metricas basicas de uso de CPU, uso de GPU, latencia e fallback
- [ ] Criar estrategia de limites para evitar sobrecarga de CPU em inferencia continua
- [ ] Validar impacto de streaming e concorrencia no consumo de recursos

## Entregavel P1.5

- runtime de inferencia operacional com preferencia por GPU e observabilidade basica de recursos

## Fase P2 - Analise estruturada de payload

- [ ] Definir schema JSON oficial da resposta da IA
- [ ] Validar resposta da LLM contra schema no backend
- [ ] Criar parser ou fallback para respostas malformadas
- [ ] Implementar extracao deterministica de IOCs basicos
- [ ] Implementar campos `summary`, `verdict`, `confidence`, `iocs`, `ttps`, `risk_reasons`, `recommended_actions`
- [ ] Separar fatos observados de inferencias da IA
- [ ] Criar mapeamento preliminar para MITRE ATT&CK
- [ ] Exibir analise estruturada na UI alem do texto livre
- [ ] Permitir copiar ou exportar a analise
- [ ] Criar feedback do analista: aprovar, corrigir, rejeitar
- [ ] Persistir feedback vinculado a sessao e payload

## Entregavel P2

- analise auditavel e reaproveitavel, com dados estruturados

## Fase P3 - RAG e bases de inteligencia

- [ ] Levantar fontes internas disponiveis
- [ ] Definir politica de limpeza e normalizacao dos documentos
- [ ] Escolher vetor store local ou compativel com o stack
- [ ] Criar pipeline de ingestao e indexacao
- [ ] Definir chunking e estrategia de embeddings
- [ ] Implementar busca semantica por contexto
- [ ] Anexar trechos recuperados ao prompt
- [ ] Exibir fontes utilizadas na resposta final
- [ ] Criar estrategia de versionamento e reindexacao
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
- [ ] Adicionar testes para schema de resposta
- [ ] Adicionar testes de integracao do endpoint de chat
- [ ] Adicionar testes para o loader da camada declarativa do agente
- [ ] Adicionar observabilidade basica: latencia, erros, taxa de schema valido
- [ ] Adicionar observabilidade de recursos: CPU, GPU, memoria e backend de inferencia ativo
- [ ] Criar feature flags para ligar e desligar modulos
- [ ] Documentar variaveis de ambiente
- [ ] Revisar tratamento de dados sensiveis em logs e prompts
- [ ] Criar estrategia de fallback quando a LLM estiver indisponivel
- [ ] Documentar estrategia de instalacao e bootstrap do runtime local

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

- [ ] Usuario consegue conversar com a LLM local pela UI
- [ ] Sistema devolve JSON estruturado valido
- [ ] Sistema extrai IOCs basicos com consistencia aceitavel
- [ ] Analista consegue registrar feedback
- [ ] Fluxo possui logs e tratamento de erro suficiente para suporte
- [ ] Persona, playbooks e ferramentas podem ser carregados a partir da estrutura do `SOC Copilot`

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
