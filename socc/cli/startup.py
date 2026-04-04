"""Startup bootstrap for the SOCC runtime."""
from __future__ import annotations

import logging
import threading

__all__ = ["startup"]

_logger = logging.getLogger(__name__)
_started = False
_lock = threading.Lock()


def startup(*, block: bool = False, verbose: bool = False) -> threading.Thread:
    """Bootstrap the SOCC runtime in a daemon thread."""
    global _started

    with _lock:
        if _started:
            # Return a dummy finished thread for callers that call .join()
            t = threading.Thread(target=lambda: None, daemon=True)
            t.start()
            t.join()
            return t
        _started = True

    def _run() -> None:
        try:
            # 1. Environment
            from socc.utils.config_loader import load_environment
            load_environment()
            if verbose:
                print("[startup] environment loaded")

            # 2. Core tools (auto-register on import)
            import socc.core.tools      # noqa: F401
            import socc.tools.file      # noqa: F401
            import socc.tools.shell     # noqa: F401
            if verbose:
                from socc.core.tools_registry import list_tools
                print(f"[startup] tools imported: {list_tools()}")

            # 3. Built-in slash-commands
            from socc.cli.commands import register_builtin_commands
            register_builtin_commands()

            # 4. Built-in agents (merges with snapshot)
            from socc.agents import register_builtin_agents
            register_builtin_agents()

            # 5. Plugins (skip unconfigured — no crash if env var missing)
            from socc.plugins import register_all_plugins
            results = register_all_plugins(skip_unconfigured=True)
            loaded = [name for name, ok in results.items() if ok]
            skipped = [name for name, ok in results.items() if not ok]
            if loaded:
                _logger.info("Plugins loaded: %s", ", ".join(loaded))
            if skipped and verbose:
                print(f"[startup] plugins skipped (no env vars): {skipped}")

            # 6. Runtime inventory merge
            from socc.core.harness.runtime import RUNTIME

            RUNTIME.bootstrap()
            if verbose:
                print(f"[startup] runtime: {RUNTIME!r}")
                cmds = [item.name for item in RUNTIME.list_command_inventory(limit=20)]
                agents = [item.name for item in RUNTIME.list_agent_inventory(limit=20)]
                print(f"[startup] commands: {cmds}")
                print(f"[startup] agents: {agents}")

            _logger.info("SOCC startup complete — %s", repr(RUNTIME))

        except Exception:
            _logger.exception("SOCC startup error (non-fatal)")

    t = threading.Thread(target=_run, daemon=True, name="socc-startup")
    t.start()
    if block:
        t.join()
    return t
