"""Tests for the SOCC plugin system (CC-017 to CC-020).

All external API calls are mocked — no real network access required.
"""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from socc.core.tools_registry import clear_registry, get_tool, invoke_tool, list_tools
from socc.plugins import (
    PluginLoadError,
    PluginManifest,
    SOCCPlugin,
    list_plugins,
    load_plugin,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_registry():
    """Ensure each test starts with an empty tool registry."""
    clear_registry()
    yield
    clear_registry()


# ===========================================================================
# Plugin system (CC-017)
# ===========================================================================

class TestPluginManifest:
    def test_load_virustotal_manifest(self):
        from socc.plugins.virustotal import _MANIFEST
        assert _MANIFEST.name == "virustotal"
        assert "vt_lookup_hash" in _MANIFEST.tools
        assert "VT_API_KEY" in _MANIFEST.requires_env

    def test_load_misp_manifest(self):
        from socc.plugins.misp import _MANIFEST
        assert _MANIFEST.name == "misp"
        assert "misp_search" in _MANIFEST.tools
        assert "MISP_URL" in _MANIFEST.requires_env
        assert "MISP_API_KEY" in _MANIFEST.requires_env

    def test_load_opencti_manifest(self):
        from socc.plugins.opencti import _MANIFEST
        assert _MANIFEST.name == "opencti"
        assert "opencti_search" in _MANIFEST.tools
        assert "OPENCTI_URL" in _MANIFEST.requires_env

    def test_manifest_to_dict(self):
        from socc.plugins.virustotal import _MANIFEST
        d = _MANIFEST.to_dict()
        assert d["name"] == "virustotal"
        assert isinstance(d["tools"], list)
        assert isinstance(d["requires_env"], list)


class TestListPlugins:
    def test_built_in_plugins_found(self):
        plugins = list_plugins()
        assert "virustotal" in plugins
        assert "misp" in plugins
        assert "opencti" in plugins

    def test_returns_list(self):
        assert isinstance(list_plugins(), list)


class TestLoadPlugin:
    def test_load_virustotal(self):
        plugin = load_plugin("virustotal")
        assert plugin.name == "virustotal"

    def test_load_misp(self):
        plugin = load_plugin("misp")
        assert plugin.name == "misp"

    def test_load_opencti(self):
        plugin = load_plugin("opencti")
        assert plugin.name == "opencti"

    def test_load_unknown_raises(self):
        with pytest.raises(PluginLoadError, match="not found"):
            load_plugin("nonexistent_plugin_xyz")

    def test_cached_on_second_load(self):
        p1 = load_plugin("virustotal")
        p2 = load_plugin("virustotal")
        assert p1 is p2


class TestPluginConfigCheck:
    def test_unconfigured_without_env(self):
        plugin = load_plugin("virustotal")
        # No VT_API_KEY in env
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("VT_API_KEY", None)
            missing = plugin.check_env()
            assert "VT_API_KEY" in missing

    def test_configured_with_env(self):
        plugin = load_plugin("virustotal")
        with patch.dict(os.environ, {"VT_API_KEY": "fake-key"}):
            assert plugin.is_configured

    def test_repr_shows_configured(self):
        plugin = load_plugin("virustotal")
        with patch.dict(os.environ, {"VT_API_KEY": "fake-key"}):
            assert "✓" in repr(plugin)

    def test_repr_shows_unconfigured(self):
        plugin = load_plugin("virustotal")
        env = {k: v for k, v in os.environ.items() if k != "VT_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            assert "✗" in repr(plugin)


# ===========================================================================
# VirusTotal plugin (CC-018)
# ===========================================================================

class TestVirusTotalRegistration:
    def test_register_adds_tools(self):
        plugin = load_plugin("virustotal")
        plugin.register()
        tools = list_tools()
        assert "vt_lookup_hash" in tools
        assert "vt_lookup_url" in tools
        assert "vt_lookup_domain" in tools

    def test_register_idempotent(self):
        plugin = load_plugin("virustotal")
        plugin.register()
        plugin.register()  # second call should not raise
        assert "vt_lookup_hash" in list_tools()

    def test_unregister_removes_tools(self):
        plugin = load_plugin("virustotal")
        plugin.register()
        plugin.unregister()
        assert "vt_lookup_hash" not in list_tools()

    def test_tool_specs(self):
        from socc.core.tools_registry import RiskLevel, ToolCategory
        plugin = load_plugin("virustotal")
        plugin.register()
        spec = get_tool("vt_lookup_hash")
        assert spec is not None
        assert spec.category == ToolCategory.THREAT_INTEL
        assert spec.risk_level == RiskLevel.LOW


class TestVirusTotalHashLookup:
    def setup_method(self):
        from socc.plugins.virustotal import VirusTotalPlugin
        self.plugin = load_plugin("virustotal")
        self.plugin.register()

    def test_invalid_hash_returns_error(self):
        result = invoke_tool("vt_lookup_hash", {"hash_value": "not-a-hash"})
        assert result.ok
        assert "error" in result.output
        assert result.output.get("found") is False

    def test_valid_hash_mocked(self):
        mock_response = {
            "data": {
                "attributes": {
                    "type_description": "PE32 executable",
                    "size": 12345,
                    "names": ["malware.exe"],
                    "last_analysis_stats": {
                        "malicious": 45, "suspicious": 2,
                        "undetected": 15, "harmless": 0,
                    },
                }
            }
        }
        with patch("socc.plugins.virustotal._vt_get", return_value=mock_response):
            result = invoke_tool(
                "vt_lookup_hash",
                {"hash_value": "d41d8cd98f00b204e9800998ecf8427e"},
            )
        assert result.ok
        assert result.output["found"] is True
        assert result.output["malicious"] == 45
        assert result.output["detection_ratio"] == "45/62"
        assert "permalink" in result.output

    def test_hash_not_found(self):
        with patch("socc.plugins.virustotal._vt_get", side_effect=RuntimeError("404")):
            result = invoke_tool(
                "vt_lookup_hash",
                {"hash_value": "d41d8cd98f00b204e9800998ecf8427e"},
            )
        assert result.ok
        assert result.output["found"] is False


class TestVirusTotalURLLookup:
    def setup_method(self):
        self.plugin = load_plugin("virustotal")
        self.plugin.register()

    def test_url_lookup_mocked(self):
        mock_response = {
            "data": {
                "attributes": {
                    "last_analysis_stats": {
                        "malicious": 10, "suspicious": 0,
                        "undetected": 55, "harmless": 5,
                    },
                    "categories": {"Forcepoint ThreatSeeker": "phishing"},
                    "times_submitted": 3,
                }
            }
        }
        with patch("socc.plugins.virustotal._vt_get", return_value=mock_response):
            result = invoke_tool(
                "vt_lookup_url",
                {"url": "http://evil.example.com/payload"},
            )
        assert result.ok
        assert result.output["found"] is True
        assert result.output["malicious"] == 10
        assert "permalink" in result.output


class TestVirusTotalDomainLookup:
    def setup_method(self):
        self.plugin = load_plugin("virustotal")
        self.plugin.register()

    def test_domain_lookup_mocked(self):
        mock_response = {
            "data": {
                "attributes": {
                    "last_analysis_stats": {
                        "malicious": 5, "suspicious": 1,
                        "undetected": 60, "harmless": 4,
                    },
                    "registrar": "Evil Registrar Inc.",
                    "reputation": -10,
                    "categories": {},
                }
            }
        }
        with patch("socc.plugins.virustotal._vt_get", return_value=mock_response):
            result = invoke_tool(
                "vt_lookup_domain",
                {"domain": "evil.example.com"},
            )
        assert result.ok
        assert result.output["found"] is True
        assert result.output["domain"] == "evil.example.com"
        assert result.output["malicious"] == 5


# ===========================================================================
# MISP plugin (CC-019)
# ===========================================================================

class TestMISPRegistration:
    def test_register_adds_tools(self):
        plugin = load_plugin("misp")
        plugin.register()
        tools = list_tools()
        assert "misp_search" in tools
        assert "misp_add_event" in tools
        assert "misp_add_ioc" in tools

    def test_tool_risk_levels(self):
        from socc.core.tools_registry import RiskLevel
        plugin = load_plugin("misp")
        plugin.register()
        assert get_tool("misp_search").risk_level == RiskLevel.LOW
        assert get_tool("misp_add_event").risk_level == RiskLevel.MEDIUM
        assert get_tool("misp_add_ioc").risk_level == RiskLevel.MEDIUM


class TestMISPSearch:
    def setup_method(self):
        self.plugin = load_plugin("misp")
        self.plugin.register()

    def test_search_mocked(self):
        mock_response = {
            "response": {
                "Attribute": [
                    {
                        "id": "1", "event_id": "42", "type": "ip-dst",
                        "value": "1.2.3.4", "category": "Network activity",
                        "comment": "C2", "timestamp": "1711929600", "to_ids": True,
                    }
                ]
            }
        }
        with patch("socc.plugins.misp._misp_request", return_value=mock_response):
            result = invoke_tool("misp_search", {"value": "1.2.3.4"})
        assert result.ok
        assert result.output["total_count"] == 1
        assert result.output["attributes"][0]["value"] == "1.2.3.4"

    def test_invalid_attribute_type(self):
        result = invoke_tool(
            "misp_search",
            {"value": "1.2.3.4", "type_attribute": "not-a-valid-type"},
        )
        assert result.ok
        assert "error" in result.output

    def test_valid_attribute_type_filter(self):
        mock_response = {"response": {"Attribute": []}}
        with patch("socc.plugins.misp._misp_request", return_value=mock_response) as m:
            invoke_tool("misp_search", {"value": "evil.com", "type_attribute": "domain"})
        call_body = m.call_args[0][2]
        assert call_body["type"] == "domain"


class TestMISPAddEvent:
    def setup_method(self):
        self.plugin = load_plugin("misp")
        self.plugin.register()

    def test_create_event_mocked(self):
        mock_response = {"Event": {"id": "99", "info": "Test Event"}}
        with patch("socc.plugins.misp._misp_request", return_value=mock_response):
            with patch.dict(os.environ, {"MISP_URL": "https://misp.corp", "MISP_API_KEY": "key"}):
                result = invoke_tool(
                    "misp_add_event",
                    {"title": "Phishing Campaign 2026"},
                )
        assert result.ok
        assert result.output["created"] is True
        assert result.output["event_id"] == "99"

    def test_invalid_threat_level(self):
        result = invoke_tool("misp_add_event", {"title": "Test", "threat_level": 9})
        assert result.ok
        assert "error" in result.output

    def test_invalid_distribution(self):
        result = invoke_tool("misp_add_event", {"title": "Test", "distribution": 10})
        assert result.ok
        assert "error" in result.output


class TestMISPAddIOC:
    def setup_method(self):
        self.plugin = load_plugin("misp")
        self.plugin.register()

    def test_add_ioc_mocked(self):
        mock_response = {"Attribute": {"id": "500", "type": "ip-dst", "value": "1.2.3.4"}}
        with patch("socc.plugins.misp._misp_request", return_value=mock_response):
            with patch.dict(os.environ, {"MISP_URL": "https://misp.corp", "MISP_API_KEY": "key"}):
                result = invoke_tool(
                    "misp_add_ioc",
                    {"event_id": "42", "ioc_type": "ip-dst", "value": "1.2.3.4"},
                )
        assert result.ok
        assert result.output["created"] is True
        assert result.output["attribute_id"] == "500"

    def test_invalid_ioc_type(self):
        result = invoke_tool(
            "misp_add_ioc",
            {"event_id": "1", "ioc_type": "not-real", "value": "x"},
        )
        assert result.ok
        assert "error" in result.output


# ===========================================================================
# OpenCTI plugin (CC-020)
# ===========================================================================

class TestOpenCTIRegistration:
    def test_register_adds_tools(self):
        plugin = load_plugin("opencti")
        plugin.register()
        tools = list_tools()
        assert "opencti_search" in tools
        assert "opencti_create_indicator" in tools

    def test_tool_risk_levels(self):
        from socc.core.tools_registry import RiskLevel
        plugin = load_plugin("opencti")
        plugin.register()
        assert get_tool("opencti_search").risk_level == RiskLevel.LOW
        assert get_tool("opencti_create_indicator").risk_level == RiskLevel.MEDIUM


class TestOpenCTISearch:
    def setup_method(self):
        self.plugin = load_plugin("opencti")
        self.plugin.register()

    def test_search_mocked(self):
        mock_data = {
            "stixCoreObjects": {
                "edges": [
                    {
                        "node": {
                            "id": "abc123",
                            "entity_type": "ThreatActor",
                            "name": "APT29",
                            "description": "Cozy Bear",
                            "created_at": "2026-01-01T00:00:00Z",
                        }
                    }
                ],
                "pageInfo": {"globalCount": 1},
            }
        }
        with patch("socc.plugins.opencti._graphql", return_value=mock_data):
            result = invoke_tool("opencti_search", {"query": "APT29"})
        assert result.ok
        assert result.output["total_count"] == 1
        assert result.output["results"][0]["name"] == "APT29"

    def test_invalid_entity_type(self):
        result = invoke_tool(
            "opencti_search",
            {"query": "test", "entity_types": ["NotARealType"]},
        )
        assert result.ok
        assert "error" in result.output

    def test_limit_capped_at_100(self):
        mock_data = {"stixCoreObjects": {"edges": [], "pageInfo": {"globalCount": 0}}}
        with patch("socc.plugins.opencti._graphql", return_value=mock_data) as m:
            invoke_tool("opencti_search", {"query": "test", "limit": 9999})
        variables = m.call_args[0][1]
        assert variables["first"] == 100


class TestOpenCTICreateIndicator:
    def setup_method(self):
        self.plugin = load_plugin("opencti")
        self.plugin.register()

    def test_create_ipv4_indicator(self):
        mock_data = {
            "indicatorAdd": {
                "id": "ind-001",
                "name": "C2 Server",
                "pattern": "[ipv4-addr:value = '1.2.3.4']",
                "pattern_type": "stix",
                "valid_from": "2026-01-01T00:00:00Z",
                "x_opencti_score": 80,
                "created_at": "2026-04-01T00:00:00Z",
            }
        }
        with patch("socc.plugins.opencti._graphql", return_value=mock_data):
            with patch.dict(os.environ, {"OPENCTI_URL": "https://opencti.corp", "OPENCTI_API_KEY": "key"}):
                result = invoke_tool(
                    "opencti_create_indicator",
                    {
                        "name": "C2 Server",
                        "pattern_type": "ipv4-addr",
                        "value": "1.2.3.4",
                        "score": 80,
                    },
                )
        assert result.ok
        assert result.output["created"] is True
        assert "[ipv4-addr:value = '1.2.3.4']" in result.output["pattern"]
        assert result.output["score"] == 80

    def test_create_sha256_indicator(self):
        mock_data = {
            "indicatorAdd": {
                "id": "ind-002",
                "name": "Malware Hash",
                "pattern": "[file:hashes.'SHA-256' = 'abc123']",
                "pattern_type": "stix",
                "valid_from": "2026-01-01T00:00:00Z",
                "x_opencti_score": 90,
                "created_at": "2026-04-01T00:00:00Z",
            }
        }
        with patch("socc.plugins.opencti._graphql", return_value=mock_data):
            with patch.dict(os.environ, {"OPENCTI_URL": "https://opencti.corp", "OPENCTI_API_KEY": "key"}):
                result = invoke_tool(
                    "opencti_create_indicator",
                    {
                        "name": "Malware Hash",
                        "pattern_type": "file:sha256",
                        "value": "abc123",
                        "score": 90,
                    },
                )
        assert result.ok
        assert result.output["created"] is True

    def test_invalid_pattern_type(self):
        result = invoke_tool(
            "opencti_create_indicator",
            {"name": "Test", "pattern_type": "not-valid", "value": "x"},
        )
        assert result.ok
        assert "error" in result.output

    def test_score_clamped(self):
        mock_data = {
            "indicatorAdd": {
                "id": "ind-003",
                "name": "Test",
                "pattern": "[ipv4-addr:value = '1.1.1.1']",
                "pattern_type": "stix",
                "valid_from": "2026-01-01T00:00:00Z",
                "x_opencti_score": 100,
                "created_at": "2026-04-01T00:00:00Z",
            }
        }
        with patch("socc.plugins.opencti._graphql", return_value=mock_data):
            with patch.dict(os.environ, {"OPENCTI_URL": "https://opencti.corp", "OPENCTI_API_KEY": "key"}):
                result = invoke_tool(
                    "opencti_create_indicator",
                    {
                        "name": "Test",
                        "pattern_type": "ipv4-addr",
                        "value": "1.1.1.1",
                        "score": 9999,   # should be clamped to 100
                    },
                )
        assert result.ok
        assert result.output["score"] == 100

    def test_stix_pattern_templates(self):
        """Verify all STIX pattern templates produce valid-looking patterns."""
        from socc.plugins.opencti import STIX_PATTERN_TEMPLATES
        for ptype, template in STIX_PATTERN_TEMPLATES.items():
            pattern = template.format(value="test_value")
            assert "[" in pattern and "]" in pattern, f"Bad pattern for {ptype}: {pattern}"


# ===========================================================================
# register_all_plugins
# ===========================================================================

class TestRegisterAllPlugins:
    def test_skip_unconfigured(self):
        # No env vars — all plugins should be skipped
        env = {k: v for k, v in os.environ.items()
               if k not in ("VT_API_KEY", "MISP_URL", "MISP_API_KEY",
                            "OPENCTI_URL", "OPENCTI_API_KEY")}
        with patch.dict(os.environ, env, clear=True):
            from socc.plugins import register_all_plugins
            results = register_all_plugins(skip_unconfigured=True)
        # All should have been skipped (False)
        assert all(not v for v in results.values())
        # But no tools registered
        assert not list_tools()

    def test_register_all_configured(self):
        env = {
            "VT_API_KEY": "fake-vt",
            "MISP_URL": "https://misp.corp",
            "MISP_API_KEY": "fake-misp",
            "OPENCTI_URL": "https://opencti.corp",
            "OPENCTI_API_KEY": "fake-opencti",
        }
        with patch.dict(os.environ, env):
            from socc.plugins import register_all_plugins
            results = register_all_plugins(skip_unconfigured=False)
        assert results.get("virustotal") is True
        assert results.get("misp") is True
        assert results.get("opencti") is True
        # All tools should be registered
        tools = list_tools()
        assert "vt_lookup_hash" in tools
        assert "misp_search" in tools
        assert "opencti_search" in tools
