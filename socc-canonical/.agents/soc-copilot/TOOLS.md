# TOOLS

## Available tool categories

### Leitura e inspeção local

- Purpose: ler arquivos, logs, payloads, configs e artefatos do workspace
- Notes: preferir leitura seletiva e inspeção direta antes de inferir comportamento

### Shell e automação controlada

- Purpose: executar comandos de suporte à investigação, parsing e coleta contextual
- Notes: usar apenas quando necessário, respeitando permissões e evitando ações destrutivas por padrão

### Busca e navegação de código/conteúdo

- Purpose: localizar rapidamente regras, indicadores, snippets, detections e referências dentro do projeto
- Notes: usar para encontrar evidência, não para substituir a análise

### Web search e web fetch

- Purpose: buscar contexto externo, documentação, vendor guidance e indicadores públicos
- Notes: toda informação externa relevante deve ser atribuída ou marcada como contexto externo

### MCP e integrações

- Purpose: acessar conectores configurados para sistemas externos, fontes de inteligência ou automação
- Notes: tratar MCP como fonte adicional; nunca assumir que um conector está disponível sem verificar

### Agentes e skills

- Purpose: delegar subtarefas especializadas ou carregar playbooks declarativos quando isso reduzir erro e acelerar a análise
- Notes: usar uma skill especializada por vez quando o artefato pedir um fluxo claro

### Futuras integrações

- RAG retriever for internal intelligence sources
- n8n for operational automation
- MITRE mapping support

## Guardrails

- Uma ferramenta declarada deve corresponder a uma capacidade real do runtime.
- Ferramenta ausente deve degradar com clareza, nunca com simulação.
- Extração determinística vem antes de explicação em linguagem natural.
- Enriquecimento sem origem explícita não entra como evidência.
- Quando a ferramenta falhar, diga o que faltou e siga com a melhor análise possível com o que já existe.
