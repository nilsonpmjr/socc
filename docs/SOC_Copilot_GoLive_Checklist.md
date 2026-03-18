# SOC Copilot MVP — Checklist de Go-Live Local

**Data:** 2026-03-18
**Responsável:** Claude-code Sonnet 4.6 (Fase 11)
**Status do Entregável:** Concluído e revisado por Codex GPT-5.4

**Observação de liberação:** Este checklist está concluído como entregável da Fase 11, mas o go-live operacional do MVP ainda depende dos itens pendentes do analista listados abaixo.

---

## Como usar este checklist

Marcar cada item antes de colocar o MVP em uso operacional.
Um item não marcado é um bloqueador ou risco conhecido — documentar justificativa se for aceito conscientemente.

---

## 1. Ambiente e dependências

- [ ] Python 3.11+ instalado e acessível via `python` no PATH
- [ ] `pip install -r requirements.txt` executado sem erros
- [ ] Arquivo `.env` criado em `Automacao/` com as variáveis obrigatórias:
  - `TI_API_USER` (sem default — obrigatório para o backend TI)
  - `TI_API_PASS` (sem default — obrigatório para o backend TI)
  - `TI_API_BASE_URL` (padrão: `http://localhost:8000`)
  - `THREAT_CHECK_SCRIPT` (caminho absoluto para `threat_check.py`)
  - `OUTPUT_DIR` (pasta de destino das notas geradas)
- [ ] `.env` **não** está rastreado pelo Git (verificar `.gitignore`)
- [ ] `soc_copilot/soc_copilot.db` criada com sucesso (executar `python run.py` uma vez)

---

## 2. Testes de regressão

- [x] `python tests/test_runner.py` retorna **9/9 aprovados**
- [x] `python tests/test_edge_cases.py` retorna **23/23 aprovados**
- [ ] Executar os dois testes novamente após qualquer alteração de código

---

## 3. Validação funcional manual (smoke test)

Abrir `http://localhost:8080` e executar um caso de cada tipo:

- [ ] **TP padrão** — payload JSON com IP externo → draft com "Análise Técnica:" e "Recomendação:"
- [ ] **BTP** — payload com termos de admin/scanner → draft com "Classificação Final: Benign True Positive"
- [ ] **FP** — payload com Nessus/Qualys → draft com "Classificação Final: False Positive"
- [ ] **LTF** — payload corrompido/vazio → draft com "Classificação Final: Log Transmission Failure"
- [ ] **Icatu não-TP** — cliente "Icatu" + BTP → draft com "Encaminhamento:" (sem classificação autônoma)
- [ ] **Botão Copiar** funcionando
- [ ] **Botão Salvar** grava arquivo em `OUTPUT_DIR` com nome correto
- [ ] **GET /api/history** retorna histórico com execuções salvas

---

## 4. Conformidade textual dos drafts gerados

Para cada draft do smoke test acima verificar:

- [ ] Sem caracteres de markdown (`**`, `__`, ` ``` `, `# `)
- [ ] Acentuação preservada (não aparece `Ã©`, `Ã§`, `Ã¢` etc.)
- [ ] Horário em formato `HH:MM:SS` quando presente
- [ ] Bloco "Análise do IP:" aparece **somente** quando há resultado TI válido
  - Deve ser "Análise de Indicadores:" quando os artefatos são domínio ou hash (sem IP)
- [ ] Recomendação **sem** nome real de usuário ou caminho absoluto do sistema
- [ ] Draft TP contém os blocos na ordem: Prezados → Título → Narrativa → Detalhes → [Análise TI] → Análise Técnica → Em anexo → Referência → Referência MITRE → Recomendação

---

## 5. Segurança local

- [x] Todas as queries SQLite usam placeholders parametrizados (sem SQL injection)
- [x] Filename sanitizado em `/api/save` (sem path traversal via `ofensa_id` ou `classificacao`)
- [x] Resolução de caminho verificada: arquivo salvo sempre dentro de `OUTPUT_DIR`
- [x] `GET /api/history?limit=` limitado a máximo 200 registros
- [x] `TI_API_PASS` sem valor default no código (obrigatório via `.env`)
- [x] `subprocess.run` no ti_adapter usa lista (sem `shell=True`)
- [x] Todos os timeouts configurados: subprocess (30s), API submit (10s), API poll (60s)
- [ ] Verificar que `soc_copilot.db` **não** está em pasta sincronizada ao OneDrive sem criptografia
  - O DB atual está em `soc_copilot/soc_copilot.db` dentro do OneDrive — avaliar mover para path local

---

## 6. Performance

- [x] Pipeline completo (sem TI) ≤ 200ms por caso em todos os 9 cenários de regressão
- [ ] Pipeline com TI (chamada real ao `threat_check.py` ou backend) ≤ 35s no total
- [ ] Interface responde durante a chamada TI (TI corre em `asyncio.to_thread`, não bloqueia a UI)

---

## 7. Arquivos de configuração e regras

- [ ] `ALERTAS_ROOT/.agents/rules/AGENT.md` existe e é legível
- [ ] `ALERTAS_ROOT/.agents/workflows/SOP.md` existe e é legível
- [ ] `ALERTAS_ROOT/Automacao/SOC_Copilot_Regras_Inventario.md` existe e contém regras válidas
- [ ] `ALERTAS_ROOT/Modelos/` existe e contém ao menos um modelo `.txt` ou `.md`
- [ ] `rule_loader.load(regra="X", cliente="Icatu")` retorna `pack.is_icatu == True`

---

## 8. Riscos conhecidos e aceitos para o MVP

| Risco | Impacto | Mitigação atual |
|---|---|---|
| `soc_copilot.db` no OneDrive (sincronização em nuvem) | Dados de triagem sincronizados fora do ambiente controlado | Avaliar mover `DB_PATH` para path local via `.env` |
| Domínios falso-positivos (ex: `malware.exe`) extraídos pelo parser | IOC inválido enviado ao TI | TI retorna "[AVISO]" ou erro; draft não é afetado |
| Semi-LLM em modo stub (sem LLM real) | Análise puramente determinística — sem enriquecimento textual | Comportamento documentado; classificação final é sempre do analista |
| IPs de documentação RFC 5737 no dataset de testes | Testes não exercitam o fluxo TI real | Aceitável para MVP; dataset deve ser melhorado na Fase 2 |
| Upload sem limite de tamanho de arquivo | Arquivo muito grande pode causar lentidão | Pipeline ≤ 200ms até 10KB testado; considerar limite de 1MB em Fase 2 |

---

## 9. Aprovação para go-live

| Item | Responsável | Status |
|---|---|---|
| Testes de regressão | Claude-code | ✅ 9/9 |
| Testes de casos extremos | Claude-code | ✅ 23/23 |
| Segurança (path traversal, SQL injection, credencial) | Claude-code | ✅ corrigido |
| Performance pipeline sem TI | Claude-code | ✅ ≤ 200ms |
| Smoke test manual | **Analista** | ⬜ pendente |
| Validação textual dos drafts | **Analista** | ⬜ pendente |
| Configuração do `.env` | **Analista** | ⬜ pendente |

**O MVP pode ser iniciado com `python run.py` após os itens pendentes do analista serem marcados.**
