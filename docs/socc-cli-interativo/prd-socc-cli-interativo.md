# PRD — CLI Interativa do SOCC (Onboard Wizard + Gestao de Configuracao)

## 1. Resumo executivo

Transformar a CLI do SOCC de flag-only para um wizard interativo guiado, onde o usuario configura runtime, base de conhecimento, backends de inferencia, modelos, providers de nuvem, integracoes (TI/Vantage), feature flags e seguranca — tudo via prompts no terminal, sem precisar editar `.env` manualmente.

O agente resultante nao executa acoes na maquina do usuario, mas e capaz de pesquisar, encontrar arquivos e contextualizar informacao da base de conhecimento local.

## 2. Problema

Hoje o usuario precisa:
- editar `~/.socc/.env` na mao para qualquer configuracao
- saber quais variaveis existem e seus valores validos
- testar backends e modelos com comandos avulsos
- sem feedback visual de progresso ou resumo do que foi feito

## 3. Solucao

### 3.1 Modulo `prompt_runtime`

Camada reutilizavel de prompts interativos com fallback silencioso para modo nao-interativo.

### 3.2 Wizard `socc onboard` (12 etapas)

| Etapa | O que faz |
|-------|-----------|
| 1. Runtime Home | Confirmar/escolher `~/.socc` |
| 2. Knowledge Base | Apontar pasta de SOPs/playbooks, indexar |
| 3. Backend | Detectar Ollama/LMStudio/vLLM, selecionar |
| 4. Modelos | Listar modelos, mapear Fast/Balanced/Deep |
| 5. Cloud Provider | API key mascarada, teste de conexao |
| 6. Threat Intel | URL, credenciais, teste |
| 7. Vantage | URL, auth, modulos |
| 8. Agente | Selecionar agente ativo |
| 9. Saida | Pasta de notas geradas |
| 10. Features | Checklist de feature flags |
| 11. Seguranca | Redacao, audit de prompts |
| 12. Resumo | Review, salvar, iniciar servico, abrir dashboard |

### 3.3 Subcomandos de gestao

- `socc configure show|set|unset|validate`
- `socc models list|set|fallback|test`

### 3.4 Backup de `.env`

Toda escrita em `.env` cria backup automatico com timestamp.

## 4. Nao objetivos

- Replicar o OpenClaw integralmente (canais, OAuth, device pairing)
- Criar TUI com ncurses ou similar
- Substituir a interface web
- Executar acoes destrutivas na maquina do usuario

## 5. Escopo do agente

O SOCC **nao** e um agente de execucao geral. Ele e um copiloto de analise SOC capaz de:
- Pesquisar na base local de conhecimento (RAG)
- Encontrar e ler arquivos de referencia do workspace do agente
- Contextualizar alertas com SOPs, playbooks e regras locais
- Classificar, analisar e gerar drafts de notas

## 6. Arquitetura

```
socc/cli/
├── prompt_runtime.py    # NOVO — modulo de prompts interativos
├── main.py              # MODIFICADO — wizard no onboard, novos subcomandos
├── installer.py         # MODIFICADO — integrar com wizard
└── service_manager.py   # SEM MUDANCA

socc/utils/
├── config_loader.py     # MODIFICADO — backup, validacao, batch write
└── feature_flags.py     # SEM MUDANCA
```

## 7. Requisitos funcionais

- RF-01: `prompt_runtime` com ask, confirm, select, secret, checklist, path, summary
- RF-02: Deteccao automatica de TTY; `--no-interactive` para suprimir prompts
- RF-03: Wizard `socc onboard` com 12 etapas e defaults seguros
- RF-04: Deteccao automatica de backends (probe HTTP)
- RF-05: Listagem de modelos do Ollama com mapeamento para profiles
- RF-06: Entry mascarada de API keys com teste de conexao
- RF-07: Registro e indexacao de knowledge base via prompt
- RF-08: Backup de `.env` antes de escrita
- RF-09: Resumo final com diff de configuracao
- RF-10: `socc configure show` com valores redacted
- RF-11: `socc configure set/unset` com backup e validacao
- RF-12: `socc models list/set/test`

## 8. Requisitos nao-funcionais

- Zero dependencias novas (apenas stdlib: getpass, shutil, sys, os)
- Compatibilidade com `--json` em todos os subcomandos
- Nao quebrar scripts existentes
- Segredos nunca em log, tela ou resumo

## 9. Fases de entrega

| Fase | Conteudo |
|------|----------|
| F1 | `prompt_runtime.py` + backup de `.env` |
| F2 | Wizard `socc onboard` completo |
| F3 | `socc configure` + `socc models` |
| F4 | Doctor interativo |
