# UI Spec — SOCC Claude-Code-Like TUI

**Data:** 2026-04-01  
**Status:** Baseline para implementacao  
**Objetivo:** aproximar a TUI do SOCC da linguagem visual e ergonomia percebidas no Claude Code, adaptadas ao dominio SOC

---

## 1. Design Goals

- parecer uma ferramenta de operador, nao um chat casual
- transmitir densidade, foco e confianca visual
- privilegiar leitura rapida de sessao, estado e resposta
- tornar slash-commands, sessoes e runtime visiveis sem poluir o transcript
- suportar evolucao futura para modo remoto e `session bridge`

---

## 2. Core Layout

```text
┌ Top Chrome ────────────────────────────────────────────────────────────────┐
│ SOCC / active agent / session / mode / backend / model / remote state    │
├ Transcript Header ───────────────────────────────┬ Sidebar Header ────────┤
│ transcript / activity / phases / tool results    │ session / runtime /    │
│                                                   │ shortcuts / quick info │
│ main history pane                                 │ compact side pane      │
│                                                   │                        │
├ Composer Header ───────────────────────────────────────────────────────────┤
│ prompt state / hints / command palette context                            │
│ multiline input                                                            │
├ Footer Status ─────────────────────────────────────────────────────────────┤
│ keybind hints / busy state / latency / last skill / transport mode        │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Visual Language

### Palette

- base background: deep graphite / blue-black
- panel background: slightly lifted slate
- primary accent: cyan
- secondary accent: amber
- positive state: green
- warning state: warm yellow
- error state: soft red
- muted text: cool gray

### Typography Feel

- compact, terminal-native, high-density
- stronger weight only for state labels and section headers
- transcript should favor legibility over decoration

### Borders and Chrome

- use deliberate separators and panel titles
- avoid excessive ASCII art inside transcript
- keep one strong top chrome and one strong footer, with subtle internal dividers

---

## 4. Transcript Rules

- user messages should be visually distinct from assistant output
- system/meta events should render as compact status rows, not as normal chat
- phase events should appear as lightweight progress markers
- tool calls and tool results should render as small operational cards
- errors should stand out immediately but not flood the screen

---

## 5. Sidebar Rules

- show current session id and future remote/local mode
- show active backend, model, response mode and agent when known
- show quick slash commands
- show last skill, last latency and busy/idle state
- keep width fixed and content intentionally compact

---

## 6. Composer Rules

- multiline input with clear focus affordance
- explicit busy indicator when inference is running
- hint strip for `/help`, `/session`, `/new`, `/resume`
- autocomplete menu should feel like a command palette, not default terminal completion

---

## 7. Interaction Model

- `Enter`: submit
- `Tab`: slash-command completion
- `Ctrl+C` and `Esc`: exit
- `/session`: inspect session
- `/new`: create a fresh session
- `/resume`: reserved for parity work
- future: explicit toggle or command for local vs remote session

---

## 8. Remote-Ready States

The top chrome and sidebar must reserve space for:

- local vs remote badge
- connected session id
- transport state: disconnected, connecting, attached, degraded
- bridge-specific errors

These states may be placeholders in the first visual pass, but the layout must not need redesign later to support them.

---

## 9. Out of Scope for This Pass

- pixel-perfect reproduction of a proprietary TUI
- websocket bridge implementation
- full command palette search UI
- mouse-first interaction patterns

