"""
Tests for tools_registry.py - Dynamic Tool Registry System.

This test suite covers:
- ToolSpec and ParamSpec dataclasses
- Tool registration and unregistration
- Tool invocation with validation
- JSON Schema generation
- Legacy API compatibility
"""
import pytest
from unittest.mock import MagicMock

from socc.core.tools_registry import (
    ToolCategory,
    RiskLevel,
    ParamSpec,
    ToolSpec,
    ToolResult,
    TOOL_REGISTRY,
    register_tool,
    unregister_tool,
    get_tool,
    list_tools,
    list_tools_specs,
    invoke_tool,
    validate_arguments,
    get_tools_json_schema,
    clear_registry,
    tool,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(autouse=True)
def clean_registry():
    """Clear registry before and after each test.
    
    Note: This fixture is NOT used by TestRealToolsIntegration, which has
    its own fixture that re-registers real tools.
    """
    clear_registry()
    yield
    clear_registry()


@pytest.fixture
def simple_tool_handler():
    """A simple tool handler for testing."""
    def handler(text: str, count: int = 1) -> dict:
        return {"text": text, "count": count}
    return handler


@pytest.fixture
def simple_tool_spec(simple_tool_handler):
    """A simple ToolSpec for testing."""
    return ToolSpec(
        name="test_tool",
        description="A test tool for unit testing",
        parameters={
            "text": ParamSpec(type="string", description="Input text", required=True),
            "count": ParamSpec(type="integer", description="Repeat count", required=False, default=1),
        },
        handler=simple_tool_handler,
        category=ToolCategory.UTILITY,
        risk_level=RiskLevel.LOW,
    )


# ============================================================================
# ParamSpec Tests
# ============================================================================

class TestParamSpec:
    """Tests for ParamSpec dataclass."""
    
    def test_defaults(self):
        """Test default values."""
        spec = ParamSpec()
        assert spec.type == "string"
        assert spec.description == ""
        assert spec.required is True
        assert spec.default is None
        assert spec.enum is None
    
    def test_to_json_schema_minimal(self):
        """Test JSON Schema with minimal fields."""
        spec = ParamSpec(type="string", description="Test param")
        schema = spec.to_json_schema()
        
        assert schema["type"] == "string"
        assert schema["description"] == "Test param"
        assert "enum" not in schema
    
    def test_to_json_schema_with_enum(self):
        """Test JSON Schema with enum values."""
        spec = ParamSpec(
            type="string",
            description="Status",
            enum=["active", "inactive"]
        )
        schema = spec.to_json_schema()
        
        assert schema["enum"] == ["active", "inactive"]
    
    def test_to_json_schema_with_items(self):
        """Test JSON Schema with array items."""
        spec = ParamSpec(
            type="array",
            description="List of items",
            items={"type": "string"}
        )
        schema = spec.to_json_schema()
        
        assert schema["type"] == "array"
        assert schema["items"] == {"type": "string"}


# ============================================================================
# ToolSpec Tests
# ============================================================================

class TestToolSpec:
    """Tests for ToolSpec dataclass."""
    
    def test_to_json_schema(self, simple_tool_spec):
        """Test JSON Schema generation."""
        schema = simple_tool_spec.to_json_schema()
        
        assert schema["name"] == "test_tool"
        assert "test tool" in schema["description"].lower()
        assert "properties" in schema["parameters"]
        assert "text" in schema["parameters"]["properties"]
        assert "count" in schema["parameters"]["properties"]
        assert schema["parameters"]["required"] == ["text"]
    
    def test_to_dict(self, simple_tool_spec):
        """Test dictionary conversion."""
        data = simple_tool_spec.to_dict()
        
        assert data["name"] == "test_tool"
        assert data["category"] == "utility"
        assert data["risk_level"] == "low"
        assert "text" in data["parameters"]
        assert "count" in data["parameters"]


# ============================================================================
# ToolResult Tests
# ============================================================================

class TestToolResult:
    """Tests for ToolResult dataclass."""
    
    def test_success_result(self):
        """Test successful result."""
        result = ToolResult(
            ok=True,
            output={"data": "test"},
            arguments={"text": "hello"},
        )
        
        data = result.to_dict()
        assert data["ok"] is True
        assert data["output"] == {"data": "test"}
        assert "error" not in data
    
    def test_error_result(self):
        """Test error result."""
        result = ToolResult(
            ok=False,
            error="Something went wrong",
            arguments={"text": "hello"},
        )
        
        data = result.to_dict()
        assert data["ok"] is False
        assert data["error"] == "Something went wrong"
        assert "output" not in data
    
    def test_result_with_metadata(self):
        """Test result with metadata."""
        result = ToolResult(
            ok=True,
            output="done",
            arguments={},
            metadata={"elapsed_ms": 42.5},
        )
        
        data = result.to_dict()
        assert data["metadata"]["elapsed_ms"] == 42.5


# ============================================================================
# Registration Tests
# ============================================================================

class TestToolRegistration:
    """Tests for tool registration."""
    
    def test_register_tool(self, simple_tool_spec):
        """Test basic tool registration."""
        register_tool(simple_tool_spec)
        
        assert "test_tool" in TOOL_REGISTRY
        assert TOOL_REGISTRY["test_tool"] == simple_tool_spec
    
    def test_register_duplicate_raises(self, simple_tool_spec):
        """Test that duplicate registration raises error."""
        register_tool(simple_tool_spec)
        
        with pytest.raises(ValueError, match="already registered"):
            register_tool(simple_tool_spec)
    
    def test_unregister_tool(self, simple_tool_spec):
        """Test tool unregistration."""
        register_tool(simple_tool_spec)
        
        result = unregister_tool("test_tool")
        assert result is True
        assert "test_tool" not in TOOL_REGISTRY
    
    def test_unregister_nonexistent(self):
        """Test unregistering non-existent tool."""
        result = unregister_tool("nonexistent")
        assert result is False
    
    def test_get_tool(self, simple_tool_spec):
        """Test getting tool by name."""
        register_tool(simple_tool_spec)
        
        spec = get_tool("test_tool")
        assert spec == simple_tool_spec
        
        spec = get_tool("nonexistent")
        assert spec is None
    
    def test_register_with_missing_handler_params_raises(self):
        """Test that mismatched handler params raises error."""
        def handler(text: str) -> str:
            return text
        
        spec = ToolSpec(
            name="bad_tool",
            description="Bad tool",
            parameters={
                "text": ParamSpec(required=True),
                "missing_param": ParamSpec(required=True),  # Not in handler
            },
            handler=handler,
        )
        
        with pytest.raises(ValueError, match="missing parameters"):
            register_tool(spec)


# ============================================================================
# List Tools Tests
# ============================================================================

class TestListTools:
    """Tests for listing tools."""
    
    def test_list_tools_empty(self):
        """Test listing tools when empty."""
        tools = list_tools()
        assert tools == []
    
    def test_list_tools_basic(self, simple_tool_spec):
        """Test listing tools."""
        register_tool(simple_tool_spec)
        
        tools = list_tools()
        assert tools == ["test_tool"]
    
    def test_list_tools_sorted(self):
        """Test that tools are sorted."""
        def handler_a() -> str:
            return "a"
        def handler_b() -> str:
            return "b"
        def handler_c() -> str:
            return "c"
        
        register_tool(ToolSpec(
            name="zebra_tool",
            description="Z",
            parameters={},
            handler=handler_a,
        ))
        register_tool(ToolSpec(
            name="alpha_tool",
            description="A",
            parameters={},
            handler=handler_b,
        ))
        register_tool(ToolSpec(
            name="middle_tool",
            description="M",
            parameters={},
            handler=handler_c,
        ))
        
        tools = list_tools()
        assert tools == ["alpha_tool", "middle_tool", "zebra_tool"]
    
    def test_list_tools_by_category(self):
        """Test filtering by category."""
        def handler_a() -> str:
            return "a"
        def handler_b() -> str:
            return "b"
        
        register_tool(ToolSpec(
            name="ioc_tool",
            description="IOC tool",
            parameters={},
            handler=handler_a,
            category=ToolCategory.IOC,
        ))
        register_tool(ToolSpec(
            name="file_tool",
            description="File tool",
            parameters={},
            handler=handler_b,
            category=ToolCategory.FILE,
        ))
        
        ioc_tools = list_tools(category=ToolCategory.IOC)
        assert ioc_tools == ["ioc_tool"]
        
        file_tools = list_tools(category=ToolCategory.FILE)
        assert file_tools == ["file_tool"]
    
    def test_list_tools_by_risk_level(self):
        """Test filtering by risk level."""
        def handler_a() -> str:
            return "a"
        def handler_b() -> str:
            return "b"
        
        register_tool(ToolSpec(
            name="safe_tool",
            description="Safe",
            parameters={},
            handler=handler_a,
            risk_level=RiskLevel.LOW,
        ))
        register_tool(ToolSpec(
            name="risky_tool",
            description="Risky",
            parameters={},
            handler=handler_b,
            risk_level=RiskLevel.HIGH,
        ))
        
        low_tools = list_tools(risk_level=RiskLevel.LOW)
        assert low_tools == ["safe_tool"]
        
        high_tools = list_tools(risk_level=RiskLevel.HIGH)
        assert high_tools == ["risky_tool"]
    
    def test_list_tools_by_tags(self):
        """Test filtering by tags."""
        def handler_a() -> str:
            return "a"
        def handler_b() -> str:
            return "b"
        
        register_tool(ToolSpec(
            name="tagged_tool",
            description="Tagged",
            parameters={},
            handler=handler_a,
            tags=["security", "ioc"],
        ))
        register_tool(ToolSpec(
            name="untagged_tool",
            description="Untagged",
            parameters={},
            handler=handler_b,
            tags=[],
        ))
        
        security_tools = list_tools(tags=["security"])
        assert security_tools == ["tagged_tool"]
        
        # All tags must match
        both_tools = list_tools(tags=["security", "ioc"])
        assert both_tools == ["tagged_tool"]
        
        # Partial match fails
        ioc_only = list_tools(tags=["ioc"])
        assert ioc_only == ["tagged_tool"]


# ============================================================================
# Validate Arguments Tests
# ============================================================================

class TestValidateArguments:
    """Tests for argument validation."""
    
    def test_validate_all_required(self, simple_tool_spec):
        """Test validation with all required params."""
        validated, warnings = validate_arguments(
            simple_tool_spec,
            {"text": "hello", "count": 3}
        )
        
        assert validated == {"text": "hello", "count": 3}
        assert warnings == []
    
    def test_validate_with_defaults(self, simple_tool_spec):
        """Test validation using default values."""
        validated, warnings = validate_arguments(
            simple_tool_spec,
            {"text": "hello"}
        )
        
        assert validated == {"text": "hello", "count": 1}
        assert "default" in warnings[0].lower()
    
    def test_validate_missing_required_raises(self, simple_tool_spec):
        """Test that missing required params raises error."""
        with pytest.raises(ValueError, match="Missing required"):
            validate_arguments(simple_tool_spec, {})
    
    def test_validate_unknown_params_warns(self, simple_tool_spec):
        """Test that unknown params generate warnings."""
        validated, warnings = validate_arguments(
            simple_tool_spec,
            {"text": "hello", "unknown": "value"}
        )
        
        assert validated == {"text": "hello", "count": 1}
        assert any("unknown" in w.lower() for w in warnings)


# ============================================================================
# Invoke Tool Tests
# ============================================================================

class TestInvokeTool:
    """Tests for tool invocation."""
    
    def test_invoke_success(self, simple_tool_spec):
        """Test successful tool invocation."""
        register_tool(simple_tool_spec)
        
        result = invoke_tool("test_tool", {"text": "hello", "count": 2})
        
        assert result.ok is True
        assert result.output == {"text": "hello", "count": 2}
        assert result.error == ""
        assert "elapsed_ms" in result.metadata
    
    def test_invoke_with_defaults(self, simple_tool_spec):
        """Test invocation using default values."""
        register_tool(simple_tool_spec)
        
        result = invoke_tool("test_tool", {"text": "test"})
        
        assert result.ok is True
        assert result.output == {"text": "test", "count": 1}
    
    def test_invoke_not_found(self):
        """Test invocation of non-existent tool."""
        result = invoke_tool("nonexistent", {"text": "test"})
        
        assert result.ok is False
        assert "not found" in result.error.lower()
    
    def test_invoke_validation_error(self, simple_tool_spec):
        """Test invocation with validation error."""
        register_tool(simple_tool_spec)
        
        result = invoke_tool("test_tool", {})  # Missing required param
        
        assert result.ok is False
        assert "Validation error" in result.error
    
    def test_invoke_execution_error(self):
        """Test invocation with execution error."""
        def bad_handler(text: str) -> str:
            raise RuntimeError("Something went wrong")
        
        register_tool(ToolSpec(
            name="bad_tool",
            description="Bad tool",
            parameters={"text": ParamSpec(required=True)},
            handler=bad_handler,
        ))
        
        result = invoke_tool("bad_tool", {"text": "test"})
        
        assert result.ok is False
        assert "RuntimeError" in result.error
    
    def test_invoke_with_kwargs(self, simple_tool_spec):
        """Test invocation using kwargs."""
        register_tool(simple_tool_spec)
        
        result = invoke_tool("test_tool", text="hello", count=3)
        
        assert result.ok is True
        assert result.output == {"text": "hello", "count": 3}


# ============================================================================
# JSON Schema Tests
# ============================================================================

class TestGetToolsJsonSchema:
    """Tests for JSON Schema generation."""
    
    def test_empty_registry(self):
        """Test with empty registry."""
        schemas = get_tools_json_schema()
        assert schemas == []
    
    def test_single_tool(self, simple_tool_spec):
        """Test with single tool."""
        register_tool(simple_tool_spec)
        
        schemas = get_tools_json_schema()
        
        assert len(schemas) == 1
        assert schemas[0]["name"] == "test_tool"
        assert "parameters" in schemas[0]
    
    def test_multiple_tools(self, simple_tool_spec):
        """Test with multiple tools."""
        register_tool(simple_tool_spec)
        
        def handler2() -> str:
            return "b"
        
        register_tool(ToolSpec(
            name="another_tool",
            description="Another",
            parameters={},
            handler=handler2,
        ))
        
        schemas = get_tools_json_schema()
        
        assert len(schemas) == 2
        names = [s["name"] for s in schemas]
        assert "test_tool" in names
        assert "another_tool" in names


# ============================================================================
# Decorator Tests
# ============================================================================

class TestToolDecorator:
    """Tests for the @tool decorator."""
    
    def test_basic_decorator(self):
        """Test basic decorator usage."""
        @tool("my_tool", "Does something")
        def my_tool(text: str) -> str:
            return text.upper()
        
        assert "my_tool" in TOOL_REGISTRY
        spec = get_tool("my_tool")
        assert spec.description == "Does something"
        
        result = invoke_tool("my_tool", {"text": "hello"})
        assert result.ok is True
        assert result.output == "HELLO"
    
    def test_decorator_infers_name(self):
        """Test that decorator infers name from function."""
        @tool()
        def auto_named(text: str) -> str:
            return text
        
        assert "auto_named" in TOOL_REGISTRY
    
    def test_decorator_with_params(self):
        """Test decorator with parameter specs."""
        @tool(
            "param_tool",
            "Tool with params",
            text={"type": "string", "description": "Input", "required": True},
            count={"type": "integer", "description": "Count", "required": False},
        )
        def param_tool(text: str, count: int = 1) -> dict:
            return {"text": text, "count": count}
        
        spec = get_tool("param_tool")
        assert "text" in spec.parameters
        assert spec.parameters["text"].required is True
        assert spec.parameters["count"].required is False
    
    def test_decorator_with_category_and_risk(self):
        """Test decorator with category and risk level."""
        @tool("cat_tool", "Categorized", category=ToolCategory.IOC, risk_level=RiskLevel.HIGH)
        def cat_tool(text: str) -> str:
            return text
        
        spec = get_tool("cat_tool")
        assert spec.category == ToolCategory.IOC
        assert spec.risk_level == RiskLevel.HIGH


# ============================================================================
# Clear Registry Tests
# ============================================================================

class TestClearRegistry:
    """Tests for registry clearing."""
    
    def test_clear_removes_all(self, simple_tool_spec):
        """Test that clear removes all tools."""
        register_tool(simple_tool_spec)
        assert len(TOOL_REGISTRY) > 0
        
        clear_registry()
        
        assert len(TOOL_REGISTRY) == 0


# ============================================================================
# ToolCategory and RiskLevel Tests
# ============================================================================

class TestEnums:
    """Tests for category and risk level enums."""
    
    def test_tool_category_values(self):
        """Test ToolCategory enum values."""
        assert ToolCategory.IOC.value == "ioc"
        assert ToolCategory.FILE.value == "file"
        assert ToolCategory.SHELL.value == "shell"
        assert ToolCategory.NETWORK.value == "network"
        assert ToolCategory.THREAT_INTEL.value == "threat_intel"
        assert ToolCategory.UTILITY.value == "utility"
        assert ToolCategory.SYSTEM.value == "system"
    
    def test_risk_level_values(self):
        """Test RiskLevel enum values."""
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.MEDIUM.value == "medium"
        assert RiskLevel.HIGH.value == "high"


# ============================================================================
# Integration Tests with Real Tools
# ============================================================================

class TestRealToolsIntegration:
    """Integration tests with actual SOC tools."""
    
    @pytest.fixture(autouse=True)
    def _setup_real_tools(self):
        """Register real tools before each integration test.

        Unlike unit tests, integration tests need the actual SOC tools registered.
        We clear and re-register to ensure a clean state.
        """
        from socc.core.tools_registry import clear_registry
        from socc.core.tools import register_builtin_tools
        clear_registry()
        register_builtin_tools()
        yield
        clear_registry()
    
    def test_tools_module_imports(self):
        """Test that tools module can be imported."""
        from socc.core.tools import (
            TOOL_REGISTRY,
            list_tools,
            invoke_tool,
            extract_iocs,
            defang,
            decode_base64,
        )
        
        # Should have the built-in tools registered
        tools = list_tools()
        assert "extract_iocs" in tools
        assert "defang" in tools
        assert "decode_base64" in tools
    
    def test_extract_iocs_invocation(self):
        """Test invoking extract_iocs through registry."""
        from socc.core.tools import invoke_tool
        
        result = invoke_tool("extract_iocs", {"text": "Malicious IP: 192.168.1.1"})
        assert result["ok"] is True
        assert result["output"] is not None
    
    def test_defang_invocation(self):
        """Test invoking defang through registry."""
        from socc.core.tools import invoke_tool
        
        result = invoke_tool("defang", {"text": "http://evil.com/malware"})
        assert result["ok"] is True
        # Should defang the URL
        assert "[://" in result["output"] or "[.]" in result["output"]
    
    def test_decode_base64_invocation(self):
        """Test invoking decode_base64 through registry."""
        from socc.core.tools import invoke_tool
        import base64
        
        encoded = base64.b64encode(b"hello world").decode()
        result = invoke_tool("decode_base64", {"value": encoded})
        
        assert result["ok"] is True
        assert result["output"] == "hello world"


# ============================================================================
# Concurrency Tests
# ============================================================================

class TestConcurrency:
    """Tests for thread safety (basic checks)."""
    
    def test_sequential_registrations(self):
        """Test sequential registrations work correctly."""
        def make_handler(n):
            def handler() -> int:
                return n
            return handler
        
        for i in range(10):
            register_tool(ToolSpec(
                name=f"tool_{i}",
                description=f"Tool {i}",
                parameters={},
                handler=make_handler(i),
            ))
        
        assert len(TOOL_REGISTRY) == 10
        
        for i in range(10):
            result = invoke_tool(f"tool_{i}", {})
            assert result.ok is True
            assert result.output == i