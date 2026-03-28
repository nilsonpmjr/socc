# PRD - SOCC Copiloto de IA para Analise de Payloads

## 1. Resumo executivo

Este documento define a evolucao do SOCC para um copiloto de analise de payloads com suporte de LLM local, enriquecimento contextual e, em fases posteriores, classificacao baseada em machine learning e correlacao por knowledge graph.

O objetivo inicial nao e substituir o analista, mas acelerar triagem, sumarizacao, extracao de IOCs/TTPs e recomendacao de proximos passos com rastreabilidade e baixo custo operacional.

Como evolucao natural do produto, o SOCC tambem deve poder operar como um runtime instalavel no estilo OpenClaw, com CLI propria, gateway local para execucao do LLM e integracao MCP, permitindo reutilizar o mesmo motor via terminal, automacao e interface web.

## 2. Contexto

Hoje existe uma pagina de chat inspirada em interfaces modernas, um MCP associado ao ambiente atual e a intencao de usar uma LLM local `qwen2.5:3b` para apoiar a analise de payloads.

Pelo contexto atual, ainda nao existe um fluxo de chat funcional de ponta a ponta com a LLM, nem um pipeline completo de analise estruturada.

Tambem surgiu a necessidade de criar uma camada de agente semelhante ao modelo usado por ferramentas como OpenClaw, com arquivos declarativos de identidade, memoria, ferramentas e playbooks, permitindo que o `SOC Copilot` tenha uma persona consistente e versionada.

Tambem passa a fazer parte do contexto de produto a necessidade de empacotar o SOCC como componente instalavel, com bootstrap local do agente, gateway para LLM + MCP e preferencia por inferencia em GPU, reduzindo saturacao de CPU em operacao continua.

## 3. Problema

Analistas SOC perdem tempo com:

- leitura manual de payloads e logs desestruturados
- extracao repetitiva de IOCs
- correlacao manual com inteligencia interna e externa
- classificacao inconsistente entre casos parecidos
- baixa reutilizacao do aprendizado acumulado em casos anteriores

## 4. Visao do produto

Transformar o SOCC em um assistente operacional para analistas, capaz de:

- conversar sobre um payload ou alerta em linguagem natural
- retornar analise estruturada e auditavel
- buscar contexto nas bases de inteligencia da organizacao
- sugerir verdict, risco, TTPs e acoes recomendadas
- aprender com feedback humano para melhorar priorizacao e precisao
- operar com uma persona tecnica consistente e controlada por arquivos versionados
- operar tanto como aplicacao web quanto como runtime instalavel com CLI e gateway reutilizavel

## 5. Objetivos

### Objetivos de negocio

- reduzir o tempo medio de triagem de payloads
- aumentar padronizacao das analises
- melhorar qualidade do registro tecnico de incidentes
- preparar base historica para modelos de ML e correlacao avancada

### Objetivos de produto

- disponibilizar chat funcional com LLM local
- retornar respostas estruturadas em JSON e tambem em formato legivel
- permitir enriquecimento com bases internas e externas
- registrar feedback do analista para melhoria continua
- centralizar comportamento do copiloto em uma camada declarativa reutilizavel
- disponibilizar um modo instalavel com bootstrap local e comandos operacionais
- permitir que a inferencia priorize GPU quando houver hardware disponivel

## 6. Nao objetivos

Esta fase nao pretende:

- automatizar bloqueios sem revisao humana
- treinar uma LLM do zero
- substituir SIEM, EDR ou ferramenta de case management
- entregar um knowledge graph completo antes de existir extracao confiavel de entidades
- deslocar para markdown toda a logica que deve permanecer no backend

## 7. Usuarios alvo

- analista SOC nivel 1: precisa de triagem rapida e explicacoes claras
- analista SOC nivel 2: precisa de evidencias, correlacao e contexto tecnico
- lideranca tecnica: precisa de consistencia, auditoria e metricas

## 8. Casos de uso principais

1. O analista cola um payload no chat e recebe:
   - resumo tecnico
   - IOCs extraidos
   - possiveis TTPs
   - verdict inicial
   - score de confianca
   - acoes sugeridas
2. O analista envia um alerta ou artefato parcial e pede correlacao com conhecimento interno.
3. O sistema gera uma estrutura pronta para registro de incidente ou nota tecnica.
4. O analista corrige a resposta da IA, e essa correcao fica registrada para retroalimentar classificadores e regras futuras.
5. O sistema escolhe um playbook de analise adequado ao tipo de artefato, mantendo uma persona operacional consistente.

## 9. Escopo por fase

### Fase 0 - Fundacao do agente

- estrutura declarativa do `SOC Copilot`
- persona base versionada
- memoria operacional controlada
- catalogo de ferramentas
- playbooks iniciais por tipo de analise
- schema estruturado de resposta

### Fase 1 - Copiloto operacional

- chat funcional com LLM local
- streaming de resposta
- prompt especializado para contexto SOC
- saida estruturada em JSON
- memoria por sessao ou caso
- anexar ou colar payloads/textos

### Fase 2 - Analise estruturada

- extracao de IOCs
- classificacao inicial do payload
- mapeamento preliminar para MITRE ATT&CK
- explicacao com evidencias
- recomendacoes operacionais

### Fase 3 - RAG e bases de inteligencia

- indexacao de documentos internos
- recuperacao de contexto relevante antes da chamada da LLM
- exibicao de fontes utilizadas
- mecanismo de versionamento das bases consultadas

### Fase 4 - ML supervisionado

- coleta de feedback humano
- dataset de treino derivado de casos rotulados
- modelo de scoring/priorizacao
- comparacao entre heuristica, LLM e classificador

### Fase 5 - Knowledge graph

- modelagem de entidades e relacoes
- correlacao entre alertas, artefatos, IOCs, CVEs e campanhas
- navegacao por relacionamentos relevantes em investigacoes

## 10. Requisitos funcionais

### RF-01 Chat com LLM local

O sistema deve permitir conversa em tempo real com uma LLM local para analise tecnica de payloads.

### RF-02 Analise estruturada

O sistema deve retornar, no minimo:

- `summary`
- `verdict`
- `confidence`
- `iocs`
- `ttps`
- `risk_reasons`
- `recommended_actions`

### RF-03 Memoria contextual

O sistema deve manter contexto da conversa por sessao ou caso, com possibilidade de reset controlado.

### RF-04 Enriquecimento

O sistema deve consultar fontes de inteligencia configuradas e anexar esse contexto ao processo de analise.

### RF-05 Feedback do analista

O sistema deve permitir confirmar, corrigir ou rejeitar a resposta proposta.

### RF-06 Historico e auditoria

O sistema deve registrar pergunta, contexto enviado, resposta, fontes usadas e feedback aplicado.

### RF-07 Exportacao operacional

O sistema deve permitir reaproveitar a analise em formato compativel com nota tecnica, incidente, ou fluxo automatizado.

### RF-08 Integracao por automacao

O sistema deve expor endpoint ou fluxo utilizavel por ferramentas como n8n para ingestao e resposta automatizada.

### RF-09 Persona operacional configuravel

O sistema deve carregar a persona do `SOC Copilot` a partir de arquivos versionados, permitindo ajustar identidade, tom, limites e comportamento sem alterar a logica principal do backend.

### RF-10 Playbooks especializados

O sistema deve suportar playbooks por tipo de caso, como triagem de payload, phishing, malware e URL suspeita, reutilizaveis no chat e em automacoes.

### RF-11 Memoria operacional controlada

O sistema deve permitir memoria operacional do agente com escopo controlado, distinguindo conhecimento permanente, convencoes internas e historico de sessao.

### RF-12 Catalogo explicito de ferramentas

O sistema deve declarar de forma auditavel quais ferramentas, modulos e adaptadores o agente pode usar em cada fluxo.

### RF-13 Distribuicao instalavel

O sistema deve poder ser instalado como pacote executavel com CLI, incluindo comandos de bootstrap local, inicializacao do ambiente do agente e execucao de fluxos de analise fora da interface web.

Como evolucao imediata dessa experiencia instalavel, o fluxo deve se aproximar do OpenClaw com:

- onboarding guiado via CLI
- comando de diagnostico do ambiente
- instalacao local previsivel em `~/.socc` com manifesto, workspace seedado e trilha clara de configuracao
- caminho progressivo de "instalar -> configurar -> validar -> servir"

### RF-14 Gateway local para LLM e MCP

O sistema deve prover um gateway local ou camada de runtime capaz de intermediar chamadas ao LLM, execucao de ferramentas e integracao com servidores MCP de forma reutilizavel entre chat, CLI e automacoes.

### RF-15 Preferencia por aceleracao em GPU

O sistema deve suportar configuracao de backend de inferencia com preferencia por GPU quando disponivel, incluindo fallback controlado para CPU e observabilidade minima de uso de recursos.

## 11. Requisitos nao funcionais

- operar localmente ou em ambiente controlado
- priorizar baixo consumo de recursos para o hardware atual
- ter tempo de resposta aceitavel para uso interativo
- suportar respostas parciais via streaming
- manter logs tecnicos e trilha de auditoria
- evitar vazamento de dados sensiveis em prompts e logs
- permitir desligar integracoes externas por configuracao
- manter a camada declarativa versionada e coerente com o comportamento real do sistema
- suportar distribuicao instalavel e reprodutivel em estacoes de trabalho ou servidores controlados
- priorizar inferencia acelerada por GPU para reduzir saturacao de CPU quando houver hardware adequado

## 12. Arquitetura proposta

### 12.1 Componentes

- frontend de chat no SOCC
- backend de chat e orquestracao
- camada declarativa do agente (`SOC Copilot`)
- adaptador para LLM local, preferencialmente via Ollama
- pipeline de pre-processamento do payload
- modulo de extracao de entidades
- modulo RAG para bases internas
- camada de persistencia de sessoes, mensagens e feedback
- endpoint de integracao com n8n e outros orquestradores

### 12.2 Fluxo de alto nivel

1. Usuario envia payload, alerta ou pergunta.
2. Backend normaliza entrada.
3. Sistema identifica skill ou playbook aplicavel.
4. Sistema executa extracao preliminar de sinais e IOCs.
5. Sistema recupera contexto relevante das bases de inteligencia.
6. Sistema compoe prompt com persona, playbook, memoria e contexto da sessao.
7. LLM responde em JSON estruturado.
8. Backend valida schema, persiste resultado e devolve streaming/UI.
9. Usuario confirma ou corrige a analise.
10. Feedback alimenta dataset para melhoria futura.

### 12.3 Camada declarativa do agente

Para aproximar o SOCC de um modelo semelhante ao OpenClaw, o produto deve incluir uma camada declarativa de agente separada da logica de execucao. Essa camada define identidade, regras operacionais, memoria e playbooks do `SOC Copilot`.

Estrutura sugerida:

```text
socc/
  .agents/
    soc-copilot/
      SOUL.md
      USER.md
      AGENTS.md
      MEMORY.md
      TOOLS.md
      identity.md
      skills.md
      skills/
        payload-triage.md
        phishing-analysis.md
        malware-behavior.md
        suspicious-url.md
      schemas/
        analysis_response.json
```

Responsabilidades:

- `SOUL.md`: missao, principios, limites e postura analitica do copiloto
- `USER.md`: contexto operacional do usuario e do ambiente SOC
- `AGENTS.md`: regras de coordenacao, quando usar playbooks e quando pedir validacao
- `MEMORY.md`: memoria operacional controlada, padroes recorrentes e convencoes internas
- `TOOLS.md`: capacidades disponiveis e contratos de uso dos modulos e ferramentas
- `identity.md`: resumo curto da persona para injecao eficiente em prompt
- `skills.md`: indice de skills e playbooks ativos
- `skills/`: playbooks especializados por caso de uso
- `schemas/`: contratos estruturados obrigatorios da saida

Essa camada nao substitui a implementacao em codigo. Ela deve orientar o comportamento do sistema, enquanto o backend e os modulos continuam responsaveis por extracao, validacao, integracoes e persistencia.

### 12.4 Papel dos modulos existentes

A pasta `modules` deve continuar como a camada de execucao do sistema. A camada declarativa do agente nao duplica essa logica.

Divisao sugerida:

- `.agents/soc-copilot/`: persona, regras, memoria, playbooks e schemas
- `modules/`: adaptadores, enriquecimento, montagem de draft e logica especializada
- backend de chat: orquestracao, sessoes, streaming, persistencia e validacao

Mapeamento esperado dos modulos atuais:

- `semi_llm_adapter`: adaptador para o modelo local
- `draft_engine`: montagem de prompt, composicao de resposta e organizacao do fluxo
- `ti_adapter`: enriquecimento com inteligencia e contexto tecnico

### 12.5 Evolucao para pacote instalavel estilo OpenClaw

Faz sentido aproximar o SOCC do modelo do OpenClaw desde que a transicao preserve a separacao entre:

- motor do agente
- gateway de execucao de LLM e MCP
- interfaces consumidoras, como chat web, CLI e automacoes

Estrutura alvo sugerida:

```text
soc-companion/
  socc/
    __init__.py
    cli/
      __init__.py
      main.py
      installer.py
    core/
      __init__.py
      engine.py
      memory.py
      prompts.py
      tools.py
    gateway/
      __init__.py
      llm_gateway.py
      mcp_gateway.py
    utils/
      config_loader.py
      file_parser.py
  pyproject.toml
  requirements.txt
  README.md
```

Diretrizes para esse desenho:

- o repositorio pode evoluir para `soc-companion`, mantendo o pacote Python como `socc`
- a camada atual `soc_copilot/modules` deve migrar gradualmente para `socc/core` e `socc/gateway`
- a interface web deve ser tratada como cliente do motor, nao como unico ponto de entrada
- o instalador deve preparar `~/.socc` ou diretório equivalente com `.env`, identidade, memoria, skills e configuracoes do runtime

### 12.6 Runtime, gateway e uso de GPU

O runtime instalavel deve abstrair backend local de inferencia e uso de ferramentas, permitindo trocar implementacao sem reescrever o motor do agente.

Diretrizes:

- o gateway deve encapsular chamadas ao backend local de inferencia, como Ollama ou runtime equivalente
- a estrategia padrao deve priorizar GPU quando disponivel
- a CPU deve permanecer como fallback controlado, nao como alvo principal de operacao continua quando houver GPU subutilizada
- o sistema deve registrar latencia, uso de CPU, uso de GPU e fallback de backend
- a configuracao do runtime deve permitir ajustar modelo, contexto, backend, device e politicas de fallback por ambiente

## 13. Esquema inicial de resposta

```json
{
  "summary": "Resumo tecnico do payload",
  "verdict": "benigno|suspeito|malicioso|inconclusivo",
  "confidence": 0.0,
  "iocs": [
    {
      "type": "ip|domain|url|hash|email|file|process",
      "value": "indicador",
      "context": "onde apareceu"
    }
  ],
  "ttps": [
    {
      "id": "Txxxx",
      "name": "Technique name",
      "reason": "justificativa"
    }
  ],
  "risk_reasons": [
    "motivos tecnicos que sustentam o verdict"
  ],
  "recommended_actions": [
    "proximos passos sugeridos"
  ],
  "sources": [
    "fontes internas ou externas usadas"
  ]
}
```

## 14. Integracao com n8n

O n8n deve ser tratado como camada de automacao, nao como motor principal de analise. Casos de uso recomendados:

- receber evento de alerta
- chamar endpoint do SOCC
- anexar enriquecimentos externos
- abrir ticket ou registrar caso
- enviar notificacao para Teams, Slack ou email
- armazenar feedback operacional

## 15. Estrategia de ML

ML deve entrar depois que houver historico suficiente e feedback humano minimamente confiavel.

Primeiros candidatos:

- classificacao de severidade e prioridade
- sugestao de verdict
- deduplicacao ou agrupamento de payloads parecidos
- reordenacao de resultados por relevancia

Modelos iniciais recomendados:

- Logistic Regression
- Random Forest
- XGBoost ou LightGBM

## 16. Estrategia de Knowledge Graph

Entidades iniciais:

- IP
- dominio
- URL
- hash
- arquivo
- processo
- CVE
- malware family
- campanha
- host
- usuario

Relacoes iniciais:

- resolves_to
- contacts
- downloads
- drops
- executes
- related_to
- associated_with
- exploits

## 17. Metricas de sucesso

- tempo medio de triagem antes e depois
- percentual de payloads com IOC extraido corretamente
- taxa de aceitacao da resposta pelo analista
- taxa de correcao manual
- latencia media de resposta
- percentual de respostas com fontes relevantes
- cobertura de schema valido na saida estruturada
- cobertura de playbooks adequadamente selecionados

## 18. Riscos

- hallucination da LLM sem evidencias suficientes
- baixa qualidade das bases de inteligencia
- schema inconsistente na resposta
- hardware limitar latencia ou contexto
- acoplamento excessivo com MCP ou automacoes externas
- vazamento de dados sensiveis em logs
- memoria declarativa desatualizada ou divergente do comportamento real do sistema
- playbooks crescerem sem governanca e virarem prompts conflitantes

## 19. Mitigacoes

- obrigar resposta estruturada e validacao de schema
- separar fatos observados de inferencias
- mostrar evidencias e fontes
- registrar feedback humano
- limitar escopo de automacao sem aprovacao
- usar heuristicas deterministicas antes da LLM sempre que possivel
- versionar a camada declarativa do agente junto com o codigo
- definir proprietarios e revisao tecnica para memoria, playbooks e ferramentas

## 20. Roadmap sugerido

### P0

- scaffold da estrutura declarativa do `SOC Copilot`
- definicao de persona, regras e ferramentas
- schema base de resposta estruturada
- primeiros playbooks de analise
- carregamento dessa configuracao pelo backend

### P1

- chat funcional ponta a ponta
- streaming
- adaptador LLM local
- resposta estruturada

### P2

- extracao de IOCs
- MITRE preliminar
- historico e feedback
- exportacao de analise

### P3

- RAG em bases internas
- automacoes n8n
- score de priorizacao

### Proximo passo imediato

- alinhar a experiencia de instalacao do `socc` ao modelo do OpenClaw
- adicionar `socc onboard` para bootstrap + validacao inicial
- adicionar `socc doctor` para diagnostico local e verificacao do runtime
- adicionar instalador one-shot local no estilo `install.sh`/`install-cli.sh`
- adicionar controle local de servico/daemon e atalho de dashboard por CLI

### P4

- ML supervisionado
- knowledge graph inicial

## 21. Premissas

- existe uma interface web de chat ja criada
- existe um backend Python no SOCC
- a LLM local alvo atual e `qwen2.5:3b`
- o ambiente pode usar integracao local com modelo via servico compativel
- o padrao OpenClaw sera adaptado como inspiracao arquitetural, nao como copia literal obrigatoria
- este documento foi elaborado sem leitura direta do codigo nesta sessao, por falha de acesso ao terminal, e pode ser refinado apos inspecao do repositorio

## 22. Criterios de aceite do MVP

- existe uma estrutura de agente versionada para o `SOC Copilot`
- a persona, ferramentas declaradas e schema podem ser carregados pelo backend
- o usuario envia mensagem na tela de chat e recebe resposta da LLM local
- a resposta chega via streaming ou atualizacao incremental
- o backend persiste historico da sessao
- a resposta final segue schema estruturado valido
- o sistema consegue extrair ao menos IOCs basicos de payloads comuns
- o analista consegue confirmar ou corrigir a resposta
