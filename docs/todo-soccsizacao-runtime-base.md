# TODO — Implementação da SOCCsização do Runtime Base

**PRD pai:** `prd-soccsizacao-runtime-base.md`  
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
**Status:** ✅ DONE

**Acceptance Criteria**

- [x] `README.md` abre com posicionamento de SOC / threat intel / incident response
- [x] quick starts e guide não técnico descrevem o SOCC como copiloto de segurança
- [x] extensão VS Code e superfícies visuais principais já expõem SOCC como identidade primária
- [x] `insights`, onboarding visual e control center da extensão já usam identidade e paleta SOCC
- [x] menções operacionais ao branding anterior saem das superfícies principais, preservando apenas atribuição histórica quando útil

**Evidência atual**

- `README.md`, quick starts e docs principais já expõem SOCC como identidade primária
- grep de superfícies prioritárias encontra branding anterior apenas em atribuição histórica do `README.md`, testes de identidade e pontos de compatibilidade técnica

---

## Fase 2 — Runtime e Convenções

### SI-201: migrar naming técnico principal para SOCC
**Prioridade:** P0  
**Status:** ✅ DONE

**Acceptance Criteria**

- [x] paths, nomes e mensagens principais deixam de depender do branding anterior
- [x] convenção de runtime/configuração aponta para identidade `socc`
- [x] secure storage, native host e metadata principal de integração já priorizam `SOCC`
- [x] proto ativo do runtime migrou para `src/proto/socc.proto`
- [x] inventário de renomeação cobre binários, help, docs, scripts e artefatos de protocolo

**Evidência atual**

- binário: `package.json` expõe `bin.socc -> bin/socc`
- help: `node dist/cli.mjs --help` já responde com `Usage: socc ...`
- docs: `README.md`, `docs/quick-start-*.md`, `docs/advanced-setup.md`, `docs/litellm-setup.md`
- scripts: `scripts/bootstrap-socc-soul.mjs`, `scripts/grpc-cli.ts`, `scripts/start-grpc.ts`
- protocolo: `src/proto/socc.proto`
- pacote: `npm pack --dry-run` inclui `.socc/agents`, `.socc/rules`, `.socc/skills`, `.socc/references`

### SI-202: definir estratégia de compatibilidade transitória
**Prioridade:** P1  
**Status:** ✅ DONE

**Acceptance Criteria**

- [x] compatibilidade temporária, se existir, é explícita e limitada
- [x] compatibilidade legada de perfil e credenciais permanece funcional sem expor branding antigo como padrão
- [x] superfícies novas não apresentam branding anterior como nome principal

**Evidência atual**

- quick starts, advanced setup, help principal e package metadata usam `SOCC`/`socc` como nome principal
- branding anterior restante está concentrado em atribuição histórica, testes, integrações externas Anthropic e compatibilidade técnica explícita

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
**Status:** ✅ DONE

**Acceptance Criteria**

- [x] docs principais tratam coding workflows como suporte ao analista
- [x] help e superfícies remanescentes tratam coding workflows como suporte ao analista
- [x] exemplos principais usam triagem, análise, investigação e resposta

### SI-402: alinhar narrativa de segurança
**Prioridade:** P1  
**Status:** ✅ DONE

**Acceptance Criteria**

- [x] linguagem principal do produto já favorece investigação, análise e IR
- [x] docs deixam claros limites de automação e necessidade de validação humana

**Evidência atual**

- `README.md` agora inclui a seção `Security Usage Notes`
- `docs/quick-start-windows.md` e `docs/quick-start-mac-linux.md` agora incluem `Safety Reminder`

---

## Fase 5 — Verificação

### SI-501: validar branding e onboarding
**Prioridade:** P0  
**Status:** ✅ DONE

**Acceptance Criteria**

- [x] busca por branding residual nas superfícies prioritárias não encontra regressões relevantes
- [x] `socc --help` ou fluxo equivalente reflete a nova identidade
- [x] `npm pack` + instalação limpa confirmam binário principal `socc` e geração da alma canônica no pacote instalado

**Evidência atual**

- grep em `README.md`, `docs`, `src`, `package.json`, `scripts` e `bin` não mostra regressões relevantes nas superfícies prioritárias
- residual atual ficou restrito a:
  - atribuição histórica em `README.md`
  - testes de identidade
  - integrações externas Anthropic / compatibilidade técnica

### SI-502: validar comportamento base do agente
**Prioridade:** P1  
**Status:** ✅ DONE

**Acceptance Criteria**

- [x] testes ou checks de prompt cobrem não-fabricação e observed-vs-inferred
- [x] riscos remanescentes ficam documentados

**Evidência atual**

- `src/utils/soccCanonicalRuntime.test.ts` valida que o agente gerado em `.socc/agents/socc.md` preserva:
  - não-fabricação de IOCs/CVEs/hashes/domínios/IPs/TTPs/fontes
  - separação entre observado e inferido

**Riscos remanescentes**

- ainda existem referências técnicas a `Claude` em integrações externas Anthropic, telemetry IDs e URLs de compatibilidade que não devem ser renomeadas cegamente
- a persona canônica do `socc` está coberta por testes de contrato, mas a qualidade analítica final ainda depende do modelo/provedor selecionado
- superfícies históricas de atribuição e compatibilidade continuam existindo por necessidade operacional e legal

### SI-504: validar equivalência da alma do `socc` entre REPL e headless
**Prioridade:** P1  
**Status:** ✅ DONE

**Acceptance Criteria**

- [x] o agente `socc` carregado do artefato canônico gera o mesmo prompt-base no fluxo interativo e no não interativo
- [x] regras geradas em `.socc/rules/` continuam entrando no contexto por `claudemd.ts`
- [x] todas as skills de `socc-copilot/skills` continuam visíveis via `loadSkillsDir.ts`

**Evidência atual**

- `src/tools/AgentTool/loadAgentsDir.socc.test.ts` valida equivalência do prompt-base entre fluxo interativo e headless
- `src/utils/soccCanonicalRuntime.test.ts` já valida carregamento de `.socc/rules/socc-business-rules.md`
- `src/utils/soccCanonicalRuntime.test.ts` já valida visibilidade das skills canônicas via `getSkillDirCommands()`

### SI-503: publicar `@vantagesec/socc` no npm como passo final da SOCCsização
**Prioridade:** P0  
**Status:** ✅ DONE

**Acceptance Criteria**

- [x] `npm whoami` confirma sessão autenticada no `npmjs.com`
- [x] `npm view @vantagesec/socc version` confirma que o nome público está livre
- [x] `npm publish --dry-run` passa com o pacote atual
- [x] diretório do projeto foi limpo antes da publicação, mantendo só runtime, docs úteis e fonte canônica mínima da alma
- [x] `npm publish` executado com sucesso
- [x] `npm install -g @vantagesec/socc` funciona a partir do registry público
