# Product Requirements Document (PRD): SOC Copilot Local - MVP

## 1. Resumo Executivo

### Problema

Analistas de SOC gastam tempo excessivo em tarefas repetitivas e sensíveis a erro:

- parsing de payloads brutos em JSON, CSV e textos copiados do QRadar
- extração e normalização de entidades
- enriquecimento de IOCs externos
- conversão de horário para São Paulo
- aplicação rígida das regras do SOP e dos modelos internos
- geração de alertas e notas com português correto, sem markdown e com anonimização adequada

O processo atual funciona, mas depende demais de atenção manual e de interpretação consistente das regras.

### Solução Proposta

Construir um sistema local chamado `SOC Copilot` para apoiar a análise e a redação operacional, com foco em previsibilidade, velocidade e aderência ao fluxo atual.

O MVP será dividido em três camadas:

1. `Parsing e Normalização Determinística`
2. `Enriquecimento e Regras Operacionais`
3. `Geração de Saída Controlada`

A ferramenta deve priorizar lógica determinística. A camada semi-LLM, se usada, ficará restrita ao apoio analítico estruturado e jamais será a fonte única do texto final repassado ao cliente.

### Objetivo do MVP

Entregar um fluxo local e confiável que:

- receba payload bruto e metadados da ofensa
- extraia campos normalizados
- consulte Threat Intelligence quando aplicável
- aplique regras do SOP, modelos e exceções por cliente
- gere rascunhos controlados de `TP`, `BTP`, `FP`, `TN`, `LTF` e `alerta de repasse técnico`
- permita revisão humana antes de copiar ou salvar o texto final

### Métricas de Sucesso do MVP

- Reduzir o tempo de análise e rascunho para menos de 2 minutos em casos comuns.
- Atingir pelo menos 95% de conformidade automática em uma suíte de casos reais anonimizados.
- Garantir 100% de conformidade em:
  - acentuação e cedilha
  - formato de horário
  - ausência de markdown
  - não exibição de `Análise do IP:` vazia
  - uso correto de `threat_check.py` versus `batch.py`

## 2. Escopo do Produto

### Usuários

- Analista N1
- Analista N2
- Analista N3
- Analista de Qualidade / Processos

### Casos de Uso Principais

1. Colar payload bruto e obter campos estruturados.
2. Enriquecer IOCs externos com a ferramenta local de Threat Intelligence.
3. Visualizar a análise estruturada antes da geração do texto final.
4. Gerar alerta ou nota no formato operacional correto.
5. Copiar o resultado final ou salvar em pasta local.

### Fora de Escopo no MVP

- integração de escrita em QRadar, Jira, plataformas operacionais ou e-mail
- chat aberto com comportamento conversacional livre
- dashboard histórico completo
- busca avançada por ofensas antigas
- orquestração automática de decisões sem revisão humana
- embeddings, RAG, vetores ou memória semântica
- MCP como dependência obrigatória

## 3. Princípios de Projeto

1. `Determinismo primeiro`
   - parsing, classificação base, uso de TI, timezone e formatação devem ser reprodutíveis

2. `A semi-LLM apoia, não governa`
   - pode resumir, organizar hipóteses e explicar contexto
   - não decide sozinha a classificação final
   - não escreve sozinha o alerta final fora do template controlado

3. `As regras locais são a fonte da verdade`
   - `.agents/rules`
   - `.agents/workflows/SOP.md`
   - modelos em `Modelos\`
   - exceções por cliente

4. `Privacidade por padrão`
   - tudo local
   - sem envio de payloads para nuvem
   - persistência mínima no MVP

5. `Saída operacional antes de interface bonita`
   - a qualidade do texto e a aderência ao SOP vêm antes de qualquer refinamento visual

## 4. Requisitos Funcionais

### 4.1. Entrada

O sistema deve aceitar:

- texto bruto colado
- arquivos `.json`
- arquivos `.csv`
- campos adicionais:
  - `ID da Ofensa`
  - `Cliente`
  - `Nome da Regra`
  - `Tipo de Saída Desejado` opcional

### 4.2. Parsing e Normalização

O sistema deve:

- identificar horário, usuário, IP de origem, destino, diretório, log source e assunto
- normalizar chaves equivalentes
- extrair IOCs do conteúdo bruto
- distinguir IOC interno de IOC externo
- aplicar defang em URLs e domínios quando necessário

Mapeamentos mínimos esperados:

- `SourceIp`, `SourceIP`, `ClientIP` -> `IP_Origem`
- `UserId`, `Username`, `User` -> `Usuário`
- `CreationTime`, `StartTime`, `LogTime` -> `Horário`

### 4.3. Timezone

Toda hora de entrada em UTC deve ser convertida para São Paulo.

Regra operacional:

- no texto final, usar `HH:MM:SS`
- data só deve aparecer quando o modelo exigir explicitamente

### 4.4. Enriquecimento de IOC

Regras obrigatórias:

- IOC único externo: usar `threat_check.py --dashboard`
- múltiplos IOCs externos: usar `batch.py`
- nunca consultar o mesmo IOC duas vezes por ferramentas diferentes
- não consultar IP privado
- registrar falha operacional sem inventar reputação

### 4.5. Aplicação de Regras

O sistema deve carregar e aplicar:

- `AGENT.md`
- `TOOLS.md`
- `SOP.md`
- exceções por cliente
- modelos equivalentes em `Modelos\`

Regras mínimas a aplicar:

- acentuação e cedilha corretas
- texto em português
- sem markdown
- anonimização de recomendações
- classificação obrigatória
- estrutura correta de `TP`, `BTP`, `FP`, `TN`, `LTF`
- exceção da `Icatu` para repasse técnico

### 4.6. Geração de Saída

O sistema deve gerar, conforme o caso:

- alerta completo `True Positive`
- nota de encerramento `Benign True Positive`
- nota curta `False Positive`, `True Negative` ou `Log Transmission Failure`
- alerta de repasse técnico quando a regra do cliente exigir

Para `True Positive` sem modelo aderente, a saída deve seguir a ordem:

1. `Prezados,`
2. `Título`
3. `Narrativa do Evento`
4. `Detalhes do Evento`
5. `Análise do IP:` quando aplicável
6. `Análise Técnica:`
7. `Em anexo o Payload.`
8. `Referência:`
9. `Referência MITRE:`
10. `Recomendação:`

### 4.7. Interface

O MVP deve fornecer:

- formulário simples
- prévia dos campos extraídos
- prévia da análise técnica estruturada
- texto final gerado
- botão `Copiar`
- botão `Salvar`

A interface deve ser rápida, funcional e sem dependência de bibliotecas pesadas.

## 5. Requisitos Não Funcionais

### Segurança e Privacidade

- processamento 100% local
- sem envio de payloads para modelos ou APIs externas, exceto a ferramenta local de TI já aprovada
- segredos em `.env`
- logs do sistema sem conteúdo sensível desnecessário
- caminho de saída controlado

### Confiabilidade

- parser resiliente a CSV malformado
- fallback para campos ausentes
- mensagens claras de erro
- timeout configurável nas integrações externas

### Manutenibilidade

- separar parser, engine de regras, enriquecimento, templates e UI
- evitar lógica de negócio dentro da camada de interface
- permitir adicionar novos modelos sem reescrever o sistema

### Performance

- resposta comum em menos de 5 segundos sem enriquecimento
- resposta comum em menos de 30 segundos com enriquecimento simples

## 6. Arquitetura Proposta

### Decisão para o MVP

Usar `FastAPI + Jinja2 + Python + SQLite`.

Justificativa:

- simples de subir localmente
- fácil integração com scripts já existentes
- boa separação entre UI e backend
- baixo custo operacional

### Componentes

#### 1. `Input Adapter`

Responsável por:

- receber texto e arquivos
- detectar formato
- normalizar entrada

#### 2. `Parser Engine`

Responsável por:

- extrair campos conhecidos
- aplicar regex
- classificar IOCs internos e externos
- detectar campos ausentes

#### 3. `Rule Pack Loader`

Responsável por:

- carregar regras locais
- ler SOP e exceções
- localizar modelo aderente
- entregar um objeto de regras já consolidado

#### 4. `Threat Intel Adapter`

Responsável por:

- decidir entre `threat_check.py` e `batch.py`
- evitar duplicidade
- consolidar resultados
- retornar erro de forma segura

#### 5. `Classification Helper`

Responsável por:

- organizar os fatos observados
- sugerir hipóteses e lacunas
- preparar dados para a etapa de saída

#### 6. `Semi-LLM Adapter`

Responsável por:

- receber fatos já normalizados
- gerar apoio analítico estruturado
- devolver saída em formato estrito

#### 7. `Draft Engine`

Responsável por:

- preencher templates controlados
- aplicar restrições de formato
- validar a saída final

#### 8. `Persistence Layer`

No MVP, armazenar apenas:

- metadados da execução
- hash do payload
- saída gerada
- classificação sugerida

Não armazenar `payload_raw` completo por padrão no MVP. Se isso for realmente necessário, deve existir configuração explícita de retenção.

## 7. Contrato da Semi-LLM

### Objetivo

Fornecer apoio analítico estruturado, sem substituir as regras determinísticas e sem gerar o texto final por conta própria.

### Inteligência Permitida

- resumir tecnicamente o comportamento observado
- organizar a sequência `o quê`, `onde`, `quem`, `quando` e `por quê`
- sugerir hipóteses ranqueadas
- apontar lacunas de evidência
- sugerir classificação candidata com justificativa
- sugerir técnica MITRE candidata
- sugerir o modelo mais aderente
- sugerir próximos passos de hunting
- validar qualidade textual e aderência ao SOP

### Inteligência Proibida

- decidir sozinha a classificação final
- ignorar regras do SOP
- inventar campos ausentes
- alterar a estrutura final dos templates
- substituir a validação determinística de TI, timezone e anonimização
- consultar fontes externas por conta própria

### Entrada Obrigatória

- campos normalizados do parser
- IOCs extraídos
- resultados de Threat Intelligence
- regras consolidadas
- classificação candidata
- cliente
- modelo aderente, se houver

### Saída Obrigatória

A semi-LLM deve devolver um objeto estruturado, nunca texto final solto.

Formato de referência:

```json
{
  "resumo_factual": {
    "o_que": "",
    "quem": [],
    "onde": [],
    "quando": "",
    "artefatos": []
  },
  "hipoteses": [
    {
      "tipo": "false_positive",
      "confianca": 0.0,
      "justificativa": ""
    }
  ],
  "lacunas": [],
  "classificacao_sugerida": {
    "tipo": "",
    "confianca": 0.0,
    "racional": ""
  },
  "mitre_candidato": {
    "tecnica": "",
    "justificativa": ""
  },
  "modelo_sugerido": "",
  "blocos_recomendados": {
    "incluir_analise_ip": false,
    "incluir_referencia_mitre": false
  },
  "proximos_passos": [],
  "alertas_de_qualidade": []
}
```

### Regras de Execução

- a semi-LLM só roda depois do parsing e das regras mínimas
- a semi-LLM não altera diretamente o banco
- o `Draft Engine` continua sendo o responsável pela saída final
- qualquer campo não confiável deve ser marcado como lacuna, nunca inferido como fato

## 8. Dados e Persistência

### SQLite no MVP

Tabela mínima sugerida:

- `runs`
  - `id`
  - `created_at`
  - `ofensa_id`
  - `cliente`
  - `regra`
  - `input_hash`
  - `classificacao_sugerida`
  - `template_usado`
  - `status_execucao`

- `intel_results`
  - `run_id`
  - `ioc`
  - `tipo`
  - `ferramenta`
  - `resultado_resumido`
  - `timestamp_consulta`

- `analysis_helper`
  - `run_id`
  - `resumo_json`
  - `hipoteses_json`
  - `lacunas_json`
  - `qualidade_json`

- `outputs`
  - `run_id`
  - `tipo_saida`
  - `conteudo`
  - `salvo_em`

## 9. Critérios de Aceite

### Aceite Funcional

- aceita JSON, CSV e texto colado
- extrai corretamente os campos mínimos em pelo menos 95% da suíte de testes
- converte horário para São Paulo
- usa `threat_check.py` para IOC único
- usa `batch.py` apenas para múltiplos IOCs
- gera `TP`, `BTP`, `FP`, `TN`, `LTF` e repasse técnico Icatu

### Aceite da Semi-LLM

- devolve apenas estrutura JSON
- não gera texto final solto
- não preenche fatos inexistentes
- aponta lacunas quando faltarem dados

### Aceite de Saída

- sem markdown
- sem palavras sem acento quando deveriam ter
- sem `Análise do IP:` vazia
- sem recomendação com dados sensíveis do cliente
- com labels corretos do SOP

### Aceite de Segurança

- sem segredo hardcoded
- sem upload para nuvem
- sem persistência indevida de payload sensível por padrão

## 10. Estratégia de Testes

Criar suíte local com casos anonimizados cobrindo:

- JSON simples
- CSV malformado
- múltiplos IOCs externos
- sem IOC externo
- IP privado apenas
- caso `TP`
- caso `BTP`
- caso `FP`
- caso `TN`
- caso `Log Transmission Failure`
- exceção da `Icatu`

Além disso, validar automaticamente:

- presença ou ausência correta de blocos
- acentuação mínima esperada
- formatação de horário
- ausência de markdown
- aderência do JSON da semi-LLM ao schema esperado

## 11. Roadmap do MVP

1. Parser local
2. Loader de regras
3. Integração TI
4. Draft Engine
5. Semi-LLM Adapter sob contrato estrito
6. UI simples
7. Salvamento local
8. Suíte de testes de regressão

## 12. Riscos e Mitigações

### Risco 1: CSV inconsistente

Mitigação:

- parser tolerante
- fallback por regex
- mensagens claras de campo ausente

### Risco 2: TI lenta ou limitada

Mitigação:

- cache por IOC
- timeout
- decisão automática entre script individual e lote

### Risco 3: Deriva de regras

Mitigação:

- loader central de regras
- testes com snapshots de saída
- validação de estrutura antes da entrega

### Risco 4: Saída bonita porém errada

Mitigação:

- semi-LLM confinada a resumo estruturado
- geração final via templates controlados

## 13. Decisões em Aberto

1. A classificação final será selecionada manualmente pelo analista ou o sistema deve apenas sugerir uma?
2. O MVP deve permitir desligar completamente a semi-LLM por configuração?
3. O armazenamento de payload completo será proibido por padrão ou habilitável por cliente?
