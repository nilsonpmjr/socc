"""
SOCC Tool Registry - SOC-specific tools for security operations.

This module provides SOC-specific tools and integrates with the dynamic tool registry.
The TOOL_REGISTRY in this file is now a proxy to the dynamic registry in tools_registry.py.

For dynamic tool registration, use:
    from socc.core.tools_registry import register_tool, ToolSpec, ParamSpec

v1 Compatibility: The old function-based TOOL_REGISTRY is deprecated but still works.
v2 Recommended: Use tools_registry for new tools.
"""
from __future__ import annotations

import base64
from typing import Any

from socc.core.contracts import ToolExecutionContract
from socc.core import parser as parser_runtime
from socc.core.tools_registry import (
    ToolCategory,
    ToolSpec,
    ParamSpec,
    RiskLevel,
    register_tool,
    invoke_tool as _invoke_tool_v2,
    list_tools as _list_tools_v2,
    TOOL_REGISTRY as DYNAMIC_REGISTRY,
)


# ============================================================================
# Tool Implementations (Handler Functions)
# ============================================================================

def extract_iocs(text: str) -> dict:
    """Extract IOCs (Indicators of Compromise) from text.
    
    Args:
        text: Input text to parse for IOCs
        
    Returns:
        Dictionary with extracted IOCs grouped by type
    """
    return parser_runtime.extract_iocs(text)


def defang(text: str) -> str:
    """Defang potentially malicious URLs and indicators in text.
    
    Replaces dangerous characters to make URLs/IOCs safe for sharing.
    
    Args:
        text: Input text containing URLs/IOCs to defang
        
    Returns:
        Defanged text safe for sharing
    """
    return parser_runtime.defang(text)


def decode_base64(value: str) -> str:
    """Decode a base64-encoded string.
    
    Args:
        value: Base64-encoded string
        
    Returns:
        Decoded string (UTF-8, with replacement for invalid chars)
    """
    raw = base64.b64decode(value)
    return raw.decode("utf-8", errors="replace")


# ============================================================================
# Tool Registration
# ============================================================================

def _register_builtin_tools() -> None:
    """Register built-in SOC tools in the dynamic registry."""
    
    # Extract IOCs
    register_tool(ToolSpec(
        name="extract_iocs",
        description=(
            "Extract Indicators of Compromise (IOCs) from text. "
            "Identifies IPs, domains, URLs, hashes (MD5/SHA1/SHA256), "
            "emails, and other security-relevant indicators."
        ),
        parameters={
            "text": ParamSpec(
                type="string",
                description="Input text to parse for IOCs",
                required=True,
            ),
        },
        handler=extract_iocs,
        category=ToolCategory.IOC,
        risk_level=RiskLevel.LOW,
        tags=["ioc", "threat-intel", "parsing"],
    ))
    
    # Defang
    register_tool(ToolSpec(
        name="defang",
        description=(
            "Defang potentially malicious URLs and indicators. "
            "Replaces :// with [://] and . with [.], making URLs safe "
            "to share without risk of accidental clicks."
        ),
        parameters={
            "text": ParamSpec(
                type="string",
                description="Text containing URLs/IOCs to defang",
                required=True,
            ),
        },
        handler=defang,
        category=ToolCategory.IOC,
        risk_level=RiskLevel.LOW,
        tags=["ioc", "defang", "security"],
    ))
    
    # Decode Base64
    register_tool(ToolSpec(
        name="decode_base64",
        description=(
            "Decode a base64-encoded string. "
            "Commonly used for decoding encoded payloads in security analysis."
        ),
        parameters={
            "value": ParamSpec(
                type="string",
                description="Base64-encoded string to decode",
                required=True,
            ),
        },
        handler=decode_base64,
        category=ToolCategory.UTILITY,
        risk_level=RiskLevel.LOW,
        tags=["decode", "base64", "utility"],
    ))


# Register tools on module import
_register_builtin_tools()


# ============================================================================
# Legacy API (v1 Compatibility)
# ============================================================================

# Legacy TOOL_REGISTRY - acts as a proxy to the dynamic registry
# This provides backward compatibility for code that uses:
#   from socc.core.tools import TOOL_REGISTRY
#   TOOL_REGISTRY["extract_iocs"]
class _LegacyRegistry:
    """Legacy registry wrapper for backward compatibility."""
    
    def __getitem__(self, name: str):
        spec = DYNAMIC_REGISTRY.get(name)
        if spec is None:
            raise KeyError(f"Tool '{name}' not found")
        return spec.handler
    
    def __contains__(self, name: str) -> bool:
        return name in DYNAMIC_REGISTRY
    
    def __iter__(self):
        return iter(sorted(DYNAMIC_REGISTRY.keys()))
    
    def __len__(self) -> int:
        return len(DYNAMIC_REGISTRY)
    
    def keys(self):
        return sorted(DYNAMIC_REGISTRY.keys())


TOOL_REGISTRY = _LegacyRegistry()


def list_tools() -> list[str]:
    """List all registered tool names.
    
    Returns:
        Sorted list of tool names
    """
    return _list_tools_v2()


def invoke_tool(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """Invoke a tool by name with the given arguments.
    
    This function provides backward compatibility with the v1 API,
    returning a dictionary in ToolExecutionContract format.
    
    Args:
        name: Tool name to invoke
        arguments: Arguments to pass to the tool
        
    Returns:
        Dictionary with ok, output, error, arguments fields
    """
    result = _invoke_tool_v2(name, arguments)
    
    # Convert to legacy format
    return ToolExecutionContract(
        name=name,
        ok=result.ok,
        arguments=result.arguments,
        output=result.output,
        error=result.error,
        metadata=result.metadata,
    ).to_dict()


# ============================================================================
# Exports
# ============================================================================

__all__ = [
    # Legacy API (v1)
    "TOOL_REGISTRY",
    "list_tools",
    "invoke_tool",
    
    # Tool implementations (for direct use if needed)
    "extract_iocs",
    "defang",
    "decode_base64",
    
    # Re-export from tools_registry for convenience
    "ToolSpec",
    "ParamSpec",
    "ToolCategory",
    "RiskLevel",
    "register_tool",
    "DYNAMIC_REGISTRY",
]