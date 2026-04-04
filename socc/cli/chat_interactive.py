"""Full-screen TUI chat for SOCC.

Inspired by source-first terminal operator UIs:
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
import asyncio
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
        from socc.core.harness.runtime import RUNTIME

        return [f"/{c.name}" for c in RUNTIME.list_commands()]
    except Exception:
        return []


def _slash_surface() -> list[str]:
    commands = list(dict.fromkeys(SLASH_COMMANDS + _harness_commands()))
    return sorted(commands)


SLASH_COMMANDS = [
    "/exit", "/quit",
    "/clear",
    "/help",
    "/mode fast", "/mode balanced", "/mode deep",
    "/backend anthropic", "/backend ollama", "/backend openai",
    "/model",
    "/session",
    "/new",
    "/resume",
]

QUICK_ACTIONS = [
    "/help",
    "/session",
    "/new",
    "/resume",
    "/agents",
    "/tools",
    "/case",
    "/hunt",
]

LOCAL_HELP_LINES = [
    ("", ""),
    ("bold", "  Comandos locais"),
    ("dim", "  " + "─" * 48),
    ("", "  /mode fast|balanced|deep   Troca o perfil de resposta"),
    ("", "  /backend anthropic|ollama|openai   Troca o backend LLM"),
    ("", "  /model <nome>              Troca o modelo"),
    ("", "  /new                       Nova sessão"),
    ("", "  /session                   Mostra resumo da sessão atual"),
    ("", "  /resume <id>               Retoma uma sessão persistida"),
    ("", "  /clear                     Limpa o histórico"),
    ("", "  /help [comando]            Ajuda local ou da harness"),
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
    "anthropic": "◆ anthropic",
    "ollama": "◈ ollama",
    "openai-compatible": "◇ openai",
    "openai": "◇ openai",
}

LOCAL_COMMAND_SPECS: dict[str, dict[str, Any]] = {
    "/help": {"description": "Ajuda local e da harness", "aliases": []},
    "/clear": {"description": "Limpa o histórico atual", "aliases": []},
    "/exit": {"description": "Sai da interface", "aliases": ["/quit"]},
    "/quit": {"description": "Sai da interface", "aliases": ["/exit"]},
    "/mode": {"description": "Troca o perfil de resposta", "aliases": []},
    "/backend": {"description": "Troca o backend LLM ativo", "aliases": []},
    "/model": {"description": "Troca o modelo ativo", "aliases": []},
    "/session": {"description": "Mostra o resumo da sessão atual", "aliases": []},
    "/new": {"description": "Cria uma nova sessão", "aliases": []},
    "/resume": {"description": "Retoma uma sessão persistida", "aliases": []},
}


def _render_help_lines(history: "HistoryBuffer", lines: list[tuple[str, str]]) -> None:
    for style_hint, line in lines:
        if style_hint == "bold":
            history.append_line(_bold(line))
        elif style_hint == "dim":
            history.append_line(_dim(line))
        else:
            history.append_line(line)


def _render_harness_help(history: "HistoryBuffer", command_name: str = "") -> bool:
    try:
        from socc.core.harness.runtime import RUNTIME

        help_text = RUNTIME.command_help(command_name.lstrip("/")) if command_name else RUNTIME.command_help()
    except Exception:
        return False

    if not help_text:
        return False
    history.append_line(_bold("  Comandos da harness"))
    history.append_line(_dim("  " + "─" * 48))
    for line in help_text.splitlines():
        history.append_line(f"  {line}" if line else "")
    history.append_line("")
    return True

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
        self._input_value = ""
        self._history_follow = True
        self._history_area = None
        self._transcript_mode = False

        # Welcome message
        self._welcome()
        self._resume_session(self.session_id, render_notice=False)

    # ------------------------------------------------------------------
    # Welcome
    # ------------------------------------------------------------------

    def _welcome(self) -> None:
        return None
        self.history.append_line("")

    # ------------------------------------------------------------------
    # Status bar
    # ------------------------------------------------------------------

    def _status_bar_text(self) -> FormattedText:
        icon = MODE_ICON.get(self.mode, "◈")
        be = BACKEND_ICON.get(self.backend, self.backend)
        model_short = self.model[:24] if self.model else "auto"
        busy_indicator = "  ⟳ processando..." if self._busy else "  ✓ idle"
        task = self._get_active_task()
        task_state = str(task.get("status") or "-") if task else "-"

        return FormattedText([
            ("class:status-bar.key", f"  {icon} {self.mode} "),
            ("class:status-bar.sep", " │ "),
            ("class:status-bar.backend", f" {be}/{model_short} "),
            ("class:status-bar.sep", " │ "),
            ("class:status-bar.session", f" sessão {self.session_id[:12]} "),
            ("class:status-bar.sep", " │ "),
            ("class:status-bar.session", f" task {task_state} "),
            ("class:status-bar.busy", busy_indicator),
            ("class:status-bar", " " * 40),
        ])

    def _top_chrome_text(self) -> FormattedText:
        be = BACKEND_ICON.get(self.backend, self.backend)
        model_short = self.model[:18] if self.model else "auto"
        session_summary = self._get_session_summary(self.session_id, limit=6) or {}
        session_title = str(session_summary.get("titulo") or "untitled")[:20]
        bridge = self._get_bridge_summary()
        task = self._get_active_task()
        task_label = str(task.get("status") or "idle")[:10] if task else "idle"
        mode_badge = self.mode[:8]
        transport_badge = str(bridge.get("transport_state") or "attached")[:10]
        return FormattedText([
            ("class:chrome.brand", "  SOCC  "),
            ("class:chrome.meta", session_title),
            ("class:chrome.sep", "  ·  "),
            ("class:chrome.meta", mode_badge),
            ("class:chrome.sep", "  ·  "),
            ("class:chrome.meta", f"{be}/{model_short}"),
            ("class:chrome.sep", "  ·  "),
            ("class:chrome.meta", f"{task_label}/{transport_badge}"),
            ("class:chrome.sep", "  ·  "),
            ("class:chrome.meta", self.session_id[:10]),
        ])

    def _composer_header_text(self) -> FormattedText:
        hint = "busy" if self._busy else "ready"
        return FormattedText([
            ("class:composer-title.accent", "  prompt  "),
            ("class:composer-title.sep", "│"),
            ("class:composer-title.meta", f" enter send  ·  / slash commands  ·  {hint} "),
        ])

    def _command_catalog(self) -> dict[str, dict[str, Any]]:
        catalog = {name: dict(spec) for name, spec in LOCAL_COMMAND_SPECS.items()}
        try:
            from socc.core.harness.runtime import RUNTIME

            for command in RUNTIME.list_commands():
                catalog[f"/{command.name}"] = {
                    "description": command.description,
                    "aliases": [f"/{alias}" for alias in command.aliases],
                    "arguments": [argument.name for argument in command.arguments],
                }
        except Exception:
            pass
        return catalog

    def _command_palette_text(self) -> FormattedText:
        raw = str(self._input_value or "").strip()
        if not raw.startswith("/"):
            return FormattedText([
                ("class:palette.label", "  prompt "),
                ("class:palette.meta", "\n"),
                ("class:palette.meta", "  natural language / payload"),
                ("class:palette.meta", "\n"),
                ("class:palette.meta", "  enter send  ·  tab commands  ·  /help"),
            ])

        command_token = raw.split(maxsplit=1)[0].lower()
        catalog = self._command_catalog()
        best_name = ""
        best_spec: dict[str, Any] = {}

        if command_token in catalog:
            best_name = command_token
            best_spec = catalog[command_token]
        else:
            for name, spec in catalog.items():
                aliases = [alias.lower() for alias in spec.get("aliases", [])]
                if name.startswith(command_token) or command_token in aliases:
                    best_name = name
                    best_spec = spec
                    break

        if not best_name:
            return FormattedText([
                ("class:palette.label", "  slash "),
                ("class:palette.warn", f"  comando desconhecido {command_token} "),
                ("class:palette.meta", "\n"),
                ("class:palette.meta", "  tente /help ou Tab para navegar"),
            ])

        aliases = list(best_spec.get("aliases") or [])
        args = list(best_spec.get("arguments") or [])
        alias_text = f"aliases {', '.join(aliases[:2])}" if aliases else "no aliases"
        args_text = f"args {', '.join(args[:3])}" if args else "no args"
        return FormattedText([
            ("class:palette.label", "  slash "),
            ("class:palette.key", f"  {best_name}"),
            ("class:palette.meta", "\n"),
            ("class:palette.meta", f"  {best_spec.get('description') or '-'}"),
            ("class:palette.meta", "\n"),
            ("class:palette.meta", f"  {alias_text}  ·  {args_text}"),
        ])

    def _footer_bar_text(self) -> FormattedText:
        phase = self._last_phase or "idle"
        latency = f"{self._last_latency_ms:.0f}ms" if self._last_latency_ms else "-"
        state = "busy" if self._busy else "idle"
        bridge = self._get_bridge_summary()
        task = self._get_active_task()
        task_state = str(task.get("status") or "-") if task else "-"
        transport_state = str(bridge.get("transport_state") or "disconnected")
        return FormattedText([
            ("class:footer.key", "  ctrl+c "),
            ("class:footer.sep", "│"),
            ("class:footer.meta", " esc "),
            ("class:footer.sep", "│"),
            ("class:footer.meta", " ctrl+o "),
            ("class:footer.sep", "│"),
            ("class:footer.meta", " tab commands "),
            ("class:footer.sep", "│"),
            ("class:footer.meta", f" {state}/{task_state} "),
            ("class:footer.sep", "│"),
            ("class:footer.meta", f" {phase} "),
            ("class:footer.sep", "│"),
            ("class:footer.meta", f" {latency} "),
            ("class:footer.sep", "│"),
            ("class:footer.meta", f" {transport_state} "),
        ])

    def _sidebar_text(self):
        summary = self._get_session_summary(self.session_id, limit=6) or {}
        usage = summary.get("usage") or {}
        bridge = self._get_bridge_summary()
        task = self._get_active_task()
        model = self.model or "(auto)"
        title = str(summary.get("titulo") or "-")
        preview = str(summary.get("preview") or "-").replace("\n", " ")
        if len(preview) > 42:
            preview = preview[:42] + "..."
        last_latency = f"{self._last_latency_ms:.0f}ms" if self._last_latency_ms else "-"
        state = "busy" if self._busy else "idle"
        task_kind = str((task or {}).get("kind") or "-")
        task_status = str((task or {}).get("status") or "-")
        task_phase = str((task or {}).get("phase") or self._last_phase or "-")
        task_summary = str((task or {}).get("result_summary") or (task or {}).get("input_preview") or "-").replace("\n", " ")
        if len(task_summary) > 42:
            task_summary = task_summary[:42] + "..."
        runtime_lines = [
            ("class:sidebar.label", "  session\n"),
            ("class:sidebar.value", f"  {title}\n"),
            ("class:sidebar.value", f"  {self.session_id[:10]}\n"),
            ("class:sidebar.value", f"  {preview}\n\n"),
            ("class:sidebar.label", "  runtime\n"),
            ("class:sidebar.value", f"  {self.mode} · {self.backend} · {model}\n"),
            ("class:sidebar.value", f"  {state} · {last_latency}\n\n"),
            ("class:sidebar.label", "  task\n"),
            ("class:sidebar.value", f"  {task_status} · {task_phase}\n"),
            ("class:sidebar.value", f"  {task_summary}\n\n"),
            ("class:sidebar.label", "  remote\n"),
            ("class:sidebar.value", f"  {bridge.get('mode') or self._transport_mode} · {bridge.get('transport_state') or 'disconnected'}\n"),
            ("class:sidebar.value", f"  {bridge.get('auth_mode') or 'none'} · {bridge.get('transport') or 'memory'}\n\n"),
            ("class:sidebar.label", "  stats\n"),
            ("class:sidebar.value", f"  {usage.get('messages', 0)} msgs · {usage.get('tokens_in', 0)}/{usage.get('tokens_out', 0)} tok\n\n"),
        ]
        return FormattedText(runtime_lines)

    def _get_active_task(self) -> dict[str, Any] | None:
        try:
            from socc.core import task_state as task_state_runtime

            for task in task_state_runtime.list_tasks(limit=20):
                if str(task.session_id) == str(self.session_id):
                    return task.to_dict()
        except Exception:
            return None
        return None

    def _get_bridge_summary(self) -> dict[str, Any]:
        try:
            from socc.core import session_bridge

            for bridge in session_bridge.list_bridges(limit=20):
                if str(bridge.session_id) == str(self.session_id):
                    return bridge.to_dict()
        except Exception:
            pass
        return {
            "session_id": self.session_id,
            "mode": self._transport_mode,
            "transport": "memory",
            "transport_state": "attached" if self._transport_mode == "local" else "disconnected",
            "auth_mode": "none",
        }

    def _append_phase_event(self, phase: str, label: str) -> None:
        self._last_phase = phase or self._last_phase
        rendered = label or phase or "processing"
        self.history.append_line(_dim(f"  · {phase or '-'}  {rendered}"))
        self.history.append_line("")

    def _append_tool_call_event(self, tool_name: str, arguments: dict[str, Any] | None = None) -> None:
        self.history.append_line(_yellow(f"  ⚙ {tool_name or '-'}"))
        if arguments:
            for key, value in list(arguments.items())[:3]:
                rendered = str(value).replace("\n", " ")
                if len(rendered) > 96:
                    rendered = rendered[:96] + "..."
                self.history.append_line(_dim(f"    {key}={rendered}"))
        self.history.append_line("")

    def _append_tool_result_event(self, content: str) -> None:
        preview = str(content or "").strip().replace("\n", " ")
        if len(preview) > 140:
            preview = preview[:140] + "..."
        self.history.append_line(_green(f"  ✓ {preview or '-'}"))
        self.history.append_line("")

    def _append_error_event(self, message: str) -> None:
        rendered = str(message or "").replace("\n", " ")
        self.history.append_line(_red(f"  ✗ {rendered}"))
        self.history.append_line("")

    def _append_transcript_message(
        self,
        role: str,
        content: str,
        *,
        header_detail: str = "",
        footer_detail: str = "",
    ) -> None:
        normalized_role = str(role or "").strip().lower()
        label = "socc"
        color = _green
        if normalized_role in {"user", "human"}:
            label = "operator"
            color = _cyan
        elif normalized_role in {"assistant", "ai"}:
            label = "runtime"
            color = _green
        elif normalized_role in {"system"}:
            label = "system"
            color = _magenta

        rendered_lines = str(content or "").splitlines() or [""]
        header = label
        if header_detail:
            header += f"  {header_detail}"
        self.history.append_line(f"  {_bold(color(header))}")
        self.history.append_line(f"    {rendered_lines[0]}")
        for extra in rendered_lines[1:]:
            self.history.append_line(f"    {extra}")
        if footer_detail:
            self.history.append_line(_dim(f"    {footer_detail}"))
        self.history.append_line("")

    def _get_session_summary(self, session_id: str, limit: int = 40) -> dict[str, Any] | None:
        try:
            from socc.core import storage as storage_runtime

            return storage_runtime.get_chat_session_summary(session_id, limit=limit)
        except Exception:
            return None

    def _resume_session(self, session_id: str, *, render_notice: bool = True) -> bool:
        summary = self._get_session_summary(session_id)
        if summary is None:
            return False

        self.session_id = str(summary.get("session_id") or session_id)
        self.cliente = str(summary.get("cliente") or self.cliente or "")
        self.history.clear()
        self._welcome()
        if render_notice:
            usage = summary.get("usage") or {}
            self.history.append_line(
                _dim(
                    "  Sessão retomada: "
                    f"{self.session_id}  |  "
                    f"mensagens {usage.get('messages', 0)}  |  "
                    f"atualizada {summary.get('updated_at') or '-'}"
                )
            )
            self.history.append_line("")
        for message in summary.get("messages") or []:
            self._append_transcript_message(
                str(message.get("role") or ""),
                str(message.get("content") or ""),
            )
        return True

    # ------------------------------------------------------------------
    # Build layout
    # ------------------------------------------------------------------

    def _build_app(self) -> Application:
        history_area = TextArea(
            text=self.history.get_plain(),
            read_only=True,
            focusable=False,
            scrollbar=True,
            wrap_lines=True,
            style="class:transcript",
        )
        self._history_area = history_area

        history_window = history_area

        sidebar_window = Window(
            content=FormattedTextControl(text=self._sidebar_text),
            wrap_lines=True,
            ignore_content_width=True,
            style="class:sidebar",
        )

        completer = WordCompleter(_slash_surface(), sentence=True, ignore_case=True)

        input_buffer = Buffer(
            name="input",
            completer=completer,
            complete_while_typing=True,
            accept_handler=self._on_submit,
        )
        input_buffer.on_text_changed += lambda _: self._on_input_value_change(input_buffer.text)

        input_control = BufferControl(
            buffer=input_buffer,
            include_default_input_processors=True,
        )

        prompt_window = Window(
            content=FormattedTextControl(
                text=lambda: FormattedText([
                    (
                        "class:prompt.arrow" if not self._input_value.startswith("/") else "class:prompt.slash",
                        " msg " if not self._input_value.startswith("/") else " cmd ",
                    ),
                ])
            ),
            width=6,
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

        command_palette_bar = Window(
            height=2,
            content=FormattedTextControl(text=self._command_palette_text),
            style="class:palette",
        )

        footer_bar = Window(
            height=1,
            content=FormattedTextControl(text=self._footer_bar_text),
            style="class:footer",
        )

        body_split = VSplit(
            [
                HSplit(
                    [history_window],
                    style="class:panel-shell",
                ),
                ConditionalContainer(
                    content=Window(width=1, char="│", style="class:panel-divider"),
                    filter=Condition(lambda: not self._transcript_mode),
                ),
                ConditionalContainer(
                    content=HSplit(
                        [sidebar_window],
                        width=D(preferred=20, min=18, max=22),
                        style="class:sidebar-shell",
                    ),
                    filter=Condition(lambda: not self._transcript_mode),
                ),
            ]
        )

        root_container = FloatContainer(
            content=HSplit([
                chrome_bar,
                body_split,
                Window(height=1, char="─", style="class:divider"),
                composer_header,
                ConditionalContainer(
                    content=command_palette_bar,
                    filter=Condition(lambda: self._show_command_palette()),
                ),
                input_area,
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
            "prompt.slash":                    "#FBBF24 bold",
            "divider":                         "#243140",
            "composer-title":                  "bg:#17202B #94A3B8",
            "composer-title.accent":           "bg:#17202B #FBBF24 bold",
            "composer-title.sep":              "bg:#17202B #334155",
            "composer-title.meta":             "bg:#17202B #94A3B8",
            "palette":                         "bg:#161F2A #B8C6D8",
            "palette.label":                   "bg:#161F2A #67E8F9 bold",
            "palette.key":                     "bg:#161F2A #FBBF24 bold",
            "palette.meta":                    "bg:#161F2A #D6DEE6",
            "palette.sep":                     "bg:#161F2A #334155",
            "palette.warn":                    "bg:#161F2A #FCA5A5 bold",
            "composer":                        "bg:#101823 #E2E8F0",
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

        @kb.add("c-o")
        def _toggle_transcript(event):
            self._toggle_transcript_mode()

        @kb.add("pageup")
        def _page_up(event):
            if self._history_area is None:
                return
            self._history_follow = False
            self._history_area.buffer.cursor_up(count=10)

        @kb.add("pagedown")
        def _page_down(event):
            if self._history_area is None:
                return
            self._history_follow = False
            self._history_area.buffer.cursor_down(count=10)

        @kb.add("home")
        def _home(event):
            if self._history_area is None:
                return
            self._history_follow = False
            self._history_area.buffer.cursor_position = 0

        @kb.add("end")
        def _end(event):
            if self._history_area is None:
                return
            self._history_follow = True
            self._history_area.buffer.cursor_position = len(self.history.get_plain())

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
            self._sync_history_view()
            if app.is_running:
                app.invalidate()

        self.history.subscribe(_refresh)
        self.app = app
        return app

    def _on_input_value_change(self, value: str) -> None:
        self._input_value = value
        if self.app:
            self.app.invalidate()

    def _show_command_palette(self) -> bool:
        return str(self._input_value or "").strip().startswith("/")

    def _toggle_transcript_mode(self) -> None:
        self._transcript_mode = not self._transcript_mode
        if self.app:
            self.app.invalidate()

    def _sync_history_view(self) -> None:
        area = self._history_area
        if area is None:
            return
        text = self.history.get_plain()
        current_pos = area.buffer.cursor_position
        new_pos = len(text) if self._history_follow else min(current_pos, len(text))
        area.buffer.set_document(Document(text=text, cursor_position=new_pos), bypass_readonly=True)

    # ------------------------------------------------------------------
    # Submit handler
    # ------------------------------------------------------------------

    def _on_submit(self, buffer: Buffer) -> None:
        message = buffer.text.strip()
        buffer.reset()
        self._on_input_value_change("")
        self._history_follow = True

        if not message:
            return

        # Echo user message
        self._append_transcript_message("user", message, header_detail=self.session_id[:12])

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
            _render_help_lines(self.history, LOCAL_HELP_LINES)
            is_local_help = arg.lower() in {
                "",
                "mode",
                "backend",
                "model",
                "new",
                "session",
                "resume",
                "clear",
                "help",
                "exit",
                "quit",
            }
            if not is_local_help:
                rendered = _render_harness_help(self.history, arg)
                if not rendered:
                    self.history.append_line(_yellow(f"  ⚠  Sem ajuda disponível para: {arg}"))
                    self.history.append_line("")
            else:
                _render_harness_help(self.history)
            return

        if verb == "/session":
            summary = self._get_session_summary(self.session_id)
            if summary is None:
                self.history.append_line(_dim(f"  sessão: {self.session_id}"))
            else:
                usage = summary.get("usage") or {}
                self.history.append_line(_dim(f"  sessão: {self.session_id}"))
                self.history.append_line(_dim(f"  título: {summary.get('titulo') or '-'}"))
                self.history.append_line(_dim(f"  cliente: {summary.get('cliente') or '-'}"))
                self.history.append_line(
                    _dim(
                        "  uso: "
                        f"mensagens {usage.get('messages', 0)} · "
                        f"tokens_in {usage.get('tokens_in', 0)} · "
                        f"tokens_out {usage.get('tokens_out', 0)}"
                    )
                )
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

        if verb == "/resume":
            if not arg:
                self.history.append_line(_yellow("  ⚠  Use: /resume <session-id>"))
                self.history.append_line("")
                return
            if self._resume_session(arg):
                self.history.append_line(_dim(f"  Sessão ativa → {self.session_id}"))
            else:
                self.history.append_line(_yellow(f"  ⚠  Sessão não encontrada: {arg}"))
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
            from socc.core.harness.runtime import RUNTIME

            result = RUNTIME.dispatch_command(cmd)
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
                async def _consume_stream() -> None:
                    nonlocal skill, content
                    backend_label = BACKEND_ICON.get(self.backend, self.backend)
                    runtime_header = f"runtime  {backend_label}/{self.model or 'auto'}"
                    self.history.append_line(f"  {runtime_header}")
                    parts: list[str] = []

                    async for event in stream_chat_submission_events(
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
                        if event_name == "tool_call":
                            self._append_tool_call_event(
                                str(payload.get("tool") or ""),
                                payload.get("arguments") if isinstance(payload.get("arguments"), dict) else {},
                            )
                            continue
                        if event_name == "tool_result":
                            self._append_tool_result_event(str(payload.get("content") or ""))
                            continue
                        if event_name == "delta":
                            delta = str(payload.get("delta") or "")
                            parts.append(delta)
                            if parts and len(parts) == 1:
                                self.history.append_line(f"  {delta}")
                            else:
                                self.history.append_inline(delta)
                            if self.app:
                                self.app.invalidate()
                            continue
                        if event_name == "final":
                            data = payload
                            if isinstance(data, dict):
                                self.session_id = str(data.get("session_id") or self.session_id)
                                skill = str((data.get("metadata") or {}).get("skill") or data.get("skill") or "")
                                self._last_skill = skill or self._last_skill
                                runtime_info = data.get("runtime") if isinstance(data.get("runtime"), dict) else {}
                                self.model = str(runtime_info.get("model") or data.get("model") or self.model)
                    content = "".join(parts)

                asyncio.run(_consume_stream())

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

                for tool_call in response.get("tool_calls") or []:
                    if isinstance(tool_call, dict):
                        self._append_tool_call_event(
                            str(tool_call.get("tool") or tool_call.get("name") or ""),
                            tool_call.get("arguments") if isinstance(tool_call.get("arguments"), dict) else {},
                        )
                for tool_result in ((response.get("metadata") or {}).get("tool_results") or []):
                    if isinstance(tool_result, dict):
                        self._append_tool_result_event(str(tool_result.get("content") or ""))

                # Render content as assistant card
                self._append_transcript_message(
                    "assistant",
                    content,
                    header_detail=f"{BACKEND_ICON.get(self.backend, self.backend)}/{self.model or 'auto'}",
                    footer_detail=f"skill {skill or '-'}",
                )

        except Exception as exc:
            self._append_error_event(str(exc))

        finally:
            latency = (time() - started) * 1000
            self._last_latency_ms = latency
            meta_parts = [f"{latency:.0f}ms"]
            if skill and skill != "soc-generalist":
                meta_parts.append(f"skill:{skill}")
            self.history.append_line(_dim("  turn  " + "  │  ".join(meta_parts)))
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
            async def _consume_stream() -> None:
                nonlocal sid
                async for event in stream_chat_submission_events(
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
                    elif event_name == "tool_call":
                        print(f"\n  ⚙ {payload.get('tool') or '-'}")
                        print(f"{backend}/{model} › ", end="", flush=True)
                    elif event_name == "tool_result":
                        print(f"\n  ✓ {str(payload.get('content') or '')[:120]}")
                        print(f"{backend}/{model} › ", end="", flush=True)
                    elif event_name == "delta":
                        print(str(payload.get('delta') or ''), end="", flush=True)
                    elif event_name == "final":
                        data = payload
                        if isinstance(data, dict):
                            sid = str(data.get("session_id") or sid)
            asyncio.run(_consume_stream())
            print("\n")
        else:
            response = chat_reply(
                raw, session_id=sid, cliente=cliente,
                response_mode=mode, selected_backend=backend, selected_model=model,
            )
            sid = str(response.get("session_id") or sid)
            for tool_call in response.get("tool_calls") or []:
                if isinstance(tool_call, dict):
                    print(f"  ⚙ tool {tool_call.get('tool') or tool_call.get('name') or '-'}")
            for tool_result in ((response.get("metadata") or {}).get("tool_results") or []):
                if isinstance(tool_result, dict):
                    print(f"  ✓ result {str(tool_result.get('content') or '')[:120]}")
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
