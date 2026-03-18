# Revisão — Fase 6: Integração Threat Intelligence

**Data:** 2026-03-18
**Revisor:** Claude-code Opus 4.6
**Arquivo revisado:** `soc_copilot/modules/ti_adapter.py`

---

## Checklist do TODO

| Item | Status |
|---|---|
| Decisão automática único vs lote | OK |
| `batch.py` só para múltiplos IOCs | OK |
| Sem consulta duplicada | OK — `seen` set em `_collect_targets` |
| Timeout e tratamento de falha | OK — 3 camadas de fallback |
| Resumir resultado para `Análise do IP:` | OK |

---

## Bugs corrigidos

### Bug 1 — `main.py` — TI não disparava para domínios nem hashes

**Causa:** A guarda `if fields["IOCs"]["ips_externos"]` só verificava IPs externos. Ofensas com apenas domínio malicioso ou hash nunca chegavam ao TI, mesmo com `_collect_targets()` preparado para coletar os três tipos.

**Correção aplicada em `main.py`:**
```python
_iocs = fields["IOCs"]
if _iocs.get("ips_externos") or _iocs.get("dominios") or _iocs.get("hashes"):
    ti_results = ti_adapter.enrich(_iocs)
```

---

### Bug 2 — `_query_batch_script` mapeava stdout bruto para todos os IOCs

**Causa:** O `batch.py` emite saída Rich/ANSI em tabela formatada. O subprocess capturava esse blob e fazia `{ioc: stdout for ioc in iocs}`, associando o mesmo texto completo a cada IOC individualmente. Isso vazaria todos os resultados no bloco `Análise do IP:` de cada IOC na nota.

**Correção aplicada em `ti_adapter.py`:**
`_query_batch_script` removido do caminho de execução de `enrich()`. A função permanece no arquivo como utilitário CLI independente, mas não é mais chamada pelo sistema.

Nova ordem de prioridade para múltiplos IOCs:
1. `_query_batch_api` — retorna resultado estruturado por `target`
2. Fallback: consultas individuais via `_query_single`

---

## Palpites e recomendações

### Palpite 1 — Bloqueio do event loop (recomendado corrigir antes do go-live)

`ti_adapter.enrich()` é síncrono e pode levar até 60s (polling do lote). Está sendo chamado diretamente de `async def analyze()` no FastAPI, o que trava o servidor inteiro durante a consulta.

Para uso single-user local não impacta. Se dois analistas usarem simultaneamente, um ficará aguardando o outro terminar.

**Correção sugerida em `main.py`:**
```python
import asyncio
ti_results = await asyncio.to_thread(ti_adapter.enrich, _iocs)
```

---

### Palpite 2 — `threat_check.py --dashboard` provavelmente não aceita domínio ou hash

O script `threat_check.py` foi escrito para IP. Quando o único IOC for um domínio (`evil.ru`) ou hash, o sistema chamará `threat_check.py --dashboard evil.ru`, que pode retornar erro ou saída vazia.

**Impacto atual:** o `draft_engine` já filtra linhas com `[AVISO]` e `[ERRO]` antes de incluir no bloco `Análise do IP:`, portanto não vaza texto ruim na nota.

**Ação sugerida:** investigar se `threat_check.py` aceita domínios e hashes, ou condicionar a chamada individual apenas para IPs, roteando domínios e hashes direto para a API.

---

### Palpite 3 — Cache de sessão para IOCs repetidos (Fase 2)

Um analista que processa múltiplas ofensas do mesmo cliente cruzará os mesmos IPs repetidamente na mesma sessão. Um `dict` simples em memória `{ioc: resultado}` eliminaria re-consultas sem complexidade adicional.

**Prioridade:** Fase 2.

---

### Palpite 4 — Risco de timeout em cascata com backend TI offline

Se o backend TI estiver offline, `_query_batch_api` falha rapidamente (timeout de 10s na autenticação). O sistema cai no fallback de consultas individuais: com `MAX_TI_IOCS=5` e timeout de 30s por IOC, o pior caso é **150s bloqueados**.

**Recomendação operacional:** definir `MAX_TI_IOCS=3` no `.env` como padrão mais seguro para ambientes onde o backend TI pode estar instável.

---

## Estado final da fase

| Item | Situação |
|---|---|
| Bugs corrigidos | 2 |
| Palpites críticos | 1 (asyncio — recomendado antes do go-live) |
| Palpites operacionais | 1 (MAX_TI_IOCS=3) |
| Palpites Fase 2 | 1 (cache de sessão) |
| Investigação pendente | 1 (domínio/hash no --dashboard) |

**Fase 6 encerrada.**
