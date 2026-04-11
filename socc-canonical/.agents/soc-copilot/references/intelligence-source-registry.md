# Intelligence Source Registry

## Modelo mínimo de fonte

```json
{
  "id": "sops-internos",
  "name": "SOPs Internos",
  "kind": "document_set",
  "trust": "internal",
  "path": "/caminho/para/documentos",
  "tags": ["sop", "runbook", "soc"],
  "description": "Procedimentos operacionais validados pelo time."
}
```

## Campos

- `id`: identificador estável e legível por máquina
- `name`: nome amigável para UI, CLI e auditoria
- `kind`: tipo da fonte, por exemplo `document_set`, `case_notes`, `threat_reports`
- `trust`: `internal`, `curated_external` ou equivalente
- `path`: arquivo ou diretório local de origem
- `tags`: rótulos para futuras estratégias de retrieval e filtro
- `description`: contexto resumido para o analista

## Convenções

- prefira um `id` curto, previsível e sem espaços
- evite misturar fontes internas e externas no mesmo `source_id`
- se um acervo tiver ciclo de vida próprio, mantenha uma fonte separada
- trate coleções históricas sensíveis como fontes distintas para facilitar desligamento e reindexação
