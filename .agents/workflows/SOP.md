---
description: Procedimento obrigatório para classificar, validar e redigir alertas
---

# SOP de Análise e Redação de Alertas

## 1. Objetivo

Este arquivo define a sequência obrigatória de trabalho. O agente deve seguir as etapas abaixo na ordem apresentada.

## 2. Fluxo obrigatório

### Etapa 1 - Entender a regra

1. Leia `all_rules_content.md` para entender a lógica da regra que gerou a ofensa.
2. Identifique qual comportamento a regra tenta detectar e quais evidências mínimas deveriam existir.

### Etapa 2 - Encontrar modelo aderente

1. Procure um modelo equivalente em `Modelos\`.
2. Se houver mais de um modelo parecido, escolha o mais próximo pelo tipo de ofensa, fonte de log e narrativa.
3. Se não houver modelo aderente, siga o formato padrão deste SOP sem inventar uma estrutura nova.

### Etapa 3 - Coletar contexto completo

1. Analise o arquivo, export ou payload por inteiro.
2. Não baseie a conclusão em trechos isolados quando houver mais contexto disponível.
3. Se houver horários, normalize a leitura para São Paulo.
4. Use apenas comandos compatíveis com Windows.
5. Evite comandos que possam gerar eventos desnecessários no ambiente monitorado.

### Etapa 4 - Validar IOCs e evidências externas

1. Siga `rules/TOOLS.md` para consultar IPs públicos, domínios e hashes externos.
2. Classifique IPs internos como internos antes de tentar reputação externa, salvo necessidade técnica do caso.
3. Se houver apenas um IOC, use somente a consulta individual.
4. Só use `batch.py` quando houver mais de um IOC e a consulta for realmente em lote.

### Etapa 5 - Classificar o caso

Escolha exatamente uma classificação:

- `True Positive`: atividade maliciosa ou fortemente suspeita com evidência suficiente.
- `Benign True Positive`: atividade confirmada como legítima, mas corretamente detectada pela regra.
- `False Positive`: a regra disparou por lógica inadequada, dado incorreto ou contexto que descaracteriza o risco esperado.
- `True Negative`: a evidência analisada não sustenta evento real de segurança.
- `Log Transmission Failure`: o problema principal está na coleta, transmissão ou integridade do log.

Regra de decisão:

1. `True Positive` permite alerta completo.
2. `Benign True Positive` exige nota de encerramento, sem alerta completo.
3. `False Positive`, `True Negative` e `Log Transmission Failure` encerram a tarefa sem alerta completo.

### Etapa 6 - Documentar o Racional Técnico

1. Após finalizar o alerta ou a nota de encerramento, crie obrigatoriamente um arquivo em `Training\Pensamento_Ofensa_[ID].md`.
2. A estrutura do arquivo deve seguir rigorosamente este modelo:
   - **Título:** `# Fluxo de Pensamento e Execução - Ofensa [ID] ([Cliente])`
   - **Metadados:** Data e Analista (Antigravity).
   - **Seção 1:** `## 1. Identificação Inicial da Demanda` (O quê, Quando, Onde, Objetivo).
   - **Seção 2:** `## 2. Análise do Evento Base` (Syslog/JSON/etc).
   - **Seção 3:** `## 3. Investigação e Contextualização` (CSV/TI/etc).
   - **Seção 4:** `## 4. Detalhamento de Raciocínio (Interno)` (Transcrição INTEGRAL dos thoughts. Documente todos os pensamentos).
   - **Seção 5:** `## 5. Próximos Passos (Execução Atual)`.
   - **Rodapé:** Divisor `---` e nota de auditoria da IA.

## 3. Formato de saída

### Exceção de cliente

Para o cliente `Icatu`, quando a operação exigir encaminhamento ao time interno de Segurança do cliente, o agente deve gerar alerta de repasse técnico mesmo que a classificação final não seja `True Positive`.

Nesse caso:

1. mantenha a classificação técnica real do caso
2. não trate o envio como encerramento automático
3. deixe explícito que a continuidade da apuração cabe ao time do cliente
4. use tom objetivo, sem afirmar confirmação de exfiltração ou comprometimento quando a evidência não sustentar isso

### Quando a classificação for `Benign True Positive`

Entregue uma nota de encerramento com:

1. `Classificação Final: Benign True Positive`
2. `Justificativa da benignidade de forma breve e direta, com no máximo 3 a 4 frases, em um parágrafo:`

Não gere saudação, alerta completo, referência MITRE ou recomendação ao cliente.

### Quando a classificação for `False Positive`, `True Negative` ou `Log Transmission Failure`

Entregue apenas:

1. `Classificação Final:`
2. `Justificativa da benignidade de forma breve e direta, com no máximo 3 a 4 frases, em um parágrafo:`

Não gere saudação, narrativa completa, referência MITRE ou recomendação ao cliente.

### Quando a classificação for `True Positive`

Se existir modelo aderente, siga o modelo.

Se não existir modelo aderente, use a seguinte estrutura exata:

- Introdução: `Prezados,` seguida de uma linha em branco.
- Título: identificação clara do comportamento no primeiro parágrafo, como nos modelos existentes.
- Narrativa do Evento: segundo parágrafo com o quê, quem, quando e onde.
- Detalhes do Evento: campos técnicos (APENAS SE HOUVER) com uma linha em branco entre eles:
  - `Usuário:`
  - `IP de Origem:`
  - `Destino:` ou `Arquivo/Porta:` conforme o caso
  - `Diretório/Caminho:` quando aplicável
  - `Log Source:`
- `Análise do IP:` bloco dedicado quando houver IOC de rede relevante para a conclusão.
- `Análise Técnica:` parágrafo técnico objetivo.
- Anexos: `Em anexo o Payload.`
- `Referência:` primeiro parágrafo da técnica do MITRE na íntegra em Português. NÃO INTERPRETE NEM ALTERE
- `Referência MITRE:` link direto da técnica.
- `Recomendação:` parágrafo final fluido, anônimo e reaproveitável, preferencialmente iniciado por `Recomendamos ...`.

Não inclua nada após a recomendação.

## 4. Regras de redação

1. Não use asteriscos, negrito, itálico ou listas no corpo final do alerta.
2. Não use subtítulos fora dos rótulos previstos neste arquivo ou no modelo escolhido.
3. Os rótulos `Análise do IP:`, `Análise Técnica:` e `Referência MITRE:` devem ser preservados quando fizerem parte do modelo aderente ou da estrutura padrão deste SOP.
4. O bloco final de recomendação deve ser mantido no alerta completo, preferencialmente iniciado por `Recomendamos ...`.
5. Se algum campo estiver ausente, não inclua nada.
6. Mantenha a recomendação genérica o suficiente para reuso.
7. Não exponha nenhum dado do cliente na recomendação (nomes de serviços, máquinas, usuários ou programas).
8. Todo alerta e toda nota de encerramento devem ser entregues com acentuação e cedilha corretas em português. Texto sem acentuação é erro de saída.
9. Faça uma revisão final de idioma antes da entrega, verificando especialmente palavras como `não`, `análise`, `ação`, `segurança`, `técnica`, `usuário`, `informações` e `referência`.

## 5. Aprendizado operacional

Se durante a execução houver erro recorrente, ambiguidade relevante ou ajuste de processo que mereça ser lembrado depois, registre em `rules/MEMORY.md` com nota curta e objetiva.
