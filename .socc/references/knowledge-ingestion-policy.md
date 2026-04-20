# Knowledge Ingestion Policy

## Objetivo

Definir a política inicial de ingestão para a base local de conhecimento do `SOC Copilot`, preparando o runtime para RAG sem depender ainda de um vetor store definitivo.

## Fontes priorizadas

- playbooks, SOPs e runbooks internos
- notas técnicas e post-mortems
- casos históricos curados
- documentação de integrações defensivas
- referências externas previamente validadas e curadas

## Limpeza e normalização

- remover bytes nulos e quebras de linha inconsistentes
- preservar texto legível; descartar binário e arquivos acima do limite operacional
- reduzir excesso de linhas vazias sem destruir a estrutura lógica do documento
- manter o conteúdo normalizado separado do original para auditoria

## Regras operacionais

- toda fonte deve ter `source_id`, `name`, `trust`, `kind` e `path`
- referências externas devem ser marcadas como `curated_external`
- o runtime não deve misturar automaticamente conteúdo bruto e conteúdo curado sem identificação da origem
- reingestões devem ser rastreáveis por manifesto/versionamento do índice

## Chunking inicial

- chunking textual orientado a parágrafos
- alvo inicial: ~900 caracteres por chunk
- overlap inicial: ~120 caracteres
- embeddings ficam para a próxima etapa; nesta fase o índice é textual e auditável
