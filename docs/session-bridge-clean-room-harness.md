# Session Bridge — Clean-Room Harness

**Data:** 2026-04-03  
**Status:** baseline arquitetural

---

## Objetivo

Definir o contrato mínimo para sessões remotas sem implementar ainda o transporte real.

---

## Estados da sessão remota

Estados modelados:

- `created`
- `connecting`
- `attached`
- `paused`
- `closed`
- `error`

Estados de transporte:

- `disconnected`
- `connecting`
- `attached`
- `degraded`

Separação:

- **session state** responde "em que estágio lógico a sessão está"
- **transport state** responde "como está o canal entre TUI/CLI e o backend remoto"

---

## Contrato local mínimo

Arquivo: `socc/core/session_bridge.py`

Interface inicial:

- `create_session(...)`
- `attach_session(bridge_id)`
- `resume_session(bridge_id)`
- `pause_session(bridge_id)`
- `close_session(bridge_id)`
- `get_bridge(bridge_id)`
- `list_bridges(limit=...)`

Handle mínimo:

- `bridge_id`
- `session_id`
- `mode` (`local` / `remote`)
- `state`
- `transport`
- `transport_state`
- `auth_mode`
- `remote_target`
- `error`

---

## Estratégia de transporte inicial

Escolha para a primeira iteração remota:

- **control plane:** HTTP
- **event stream:** WebSocket

Representação curta no contrato: `http+ws`

Justificativa:

- combina bem com attach/resume explícitos
- separa criação/controle de sessão do streaming de eventos
- acomoda evolução futura da TUI sem redesenhar os estados

Para o presente passo:

- `memory` é o transporte local/stub
- `http+ws` é o transporte remoto planejado
- o transporte remoto permanece marcado como indisponível por padrão

---

## Estratégia de autenticação

Baseline escolhida:

- **bearer token** para o bridge remoto
- compatível com futura reutilização de OAuth/API key já tratados no runtime

Campos já previstos:

- `auth_mode`
- `remote_target`

---

## Estratégia de degradação

Quando o transporte remoto não estiver disponível:

- a sessão pode existir no estado lógico `created`
- a tentativa de attach move para:
  - `state = error`
  - `transport_state = degraded`
- `error` recebe um marcador explícito, ex.: `transport_unavailable:http+ws`

Comportamento esperado da UI/CLI em fase futura:

- mostrar badge/localização de erro sem travar o transcript local
- permitir fallback para sessão local
- preservar a distinção entre sessão inválida e transporte indisponível

---

## Relação com TUI e task state

- TUI já reserva espaço visual para `transport mode/state`
- `task state` pode futuramente apontar para `bridge_id`/sessão remota
- este contrato evita acoplar session bridge ao transcript persistido

---

## Fora do escopo deste passo

- websocket real
- reconexão automática
- sincronização de transcript remoto
- multiplexação de múltiplos backends remotos
- persistência de bridges em banco
