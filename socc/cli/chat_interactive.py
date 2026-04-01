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

def _harness_commands() -> list[str]:
    """Return slash-command names registered in the harness CommandRegistry."""
    try:
        from socc.core.harness.commands import COMMAND_REGISTRY
        return [f"/{c.name}" for c in COMMAND_REGISTRY.list()]
    except Exception:
        return []


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

QUICK_ACTIONS = [
    "/help",
    "/session",
    "/new",
    "/agents",
    "/tools",
    "/case",
    "/hunt",
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
        self._last_skill = ""
        self._last_phase = ""
        self._last_latency_ms = 0.0
        self._transport_mode = "local"

        # Welcome message
        self._welcome()

    # ------------------------------------------------------------------
    # Welcome
    # ------------------------------------------------------------------

    def _welcome(self) -> None:
        self.history.append_line(f"  {_bold(_cyan('SOCC operator cockpit'))}")
        self.history.append_line(
            _dim("  Harness ativo  │  slash commands  │  sessoes  │  runtime observavel")
        )
        self.history.append_line(
            _dim("  /help para comandos  │  Tab autocomplete  │  Ctrl+C ou Esc para sair")
        )
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

    def _top_chrome_text(self) -> FormattedText:
        be = BACKEND_ICON.get(self.backend, self.backend)
        model_short = self.model[:18] if self.model else "auto"
        return FormattedText([
            ("class:chrome.brand", "  SOCC  "),
            ("class:chrome.sep", " // "),
            ("class:chrome.title", "Claude-style SOC cockpit"),
            ("class:chrome.sep", "  │  "),
            ("class:chrome.meta", f"{be}"),
            ("class:chrome.sep", "  ·  "),
            ("class:chrome.meta", model_short),
            ("class:chrome.sep", "  ·  "),
            ("class:chrome.meta", f"session {self.session_id[:12]}"),
            ("class:chrome.sep", "  ·  "),
            ("class:chrome.meta", self._transport_mode),
        ])

    def _transcript_header_text(self) -> FormattedText:
        return FormattedText([
            ("class:panel-title.accent", "  transcript  "),
            ("class:panel-title.sep", "│"),
            ("class:panel-title.meta", " operator activity / phases / responses "),
        ])

    def _sidebar_header_text(self) -> FormattedText:
        return FormattedText([
            ("class:panel-title.accent", "  runtime  "),
            ("class:panel-title.sep", "│"),
            ("class:panel-title.meta", " session / hints / transport "),
        ])

    def _composer_header_text(self) -> FormattedText:
        hint = "busy" if self._busy else "ready"
        return FormattedText([
            ("class:composer-title.accent", "  composer  "),
            ("class:composer-title.sep", "│"),
            ("class:composer-title.meta", f" Enter send  ·  Tab commands  ·  state {hint} "),
        ])

    def _footer_bar_text(self) -> FormattedText:
        skill = self._last_skill or "general"
        phase = self._last_phase or "idle"
        latency = f"{self._last_latency_ms:.0f}ms" if self._last_latency_ms else "-"
        return FormattedText([
            ("class:footer.key", "  /help "),
            ("class:footer.sep", "│"),
            ("class:footer.meta", " /session "),
            ("class:footer.sep", "│"),
            ("class:footer.meta", " /new "),
            ("class:footer.sep", "│"),
            ("class:footer.meta", f" skill {skill} "),
            ("class:footer.sep", "│"),
            ("class:footer.meta", f" phase {phase} "),
            ("class:footer.sep", "│"),
            ("class:footer.meta", f" latency {latency} "),
        ])

    def _sidebar_text(self):
        quick = "  " + "\n  ".join(QUICK_ACTIONS)
        model = self.model or "(auto)"
        runtime_lines = [
            ("class:sidebar.label", "  session\n"),
            ("class:sidebar.value", f"  {self.session_id}\n\n"),
            ("class:sidebar.label", "  transport\n"),
            ("class:sidebar.value", f"  {self._transport_mode}\n\n"),
            ("class:sidebar.label", "  backend\n"),
            ("class:sidebar.value", f"  {self.backend}\n\n"),
            ("class:sidebar.label", "  model\n"),
            ("class:sidebar.value", f"  {model}\n\n"),
            ("class:sidebar.label", "  mode\n"),
            ("class:sidebar.value", f"  {self.mode}\n\n"),
            ("class:sidebar.label", "  last skill\n"),
            ("class:sidebar.value", f"  {self._last_skill or '-'}\n\n"),
            ("class:sidebar.label", "  last phase\n"),
            ("class:sidebar.value", f"  {self._last_phase or '-'}\n\n"),
            ("class:sidebar.label", "  quick actions\n"),
            ("class:sidebar.value", quick + "\n"),
        ]
        return FormattedText(runtime_lines)

    def _append_phase_event(self, phase: str, label: str) -> None:
        self._last_phase = phase or self._last_phase
        rendered = label or phase or "processing"
        self.history.append_line(_dim(f"  · {rendered}"))
        self.history.append_line("")

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
            style="class:transcript",
        )

        history_header = Window(
            height=1,
            content=FormattedTextControl(text=self._transcript_header_text),
            style="class:panel-title",
        )

        sidebar_window = Window(
            content=FormattedTextControl(text=self._sidebar_text),
            wrap_lines=True,
            ignore_content_width=True,
            style="class:sidebar",
        )

        sidebar_header = Window(
            height=1,
            content=FormattedTextControl(text=self._sidebar_header_text),
            style="class:panel-title",
        )

        completer = WordCompleter(SLASH_COMMANDS + _harness_commands(), sentence=True, ignore_case=True)

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
            style="class:composer",
        )

        input_area = VSplit([
            prompt_window,
            input_line,
        ])

        chrome_bar = Window(
            height=1,
            content=FormattedTextControl(text=self._top_chrome_text),
            style="class:chrome",
        )

        composer_header = Window(
            height=1,
            content=FormattedTextControl(text=self._composer_header_text),
            style="class:composer-title",
        )

        status_bar = Window(
            height=1,
            content=FormattedTextControl(text=self._status_bar_text),
            style="class:status-bar",
        )

        footer_bar = Window(
            height=1,
            content=FormattedTextControl(text=self._footer_bar_text),
            style="class:footer",
        )

        body_split = VSplit(
            [
                HSplit(
                    [history_header, history_window],
                    style="class:panel-shell",
                ),
                Window(width=1, char="│", style="class:panel-divider"),
                HSplit(
                    [sidebar_header, sidebar_window],
                    width=D(preferred=34, min=28, max=40),
                    style="class:sidebar-shell",
                ),
            ]
        )

        root_container = FloatContainer(
            content=HSplit([
                chrome_bar,
                body_split,
                Window(height=1, char="─", style="class:divider"),
                composer_header,
                input_area,
                status_bar,
                footer_bar,
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
            "chrome":                          "bg:#0B1118 #8EA1B5",
            "chrome.brand":                    "bg:#0B1118 #5EEAD4 bold",
            "chrome.title":                    "bg:#0B1118 #F8FAFC bold",
            "chrome.meta":                     "bg:#0B1118 #93C5FD",
            "chrome.sep":                      "bg:#0B1118 #334155",
            "panel-shell":                     "bg:#0F1720",
            "sidebar-shell":                   "bg:#111A23",
            "transcript":                      "bg:#0F1720 #D6DEE6",
            "sidebar":                         "bg:#111A23 #C0CBD7",
            "panel-title":                     "bg:#16212C #94A3B8",
            "panel-title.accent":              "bg:#16212C #67E8F9 bold",
            "panel-title.sep":                 "bg:#16212C #334155",
            "panel-title.meta":                "bg:#16212C #94A3B8",
            "panel-divider":                   "bg:#0B1118 #243140",
            "prompt.arrow":                    "#67E8F9 bold",
            "divider":                         "#243140",
            "composer-title":                  "bg:#17202B #94A3B8",
            "composer-title.accent":           "bg:#17202B #FBBF24 bold",
            "composer-title.sep":              "bg:#17202B #334155",
            "composer-title.meta":             "bg:#17202B #94A3B8",
            "composer":                        "bg:#0D141C #E2E8F0",
            "status-bar":                      "bg:#0E1620 #64748B",
            "status-bar.key":                  "bg:#0E1620 #67E8F9 bold",
            "status-bar.backend":              "bg:#0E1620 #5EEAD4",
            "status-bar.session":              "bg:#0E1620 #94A3B8",
            "status-bar.sep":                  "bg:#0E1620 #334155",
            "status-bar.busy":                 "bg:#0E1620 #FBBF24 bold",
            "footer":                          "bg:#0B1118 #7C8CA0",
            "footer.key":                      "bg:#0B1118 #F8FAFC bold",
            "footer.meta":                     "bg:#0B1118 #7C8CA0",
            "footer.sep":                      "bg:#0B1118 #334155",
            "sidebar.label":                   "#7C8CA0",
            "sidebar.value":                   "#D6DEE6",
            "completion-menu.completion":         "bg:#12202B #CBD5E1",
            "completion-menu.completion.current": "bg:#67E8F9 #0B1118 bold",
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
            self._last_phase = ""
            self._last_skill = ""
            self._last_latency_ms = 0.0
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

        # Delegate unknown commands to the harness CommandRegistry
        try:
            from socc.core.harness.commands import COMMAND_REGISTRY
            result = COMMAND_REGISTRY.dispatch(cmd)
            if result.ok:
                for line in result.output.splitlines():
                    self.history.append_line(f"  {line}")
            else:
                self.history.append_line(_yellow(f"  ⚠  {result.error}"))
        except Exception as _exc:
            self.history.append_line(_yellow(f"  ⚠  Erro no comando: {_exc}"))
        self.history.append_line("")

    # ------------------------------------------------------------------
    # LLM call (runs in background thread)
    # ------------------------------------------------------------------

    def _call_llm(self, message: str) -> None:
        from socc.core.engine import chat_reply, stream_chat_submission_events

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

                parts: list[str] = []
                self.history.append_line("  ")

                for event in stream_chat_submission_events(
                    message=message,
                    session_id=self.session_id,
                    classificacao="AUTO",
                    cliente=self.cliente,
                    response_mode=self.mode,
                    selected_backend=self.backend,
                    selected_model=self.model,
                ):
                    event_name = str(event.get("event") or "")
                    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}

                    if event_name == "meta":
                        self.session_id = str(payload.get("session_id") or self.session_id)
                        self._last_skill = str(payload.get("skill") or self._last_skill)
                        self.model = str(payload.get("model") or self.model)
                        continue
                    if event_name == "phase":
                        self._append_phase_event(
                            str(payload.get("phase") or ""),
                            str(payload.get("label") or ""),
                        )
                        continue
                    if event_name == "delta":
                        delta = str(payload.get("delta") or "")
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
                    elif event_name == "final":
                        data = payload
                        if isinstance(data, dict):
                            self.session_id = str(data.get("session_id") or self.session_id)
                            skill = str((data.get("metadata") or {}).get("skill") or data.get("skill") or "")
                            self._last_skill = skill or self._last_skill
                            runtime_info = data.get("runtime") if isinstance(data.get("runtime"), dict) else {}
                            self.model = str(runtime_info.get("model") or data.get("model") or self.model)

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
                self._last_skill = skill or self._last_skill
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
            self._last_latency_ms = latency
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
    from socc.core.engine import chat_reply, stream_chat_submission_events

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
            for event in stream_chat_submission_events(
                message=raw,
                session_id=sid,
                classificacao="AUTO",
                cliente=cliente,
                response_mode=mode,
                selected_backend=backend,
                selected_model=model,
            ):
                event_name = str(event.get("event") or "")
                payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
                if event_name == "phase":
                    print(f"\n  · {payload.get('label') or payload.get('phase')}")
                    print(f"{backend}/{model} › ", end="", flush=True)
                elif event_name == "delta":
                    print(str(payload.get("delta") or ""), end="", flush=True)
                elif event_name == "final":
                    data = payload
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
