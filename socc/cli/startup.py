"""SOCC startup bootstrap.

Call ``startup()`` once before launching the TUI or any interactive session.
It runs in a daemon thread so the CLI opens immediately without blocking.

Usage::

    from socc.cli.startup import startup
    startup()          # non-blocking — returns Thread
    startup(block=True)  # blocking — wait for completion (tests / CLI --verbose)
"""
from __future__ import annotations

import logging
import threading

__all__ = ["startup"]

_logger = logging.getLogger(__name__)
_started = False
_lock = threading.Lock()


def startup(*, block: bool = False, verbose: bool = False) -> threading.Thread:
    """Bootstrap the SOCC runtime in a daemon thread.

    Idempotent: a second call returns immediately without re-running the bootstrap.

    Order:
        1. load_environment()         — ~/.socc/.env → os.environ
        2. RUNTIME.bootstrap()        — agents snapshot + logging
        3. register_builtin_commands()— /case /hunt /tools /agents /help
        4. register_builtin_agents()  — SOC_ANALYST, IR_AGENT, THREAT_HUNT
        5. register_all_plugins()     — VT / MISP / OpenCTI if env vars present
    """
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

            # 2. Runtime bootstrap
            from socc.core.harness.runtime import RUNTIME
            RUNTIME.bootstrap()
            if verbose:
                print(f"[startup] runtime: {RUNTIME!r}")

            # 3. Built-in slash-commands
            from socc.cli.commands import register_builtin_commands
            register_builtin_commands()
            if verbose:
                cmds = [c.name for c in RUNTIME.list_commands()]
                print(f"[startup] commands: {cmds}")

            # 4. Built-in agents (merges with snapshot)
            from socc.agents import register_builtin_agents
            register_builtin_agents()
            if verbose:
                agents = [a.name for a in RUNTIME.list_agents()]
                print(f"[startup] agents: {agents}")

            # 4b. Core tools (auto-register on import)
            import socc.core.tools      # extract_iocs, defang, decode_base64
            import socc.tools.file      # read, write, edit
            import socc.tools.shell     # bash
            if verbose:
                from socc.core.tools_registry import list_tools
                print(f"[startup] tools: {list_tools()}")

            # 5. Plugins (skip unconfigured — no crash if env var missing)
            from socc.plugins import register_all_plugins
            results = register_all_plugins(skip_unconfigured=True)
            loaded = [name for name, ok in results.items() if ok]
            skipped = [name for name, ok in results.items() if not ok]
            if loaded:
                _logger.info("Plugins loaded: %s", ", ".join(loaded))
            if skipped and verbose:
                print(f"[startup] plugins skipped (no env vars): {skipped}")

            _logger.info("SOCC startup complete — %s", repr(RUNTIME))

        except Exception:
            _logger.exception("SOCC startup error (non-fatal)")

    t = threading.Thread(target=_run, daemon=True, name="socc-startup")
    t.start()
    if block:
        t.join()
    return t
