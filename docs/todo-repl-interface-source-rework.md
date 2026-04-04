# TODO — REPL Interface Rework from Source

**Data:** 2026-04-03  
**Status:** Em execução  
**Fonte primária:** `/home/nilsonpmjr/Documentos/claude-code-analysis/src/screens/REPL.tsx`  
**Objetivo:** continuar refazendo a interface REPL/TUI do SOCC para ficar mais próxima da fonte em layout, densidade operacional e sinais de estado.

---

## Legenda

| Símbolo | Significado |
|---|---|
| ⬜ | TODO |
| 🔄 | WIP |
| ✅ | DONE |

---

## Fase 0 — Guia de rework

### REPL-000: congelar o recorte de referência
**Prioridade:** P0  
**Status:** ✅ DONE

- [x] usar `REPL.tsx` como referência principal de interface
- [x] tratar a UI atual do SOCC como base de implementação, não como referência final
- [x] manter dependência zero de libs novas pesadas

---

## Fase 1 — Estrutura visual principal

### REPL-101: chrome/sidebar/footer mais próximos da fonte
**Prioridade:** P0  
**Status:** ✅ DONE

- [x] top chrome mais informativo
- [x] sidebar mais densa
- [x] footer mais operacional
- [x] sinais de task/bridge/transport visíveis

### REPL-102: transcript com linguagem operacional
**Prioridade:** P0  
**Status:** ✅ DONE

- [x] mensagens de usuário viram blocos visuais mais nítidos
- [x] mensagens de assistant viram blocos visuais mais nítidos
- [x] phase events viram cards compactos
- [x] tool call/result viram cards compactos
- [x] erros ficam mais destacados

---

## Fase 2 — Fluxo operacional

### REPL-201: command palette / autocomplete
**Prioridade:** P1  
**Status:** 🔄 WIP

- [x] slash surface unificada local+harness
- [x] autocomplete com contexto visual mais próximo da fonte
- [x] hints de comando mais explícitos no composer

### REPL-202: task/bridge awareness
**Prioridade:** P1  
**Status:** ✅ DONE

- [x] task state exposto na UI
- [x] bridge/transport state exposto na UI
- [x] task rail/lista mais explícita
- [x] badge remoto/degradado mais visível

### REPL-203: interaction/runtime parity
**Prioridade:** P0  
**Status:** 🔄 WIP

- [x] transcript volta a acompanhar a conversa
- [x] stream do chat volta a consumir corretamente os eventos assíncronos
- [x] chat volta a usar os backends configurados em vez de parecer sempre travado
- [x] atalhos básicos de navegação do transcript (`PgUp/PgDn/Home/End`) existem
- [x] atalho/modalidade de transcript mais próxima da referência

---

## Fase 3 — Refinamento

### REPL-301: transcript layout refinement
**Prioridade:** P1  
**Status:** 🔄 WIP

- [x] agrupamento visual mais próximo do REPL da fonte
- [x] separação mais clara entre meta/progresso/resposta
- [x] melhor densidade vertical sem poluir o histórico

### REPL-302: revisão final de paridade visual
**Prioridade:** P2  
**Status:** 🔄 WIP

- [x] comparar novamente com a fonte
- [x] listar gaps restantes
- [x] decidir o que fica para uma iteração posterior

### Gaps restantes identificados

- [ ] command palette ainda não tem interação/seleção tão rica quanto a referência
- [x] sidebar ainda é mais explícita do que a referência
- [ ] transcript ainda não tem virtualização/ritmo fino da fonte

### Estado atual

- transcript e composer agora dominam mais a tela
- sidebar virou um rail mais compacto
- palette/composer ficou visualmente mais central
- ainda falta a sofisticação interativa da palette e o ritmo fino de transcript da fonte
