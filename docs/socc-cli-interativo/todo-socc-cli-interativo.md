# TODO — Implementacao CLI Interativa SOCC

## Fase F1 — Fundacao

- [x] Criar `socc/cli/prompt_runtime.py` com funcoes: is_interactive, ask, ask_secret, confirm, select, checklist, ask_path, summary, step, success, warning, error, skip
- [x] Integrar InquirerPy para navegacao com setas, espaco para toggle, enter para confirmar (fallback para input() se nao instalado)
- [x] Adicionar backup automatico de `.env` em `config_loader.py` (antes de cada escrita)
- [x] Adicionar `batch_update_env()` em `config_loader.py` para escrita atomica de multiplas chaves
- [x] Adicionar validacao basica de tipos em `config_loader.py` (url, int, bool, path) — implementada em `socc configure validate`
- [x] Adicionar `read_all_env()` e `read_env_value()` em `config_loader.py`
- [x] Adicionar `remove_env_assignment()` em `config_loader.py`
- [x] Adicionar `InquirerPy` como dependencia opcional em `pyproject.toml`

## Fase F2 — Wizard `socc onboard`

- [x] Refatorar `main.py` onboard para usar wizard interativo
- [x] Etapa 1: Runtime Home (confirmar/escolher ~/.socc)
- [x] Etapa 2: Knowledge Base (apontar pasta, tipo, confianca, indexar)
- [x] Etapa 3: Backend de inferencia (detectar, selecionar, testar)
- [x] Etapa 4: Modelos (listar, mapear Fast/Balanced/Deep)
- [x] Etapa 5: Cloud provider fallback (API key mascarada, teste)
- [x] Etapa 6: Threat Intelligence (URL, credenciais, teste)
- [x] Etapa 7: Vantage API (URL, auth, modulos)
- [x] Etapa 8: Agente ativo (selecionar entre disponiveis)
- [x] Etapa 9: Pasta de saida (notas geradas)
- [x] Etapa 10: Feature flags (checklist)
- [x] Etapa 11: Seguranca (redacao, audit)
- [x] Etapa 12: Resumo e confirmacao (review, salvar, iniciar, abrir)

## Fase F3 — Subcomandos de gestao

- [x] `socc configure show` — exibir config ativa com redaction
- [x] `socc configure set KEY VALUE` — escrever com backup e validacao
- [x] `socc configure unset KEY` — remover chave
- [x] `socc configure validate` — validar valores contra regras
- [x] `socc models list` — listar modelos de todos os backends
- [x] `socc models set --fast|--balanced|--deep MODEL` — definir perfil
- [x] `socc models fallback list` — exibir fallback provider e priority
- [x] `socc models fallback add PROVIDER` — definir fallback provider
- [x] `socc models fallback remove` — desabilitar fallback provider
- [x] `socc models test [MODEL]` — smoke test de inferencia

## Fase F4 — Doctor interativo

- [x] `socc doctor` em TTY: checklist visual por categoria (8 categorias)
- [x] Expand/collapse de categorias via selecao interativa
- [x] Recomendacoes acionaveis com comando sugerido
- [x] Fix inline para pendencias simples (socc init, socc configure set, etc.)
- [x] Fallback para `_print_doctor()` original quando fora de TTY

## Testes

- [x] `tests/test_cli_interactive.py` — 74 checks cobrindo prompt_runtime, config_loader, parsing, wizard helpers, doctor evaluation

## Status: COMPLETO
