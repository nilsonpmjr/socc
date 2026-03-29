"""Interactive prompt helpers for the SOCC CLI.

Uses InquirerPy (arrow-key navigation, space to toggle, enter to confirm)
with Rich for styled output when available.
Falls back to plain ``input()`` so the CLI never hard-depends on TUI libs.
"""

from __future__ import annotations

import getpass
import sys
from pathlib import Path
from typing import Callable, Sequence

# ---------------------------------------------------------------------------
# Optional imports
# ---------------------------------------------------------------------------

_HAS_INQUIRER = False
try:
    from InquirerPy import inquirer as _iq
    _HAS_INQUIRER = True
except ModuleNotFoundError:
    _iq = None  # type: ignore[assignment]

_HAS_RICH = False
try:
    from rich.console import Console as _Console
    from rich.theme import Theme as _Theme
    _THEME = _Theme({
        "prompt":   "bold cyan",
        "hint":     "dim",
        "ok":       "bold green",
        "warn":     "bold yellow",
        "err":      "bold red",
        "skip":     "dim",
        "step.num": "bold cyan",
        "step.bar": "cyan",
        "choice":   "white",
        "default":  "dim cyan",
    })
    _con = _Console(theme=_THEME, highlight=False)
    _HAS_RICH = True
except ImportError:
    _con = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# TTY detection
# ---------------------------------------------------------------------------

_FORCE_NON_INTERACTIVE = False


def set_non_interactive(value: bool = True) -> None:
    global _FORCE_NON_INTERACTIVE
    _FORCE_NON_INTERACTIVE = value


def is_interactive() -> bool:
    if _FORCE_NON_INTERACTIVE:
        return False
    return sys.stdin.isatty() and sys.stdout.isatty()


# ---------------------------------------------------------------------------
# Internal print helpers
# ---------------------------------------------------------------------------

def _rprint(markup: str, **kwargs) -> None:
    if _HAS_RICH and _con:
        _con.print(markup, **kwargs)
    else:
        # Strip basic markup tags for plain output
        import re
        plain = re.sub(r"\[/?[^\]]+\]", "", markup)
        print(plain, **kwargs)


def _hint(text: str) -> str:
    """Wrap text in dim style for hints."""
    return f"[hint]{text}[/hint]"


def _label(text: str) -> str:
    return f"[prompt]{text}[/prompt]"


# ---------------------------------------------------------------------------
# InquirerPy style config
# ---------------------------------------------------------------------------

try:
    from InquirerPy.utils import get_style as _get_iq_style
    _IQ_STYLE = _get_iq_style({
        "questionmark":     "#4FC3F7 bold",
        "answermark":       "#4FC3F7 bold",
        "answer":           "#FFFFFF bold",
        "input":            "#FFFFFF",
        "question":         "#4FC3F7 bold",
        "instruction":      "#546E7A italic",
        "long_instruction":  "#546E7A italic",
        "pointer":          "#26C6DA bold",
        "checkbox":         "#26C6DA",
        "separator":        "#546E7A",
        "skipped":          "#546E7A",
        "validator":        "#EF5350",
        "marker":           "#26C6DA bold",
        "fuzzy_prompt":     "#4FC3F7 bold",
        "fuzzy_info":       "#546E7A italic",
        "fuzzy_border":     "#546E7A",
        "fuzzy_match":      "#FFCA28",
        "spinner_pattern":  "#4FC3F7",
        "spinner_text":     "#546E7A",
    })
except Exception:
    _IQ_STYLE = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Redaction helpers
# ---------------------------------------------------------------------------

_REDACT_TOKENS = {"KEY", "TOKEN", "PASS", "SECRET", "PASSWORD", "BEARER"}


def _should_redact(label: str) -> bool:
    upper = label.upper()
    return any(tok in upper for tok in _REDACT_TOKENS)


def _redact_value(value: str) -> str:
    if len(value) <= 8:
        return "****"
    return value[:4] + "*" * (len(value) - 8) + value[-4:]


# ---------------------------------------------------------------------------
# Step header
# ---------------------------------------------------------------------------

def step(number: int, total: int, title: str) -> None:
    if not is_interactive():
        return
    if _HAS_RICH and _con:
        from rich.rule import Rule
        pct = int((number / total) * 100)
        bar_filled = int(pct / 5)
        bar = "█" * bar_filled + "░" * (20 - bar_filled)
        _con.print()
        _con.print(Rule(
            f"[step.num][{number}/{total}][/step.num] [bold white]{title}[/bold white]  "
            f"[step.bar]{bar}[/step.bar] [hint]{pct}%[/hint]",
            style="step.bar",
        ))
    else:
        print(f"\n[{number}/{total}] {title}")
        print("-" * (len(title) + len(str(number)) + len(str(total)) + 5))


# ---------------------------------------------------------------------------
# ask — texto livre
# ---------------------------------------------------------------------------

def ask(
    prompt: str,
    *,
    default: str = "",
    validate: Callable[[str], bool] | None = None,
    hint: str = "",
) -> str:
    if not is_interactive():
        return default

    full_prompt = prompt
    if hint:
        _rprint(f"  {_hint(hint)}")

    if _HAS_INQUIRER:
        try:
            return _iq.text(  # type: ignore[union-attr]
                message=full_prompt,
                default=default,
                validate=validate or (lambda _: True),
                invalid_message="Valor inválido.",
                style=_IQ_STYLE,
                amark="✓",
                qmark="›",
            ).execute()
        except (EOFError, KeyboardInterrupt):
            return default

    # fallback
    suffix = f" [{default}]" if default else ""
    while True:
        try:
            value = input(f"  {prompt}{suffix}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return default
        if not value:
            value = default
        if validate and not validate(value):
            _rprint("  [err]✗[/err]  Valor inválido.")
            continue
        return value


# ---------------------------------------------------------------------------
# ask_secret — input mascarado
# ---------------------------------------------------------------------------

def ask_secret(prompt: str, *, hint: str = "") -> str:
    if not is_interactive():
        return ""

    if hint:
        _rprint(f"  {_hint(hint)}")

    if _HAS_INQUIRER:
        try:
            return _iq.secret(  # type: ignore[union-attr]
                message=prompt,
                style=_IQ_STYLE,
                amark="✓",
                qmark="›",
            ).execute()
        except (EOFError, KeyboardInterrupt):
            return ""

    try:
        return getpass.getpass(f"  {prompt}: ")
    except (EOFError, KeyboardInterrupt):
        print()
        return ""


# ---------------------------------------------------------------------------
# confirm — Sim/Não
# ---------------------------------------------------------------------------

def confirm(prompt: str, *, default: bool = True, hint: str = "") -> bool:
    if not is_interactive():
        return default

    if hint:
        _rprint(f"  {_hint(hint)}")

    if _HAS_INQUIRER:
        try:
            default_choice = "Sim" if default else "Não"
            choices = ["Sim", "Não"] if default else ["Não", "Sim"]
            result = _iq.select(  # type: ignore[union-attr]
                message=prompt,
                choices=choices,
                default=default_choice,
                pointer="›",
                show_cursor=False,
                style=_IQ_STYLE,
                amark="✓",
                qmark="?",
            ).execute()
            return result == "Sim"
        except (EOFError, KeyboardInterrupt):
            return default

    hint_str = "S/n" if default else "s/N"
    try:
        value = input(f"  {prompt} ({hint_str}): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return default
    if not value:
        return default
    return value in {"s", "sim", "y", "yes", "1"}


# ---------------------------------------------------------------------------
# select — escolha única com setas
# ---------------------------------------------------------------------------

def select(
    prompt: str,
    options: Sequence[str],
    *,
    default: int = 0,
    hint: str = "",
) -> str:
    if not is_interactive():
        return options[default] if options else ""
    if not options:
        return ""

    if hint:
        _rprint(f"  {_hint(hint)}")

    if _HAS_INQUIRER:
        try:
            return _iq.select(  # type: ignore[union-attr]
                message=prompt,
                choices=list(options),
                default=options[default] if default < len(options) else None,
                pointer="›",
                show_cursor=False,
                style=_IQ_STYLE,
                amark="✓",
                qmark="›",
                instruction="(↑↓ navegar, Enter confirmar)",
            ).execute()
        except (EOFError, KeyboardInterrupt):
            return options[default]

    # fallback numerado
    _rprint(f"\n  [prompt]{prompt}[/prompt]")
    for idx, opt in enumerate(options):
        marker = "›" if idx == default else " "
        _rprint(f"  [hint]{marker}[/hint] [choice]{idx + 1}. {opt}[/choice]")
    while True:
        try:
            raw = input(f"  Escolha [1-{len(options)}]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return options[default]
        if not raw:
            return options[default]
        if raw.isdigit() and 0 <= int(raw) - 1 < len(options):
            return options[int(raw) - 1]
        _rprint("  [err]✗[/err]  Opção inválida.")


# ---------------------------------------------------------------------------
# checklist — seleção múltipla
# ---------------------------------------------------------------------------

def checklist(
    prompt: str,
    options: Sequence[str],
    *,
    defaults: Sequence[bool] | None = None,
    hint: str = "",
) -> list[str]:
    if not is_interactive():
        if defaults:
            return [opt for opt, on in zip(options, defaults) if on]
        return list(options)

    chosen_defaults = list(defaults) if defaults else [True] * len(options)

    if hint:
        _rprint(f"  {_hint(hint)}")

    if _HAS_INQUIRER:
        choices = [
            {"name": opt, "value": opt, "enabled": chosen_defaults[i]}
            for i, opt in enumerate(options)
        ]
        try:
            return _iq.checkbox(  # type: ignore[union-attr]
                message=prompt,
                choices=choices,
                pointer="›",
                enabled_symbol="◉",
                disabled_symbol="○",
                instruction="(espaço=toggle, Enter=confirmar)",
                style=_IQ_STYLE,
                amark="✓",
                qmark="›",
            ).execute()
        except (EOFError, KeyboardInterrupt):
            return [opt for opt, on in zip(options, chosen_defaults) if on]

    # fallback
    _rprint(f"\n  [prompt]{prompt}[/prompt]")
    for idx, opt in enumerate(options):
        mark = "◉" if chosen_defaults[idx] else "○"
        _rprint(f"  [{mark}] [choice]{idx + 1}. {opt}[/choice]")
    raw = ""
    try:
        raw = input("  Toggle (números, Enter=aceitar): ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
    if raw:
        for part in raw.replace(" ", ",").split(","):
            part = part.strip()
            if part.isdigit():
                idx = int(part) - 1
                if 0 <= idx < len(options):
                    chosen_defaults[idx] = not chosen_defaults[idx]
    return [opt for opt, on in zip(options, chosen_defaults) if on]


# ---------------------------------------------------------------------------
# ask_path — caminho com tab-completion
# ---------------------------------------------------------------------------

def ask_path(
    prompt: str,
    *,
    default: str = "",
    must_exist: bool = False,
    hint: str = "",
) -> Path | None:
    if not is_interactive():
        if default:
            return Path(default).expanduser()
        return None

    if hint:
        _rprint(f"  {_hint(hint)}")

    if _HAS_INQUIRER:
        try:
            from InquirerPy.validator import PathValidator
            validators = {}
            if must_exist:
                validators = {"validate": PathValidator(message="Caminho não encontrado.")}
            raw = _iq.filepath(  # type: ignore[union-attr]
                message=prompt,
                default=default,
                style=_IQ_STYLE,
                amark="✓",
                qmark="›",
                **validators,
            ).execute()
            if not raw:
                return Path(default).expanduser() if default else None
            return Path(raw).expanduser().resolve()
        except (EOFError, KeyboardInterrupt):
            return Path(default).expanduser() if default else None
        except Exception:
            pass

    # fallback
    suffix = f" [{default}]" if default else ""
    while True:
        try:
            raw = input(f"  {prompt}{suffix}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return Path(default).expanduser() if default else None
        if not raw:
            raw = default
        if not raw:
            return None
        path = Path(raw).expanduser().resolve()
        if must_exist and not path.exists():
            _rprint(f"  [err]✗[/err]  Caminho não encontrado: {path}")
            continue
        return path


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def summary(title: str, items: dict[str, str]) -> None:
    if not is_interactive():
        return
    if _HAS_RICH and _con:
        from rich.table import Table
        from rich.panel import Panel
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column(style="dim cyan", no_wrap=True)
        table.add_column(style="white")
        for key, value in sorted(items.items()):
            display = _redact_value(value) if _should_redact(key) and value else value
            table.add_row(key, display)
        _con.print()
        _con.print(Panel(table, title=f"[bold cyan]{title}[/bold cyan]", border_style="cyan"))
    else:
        print(f"\n=== {title} ===\n")
        max_key = max((len(k) for k in items), default=0)
        for key, value in sorted(items.items()):
            display = _redact_value(value) if _should_redact(key) and value else value
            print(f"  {key:<{max_key + 2}} {display}")
        print()


def success(msg: str) -> None:
    _rprint(f"  [ok]✓[/ok]  {msg}")


def warning(msg: str) -> None:
    _rprint(f"  [warn]⚠[/warn]   {msg}")


def error(msg: str) -> None:
    _rprint(f"  [err]✗[/err]  {msg}")


def skip(msg: str) -> None:
    _rprint(f"  [skip]→ {msg}[/skip]")
