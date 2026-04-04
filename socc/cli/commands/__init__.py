"""Built-in slash commands layered on top of the harness runtime."""

from socc.core.harness.commands import register_command
from socc.core.harness.models import CommandArg, SOCCommand

from . import case, hunt


def register_builtin_commands() -> None:
    """Register all built-in commands. Safe to call multiple times."""
    case.register()
    hunt.register()
    _register_help()
    _register_tools()
    _register_agents()


def _register_help() -> None:
    from socc.core.harness.commands import COMMAND_REGISTRY

    def _handle_help(args: list[str], ctx: dict) -> str:
        cmd_name = args[0] if args else None
        return COMMAND_REGISTRY.help(cmd_name)

    try:
        register_command(SOCCommand(
            name="help",
            description="Show help for commands",
            handler=_handle_help,
            aliases=["?"],
            arguments=[CommandArg(name="command", required=False, help="Command name")],
        ))
    except ValueError:
        pass  # already registered


def _register_tools() -> None:
    def _handle_tools(args: list[str], ctx: dict) -> str:
        from socc.core.harness.runtime import RUNTIME

        query = " ".join(args).strip()
        records = RUNTIME.list_tool_inventory(query=query, limit=25)
        lines = ["# Available Tools", ""]
        for record in records:
            badge = record.status.value
            lines.append(
                f"  **{record.name}** [{badge}] ({record.category or '-'}) — "
                f"{record.description[:72]}"
            )
        return "\n".join(lines)

    try:
        register_command(SOCCommand(
            name="tools",
            description="List available tools",
            handler=_handle_tools,
            aliases=["t"],
        ))
    except ValueError:
        pass


def _register_agents() -> None:
    def _handle_agents(args: list[str], ctx: dict) -> str:
        from socc.core.harness.runtime import RUNTIME
        query = " ".join(args).strip()
        agents = RUNTIME.list_agent_inventory(query=query, limit=25)
        if not agents:
            return "No agents registered."
        lines = ["# Available Agents", ""]
        for agent in agents:
            lines.append(
                f"  **{agent.name}** [{agent.status.value}] ({agent.specialty}) — "
                f"{agent.description[:72]}"
            )
        return "\n".join(lines)

    try:
        register_command(SOCCommand(
            name="agents",
            description="List available agents",
            handler=_handle_agents,
            aliases=["a"],
        ))
    except ValueError:
        pass
