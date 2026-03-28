"""Interactive prompt helpers for the SOCC CLI.

Uses InquirerPy (arrow-key navigation, space to toggle, enter to confirm)
when available.  Falls back to plain ``input()`` prompts so the CLI never
hard-depends on an optional TUI library.

All functions degrade gracefully when stdin is not a TTY or when
``--no-interactive`` was passed: they return the *default* value silently
so that scripts and JSON pipelines keep working unchanged.
"""

from __future__ import annotations

import getpass
import sys
from pathlib import Path
from typing import Callable, Sequence

# ---------------------------------------------------------------------------
# Optional InquirerPy import
# ---------------------------------------------------------------------------

_HAS_INQUIRER = False
try:
    from InquirerPy import inquirer as _iq
    _HAS_INQUIRER = True
except ModuleNotFoundError:
    _iq = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# TTY / interactive detection
# ---------------------------------------------------------------------------

_FORCE_NON_INTERACTIVE = False


def set_non_interactive(value: bool = True) -> None:
    """Override interactive detection (used by ``--no-interactive``)."""
    global _FORCE_NON_INTERACTIVE
    _FORCE_NON_INTERACTIVE = value


def is_interactive() -> bool:
    """Return *True* when the session can safely prompt the user."""
    if _FORCE_NON_INTERACTIVE:
        return False
    return sys.stdin.isatty() and sys.stdout.isatty()


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
    """Print a step header: ``[3/12] Seleção de Modelos``."""
    if not is_interactive():
        return
    print(f"\n[{number}/{total}] {title}")
    print("-" * (len(title) + len(str(number)) + len(str(total)) + 5))


# ---------------------------------------------------------------------------
# Primitives — InquirerPy when available, plain input() as fallback
# ---------------------------------------------------------------------------

def ask(prompt: str, *, default: str = "", validate: Callable[[str], bool] | None = None) -> str:
    """Open-ended text question."""
    if not is_interactive():
        return default
    if _HAS_INQUIRER:
        try:
            return _iq.text(  # type: ignore[union-attr]
                message=prompt,
                default=default,
                validate=validate or (lambda _: True),
                invalid_message="Valor inválido.",
            ).execute()
        except (EOFError, KeyboardInterrupt):
            return default
    # plain fallback
    suffix = f" [{default}]" if default else ""
    while True:
        try:
            value = input(f"{prompt}{suffix}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return default
        if not value:
            value = default
        if validate and not validate(value):
            print("  Valor inválido. Tente novamente.")
            continue
        return value


def ask_secret(prompt: str) -> str:
    """Masked input for passwords and tokens."""
    if not is_interactive():
        return ""
    if _HAS_INQUIRER:
        try:
            return _iq.secret(message=prompt).execute()  # type: ignore[union-attr]
        except (EOFError, KeyboardInterrupt):
            return ""
    try:
        return getpass.getpass(f"{prompt}: ")
    except (EOFError, KeyboardInterrupt):
        print()
        return ""


def confirm(prompt: str, *, default: bool = True) -> bool:
    """Yes/No confirmation.  Always requires Enter to proceed."""
    if not is_interactive():
        return default
    if _HAS_INQUIRER:
        try:
            # Use select instead of confirm to avoid single-keypress auto-submit
            default_choice = "Sim" if default else "Não"
            choices = ["Sim", "Não"] if default else ["Não", "Sim"]
            result = _iq.select(  # type: ignore[union-attr]
                message=prompt,
                choices=choices,
                default=default_choice,
                pointer=">",
                show_cursor=False,
            ).execute()
            return result == "Sim"
        except (EOFError, KeyboardInterrupt):
            return default
    hint = "S/n" if default else "s/N"
    try:
        value = input(f"{prompt} ({hint}): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return default
    if not value:
        return default
    return value in {"s", "sim", "y", "yes", "1"}


def select(prompt: str, options: Sequence[str], *, default: int = 0) -> str:
    """Single selection with arrow-key navigation (InquirerPy) or numbered list."""
    if not is_interactive():
        return options[default] if options else ""
    if not options:
        return ""
    if _HAS_INQUIRER:
        try:
            return _iq.select(  # type: ignore[union-attr]
                message=prompt,
                choices=list(options),
                default=options[default] if default < len(options) else None,
                pointer=">",
                show_cursor=False,
            ).execute()
        except (EOFError, KeyboardInterrupt):
            return options[default]
    # plain fallback
    print(f"\n{prompt}")
    for idx, opt in enumerate(options):
        marker = ">" if idx == default else " "
        print(f"  {marker} {idx + 1}. {opt}")
    while True:
        try:
            raw = input(f"Escolha [1-{len(options)}] (padrão {default + 1}): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return options[default]
        if not raw:
            return options[default]
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(options):
                return options[idx]
        for opt in options:
            if raw.lower() in opt.lower():
                return opt
        print("  Opção inválida. Tente novamente.")


def checklist(prompt: str, options: Sequence[str], *, defaults: Sequence[bool] | None = None) -> list[str]:
    """Multiple selection with space to toggle, enter to confirm (InquirerPy)."""
    if not is_interactive():
        if defaults:
            return [opt for opt, on in zip(options, defaults) if on]
        return list(options)
    chosen_defaults = list(defaults) if defaults else [True] * len(options)
    if _HAS_INQUIRER:
        choices = [
            {"name": opt, "value": opt, "enabled": chosen_defaults[i]}
            for i, opt in enumerate(options)
        ]
        try:
            return _iq.checkbox(  # type: ignore[union-attr]
                message=prompt,
                choices=choices,
                pointer=">",
                enabled_symbol="x",
                disabled_symbol=" ",
                instruction="(espaço=toggle, enter=confirmar)",
            ).execute()
        except (EOFError, KeyboardInterrupt):
            return [opt for opt, on in zip(options, chosen_defaults) if on]
    # plain fallback
    print(f"\n{prompt}")
    for idx, opt in enumerate(options):
        mark = "x" if chosen_defaults[idx] else " "
        print(f"  [{mark}] {idx + 1}. {opt}")
    raw = ""
    try:
        raw = input("Toggle (números separados por vírgula, Enter para aceitar): ").strip()
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


def ask_path(prompt: str, *, default: str = "", must_exist: bool = False) -> Path | None:
    """Path input with ``~`` expansion, tab-completion (InquirerPy), and existence check."""
    if not is_interactive():
        if default:
            return Path(default).expanduser()
        return None
    if _HAS_INQUIRER:
        try:
            from InquirerPy.validator import PathValidator
            validators = {}
            if must_exist:
                validators = {"validate": PathValidator(message="Caminho não encontrado.")}
            raw = _iq.filepath(  # type: ignore[union-attr]
                message=prompt,
                default=default,
                **validators,
            ).execute()
            if not raw:
                return Path(default).expanduser() if default else None
            return Path(raw).expanduser().resolve()
        except (EOFError, KeyboardInterrupt):
            return Path(default).expanduser() if default else None
        except Exception:
            pass  # fall through to plain input
    # plain fallback
    suffix = f" [{default}]" if default else ""
    while True:
        try:
            raw = input(f"{prompt}{suffix}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return Path(default).expanduser() if default else None
        if not raw:
            raw = default
        if not raw:
            return None
        path = Path(raw).expanduser().resolve()
        if must_exist and not path.exists():
            print(f"  Caminho não encontrado: {path}")
            continue
        return path


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def summary(title: str, items: dict[str, str]) -> None:
    """Print a formatted summary table with automatic secret redaction."""
    if not is_interactive():
        return
    print(f"\n{'=' * 3} {title} {'=' * 3}\n")
    max_key = max((len(k) for k in items), default=0)
    for key, value in items.items():
        display = _redact_value(value) if _should_redact(key) and value else value
        print(f"  {key:<{max_key + 2}} {display}")
    print()


def success(msg: str) -> None:
    print(f"  OK: {msg}")


def warning(msg: str) -> None:
    print(f"  AVISO: {msg}")


def error(msg: str) -> None:
    print(f"  ERRO: {msg}", file=sys.stderr)


def skip(msg: str) -> None:
    print(f"  [pulado] {msg}")
