from __future__ import annotations

import importlib
from types import ModuleType


def load_server_module() -> ModuleType:
    return importlib.import_module("mcp_server")


def available_entrypoints() -> dict[str, bool]:
    module = load_server_module()
    return {
        "app": hasattr(module, "app"),
        "main": callable(getattr(module, "main", None)),
        "server": hasattr(module, "server"),
    }


def run() -> None:
    module = load_server_module()
    main_fn = getattr(module, "main", None)
    if callable(main_fn):
        main_fn()
        return
    raise RuntimeError("mcp_server.py does not expose a callable main() entrypoint.")
