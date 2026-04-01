# Revisão — Fase 8: Draft Engine

**Data:** 2026-03-18
**Revisor:** Claude-code Sonnet 4.6
**Arquivo revisado:** `soc_copilot/modules/draft_engine.py`

---

## Checklist do TODO — resultado

| Item | Status |
|---|---|
| Templates controlados para TP, BTP, FP, TN, LTF | ✅ |
| Template de repasse técnico para Icatu | ✅ |
| Ordem correta dos blocos | ✅ |
| Acentuação e cedilha | ✅ |
| Ausência de markdown | ✅ |
| Anonimização nas recomendações | ✅ |
| `Análise do IP:` só aparece quando há conteúdo | ✅ |

---

## Bugs encontrados e corrigidos

### Bug 1 — Label "Análise do IP:" incorreto para domínios e hashes
**Arquivo:** `draft_engine.py` → `_build_ip_analysis`
**Problema:** Após as mudanças da Fase 6 (IOCs agora incluem domínios e hashes), o bloco de TI continuava com o cabeçalho `"Análise do IP:"` mesmo quando não havia nenhum IP nos resultados — apenas domínios ou hashes.
**Correção:** O label agora é escolhido dinamicamente:
- `"Análise do IP:"` quando há pelo menos um IP nos artefatos.
- `"Análise de Indicadores:"` quando os artefatos são exclusivamente domínios e/ou hashes.

---

### Bug 2 — Racional da sugestão automática vazando para classificação diferente
**Arquivo:** `draft_engine.py` → `_build_technical_analysis`
**Problema:** O `_build_technical_analysis` lia `analysis["classificacao_sugerida"]["racional"]` como base do parágrafo de justificativa. Quando o analista escolhia uma classificação diferente da sugerida (ex: analista escolhe LTF, mas o `classification_helper` sugeriu TP porque havia IOCs), o draft gerava um texto incoerente: `"IP externo identificado(s) no payload; reputação TI necessária..."` como justificativa de um caso LTF.
**Correção:** Adicionada função `_rationale_for(classificacao, analysis)` que percorre as hipóteses ranqueadas em busca da que corresponde à classificação *escolhida* pelo analista. Só usa o racional geral se a sugestão automática coincide com a escolha humana. Caso contrário, cai no fallback textual específico de cada classificação.

---

### Bug 3 — Lacunas truncadas silenciosamente
**Arquivo:** `draft_engine.py` → `_build_technical_analysis`
**Problema:** O código fazia `lacunas[:2]` sem nenhuma indicação de que itens foram omitidos. Com 3+ lacunas, o analista recebia um draft aparentemente completo mas com informações suprimidas.
**Correção:** Limite elevado para 3 itens e, quando truncado, acrescenta ao texto `"(e outras N limitação/ões não listadas)"`.

---

### Melhoria — Destino: N/A omitido do bloco de detalhes
**Arquivo:** `draft_engine.py` → `_build_detail_lines`
**Problema:** O campo `Destino` aparecia como `"Destino: N/A"` no draft de TP mesmo quando ausente, gerando ruído.
**Correção:** `Destino` e `Caminho` só aparecem quando têm valor real. `Usuário` e `IP de Origem` são sempre exibidos (N/A é informação relevante nesses campos para o analista).

---

## Palpites — melhorias recomendadas para fases futuras

### Palpite 1 — Limpeza de markdown incompleta (risco latente)
`_MARKDOWN_PATTERNS = ("```", "**", "__", "# ")` cobre os casos óbvios, mas perde:
- `*itálico*` (asterisco simples)
- `[texto](url)` (links markdown)
- `> citação` (blockquote)
- `## heading` / `### heading` (cabeçalhos múltiplos)

Hoje o risco é baixo porque o semi_llm_adapter está em modo stub. Quando o LLM real for ligado (Fase futura), uma resposta com markdown mal filtrada vai aparecer no draft. Recomendo trocar o `replace()` sequencial por uma função regex única aplicada em `_finalize_text` antes de ligar a integração real.

**Implementação sugerida:**
```python
import re
_MD_CLEANUPS = [
    (re.compile(r'^#{1,6}\s', re.MULTILINE), ''),    # headings
    (re.compile(r'\*{1,3}|_{1,3}'), ''),              # bold/italic
    (re.compile(r'`{1,3}[^`]*`{1,3}'), ''),           # code
    (re.compile(r'\[([^\]]*)\]\([^)]*\)'), r'\1'),    # links → só texto
    (re.compile(r'^>\s?', re.MULTILINE), ''),          # blockquote
]
```

---

### Palpite 2 — `_ensure_sentence` termina URLs com ponto
Quando `tecnica = "https://attack.mitre.org/..."`, `_ensure_sentence` acrescenta `.` ao final da URL, resultando em `"https://.../T1059/."`. Não quebra nada, mas fica visualmente feio no draft.
**Sugestão:** Adicionar exceção para strings que terminam com `/` ou sejam reconhecidas como URL.

---

### Palpite 3 — Ausência de função `validate_draft()` (crítico para Fase 10)
A Fase 10 prevê "checklist de conformidade textual", mas não há nenhuma função no `draft_engine` que valide o texto gerado antes de retornar. Seria valioso ter:

```python
def validate_draft(text: str) -> list[str]:
    """Retorna lista de avisos de conformidade (vazia = aprovado)."""
    avisos = []
    if any(m in text for m in ("**", "```", "__")):
        avisos.append("Markdown detectado no draft.")
    if "N/A" in text and text.count("N/A") > 2:
        avisos.append("Mais de 2 ocorrências de 'N/A' no draft.")
    if not any(c in text for c in "áéíóúãõçÁÉÍÓÚÃÕÇ"):
        avisos.append("Nenhum caractere acentuado detectado — possível corrupção de encoding.")
    return avisos
```

Isso permitiria que `main.py` inclua os avisos no JSON de resposta, dando ao analista visibilidade de qualidade antes de copiar o draft.

---

### Palpite 4 — TP sem TI: "Em anexo o Payload." isolado
No template TP, a linha `"Em anexo o Payload."` aparece logo após a Análise Técnica, fora do contexto de qualquer bloco. Se não houver nenhum anexo real, essa linha é enganosa. Considerar torná-la condicional ou renomeá-la para `"Payload disponível para consulta."`.

---

### Palpite 5 — Icatu com TP deveria usar o template TP padrão (está correto)
Confirmado: `if pack.is_icatu and cls != "TP"` — Icatu **TP** cai no template TP padrão, não no repasse. Comportamento correto conforme SOP.

---

## Resultado geral

O Draft Engine está **operacional e correto para o MVP**. Os quatro bugs corrigidos eliminam incoerências que seriam visíveis em uso real. Os palpites devem ser considerados antes da integração com o LLM real (Fase futura) e antes da Fase 10 de testes.
