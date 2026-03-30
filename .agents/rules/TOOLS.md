---
trigger: always_on
---

# Ferramentas e Integrações Disponíveis

## Regra geral

Use ferramentas apenas quando agregarem evidência real à análise. Não simule execução, não invente saídas e não pule etapas obrigatórias.

## 1. Threat Intelligence Checker

Acione obrigatoriamente esta verificação antes de redigir a parte de IOC quando houver pelo menos um destes artefatos externos:

- IP público
- domínio
- hash de arquivo

Não use esta etapa para IP privado, bogon ou claramente interno, exceto quando o próprio caso exigir comparar reputação ou categoria.

### Scripts permitidos

- Individual: `C:\Users\Nilson.Miranda\Threat-Intelligence-Tool\backend\threat_check.py`
- Lote: `C:\Users\Nilson.Miranda\OneDrive - iT.eam\Documentos\Alertas\batch.py`

### Regras de execução

1. Para um único IOC, use somente o script individual com a flag `--dashboard`.
2. `batch.py` é exclusivo para pesquisa em lote e só deve ser usado quando houver mais de um IOC a consultar.
3. Nunca use o script individual e o `batch.py` para pesquisar o mesmo IOC.
4. Em lote, use o arquivo completo quando houver export relevante. Não amostre sem justificativa.
5. Se a consulta falhar, informe a falha como limitação operacional. Não preencha reputação por inferência.

### Regras de uso no texto final

1. Resuma o resultado tecnicamente; não despeje saída bruta sem contexto.
2. Quando houver bloco `Análise do IP:`, use o resultado da consulta para alimentar esse trecho do alerta, mantendo o rótulo e o contexto técnico.
3. Se houver múltiplos IOCs, consolide por prioridade e destaque apenas o que impacta a conclusão.

## 2. Skills locais

Antes de improvisar um método, verifique se alguma skill em `C:\Users\Nilson.Miranda\OneDrive - iT.eam\Documentos\Alertas\.agents\skills` cobre a tarefa.

Regras:

1. Se uma skill for claramente aplicável, use-a.
2. Se nenhuma skill for aplicável, siga o fluxo padrão sem citar skills desnecessariamente.
3. Não carregue documentação extra sem necessidade.
