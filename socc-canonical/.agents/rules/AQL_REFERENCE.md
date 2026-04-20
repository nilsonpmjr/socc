# Referência de Consultas AQL (QRadar)

Este documento contém modelos de consultas AQL (Ariel Query Language) para auxiliar na investigação de incidentes e análise de logs no QRadar.

## 1. Visualização Detalhada (Headers e Payload)

Esta estrutura é ideal para quando se deseja ver os campos exatamente como aparecem na interface de "Log Activity", mas incluindo o payload completo e sem o agrupamento automático do SIEM.

```sql
SELECT
    QIDNAME(qid) AS "Event Name",
    LOGSOURCENAME(logsourceid) AS "Log Source",
    eventcount AS "Event Count",
    DATEFORMAT(starttime, 'yyyy-MM-dd HH:mm:ss') AS "Time",
    CATEGORYNAME(category) AS "Low Level Category",
    sourceip AS "Source IP",
    sourceport AS "Source Port",
    destinationip AS "Destination IP",
    destinationport AS "Destination Port",
    username AS "Username",
    magnitude AS "Magnitude",
    UTF8(payload) AS "Payload"
FROM events
WHERE 
    -- Exclui regras de correlação (Custom Rule Engine) para evitar ruído e ver o log original
    LOGSOURCENAME(logsourceid) <> 'NOME_DO_LOG_SOURCE_OU_REGRA_PARA_EXCLUIR'
    
    -- Filtros de investigação (remover comentário conforme necessidade)
    -- AND sourceip = 'IP_DE_ORIGEM'
    -- AND username = 'USUARIO_ALVO'
    
ORDER BY starttime DESC
START 'YYYY-MM-DD HH:MM:SS' STOP 'YYYY-MM-DD HH:MM:SS'
```

### Dicas

* Utilize `UTF8(payload)` para transformar o payload binário em texto legível.
* O campo `eventcount` mostra se o evento foi consolidado, mas sem a cláusula `GROUP BY`, cada linha representará um registro individual.
* A exclusão do `Custom Rule Engine` no `WHERE` ajuda a focar na evidência bruta (log source real).
