"""
Dynamic Tool Registry for SOCC.

This module provides a flexible, extensible system for registering and invoking
tools in the SOCC harness. Inspired by pi-coding-agent's tool system.

Usage:
    from socc.core.tools_registry import register_tool, invoke_tool, list_tools

    # Define a tool
    def my_tool(text: str) -> str:
        return text.upper()

    # Register it
    register_tool(ToolSpec(
        name="my_tool",
        description="Converts text to uppercase",
        parameters={"text": ParamSpec(type="string", description="Input text", required=True)},
        handler=my_tool,
        category="utility",
        risk_level="low",
    ))

    # Invoke it
    result = invoke_tool("my_tool", {"text": "hello"})
"""
from __future__ import annotations

import inspect
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable


class ToolCategory(str, Enum):
    """Categories for organizing tools."""
    IOC = "ioc"              # IOC processing (extract, defang, enrich)
    FILE = "file"            # File operations (read, write, edit)
    SHELL = "shell"          # Shell commands (bash, grep, find)
    NETWORK = "network"      # Network operations (http_get, dns_lookup)
    THREAT_INTEL = "threat_intel"  # Threat intelligence (mitre, virustotal)
    UTILITY = "utility"     # General utilities
    SYSTEM = "system"        # System operations


class RiskLevel(str, Enum):
    """Risk levels for tools. Higher risk tools may require approval."""
    LOW = "low"          # Safe to run automatically
    MEDIUM = "medium"    # Should be logged
    HIGH = "high"        # Requires explicit approval


@dataclass(slots=True)
class ParamSpec:
    """Specification for a tool parameter.
    
    Attributes:
        type: JSON Schema type (string, number, integer, boolean, array, object)
        description: Human-readable description
        required: Whether this parameter is required
        default: Default value if not provided
        enum: Allowed values (for enum types)
        items: Schema for array items
        properties: Schema for object properties
    """
    type: str = "string"
    description: str = ""
    required: bool = True
    default: Any = None
    enum: list[str] | None = None
    items: dict[str, Any] | None = None
    properties: dict[str, Any] | None = None

    def to_json_schema(self) -> dict[str, Any]:
        """Convert to JSON Schema format for LLM tool calling."""
        schema: dict[str, Any] = {
            "type": self.type,
            "description": self.description,
        }
        if self.enum:
            schema["enum"] = self.enum
        if self.items:
            schema["items"] = self.items
        if self.properties:
            schema["properties"] = self.properties
        return schema


@dataclass(slots=True)
class ToolSpec:
    """Specification for a registered tool.
    
    Attributes:
        name: Unique identifier for the tool
        description: Human-readable description for LLM context
        parameters: Parameter specifications
        handler: Callable that implements the tool
        category: Tool category for organization
        risk_level: Risk level for approval gating
        requires_auth: Whether authentication is required
        timeout_seconds: Maximum execution time
        example: Example usage for documentation
        tags: Additional tags for search/filtering
    """
    name: str
    description: str
    parameters: dict[str, ParamSpec]
    handler: Callable[..., Any]
    category: ToolCategory = ToolCategory.UTILITY
    risk_level: RiskLevel = RiskLevel.LOW
    requires_auth: bool = False
    timeout_seconds: float = 30.0
    example: str | None = None
    tags: list[str] = field(default_factory=list)

    def to_json_schema(self) -> dict[str, Any]:
        """Convert to JSON Schema format for LLM tool calling."""
        properties = {}
        required = []
        
        for param_name, param_spec in self.parameters.items():
            properties[param_name] = param_spec.to_json_schema()
            if param_spec.required:
                required.append(param_name)
        
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                name: {
                    "type": spec.type,
                    "description": spec.description,
                    "required": spec.required,
                    "default": spec.default,
                }
                for name, spec in self.parameters.items()
            },
            "category": self.category.value,
            "risk_level": self.risk_level.value,
            "requires_auth": self.requires_auth,
            "timeout_seconds": self.timeout_seconds,
            "example": self.example,
            "tags": self.tags,
        }


@dataclass(slots=True)
class ToolResult:
    """Result from a tool invocation.
    
    Attributes:
        ok: Whether the invocation succeeded
        output: The tool's output (if successful)
        error: Error message (if failed)
        arguments: The arguments that were passed
        metadata: Additional metadata (timing, etc.)
    """
    ok: bool
    output: Any = None
    error: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "ok": self.ok,
            "arguments": self.arguments,
        }
        if self.ok:
            result["output"] = self.output
        else:
            result["error"] = self.error
        if self.metadata:
            result["metadata"] = self.metadata
        return result


# Global registry - mutable dict for dynamic registration
TOOL_REGISTRY: dict[str, ToolSpec] = {}


def register_tool(spec: ToolSpec) -> None:
    """Register a tool in the global registry.
    
    Args:
        spec: Tool specification to register
        
    Raises:
        ValueError: If tool name is already registered
    """
    if spec.name in TOOL_REGISTRY:
        raise ValueError(f"Tool '{spec.name}' is already registered")
    
    # Validate handler signature matches parameters
    sig = inspect.signature(spec.handler)
    handler_params = set(sig.parameters.keys())
    spec_params = set(spec.parameters.keys())
    
    # Check for missing required parameters in handler
    missing_in_handler = spec_params - handler_params
    if missing_in_handler:
        raise ValueError(
            f"Tool '{spec.name}' handler missing parameters: {missing_in_handler}"
        )
    
    TOOL_REGISTRY[spec.name] = spec


def unregister_tool(name: str) -> bool:
    """Remove a tool from the registry.
    
    Args:
        name: Tool name to unregister
        
    Returns:
        True if tool was removed, False if not found
    """
    if name in TOOL_REGISTRY:
        del TOOL_REGISTRY[name]
        return True
    return False


def get_tool(name: str) -> ToolSpec | None:
    """Get a tool specification by name.
    
    Args:
        name: Tool name to look up
        
    Returns:
        ToolSpec if found, None otherwise
    """
    return TOOL_REGISTRY.get(name)


def list_tools(
    category: ToolCategory | None = None,
    risk_level: RiskLevel | None = None,
    tags: list[str] | None = None,
) -> list[str]:
    """List registered tools, optionally filtered.
    
    Args:
        category: Filter by category
        risk_level: Filter by risk level
        tags: Filter by tags (tools must have ALL specified tags)
        
    Returns:
        Sorted list of tool names matching filters
    """
    tools = []
    
    for name, spec in TOOL_REGISTRY.items():
        # Filter by category
        if category is not None and spec.category != category:
            continue
        
        # Filter by risk level
        if risk_level is not None and spec.risk_level != risk_level:
            continue
        
        # Filter by tags (must have ALL specified tags)
        if tags is not None:
            spec_tags = set(spec.tags)
            if not all(t in spec_tags for t in tags):
                continue
        
        tools.append(name)
    
    return sorted(tools)


def list_tools_specs(
    category: ToolCategory | None = None,
    risk_level: RiskLevel | None = None,
) -> list[ToolSpec]:
    """List tool specifications, optionally filtered.
    
    Args:
        category: Filter by category
        risk_level: Filter by risk level
        
    Returns:
        List of ToolSpec objects matching filters
    """
    names = list_tools(category=category, risk_level=risk_level)
    return [TOOL_REGISTRY[name] for name in names]


def validate_arguments(
    spec: ToolSpec,
    arguments: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """Validate and apply defaults to tool arguments.
    
    Args:
        spec: Tool specification
        arguments: Provided arguments
        
    Returns:
        Tuple of (validated arguments, list of warnings)
    """
    validated = {}
    warnings = []
    
    # Check required parameters
    for param_name, param_spec in spec.parameters.items():
        if param_name not in arguments:
            if param_spec.required and param_spec.default is None:
                raise ValueError(f"Missing required parameter: {param_name}")
            if param_spec.default is not None:
                validated[param_name] = param_spec.default
                warnings.append(f"Using default value for '{param_name}': {param_spec.default}")
        else:
            validated[param_name] = arguments[param_name]
    
    # Check for unknown parameters
    unknown = set(arguments.keys()) - set(spec.parameters.keys())
    if unknown:
        warnings.append(f"Unknown parameters ignored: {unknown}")
    
    return validated, warnings


def invoke_tool(
    name: str,
    arguments: dict[str, Any] | None = None,
    **kwargs: Any,
) -> ToolResult:
    """Invoke a registered tool by name.
    
    Args:
        name: Tool name to invoke
        arguments: Arguments to pass to the tool
        **kwargs: Alternative way to pass arguments
        
    Returns:
        ToolResult with success status and output/error
        
    Example:
        >>> result = invoke_tool("extract_iocs", {"text": "1.2.3.4"})
        >>> result.ok
        True
        >>> result.output
        {"ips": ["1.2.3.4"], ...}
    """
    import time
    
    # Merge arguments from dict and kwargs
    payload = {**(arguments or {}), **kwargs}
    
    # Look up tool
    spec = TOOL_REGISTRY.get(name)
    if spec is None:
        return ToolResult(
            ok=False,
            error=f"Tool '{name}' not found in registry. Available: {list_tools()}",
            arguments=payload,
        )
    
    try:
        # Validate arguments
        validated, _ = validate_arguments(spec, payload)
        
        # Execute with timeout handling
        start_time = time.time()
        
        output = spec.handler(**validated)
        
        elapsed_ms = (time.time() - start_time) * 1000
        
        return ToolResult(
            ok=True,
            output=output,
            arguments=validated,
            metadata={"elapsed_ms": elapsed_ms},
        )
        
    except ValueError as e:
        # Validation error
        return ToolResult(
            ok=False,
            error=f"Validation error: {e}",
            arguments=payload,
        )
        
    except Exception as e:
        # Execution error
        return ToolResult(
            ok=False,
            error=f"Execution error: {type(e).__name__}: {e}",
            arguments=payload,
        )


def get_tools_json_schema() -> list[dict[str, Any]]:
    """Get JSON Schema for all registered tools (for LLM tool calling).
    
    Returns:
        List of tool schemas in OpenAI function calling format
    """
    return [spec.to_json_schema() for spec in TOOL_REGISTRY.values()]


def clear_registry() -> None:
    """Clear all tools from the registry.
    
    Useful for testing.
    """
    TOOL_REGISTRY.clear()


# Decorator for easy tool registration
def tool(
    name: str | None = None,
    description: str = "",
    category: ToolCategory = ToolCategory.UTILITY,
    risk_level: RiskLevel = RiskLevel.LOW,
    requires_auth: bool = False,
    timeout_seconds: float = 30.0,
    **param_specs: dict[str, Any],
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to register a function as a tool.
    
    Args:
        name: Tool name (defaults to function name)
        description: Tool description
        category: Tool category
        risk_level: Risk level
        requires_auth: Whether auth is required
        timeout_seconds: Execution timeout
        **param_specs: Parameter specifications
        
    Returns:
        Decorator function
        
    Example:
        >>> @tool("my_tool", "Does something", text={"type": "string", "description": "Input"})
        ... def my_tool(text: str) -> str:
        ...     return text.upper()
    """
    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        tool_name = name or fn.__name__
        tool_description = description or fn.__doc__ or ""
        
        # Build parameter specs from decorator args and function signature
        sig = inspect.signature(fn)
        parameters = {}
        
        for param_name, param in sig.parameters.items():
            # Skip *args and **kwargs
            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue
            
            # Use decorator specs if provided, otherwise infer
            if param_name in param_specs:
                spec_data = param_specs[param_name]
                parameters[param_name] = ParamSpec(
                    type=spec_data.get("type", "string"),
                    description=spec_data.get("description", ""),
                    required=spec_data.get("required", param.default is inspect.Parameter.empty),
                    default=None if param.default is inspect.Parameter.empty else param.default,
                )
            else:
                # Infer from signature
                parameters[param_name] = ParamSpec(
                    type="string",  # Default to string
                    description="",
                    required=param.default is inspect.Parameter.empty,
                    default=None if param.default is inspect.Parameter.empty else param.default,
                )
        
        # Create and register spec
        spec = ToolSpec(
            name=tool_name,
            description=tool_description,
            parameters=parameters,
            handler=fn,
            category=category,
            risk_level=risk_level,
            requires_auth=requires_auth,
            timeout_seconds=timeout_seconds,
        )
        
        register_tool(spec)
        
        return fn
    
    return decorator