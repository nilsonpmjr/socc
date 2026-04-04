# Task Lifecycle — Clean-Room Harness

**Data:** 2026-04-03  
**Status:** ativo

---

## Objetivo

Definir o mínimo de `task state` necessário no SOCC sem misturar esse estado com
o `session state` persistido.

---

## Distinção principal

### Session state

Representa o histórico persistido de conversa/uso:

- `session_id`
- mensagens
- título
- cliente
- uso agregado
- preview

Vive em `storage`/persistência e pode sobreviver ao processo atual.

### Task state

Representa a execução operacional atual ou recente:

- `task_id`
- `session_id` associado
- `kind`
- `status`
- `phase`
- `skill`
- `input_preview`
- `result_summary`
- `error`
- `subagent_ids`
- metadata transitória

Vive separado do transcript persistido e é pensado como estado de execução.

---

## Modelo mínimo adotado

Arquivo: `socc/core/task_state.py`

Estados iniciais suportados:

- `pending`
- `running`
- `completed`
- `failed`

Campos mínimos:

- `task_id`
- `session_id`
- `kind`
- `source`
- `status`
- `phase`
- `label`
- `skill`
- `input_preview`
- `result_summary`
- `error`
- `subagent_ids`
- `metadata`

---

## Integração atual

### Engine

- `chat_reply()` cria/atualiza task state
- `stream_chat_events()` cria/atualiza task state
- `chat_submission()` cria task para a operação de alto nível
- `build_chat_payload_response()` cria/atualiza task para payload analysis
- `stream_chat_submission_events()` e `stream_chat_payload_events()` propagam task state em eventos

### Subagentes

- `SubagentConfig.task_id` permite vincular subagente a uma task existente
- `fork_subagent()` faz attach do `subagent_id` à task quando `task_id` existe

### TUI / CLI

- consomem task payloads vindos da engine
- não são source of truth do task lifecycle

---

## O que isso prepara

- acoplar runtime events a uma unidade estável de execução
- separar claramente progresso operacional de transcript persistido
- permitir futura expansão para:
  - task tree
  - session bridge / remote tasks
  - observabilidade por task

---

## Fora do escopo deste passo

- persistir tasks em banco
- scheduler de tasks
- DAG de tasks
- retries automáticos
- remote task execution
