# Product Requirements Document (PRD): SOC Copilot Local - Fase 2

## 1. Objetivo da Fase 2

Expandir o MVP para ganhar profundidade analítica, memória operacional e priorização inteligente sem comprometer a segurança e o controle conquistados na Fase 1.

A Fase 2 deve começar somente após:

- MVP estável em produção local
- suíte de regressão confiável
- templates e regras consolidadas
- taxa baixa de retrabalho manual

## 2. Objetivos de Produto

1. Reaproveitar conhecimento de casos anteriores.
2. Melhorar a precisão da classificação sugerida.
3. Aumentar a velocidade de triagem com contexto histórico.
4. Ajudar no tuning de regras e detecção de falsos positivos recorrentes.
5. Evoluir a semi-LLM sem deixá-la assumir o controle do fluxo.

## 3. Capacidades Principais

### 3.1. Busca Histórica

Adicionar interface de consulta por:

- cliente
- comportamento
- regra
- IOC
- usuário
- ativo
- classificação final

### 3.2. Similaridade de Casos

O sistema deve encontrar casos parecidos com base em:

- regra
- cliente
- entidades extraídas
- texto normalizado do comportamento
- classificação final anterior

Essa similaridade deve ser usada apenas como apoio, nunca como decisão automática.

### 3.3. Memória Analítica

Permitir que o sistema recupere:

- racionais anteriores
- modelos mais usados por tipo de evento
- alertas de qualidade recorrentes
- padrões de exceção por cliente

### 3.4. Tuning Assistido

O sistema deve sugerir:

- regras com alto volume de `FP`
- entidades recorrentes benignas
- oportunidades de ajuste por cliente
- candidatas a whitelist operacional

### 3.5. Semi-LLM Ampliada

Na Fase 2, a semi-LLM poderá:

- comparar o caso atual com casos anteriores
- sugerir causalidade mais refinada
- explicar divergência entre ferramentas
- propor hunting adicional contextual
- apontar quando um caso parece repetição de padrão benigno ou malicioso

## 4. Novos Requisitos Funcionais

### 4.1. Base Histórica

Persistir, com retenção configurável:

- payload normalizado
- entidades extraídas
- classificação final decidida pelo analista
- saída final aprovada
- notas de revisão e correção

### 4.2. Indexação

Indexar por:

- cliente
- regra
- tipo de saída
- IOC
- usuário
- ativo
- hash do input

### 4.3. Similaridade Semântica

Implementar busca por similaridade com embeddings locais ou vetores locais, desde que:

- não haja envio de dados sensíveis para nuvem
- o uso seja opcional
- exista fallback por filtros estruturados

### 4.4. Explicabilidade

Toda sugestão baseada em histórico ou similaridade deve informar:

- quais casos parecidos foram usados
- por que foram considerados parecidos
- qual o limite de confiança da sugestão

## 5. Papel da Semi-LLM na Fase 2

### Inteligência Adicional Permitida

- selecionar casos históricos relevantes
- resumir padrões repetitivos
- detectar inconsistência entre classificação humana e evidências
- sugerir tuning de regra
- produzir justificativa comparativa entre casos

### Restrições Mantidas

- continua sem escrever a saída final de forma livre
- continua sem decidir a classificação sozinha
- continua dependente do `Draft Engine`

## 6. MCP na Fase 2

Na Fase 2, MCP pode passar a fazer sentido se houver necessidade de:

- servir regras para múltiplos agentes
- consolidar fontes de contexto além do filesystem
- padronizar acesso à base histórica e aos artefatos
- isolar leitura de regras, modelos e memória operacional

MCP ainda não é obrigatório, mas passa a ser uma opção arquitetural útil se o projeto crescer para além de uma única aplicação local.

## 7. Arquitetura Proposta para Fase 2

Adicionar ao MVP:

- `Case Retrieval Engine`
- `Similarity Engine`
- `Historical Analytics Layer`
- `Tuning Suggestion Engine`

## 8. Persistência e Dados

Expandir o banco para suportar:

- casos históricos
- versões de saída
- feedback humano
- associações entre caso atual e casos similares
- regras de exceção por cliente

## 9. Critérios de Aceite

- busca histórica funcional
- recuperação de casos similares com explicação
- sugestões de tuning baseadas em evidência
- nenhum dado sensível enviado para nuvem
- semi-LLM continua aderente ao schema de saída estruturada

## 10. Riscos

### Risco 1: Similaridade enganosa

Mitigação:

- mostrar explicação
- exigir validação humana
- limitar impacto no texto final

### Risco 2: Crescimento descontrolado da base

Mitigação:

- política de retenção
- compactação
- limpeza periódica

### Risco 3: Aumento da complexidade

Mitigação:

- preservar contratos do MVP
- ativar capacidades avançadas por feature flag

## 11. Roadmap da Fase 2

1. Histórico pesquisável
2. Similaridade estruturada
3. Similaridade semântica local
4. Tuning assistido
5. Memória operacional por cliente
6. Avaliação de MCP como camada de contexto
