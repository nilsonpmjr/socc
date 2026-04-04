# Boundary Doc — Harness, Engine, Chat, TUI e Web

**Data:** 2026-04-03  
**Status:** ativo  
**Relacionados:** `prd-clean-room-harness-rewrite.md`, `todo-clean-room-harness-rewrite.md`

---

## Objetivo

Fixar as fronteiras da clean-room rewrite para evitar que command routing, inventory
e session/runtime state voltem a ficar espalhados entre camadas.

---

## Responsabilidades por camada

### 1. Harness runtime — `socc.core.harness.runtime`

É a superfície central de:

- inventário de commands, tools e agents
- merge entre snapshot e live registry
- roteamento (`route_prompt`)
- dispatch de commands (`dispatch_command`)
- introspecção de metadata (`list_*_inventory`, `get_*_record`)

**Não deve:**

- conter lógica de UI/TUI
- conter persistência de transcript de chat
- conhecer detalhes da camada web

---

### 2. Chat facade — `socc.core.chat`

É a fachada estável entre o runtime Python do SOCC e o serviço legado de chat.

Responsável por:

- expor `select_skill`
- expor `generate_chat_reply`
- expor `stream_chat_reply_events`

**Função arquitetural:** impedir que consumidores novos precisem importar
`soc_copilot.modules.chat_service` diretamente.

---

### 3. Engine — `socc.core.engine`

É a camada de composição operacional.

Responsável por:

- payload chat vs payload analysis
- envelopes/contratos estáveis
- sessão persistida, feedback, export, runtime payloads
- adaptação dos eventos do chat para payloads consumíveis por CLI/TUI/web

**Não deve:**

- reimplementar inventory/routing de harness
- reimplementar registry de commands/tools
- importar a camada web como fonte de comportamento

---

### 4. TUI / CLI interativa — `socc.cli.chat_interactive`, `socc.cli.main`

É a camada de apresentação terminal-first.

Responsável por:

- layout
- slash UX
- resumo de sessão
- renderização de phase/tool/result events

**Deve usar:**

- harness runtime para commands/help/introspection
- engine para replies e eventos de chat

**Não deve:**

- dispatchar commands por caminhos paralelos fora da harness
- montar sozinha metadata de inventory
- acessar o chat service legado diretamente

---

### 5. Web — `soc_copilot.main` e rotas HTTP

É um cliente do runtime.

Responsável por:

- transporte HTTP
- autenticação/autorização web
- serialização HTTP e UX web

**Deve usar:**

- `socc.core.engine` para payloads e operações
- `socc.core.storage` quando a operação for estritamente de persistência

**Não deve:**

- virar source of truth de runtime
- manter contracts paralelos de session/chat quando já existirem no runtime

---

## Regras práticas

### Command routing

- slash commands em TUI/CLI devem passar pela harness (`SOCRuntime.dispatch_command`)
- help de command em TUI/CLI deve vir da harness
- autocomplete/introspection de command deve refletir a superfície da harness

### Tool routing

- discovery/introspection de tool deve passar pela harness inventory
- execução de tool em fluxos de agente/subagente deve usar a policy resolvida da harness
- UI não decide policy de tool; apenas renderiza estado/evento

### Session state

- persistência e resumo de sessão vivem em `storage`/`engine`
- TUI e web consomem payloads de sessão; não reconstruem summary espalhado

---

## Fluxo canônico

```text
CLI/TUI/Web
  -> engine (chat/payload/session/export envelopes)
    -> chat facade / storage / harness runtime
      -> legacy chat service / persistence / tool registry
```

Para slash commands:

```text
CLI/TUI
  -> harness runtime
    -> command registry
```

Para inventory/routing:

```text
CLI/TUI
  -> harness runtime
    -> snapshots + live registry
```

---

## Anti-patterns a evitar

- TUI chamando `COMMAND_REGISTRY` diretamente quando a harness já expõe a operação
- engine chamando inventário de tool/command por caminhos fora da harness
- web criando payload de sessão próprio quando o engine já entrega um contrato
- novas integrações importando `soc_copilot.modules.chat_service` diretamente

---

## Estado atual após esta fase

- TUI usa a harness para slash commands, help e command list
- inventory/routing de CLI usam a harness
- engine usa a fachada `socc.core.chat` para o serviço de chat
- sessão atual possui payload resumido reutilizável por CLI/TUI

Ainda aberto para fases futuras:

- task lifecycle explícito
- remote/session bridge
- fronteira final entre runtime state e task state
