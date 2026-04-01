"""SOCC Plugin System.

Plugins extend the SOCC runtime with additional tools and integrations
(VirusTotal, MISP, OpenCTI, etc.).

Usage::

    from socc.plugins import load_plugin, list_plugins

    # Load a built-in plugin
    plugin = load_plugin("virustotal")
    plugin.register()

    # Or load all available plugins
    for name in list_plugins():
        load_plugin(name).register()

Plugin manifest (``plugin.json`` inside each package)::

    {
        "name": "virustotal",
        "version": "0.1.0",
        "description": "VirusTotal lookup tools",
        "author": "SOCC Team",
        "tools": ["vt_lookup_hash", "vt_lookup_url", "vt_lookup_domain"],
        "requires_env": ["VT_API_KEY"]
    }
"""

from __future__ import annotations

import importlib
import json
import logging
from pathlib import Path
from typing import Any

__all__ = [
    "SOCCPlugin",
    "PluginManifest",
    "PluginLoadError",
    "load_plugin",
    "list_plugins",
    "register_all_plugins",
]

_logger = logging.getLogger(__name__)

_PLUGINS_DIR = Path(__file__).parent
_REGISTRY: dict[str, "SOCCPlugin"] = {}


# ============================================================================
# Exceptions
# ============================================================================


class PluginLoadError(Exception):
    """Raised when a plugin fails to load or register."""


# ============================================================================
# Manifest
# ============================================================================


class PluginManifest:
    """Plugin metadata loaded from ``plugin.json``."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.name: str = data["name"]
        self.version: str = data.get("version", "0.0.0")
        self.description: str = data.get("description", "")
        self.author: str = data.get("author", "")
        self.tools: list[str] = data.get("tools", [])
        self.requires_env: list[str] = data.get("requires_env", [])
        self.enabled: bool = data.get("enabled", True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "tools": self.tools,
            "requires_env": self.requires_env,
            "enabled": self.enabled,
        }

    @classmethod
    def from_file(cls, path: Path) -> "PluginManifest":
        data = json.loads(path.read_text())
        return cls(data)


# ============================================================================
# Base plugin class
# ============================================================================


class SOCCPlugin:
    """Base class for all SOCC plugins.

    Subclass this and implement ``register()`` to add tools to the registry.
    """

    manifest: PluginManifest

    def register(self) -> None:
        """Register this plugin's tools in the global tool registry.

        Override in each plugin package.
        """
        raise NotImplementedError

    def unregister(self) -> None:
        """Remove this plugin's tools from the global tool registry.

        Default implementation unregisters tools listed in the manifest.
        """
        from socc.core.tools_registry import unregister_tool

        for tool_name in self.manifest.tools:
            try:
                unregister_tool(tool_name)
            except Exception:  # noqa: BLE001
                pass

    def check_env(self) -> list[str]:
        """Return list of missing environment variables required by this plugin."""
        import os

        return [v for v in self.manifest.requires_env if not os.environ.get(v)]

    @property
    def name(self) -> str:
        return self.manifest.name

    @property
    def is_configured(self) -> bool:
        return not self.check_env()

    def __repr__(self) -> str:
        configured = "✓" if self.is_configured else "✗"
        return f"<SOCCPlugin {self.name} v{self.manifest.version} {configured}>"


# ============================================================================
# Loader
# ============================================================================


def load_plugin(name: str) -> SOCCPlugin:
    """Load and return a plugin by name.

    First checks the built-in plugins directory, then looks for installed
    packages with the prefix ``socc_plugin_``.

    Args:
        name: Plugin name (e.g. ``"virustotal"``, ``"misp"``).

    Returns:
        Loaded (but not yet registered) ``SOCCPlugin`` instance.

    Raises:
        PluginLoadError: If the plugin cannot be found or loaded.
    """
    if name in _REGISTRY:
        return _REGISTRY[name]

    # Try built-in first
    plugin_pkg = _PLUGINS_DIR / name
    if plugin_pkg.is_dir() and (plugin_pkg / "__init__.py").exists():
        try:
            module = importlib.import_module(f"socc.plugins.{name}")
            plugin: SOCCPlugin = module.PLUGIN
            _REGISTRY[name] = plugin
            _logger.debug("Loaded built-in plugin: %s", name)
            return plugin
        except (ImportError, AttributeError) as exc:
            raise PluginLoadError(f"Failed to load built-in plugin '{name}': {exc}") from exc

    # Try installed package
    try:
        module = importlib.import_module(f"socc_plugin_{name}")
        plugin = module.PLUGIN
        _REGISTRY[name] = plugin
        _logger.debug("Loaded installed plugin: %s", name)
        return plugin
    except ImportError:
        pass

    raise PluginLoadError(
        f"Plugin '{name}' not found. "
        f"Available built-in plugins: {', '.join(list_plugins())}"
    )


def list_plugins(*, include_disabled: bool = False) -> list[str]:
    """Return names of all available built-in plugins."""
    names: list[str] = []
    for pkg_dir in sorted(_PLUGINS_DIR.iterdir()):
        if not pkg_dir.is_dir():
            continue
        if not (pkg_dir / "__init__.py").exists():
            continue
        if pkg_dir.name.startswith("_"):
            continue
        manifest_path = pkg_dir / "plugin.json"
        if not manifest_path.exists():
            continue
        if not include_disabled:
            try:
                manifest = PluginManifest.from_file(manifest_path)
                if not manifest.enabled:
                    continue
            except Exception:  # noqa: BLE001
                continue
        names.append(pkg_dir.name)
    return names


def register_all_plugins(*, skip_unconfigured: bool = True) -> dict[str, bool]:
    """Load and register all available plugins.

    Args:
        skip_unconfigured: If True, plugins with missing env vars are skipped
            (default).  If False, they are registered anyway and will return
            errors at call time.

    Returns:
        Dict of plugin_name → success (True/False).
    """
    results: dict[str, bool] = {}
    for name in list_plugins():
        try:
            plugin = load_plugin(name)
            if skip_unconfigured and not plugin.is_configured:
                missing = plugin.check_env()
                _logger.info(
                    "Skipping plugin '%s' — missing env vars: %s",
                    name,
                    ", ".join(missing),
                )
                results[name] = False
                continue
            plugin.register()
            results[name] = True
            _logger.info("Plugin registered: %s", name)
        except Exception as exc:  # noqa: BLE001
            _logger.warning("Failed to register plugin '%s': %s", name, exc)
            results[name] = False
    return results
