"""
SOCC Command Registry.

Manages slash-commands (``/case``, ``/hunt``, ``/report``, etc.) that users
can invoke inside the REPL or chat interface.

Attribution: Architecture inspired by instructkr/claude-code (Sigrid Jin).
"""

from __future__ import annotations

import logging
from typing import Any

from .models import CommandResult, SOCCommand

__all__ = [
    "CommandRegistry",
    "get_command",
    "list_commands",
    "register_command",
    "dispatch_command",
]

_logger = logging.getLogger(__name__)


class CommandRegistry:
    """Registry of available slash-commands."""

    def __init__(self) -> None:
        self._commands: dict[str, SOCCommand] = {}
        self._aliases: dict[str, str] = {}  # alias → canonical name

    # ── registration ──────────────────────────────────────────────────

    def register(self, command: SOCCommand) -> None:
        """Register a command (and its aliases)."""
        name = command.name.lower().lstrip("/")
        if name in self._commands:
            raise ValueError(f"Command '/{name}' is already registered")

        self._commands[name] = command

        for alias in command.aliases:
            alias_key = alias.lower().lstrip("/")
            self._aliases[alias_key] = name

        _logger.debug("Registered command /%s", name)

    def unregister(self, name: str) -> bool:
        name = name.lower().lstrip("/")
        cmd = self._commands.pop(name, None)
        if cmd is None:
            return False
        for alias in cmd.aliases:
            self._aliases.pop(alias.lower().lstrip("/"), None)
        return True

    # ── lookup ────────────────────────────────────────────────────────

    def get(self, name: str) -> SOCCommand | None:
        name = name.lower().lstrip("/")
        if name in self._commands:
            return self._commands[name]
        canonical = self._aliases.get(name)
        if canonical:
            return self._commands.get(canonical)
        return None

    def list(self, *, include_hidden: bool = False) -> list[SOCCommand]:
        commands = list(self._commands.values())
        if not include_hidden:
            commands = [c for c in commands if not c.hidden]
        return sorted(commands, key=lambda c: c.name)

    def list_names(self) -> list[str]:
        return sorted(self._commands.keys())

    # ── dispatch ──────────────────────────────────────────────────────

    def dispatch(
        self,
        raw_input: str,
        context: dict[str, Any] | None = None,
    ) -> CommandResult:
        """Parse and dispatch a slash-command string.

        Expects input like ``/case create Phishing Campaign`` where
        ``case`` is the command and ``create Phishing Campaign`` are args.

        Returns:
            CommandResult with output or error.
        """
        raw_input = raw_input.strip()
        if not raw_input.startswith("/"):
            return CommandResult(
                ok=False,
                error="Not a command (must start with /)",
            )

        parts = raw_input[1:].split(maxsplit=1)
        cmd_name = parts[0].lower()
        args_str = parts[1] if len(parts) > 1 else ""

        command = self.get(cmd_name)
        if command is None:
            available = ", ".join(f"/{n}" for n in self.list_names())
            return CommandResult(
                ok=False,
                error=f"Unknown command: /{cmd_name}. Available: {available}",
            )

        try:
            args_list = args_str.split() if args_str else []
            output = command.handler(args_list, context or {})

            if isinstance(output, CommandResult):
                return output
            return CommandResult(ok=True, output=str(output))

        except Exception as exc:  # noqa: BLE001
            _logger.exception("Command /%s failed", cmd_name)
            return CommandResult(
                ok=False,
                error=f"Command /{cmd_name} failed: {type(exc).__name__}: {exc}",
            )

    # ── help ──────────────────────────────────────────────────────────

    def help(self, cmd_name: str | None = None) -> str:
        """Return help text for one command or an overview."""
        if cmd_name:
            command = self.get(cmd_name)
            if command is None:
                return f"Unknown command: /{cmd_name}"
            return command.help_text()

        lines = ["# SOCC Commands", ""]
        for cmd in self.list():
            aliases = ""
            if cmd.aliases:
                aliases = f" ({', '.join('/' + a for a in cmd.aliases)})"
            lines.append(f"  **/{cmd.name}**{aliases} — {cmd.description}")
        lines.append("")
        lines.append("Type `/help <command>` for details.")
        return "\n".join(lines)


# ── Module-level singleton ────────────────────────────────────────────────

COMMAND_REGISTRY = CommandRegistry()


def register_command(command: SOCCommand) -> None:
    """Register a command in the global registry."""
    COMMAND_REGISTRY.register(command)


def get_command(name: str) -> SOCCommand | None:
    """Look up a command by name or alias."""
    return COMMAND_REGISTRY.get(name)


def list_commands(*, include_hidden: bool = False) -> list[SOCCommand]:
    """List all registered commands."""
    return COMMAND_REGISTRY.list(include_hidden=include_hidden)


def dispatch_command(
    raw_input: str,
    context: dict[str, Any] | None = None,
) -> CommandResult:
    """Parse and dispatch a slash-command string."""
    return COMMAND_REGISTRY.dispatch(raw_input, context)
