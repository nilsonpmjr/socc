"""Full-screen TUI chat for SOCC.

Inspired by Claude Code / Codex UI:
- Full-screen layout with separate history and input panes
- Real-time streaming tokens into the history area
- Status bar with backend/model/mode/session
- Slash-command palette with Tab autocomplete
- Keyboard shortcuts
"""

from __future__ import annotations

import os
import sys
import threading
import textwrap
from time import time
from typing import Any

# ---------------------------------------------------------------------------
# Optional deps check
# ---------------------------------------------------------------------------

try:
    from prompt_toolkit import Application
    from prompt_toolkit.buffer import Buffer
    from prompt_toolkit.completion import WordCompleter
    from prompt_toolkit.document import Document
    from prompt_toolkit.filters import Condition
    from prompt_toolkit.formatted_text import (
        HTML,
        FormattedText,
        to_formatted_text,
    )
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import (
        ConditionalContainer,
        Float,
        FloatContainer,
        HSplit,
        Layout,
        VSplit,
        Window,
    )
    from prompt_toolkit.layout.controls import (
        BufferControl,
        FormattedTextControl,
    )
    from prompt_toolkit.layout.dimension import Dimension as D
    from prompt_toolkit.layout.menus import CompletionsMenu
    from prompt_toolkit.styles import Style
    from prompt_toolkit.widgets import Frame, TextArea
    _HAS_PT = True
except ImportError:
    _HAS_PT = False

# ---------------------------------------------------------------------------
# ANSI helpers (sem Rich — prompt_toolkit cuida do terminal)
# ---------------------------------------------------------------------------

_ESC = "\x1b"

def _ansi(code: str, text: str) -> str:
    return f"{_ESC}[{code}m{text}{_ESC}[0m"

def _bold(t: str) -> str:     return _ansi("1", t)
def _dim(t: str) -> str:      return _ansi("2", t)
def _cyan(t: str) -> str:     return _ansi("36", t)
def _green(t: str) -> str:    return _ansi("32", t)
def _yellow(t: str) -> str:   return _ansi("33", t)
def _red(t: str) -> str:      return _ansi("31", t)
def _magenta(t: str) -> str:  return _ansi("35", t)
def _blue(t: str) -> str:     return _ansi("34", t)


# ---------------------------------------------------------------------------
# Slash commands
# ---------------------------------------------------------------------------

SLASH_COMMANDS = [
    "/exit", "/quit",
    "/clear",
    "/help",
    "/mode fast", "/mode balanced", "/mode deep",
    "/backend anthropic", "/backend ollama", "/backend openai",
    "/model",
    "/session",
    "/new",
]

HELP_LINES = [
    ("", ""),
    ("bold", "  Comandos disponíveis"),
    ("dim", "  " + "─" * 48),
    ("", "  /mode fast|balanced|deep   Troca o perfil de resposta"),
    ("", "  /backend anthropic|ollama|openai   Troca o backend LLM"),
    ("", "  /model <nome>              Troca o modelo"),
    ("", "  /new                       Nova sessão"),
    ("", "  /session                   Mostra ID da sessão"),
    ("", "  /clear                     Limpa o histórico"),
    ("", "  /help                      Esta ajuda"),
    ("", "  /exit  ou  Ctrl+C          Sair"),
    ("", ""),
    ("dim", "  Atalhos"),
    ("dim", "  " + "─" * 48),
    ("dim", "  Enter          Enviar mensagem"),
    ("dim", "  Ctrl+C / Esc   Sair"),
    ("dim", "  ↑ ↓            Histórico de input"),
    ("dim", "  Tab            Autocomplete de comandos"),
    ("", ""),
]

MODE_ICON = {"fast": "⚡", "balanced": "◈", "deep": "◉"}
BACKEND_ICON = {
    "anthropic": "◆ claude",
    "ollama": "◈ ollama",
    "openai-compatible": "◇ openai",
    "openai": "◇ openai",
}

# ---------------------------------------------------------------------------
# History buffer — plain text with ANSI, rendered in a Window
# ---------------------------------------------------------------------------

class HistoryBuffer:
    """Thread-safe append-only text buffer for the history pane."""

    def __init__(self) -> None:
        self._lines: list[str] = []
        self._lock = threading.Lock()
        self._on_change: list = []

    def subscribe(self, fn) -> None:
        self._on_change.append(fn)

    def _notify(self) -> None:
        for fn in self._on_change:
            try:
                fn()
            except Exception:
                pass

    def append_line(self, line: str = "") -> None:
        with self._lock:
            self._lines.append(line)
        self._notify()

    def append_inline(self, text: str) -> None:
        """Append text to the last line (for streaming)."""
        with self._lock:
            if not self._lines:
                self._lines.append(text)
            else:
                self._lines[-1] += text
        self._notify()

    def clear(self) -> None:
        with self._lock:
            self._lines.clear()
        self._notify()

    def get_formatted(self):
        from prompt_toolkit.formatted_text import ANSI
        with self._lock:
            text = "\n".join(self._lines) + "\n"
        return ANSI(text)

    def get_plain(self) -> str:
        with self._lock:
            return "\n".join(self._lines)


# ---------------------------------------------------------------------------
# Full-screen TUI
# ---------------------------------------------------------------------------

class SoccChatTUI:
    def __init__(
        self,
        *,
        session_id: str,
        cliente: str,
        response_mode: str,
        selected_backend: str,
        selected_model: str,
        stream: bool,
    ) -> None:
        self.session_id = session_id or str(int(time() * 1000))
        self.cliente = cliente
        self.mode = response_mode or "balanced"
        self.backend = selected_backend or "ollama"
        self.model = selected_model or ""
        self.stream = stream
        self.history = HistoryBuffer()
        self.app: Application | None = None
        self._running = False
        self._busy = False
        self._stream_buffer: list[str] = []

        # Welcome message
        self._welcome()

    # ------------------------------------------------------------------
    # Welcome
    # ------------------------------------------------------------------

    def _welcome(self) -> None:
        self.history.append_line(_dim("  " + "─" * 60))
        self.history.append_line(
            f"  {_bold(_cyan('⚡ SOCC'))}  {_bold('SOC Copilot')}  "
            f"{_dim('│')}  sessão {_dim(self.session_id[:16])}"
        )
        self.history.append_line(
            f"  {_dim('backend')} {_cyan(self.backend)}  "
            f"{_dim('│')}  {_dim('modelo')} {_cyan(self.model or '(auto)')}  "
            f"{_dim('│')}  {_dim('modo')} {_cyan(self.mode)}"
        )
        self.history.append_line(_dim("  " + "─" * 60))
        self.history.append_line(_dim("  /help para comandos  │  Ctrl+C ou /exit para sair"))
        self.history.append_line("")

    # ------------------------------------------------------------------
    # Status bar
    # ------------------------------------------------------------------

    def _status_bar_text(self) -> FormattedText:
        icon = MODE_ICON.get(self.mode, "◈")
        be = BACKEND_ICON.get(self.backend, self.backend)
        model_short = self.model[:24] if self.model else "auto"
        busy_indicator = "  ⟳ processando..." if self._busy else ""

        return FormattedText([
            ("class:status-bar.key", f"  {icon} {self.mode} "),
            ("class:status-bar.sep", " │ "),
            ("class:status-bar.backend", f" {be}/{model_short} "),
            ("class:status-bar.sep", " │ "),
            ("class:status-bar.session", f" sessão {self.session_id[:12]} "),
            ("class:status-bar.busy", busy_indicator),
            ("class:status-bar", " " * 40),
        ])

    # ------------------------------------------------------------------
    # Build layout
    # ------------------------------------------------------------------

    def _build_app(self) -> Application:
        history_control = FormattedTextControl(
            text=self.history.get_formatted,
            focusable=False,
        )

        history_window = Window(
            content=history_control,
            wrap_lines=True,
            ignore_content_width=True,
        )

        completer = WordCompleter(SLASH_COMMANDS, sentence=True, ignore_case=True)

        input_buffer = Buffer(
            name="input",
            completer=completer,
            complete_while_typing=True,
            accept_handler=self._on_submit,
        )

        input_control = BufferControl(
            buffer=input_buffer,
            include_default_input_processors=True,
        )

        prompt_window = Window(
            content=FormattedTextControl(
                text=lambda: FormattedText([
                    ("class:prompt.arrow", "  ❯ " if not self._busy else "  ⟳ "),
                ])
            ),
            width=4,
            dont_extend_width=False,
        )

        input_line = Window(
            content=input_control,
            height=3,
            dont_extend_height=True,
            wrap_lines=True,
        )

        input_area = VSplit([
            prompt_window,
            input_line,
        ])

        divider = Window(
            height=1,
            char="─",
            style="class:divider",
        )

        status_bar = Window(
            height=1,
            content=FormattedTextControl(text=self._status_bar_text),
            style="class:status-bar",
        )

        root_container = FloatContainer(
            content=HSplit([
                history_window,
                divider,
                input_area,
                status_bar,
            ]),
            floats=[
                Float(
                    xcursor=True,
                    ycursor=True,
                    content=CompletionsMenu(max_height=8, scroll_offset=1),
                )
            ],
        )

        layout = Layout(root_container, focused_element=input_buffer)

        style = Style.from_dict({
            "prompt.arrow":          "#4FC3F7 bold",
            "divider":               "#37474F",
            "status-bar":            "bg:#1A2332 #546E7A",
            "status-bar.key":        "bg:#1A2332 #4FC3F7 bold",
            "status-bar.backend":    "bg:#1A2332 #4DB6AC",
            "status-bar.session":    "bg:#1A2332 #546E7A",
            "status-bar.sep":        "bg:#1A2332 #37474F",
            "status-bar.busy":       "bg:#1A2332 #FFB300 bold",
            "completion-menu.completion":         "bg:#1E2A2E #B0BEC5",
            "completion-menu.completion.current": "bg:#26C6DA #000000 bold",
        })

        kb = KeyBindings()

        @kb.add("c-c")
        @kb.add("escape")
        def _exit(event):
            self._running = False
            event.app.exit()

        @kb.add("enter")
        def _submit(event):
            buf = event.app.current_buffer
            if buf.name == "input":
                buf.validate_and_handle()

        app = Application(
            layout=layout,
            style=style,
            key_bindings=kb,
            full_screen=True,
            mouse_support=False,
            color_depth=None,
        )

        # Refresh history when buffer changes
        def _refresh(_):
            if app.is_running:
                app.invalidate()

        self.history.subscribe(_refresh)
        self.app = app
        return app

    # ------------------------------------------------------------------
    # Submit handler
    # ------------------------------------------------------------------

    def _on_submit(self, buffer: Buffer) -> None:
        message = buffer.text.strip()
        buffer.reset()

        if not message:
            return

        # Echo user message
        self.history.append_line(f"  {_bold(_cyan('você'))}  {message}")
        self.history.append_line("")

        if message.startswith("/"):
            self._handle_command(message)
            return

        if self._busy:
            self.history.append_line(_yellow("  ⚠  Aguarde a resposta atual terminar."))
            self.history.append_line("")
            return

        # Dispatch LLM call in background thread
        threading.Thread(
            target=self._call_llm,
            args=(message,),
            daemon=True,
        ).start()

    # ------------------------------------------------------------------
    # Command handling
    # ------------------------------------------------------------------

    def _handle_command(self, cmd: str) -> None:
        parts = cmd.strip().split(None, 1)
        verb = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if verb in {"/exit", "/quit"}:
            self._running = False
            if self.app:
                self.app.exit()
            return

        if verb == "/clear":
            self.history.clear()
            self._welcome()
            return

        if verb == "/help":
            for style_hint, line in HELP_LINES:
                if style_hint == "bold":
                    self.history.append_line(_bold(line))
                elif style_hint == "dim":
                    self.history.append_line(_dim(line))
                else:
                    self.history.append_line(line)
            return

        if verb == "/session":
            self.history.append_line(_dim(f"  sessão: {self.session_id}"))
            self.history.append_line("")
            return

        if verb == "/new":
            self.session_id = str(int(time() * 1000))
            self.history.clear()
            self._welcome()
            self.history.append_line(_dim(f"  Nova sessão: {self.session_id}"))
            self.history.append_line("")
            return

        if verb == "/mode":
            valid = {"fast", "balanced", "deep"}
            if arg.lower() in valid:
                self.mode = arg.lower()
                icon = MODE_ICON.get(self.mode, "◈")
                self.history.append_line(
                    f"  {_dim('modo →')} {_cyan(f'{icon} {self.mode}')}"
                )
            else:
                self.history.append_line(_yellow("  ⚠  Use: /mode fast | balanced | deep"))
            self.history.append_line("")
            return

        if verb == "/backend":
            aliases = {
                "anthropic": "anthropic",
                "claude": "anthropic",
                "ollama": "ollama",
                "openai": "openai-compatible",
                "openai-compatible": "openai-compatible",
                "codex": "openai-compatible",
            }
            nb = aliases.get(arg.lower(), "")
            if nb:
                self.backend = nb
                self.history.append_line(
                    f"  {_dim('backend →')} {_cyan(self.backend)}"
                )
            else:
                self.history.append_line(_yellow("  ⚠  Use: /backend anthropic | ollama | openai"))
            self.history.append_line("")
            return

        if verb == "/model":
            if arg:
                self.model = arg
                self.history.append_line(
                    f"  {_dim('modelo →')} {_cyan(self.model)}"
                )
            else:
                self.history.append_line(_yellow("  ⚠  Use: /model <nome>"))
            self.history.append_line("")
            return

        self.history.append_line(_yellow(f"  ⚠  Comando desconhecido: {verb}. Digite /help."))
        self.history.append_line("")

    # ------------------------------------------------------------------
    # LLM call (runs in background thread)
    # ------------------------------------------------------------------

    def _call_llm(self, message: str) -> None:
        from socc.core.engine import chat_reply, stream_chat_events

        self._busy = True
        if self.app:
            self.app.invalidate()

        started = time()
        skill = ""
        content = ""

        try:
            if self.stream:
                self.history.append_line(
                    f"  {_dim(BACKEND_ICON.get(self.backend, self.backend))}"
                )
                # Linha inicial vazia pra receber o texto
                self.history.append_line("  ")

                parts: list[str] = []
                for event in stream_chat_events(
                    message,
                    session_id=self.session_id,
                    cliente=self.cliente,
                    response_mode=self.mode,
                    selected_backend=self.backend,
                    selected_model=self.model,
                ):
                    if event.get("event") == "delta":
                        delta = str(event.get("delta") or "")
                        parts.append(delta)
                        # Divide em linhas e adiciona corretamente
                        segments = delta.split("\n")
                        for i, seg in enumerate(segments):
                            if i == 0:
                                # Continua na linha atual
                                self.history.append_inline(seg)
                            else:
                                # Nova linha com indentação
                                self.history.append_line("  " + seg)
                        if self.app:
                            self.app.invalidate()
                    elif event.get("event") == "final":
                        data = event.get("data") or {}
                        if isinstance(data, dict):
                            self.session_id = str(data.get("session_id") or self.session_id)
                            skill = str((data.get("metadata") or {}).get("skill") or data.get("skill") or "")
                            self.model = str(data.get("model") or self.model)

                content = "".join(parts)

            else:
                response = chat_reply(
                    message,
                    session_id=self.session_id,
                    cliente=self.cliente,
                    response_mode=self.mode,
                    selected_backend=self.backend,
                    selected_model=self.model,
                )
                self.session_id = str(response.get("session_id") or self.session_id)
                content = str(response.get("content") or response.get("message") or "")
                skill = str((response.get("metadata") or {}).get("skill") or response.get("skill") or "")
                self.model = str(response.get("model") or self.model)

                # Render content line by line
                self.history.append_line(
                    f"  {_bold(_dim(BACKEND_ICON.get(self.backend, self.backend)))}"
                )
                for line in content.splitlines():
                    self.history.append_line(f"  {line}")

        except Exception as exc:
            self.history.append_line(f"  {_red('✗')}  {exc}")

        finally:
            latency = (time() - started) * 1000
            meta_parts = [f"{latency:.0f}ms"]
            if skill and skill != "soc-generalist":
                meta_parts.append(f"skill:{skill}")
            self.history.append_line("")
            self.history.append_line(
                _dim("  " + "  │  ".join(meta_parts))
            )
            self.history.append_line("")
            self._busy = False
            if self.app:
                self.app.invalidate()

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def run(self) -> int:
        self._running = True
        app = self._build_app()
        try:
            app.run()
        except (KeyboardInterrupt, EOFError):
            pass
        return 0


# ---------------------------------------------------------------------------
# Fallback plain REPL (quando prompt_toolkit não disponível)
# ---------------------------------------------------------------------------

def _run_plain_repl(
    *,
    session_id: str,
    cliente: str,
    response_mode: str,
    selected_backend: str,
    selected_model: str,
    stream: bool,
) -> int:
    from socc.core.engine import chat_reply, stream_chat_events

    sid = session_id or str(int(time() * 1000))
    backend = selected_backend or "ollama"
    model = selected_model or ""
    mode = response_mode or "balanced"

    print(f"\n⚡ SOCC Chat  │  {backend}/{model}  │  modo {mode}")
    print("Digite /exit para sair, /help para comandos\n")

    while True:
        try:
            raw = input("você › ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        if not raw:
            continue
        if raw.lower() in {"/exit", "/quit"}:
            return 0
        if raw.startswith("/"):
            print(f"  [comando: {raw}]")
            continue

        if stream:
            print(f"\n{backend}/{model} › ", end="", flush=True)
            for event in stream_chat_events(
                raw, session_id=sid, cliente=cliente,
                response_mode=mode, selected_backend=backend, selected_model=model,
            ):
                if event.get("event") == "delta":
                    print(str(event.get("delta") or ""), end="", flush=True)
                elif event.get("event") == "final":
                    data = event.get("data")
                    if isinstance(data, dict):
                        sid = str(data.get("session_id") or sid)
            print("\n")
        else:
            response = chat_reply(
                raw, session_id=sid, cliente=cliente,
                response_mode=mode, selected_backend=backend, selected_model=model,
            )
            sid = str(response.get("session_id") or sid)
            print(f"\nsocc › {response.get('content') or ''}\n")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_chat_tui(
    *,
    session_id: str = "",
    cliente: str = "",
    response_mode: str = "balanced",
    selected_backend: str = "",
    selected_model: str = "",
    stream: bool = True,
) -> int:
    if not _HAS_PT:
        return _run_plain_repl(
            session_id=session_id,
            cliente=cliente,
            response_mode=response_mode,
            selected_backend=selected_backend,
            selected_model=selected_model,
            stream=stream,
        )

    tui = SoccChatTUI(
        session_id=session_id,
        cliente=cliente,
        response_mode=response_mode,
        selected_backend=selected_backend,
        selected_model=selected_model,
        stream=stream,
    )
    return tui.run()
