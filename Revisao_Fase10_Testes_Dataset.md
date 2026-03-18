# Revisão — Fase 10: Casos de Teste e Dataset (Gemini)

**Data:** 2026-03-18
**Revisor:** Claude-code Sonnet 4.6
**Arquivos revisados:** `tests/SOC_Copilot_Casos_de_Teste.md`, `tests/dataset_mvp.json`

---

## Cobertura exigida pelo TODO vs. entregue

| Cenário | TODO | `dataset_mvp.json` | Doc `.md` |
|---|---|---|---|
| JSON | ✅ | TC-01, TC-04 | ✅ |
| CSV | ✅ | TC-02 | ✅ |
| Texto bruto | ✅ | TC-03, TC-06 | ✅ |
| IOC único | ✅ | TC-01 (intenção) | ✅ |
| Múltiplos IOCs | ✅ | TC-02 (parcial) | ✅ |
| IP privado | ✅ | TC-04, TC-06 | ✅ |
| TP | ✅ | TC-01, TC-02 | ✅ |
| BTP | ✅ | TC-04, TC-06 | ✅ |
| **FP** | ✅ | **❌ ausente** | **❌ ausente** |
| **TN** | ✅ | **❌ ausente** | TC-05 (só no doc) |
| LTF | ✅ | TC-03 | ✅ |
| Icatu | ✅ | TC-06 (BTP) | TC-06, TC-07 |
| **Icatu TP** | implícito | **❌ ausente** | **❌ ausente** |
| Expected outputs assertivos | ✅ | **❌ nenhum campo** | vago |
| Test runner executável | implícito | **❌ ausente** | — |

---

## Problemas encontrados

### 1 — TC-05 e TC-07 existem no documento, não existem no JSON

O arquivo `.md` descreve 7 casos, o JSON tem 5. TC-05 (TN, atividade admin) e TC-07 (Icatu BTP/FP) foram documentados mas não implementados como fixture. O TODO exige cobertura de TN — ela simplesmente não existe para execução.

---

### 2 — TC-01 usa IP de documentação RFC 5737 (`198.51.100.99`)

**Confirmado pelo parser:**
```
TC-01 → IP_ext: []  IP_Privado: True
```
`198.51.100.99` pertence ao bloco `198.51.100.0/24` (TEST-NET-2). Em Python 3.11+, `ipaddress.IPv4Address('198.51.100.99').is_private` retorna `True`. O TI Adapter **nunca é chamado** neste teste. TC-01 foi desenhado para validar exatamente o acionamento do TI, mas silenciosamente não o faz. O mesmo problema afeta TC-02 (ambos os IPs são `10.20.30.x`, privados).

---

### 3 — TC-02: hash do arquivo vazio e `malware.exe` vira domínio

**Confirmado pelo parser:**
```
TC-02 → Hashes: ['e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855']
        Dominios: ['malware.exe']  IP_ext: []
```
- O hash SHA-256 presente no payload é o hash do **arquivo vazio** (`e3b0c44...`). A ferramenta vai consultar TI para um artefato sem qualquer relevância operacional.
- `malware.exe` foi extraído como "domínio" pelo detector de domínios (`.exe` passa como TLD válido no padrão `[a-z]{2,63}`). `bad-domain.com` foi absorvido na lista de URLs e não aparece em `dominios`. O teste entrega IOCs errados para o TI.

---

### 4 — TC-06: classificação e payload incompatíveis entre doc e JSON

| Campo | Documento `.md` | JSON |
|---|---|---|
| Classificação | TP | BTP |
| Descrição | "Malware via Sandbox, hash IOC" | admin fazendo "legitimate patch" |
| Hash extraído | sim (esperado) | não — nenhum hash encontrado |

Os dois artefatos descrevem casos completamente diferentes. Não há como saber qual é o correto.

---

### 5 — Nenhum expected output assertivo no JSON

O TODO exige "expected outputs mínimos". O JSON atual só tem entrada. Para um test runner funcionar, cada caso precisaria de pelo menos:

```json
"expected": {
  "ti_triggered": true,
  "draft_must_contain": ["Análise do IP:", "Recomendação:"],
  "draft_must_not_contain": ["**", "```"],
  "campos_minimos": {"IP_Origem": "198.51.100.99"}
}
```

Sem isso, o dataset é uma coleção de fixtures, não uma suíte de testes.

---

### 6 — Nenhum test runner

`tests/` contém apenas `.md` e `.json`. Não existe `test_runner.py`, `conftest.py` nem qualquer script que carregue o dataset e execute asserções. A Fase 10 não pode ser validada automaticamente no estado atual.

---

### 7 — Checklist de conformidade textual diverge da implementação (Fase 8)

O item `Blocos Obrigatórios Rígidos` especifica:
```
Título > Narrativa > Detalhes > Análise TI > Referência > Recomendação
```
Mas `_build_tp` gera na prática:
```
Prezados > Título > Narrativa > Detalhes > [Análise TI] > Análise Técnica >
"Em anexo o Payload." > Referência > Referência MITRE > Recomendação
```
O checklist omite "Análise Técnica", "Em anexo o Payload." e "Referência MITRE". Quem implementar o test runner baseado no checklist vai reprovar testes legítimos.

Similarmente, "Notas de Encerramento: tripé Classificação > Resumo > Justificativa" está incorreto — `_build_btp` usa 4 blocos (Classificação, Resumo Técnico, Justificativa da benignidade, Ação de encerramento).

---

### 8 — "Verificador MITRE: link é acessível" é teste de rede

Verificar se a URL do MITRE responde via HTTP é um teste de integração de rede que não deveria estar no checklist de conformidade textual. O que pode ser testado de forma controlada é o formato da URL: `re.fullmatch(r"T\d{4}(?:\.\d{3})?", tecnica)`.

---

### 9 — Typos no documento

- TC-05: "Atividade legímita" → "legítima" (acento ausente)
- TC-02 referencia "batch.py" como detalhe de implementação pública — o contrato exposto é `ti_adapter.enrich()`, não scripts internos

---

## O que está bem

- Estrutura do documento (casos → expected outputs → checklist) é sólida e segue a lógica certa.
- Os cenários escolhidos cobrem os fluxos operacionais corretos — o problema está na implementação dos payloads, não no desenho.
- TC-03 (LTF com payload corrompido) e TC-04 (BTP com IP privado) executam corretamente e produzem o resultado esperado confirmado pelo parser.
- O checklist tem os itens certos; o problema é que alguns não refletem o código real das fases anteriores.

---

## Palpites

**1 — O test runner é a lacuna mais crítica e deveria ser prioridade.**
O Gemini entregou a especificação; alguém precisa escrever o `pytest` que carrega o JSON, chama as funções diretamente (sem HTTP) e valida os campos. É o trabalho mais crítico e mais direto agora que a arquitetura está estável.

**2 — IPs dos payloads deveriam ser defanged.**
Usar `198[.]51[.]100[.]99` em vez de `198.51.100.99` força o parser a exercitar o código de undefang, aumentando cobertura real do componente mais crítico.

**3 — TC-01 e TC-02 precisam de IPs roteáveis anonimizados, não de documentação RFC.**
Opções: usar `203.0.113.x` (TEST-NET-3) com um mock do TI Adapter no test runner, ou aceitar que esses testes validem apenas o parser (sem TI) e criar casos separados para o fluxo TI.

**4 — FP é o caso mais fácil de implementar e o mais ausente.**
Um payload JSON com scanner interno Nessus/Qualys e IP privado é suficiente. Exemplo mínimo:
```json
{
  "id": "TC-08",
  "classificacao": "FP",
  "regra": "Qualys - Vulnerability Scan",
  "payload": "{\"src_ip\": \"10.1.1.50\", \"tool\": \"Qualys\", \"action\": \"vulnerability scan\", \"user\": \"svc-qualys\"}"
}
```

**5 — Icatu TP está completamente descoberto.**
É o caso de maior risco operacional (alerta crítico que vai direto ao cliente) e não tem nenhum test case. Deveria ser o primeiro a ser adicionado.
