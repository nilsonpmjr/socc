# SOC Copilot - Desenho Técnico do MVP

## 1. Objetivo

Este documento traduz o PRD do MVP em desenho técnico implementável para o código já existente em `Automacao/soc_copilot`.

Ele define:

- estrutura de pastas
- módulos e responsabilidades
- contratos entre módulos
- endpoints FastAPI
- fluxo de dados
- schema SQLite
- reaproveitamento de `analise_ofensa.py`

## 2. Estado Atual do Projeto

O repositório já possui uma base funcional inicial:

- `run.py`
- `soc_copilot/main.py`
- `soc_copilot/config.py`
- `soc_copilot/modules/`
- `soc_copilot/templates/index.html`
- `soc_copilot/soc_copilot.db`
- `analise_ofensa.py`

Módulos já existentes:

- `input_adapter.py`
- `parser_engine.py`
- `rule_loader.py`
- `ti_adapter.py`
- `draft_engine.py`
- `persistence.py`

Conclusão:

- o MVP não precisa começar do zero
- a Fase 3 deve consolidar e estabilizar a arquitetura já iniciada

## 3. Estrutura de Pastas do MVP

Estrutura alvo:

```text
Automacao/
├── run.py
├── requirements.txt
├── .env
├── .env.example
├── analise_ofensa.py
├── SOC_Copilot_PRD.md
├── SOC_Copilot_Regras_Inventario.md
├── SOC_Copilot_Desenho_Tecnico_MVP.md
├── SOC_Copilot_TODO.md
└── soc_copilot/
    ├── __init__.py
    ├── main.py
    ├── config.py
    ├── schemas/
    │   ├── __init__.py
    │   ├── inputs.py
    │   ├── outputs.py
    │   └── llm_contract.py
    ├── modules/
    │   ├── __init__.py
    │   ├── input_adapter.py
    │   ├── parser_engine.py
    │   ├── rule_loader.py
    │   ├── ti_adapter.py
    │   ├── classification_helper.py
    │   ├── semi_llm_adapter.py
    │   ├── draft_engine.py
    │   └── persistence.py
    ├── services/
    │   ├── __init__.py
    │   └── analyze_service.py
    ├── templates/
    │   └── index.html
    ├── static/
    └── soc_copilot.db
```

### Decisão

No MVP:

- manter `modules/` para lógica de domínio
- adicionar `schemas/` para contratos explícitos
- adicionar `services/` para orquestração do fluxo completo

## 4. Responsabilidades dos Módulos

## 4.1. `input_adapter.py`

Responsável por:

- receber payload colado ou arquivo
- detectar formato predominante
- normalizar a entrada em uma estrutura única

Entrada:

- `raw_input: str`

Saída:

```python
(formato_detectado: str, campos_brutos: dict, raw_original: str)
```

## 4.2. `parser_engine.py`

Responsável por:

- extrair campos conhecidos
- aplicar normalização
- converter timezone
- identificar IOCs internos e externos
- aplicar defang quando aplicável

Entrada:

- `campos_brutos: dict`
- `raw_original: str`

Saída:

```python
{
  "Horario": str,
  "Usuario": str,
  "IP_Origem": str,
  "Destino": str,
  "Caminho": str,
  "LogSource": str,
  "Assunto": str,
  "IP_Origem_Privado": bool,
  "IOCs": {
    "ips_externos": list[str],
    "ips_internos": list[str],
    "urls": list[str],
    "hashes": list[str]
  }
}
```

## 4.3. `rule_loader.py`

Responsável por:

- carregar `AGENT.md`, `TOOLS.md`, `SOP.md`
- consolidar exceções por cliente
- localizar modelo aderente
- expor `RulePack` para o restante do sistema

Entrada:

- `regra: str`
- `cliente: str`

Saída:

```python
RulePack(
  agent_rules: str,
  sop_rules: str,
  client_exception: dict,
  modelo_aderente: str,
  modelo_nome: str,
  is_icatu: bool
)
```

## 4.4. `ti_adapter.py`

Responsável por:

- decidir entre `threat_check.py` e `batch.py`
- evitar duplicidade
- enriquecer IOC externo
- resumir falhas operacionais

Entrada:

- `iocs: dict`

Saída:

```python
{
  "8.8.8.8": "resultado resumido",
  "malicious[.]example": "resultado resumido"
}
```

## 4.5. `classification_helper.py`

Responsável por:

- organizar fatos observados
- preparar hipótese inicial
- identificar lacunas
- sugerir classificação candidata

Entrada:

- `fields`
- `ti_results`
- `rule_pack`
- `classificacao_input` opcional

Saída:

```python
{
  "classificacao_candidata": str,
  "racional_base": str,
  "lacunas": list[str],
  "confianca": float
}
```

## 4.6. `semi_llm_adapter.py`

Responsável por:

- aplicar a camada semi-LLM apenas como apoio analítico estruturado
- validar o contrato de saída

Entrada:

- fatos normalizados
- resultados de TI
- regras consolidadas
- classificação candidata

Saída:

JSON compatível com o contrato do PRD:

```python
{
  "resumo_factual": {...},
  "hipoteses": [...],
  "lacunas": [...],
  "classificacao_sugerida": {...},
  "mitre_candidato": {...},
  "modelo_sugerido": str,
  "blocos_recomendados": {...},
  "proximos_passos": [...],
  "alertas_de_qualidade": [...]
}
```

## 4.7. `draft_engine.py`

Responsável por:

- gerar a saída final conforme `TP`, `BTP`, `FP`, `TN`, `LTF` ou repasse técnico
- aplicar regras do SOP
- impedir markdown
- garantir anonimização
- omitir `Análise do IP:` quando não houver conteúdo relevante

Entrada:

- `classificacao`
- `fields`
- `ti_results`
- `pack`
- `analysis_helper` opcional
- `semi_llm_output` opcional

Saída:

```python
(draft_text: str, template_usado: str)
```

## 4.8. `persistence.py`

Responsável por:

- criar schema inicial
- salvar execução
- salvar resultados de TI
- salvar saída final
- listar histórico

## 4.9. `analyze_service.py`

Responsável por:

- orquestrar o fluxo completo do `/api/analyze`
- reduzir acoplamento da `main.py`

Fluxo esperado:

1. entrada
2. parsing
3. carregamento de regras
4. enriquecimento TI
5. classificação auxiliar
6. semi-LLM opcional
7. draft final
8. persistência
9. resposta da API

## 5. Contratos de Schema

## 5.1. `schemas/inputs.py`

Definir modelos para:

- `AnalyzeRequest`
- `SaveRequest`

## 5.2. `schemas/outputs.py`

Definir modelos para:

- `AnalyzeResponse`
- `HistoryResponse`
- `SaveResponse`

## 5.3. `schemas/llm_contract.py`

Definir o contrato fixo da semi-LLM.

Benefício:

- validação
- previsibilidade
- testes automáticos

## 6. Endpoints FastAPI do MVP

## 6.1. `GET /`

Responsável por:

- renderizar a interface principal

Resposta:

- `HTML`

## 6.2. `POST /api/analyze`

Responsável por:

- executar o pipeline completo de análise

Entrada:

- `ofensa_id`
- `cliente`
- `regra`
- `classificacao`
- `payload_raw`
- `arquivo` opcional

Resposta:

```json
{
  "run_id": 1,
  "formato_detectado": "json",
  "campos_extraidos": {},
  "iocs": {},
  "ti_results": {},
  "modelo_aderente": "Darktrace",
  "draft": "",
  "classificacao": "TP",
  "template_usado": "darktrace.txt"
}
```

## 6.3. `POST /api/save`

Responsável por:

- salvar o texto final em disco
- registrar o save no histórico

## 6.4. `GET /api/history`

Responsável por:

- listar execuções anteriores do MVP

## 7. Fluxo de Dados

```text
UI
  -> /api/analyze
    -> input_adapter
    -> parser_engine
    -> rule_loader
    -> ti_adapter
    -> classification_helper
    -> semi_llm_adapter (opcional por feature flag)
    -> draft_engine
    -> persistence
  <- resposta estruturada
```

## 8. Schema SQLite do MVP

## 8.1. `runs`

Campos:

- `id`
- `created_at`
- `ofensa_id`
- `cliente`
- `regra`
- `input_hash`
- `classificacao_sugerida`
- `template_usado`
- `status_execucao`

## 8.2. `intel_results`

Campos:

- `id`
- `run_id`
- `ioc`
- `tipo`
- `ferramenta`
- `resultado_resumido`
- `timestamp_consulta`

## 8.3. `analysis_helper`

Campos:

- `id`
- `run_id`
- `classificacao_candidata`
- `confianca`
- `racional_base`
- `lacunas_json`
- `semi_llm_json`

## 8.4. `outputs`

Campos:

- `id`
- `run_id`
- `tipo_saida`
- `conteudo`
- `salvo_em`

## 9. Reaproveitamento de `analise_ofensa.py`

O script atual deve ser tratado como fonte de lógica reaproveitável, não como arquitetura final.

Mapeamento:

- `convert_time_to_sp()` -> `parser_engine`
- `defang_url()` -> `parser_engine`
- `extract_iocs()` -> `parser_engine`
- `run_threat_intel()` -> `ti_adapter`
- `generate_drafts()` -> `draft_engine`

Decisão:

- não acoplar o MVP ao script monolítico
- migrar a lógica útil para os módulos atuais

## 10. Feature Flags do MVP

Flags recomendadas em `config.py`:

- `ENABLE_SEMI_LLM=false`
- `ENABLE_PERSIST_PAYLOAD=false`
- `ENABLE_HISTORY=true`

Benefício:

- MVP controlado
- rollout seguro
- facilidade de troubleshooting

## 11. Ordem de Implementação Técnica

1. estabilizar `schemas/`
2. criar `analyze_service.py`
3. refinar `parser_engine`
4. refinar `rule_loader`
5. refinar `ti_adapter`
6. estabilizar `draft_engine`
7. ajustar `persistence.py` ao schema alvo
8. simplificar `main.py`
9. adicionar `semi_llm_adapter.py` sob flag
10. validar `index.html` contra os contratos finais

## 12. Critérios de Pronto da Fase 3

- estrutura de pastas definida
- módulos e contratos definidos
- endpoints definidos
- schema SQLite definido
- reaproveitamento de `analise_ofensa.py` mapeado
- decisão arquitetural alinhada ao PRD e ao inventário

---

✅ `Fase 3 concluída`: desenho técnico do MVP consolidado.
