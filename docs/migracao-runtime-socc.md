# Migracao Gradual de `soc_copilot` para `socc`

## Objetivo

Permitir que o SOCC evolua de aplicacao web centrada em `soc_copilot/` para runtime instalavel centrado em `socc/`, sem quebra abrupta do MVP atual.

## Regra de transicao

- novos pontos de entrada devem depender de `socc/*`
- `socc/*` pode encapsular modulos legados de `soc_copilot.modules` durante a transicao
- a web atual continua funcional, mas deixa de ser a referencia para novas integracoes
- a migracao deve acontecer por fatias coesas, nao por renomeacao em massa

## Mapa atual -> alvo

| Legado atual | Fachada/alvo em `socc/` | Papel na transicao | Status |
| --- | --- | --- | --- |
| `soc_copilot.modules.parser_engine` | `socc.core.parser` | parsing e extração de IOCs | pronto |
| `soc_copilot.modules.input_adapter` | `socc.core.input_adapter` | adaptação inicial de payload | pronto |
| `soc_copilot.modules.rule_loader` | `socc.core.analysis` | seleção de pack/modelo | pronto |
| `soc_copilot.modules.semi_llm_adapter` | `socc.core.analysis` | análise semi-LLM | pronto |
| `soc_copilot.modules.draft_engine` | `socc.core.analysis` | geração de draft | pronto |
| `soc_copilot.modules.analysis_contract` | `socc.core.analysis` | contrato estruturado | pronto |
| `soc_copilot.modules.analysis_trace` | `socc.core.analysis` | trilha analítica | pronto |
| `soc_copilot.modules.analysis_export` | `socc.core.analysis` | exportação | pronto |
| `soc_copilot.modules.chat_service` | `socc.core.chat` | chat e streaming | pronto |
| `soc_copilot.modules.persistence` | `socc.core.storage` | banco e sessões | pronto |
| `soc_copilot.modules.soc_copilot_loader` | `socc.core.agent_loader` | persona, skills e referências | pronto |
| `soc_copilot.modules.ti_adapter` | `socc.gateway.threat_intel` | enrichment TI | pronto |
| `soc_copilot.main` | `socc.core.engine` + cliente web | backend FastAPI como consumidor do runtime | em andamento |

## Ordem recomendada de extracao

### Fase 1: novas dependencias entram por `socc`

- CLI, testes novos e automacoes devem importar `socc.core.*` e `socc.gateway.*`
- wrappers legados sao aceitos nessa fase

### Fase 2: mover implementacao pura

- mover primeiro modulos sem dependencias web:
- parser
- analysis contract/trace/export
- rule loader
- threat intel gateway

### Fase 3: mover orquestracao

- mover chat runtime
- mover storage/runtime memory
- reduzir `soc_copilot.main` a camada HTTP + templates + serializacao

Status atual:

- `soc_copilot.main` ja consome fachadas de `socc.core.analysis`, `socc.core.chat`, `socc.core.parser`, `socc.core.storage` e `socc.gateway.threat_intel`
- `soc_copilot.main` tambem passou a preparar payloads via `socc.core.engine.prepare_payload_input`
- `POST /api/analyze` e `POST /api/draft` ja delegam a orquestracao principal para `socc.core.engine`
- a consolidacao/validacao de entrada de `analyze` e `draft` tambem ja foi movida para helpers do `socc.core.engine`
- o fluxo de payload do chat agora usa `socc.core.engine.build_chat_payload_response` para montar e persistir o card final
- save/export/feedback/history e listagem de sessoes de chat ja delegam ao runtime em vez de manter logica propria na camada web
- deteccao de payload e emissao SSE tambem ja estao encapsuladas fora do `main.py`
- o chat sincrono e o stream SSE agora tambem delegam ao `socc.core.engine` em vez de combinar runtime e legados dentro da rota
- `GET /api/runtime/status` e `GET /api/runtime/benchmark` agora usam payloads do runtime em vez de montar resposta na camada web
- `feedback`, `export` e `chat` tambem passaram a normalizar seus corpos JSON em helpers do runtime antes de chegar na logica principal
- o parser legado/runtime tambem passou a compartilhar um catalogo ampliado de aliases de campos de seguranca para JSONs, incluindo IPv4/IPv6, hostname, server, arquivo e hash

### Fase 4: consolidar fronteiras

- `soc_copilot.main` passa a chamar apenas `socc.core.engine`
- imports diretos de `soc_copilot.modules.*` fora da camada web deixam de existir
- modulos legados viram compat shims ou sao removidos

## Critérios de prontidao por etapa

- sem regressao na web atual
- CLI e runtime continuam operacionais
- contratos `AnalysisEnvelope` e `ChatResponseEnvelope` permanecem estaveis
- testes de regressao continuam verdes

## Riscos conhecidos

- `soc_copilot.main` ainda conhece detalhes internos do legado e do banco
- alguns testes antigos ainda importam modulos legados diretamente
- a camada de TI ainda depende do adaptador legado e de configuracao externa

## Proximo corte recomendado

O corte com melhor custo/beneficio agora e:

1. consolidar os ultimos detalhes para que `soc_copilot.main` fique so com rotas, validacao basica e serializacao
2. manter `soc_copilot.modules` apenas como implementacao interna temporaria
3. depois extrair parser + analysis para dentro de `socc/core` de forma definitiva
