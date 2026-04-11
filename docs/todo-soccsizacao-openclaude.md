# TODO — Implementação da SOCCsização do Clone do OpenClaude

**PRD pai:** `prd-soccsizacao-openclaude.md`  
**Objetivo:** transformar a base atual em `SOCC`, com foco primário em SOC / threat intel / incident response, sem reaproveitar comandos nem harness do SOCC legado.

---

## Legenda

| Símbolo | Significado |
| --- | --- |
| ⬜ | TODO |
| 🔄 | WIP |
| ✅ | DONE |

---

## Fase 1 — Identidade Principal

### SI-101: tornar `socc` o comando principal
**Prioridade:** P0  
**Status:** ✅ DONE

**Acceptance Criteria**

- [x] `package.json` expõe `socc` como binário principal
- [x] o wrapper de CLI principal usa nome e mensagens de erro de `socc`
- [x] docs de instalação e quick start usam `socc` como comando padrão

### SI-102: reposicionar o produto para segurança nas superfícies principais
**Prioridade:** P0  
**Status:** 🔄 WIP

**Acceptance Criteria**

- [x] `README.md` abre com posicionamento de SOC / threat intel / incident response
- [x] quick starts e guide não técnico descrevem o SOCC como copiloto de segurança
- [x] extensão VS Code e superfícies visuais principais já expõem SOCC como identidade primária
- [x] `insights`, onboarding visual e control center da extensão já usam identidade e paleta SOCC
- [ ] menções operacionais a `OpenClaude` saem das superfícies principais, preservando apenas atribuição histórica quando útil

---

## Fase 2 — Runtime e Convenções

### SI-201: migrar naming técnico principal para SOCC
**Prioridade:** P0  
**Status:** 🔄 WIP

**Acceptance Criteria**

- [x] paths, nomes e mensagens principais deixam de depender de `openclaude`
- [x] convenção de runtime/configuração aponta para identidade `socc`
- [x] secure storage, native host e metadata principal de integração já priorizam `SOCC`
- [x] proto ativo do runtime migrou para `src/proto/socc.proto`
- [ ] inventário de renomeação cobre binários, help, docs, scripts e artefatos de protocolo

### SI-202: definir estratégia de compatibilidade transitória
**Prioridade:** P1  
**Status:** 🔄 WIP

**Acceptance Criteria**

- [x] compatibilidade temporária, se existir, é explícita e limitada
- [x] compatibilidade legada de perfil e credenciais permanece funcional sem expor branding antigo como padrão
- [ ] superfícies novas não apresentam `openclaude` como nome principal

---

## Fase 3 — Alma do Agente

### SI-301: adaptar o agente `Socc` como persona padrão
**Prioridade:** P0  
**Status:** ✅ DONE

**Acceptance Criteria**

- [x] a persona padrão assume postura de analista de segurança
- [x] guidance exige separar observado vs inferido
- [x] guidance proíbe inventar IOCs, CVEs, hashes, IPs, domínios, TTPs e fontes
- [x] PT-BR é o idioma padrão salvo instrução contrária

### SI-302: tornar `socc-canonical/.agents` a fonte canônica da alma do SOCC
**Prioridade:** P0  
**Status:** ✅ DONE

**Acceptance Criteria**

- [x] a instalação gera artefatos derivados a partir de `socc-canonical/.agents/soc-copilot`
- [x] o runtime consegue usar o agente canônico do pacote mesmo fora da raiz do repositório
- [x] o fluxo funciona em Linux, macOS e Windows sem depender de shell específico

---

## Fase 4 — Reposicionamento de Produto

### SI-401: reduzir o papel de coding-agent generalista para capacidade secundária
**Prioridade:** P1  
**Status:** 🔄 WIP

**Acceptance Criteria**

- [x] docs principais tratam coding workflows como suporte ao analista
- [ ] help e superfícies remanescentes tratam coding workflows como suporte ao analista
- [ ] exemplos principais usam triagem, análise, investigação e resposta

### SI-402: alinhar narrativa de segurança
**Prioridade:** P1  
**Status:** 🔄 WIP

**Acceptance Criteria**

- [x] linguagem principal do produto já favorece investigação, análise e IR
- [ ] docs deixam claros limites de automação e necessidade de validação humana

---

## Fase 5 — Verificação

### SI-501: validar branding e onboarding
**Prioridade:** P0  
**Status:** ⬜ TODO

**Acceptance Criteria**

- [ ] busca por branding residual nas superfícies prioritárias não encontra regressões relevantes
- [x] `socc --help` ou fluxo equivalente reflete a nova identidade
- [x] `npm pack` + instalação limpa confirmam binário principal `socc` e geração da alma canônica no pacote instalado

### SI-502: validar comportamento base do agente
**Prioridade:** P1  
**Status:** ⬜ TODO

**Acceptance Criteria**

- [ ] testes ou checks de prompt cobrem não-fabricação e observed-vs-inferred
- [ ] riscos remanescentes ficam documentados

### SI-503: publicar `@vantagesec/socc` no npm como passo final da SOCCsização
**Prioridade:** P0  
**Status:** 🔄 WIP

**Acceptance Criteria**

- [x] `npm whoami` confirma sessão autenticada no `npmjs.com`
- [x] `npm view @vantagesec/socc version` confirma que o nome público está livre
- [x] `npm publish --dry-run` passa com o pacote atual
- [x] diretório do projeto foi limpo antes da publicação, mantendo só runtime, docs úteis e fonte canônica mínima da alma
- [ ] `npm publish` executado com sucesso
- [ ] `npm install -g @vantagesec/socc` funciona a partir do registry público
