"""Tests for prompt_runtime, config_loader enhancements, and onboard wizard."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _header(label: str) -> None:
    print(f"\n{'='*60}\n  {label}\n{'='*60}")


passed = 0
failed = 0


def check(label: str, result: bool) -> None:
    global passed, failed
    if result:
        passed += 1
        print(f"  [OK] {label}")
    else:
        failed += 1
        print(f"  [FAIL] {label}")


# ============================================================
# prompt_runtime
# ============================================================
_header("prompt_runtime — non-interactive defaults")

from socc.cli.prompt_runtime import (
    ask,
    ask_path,
    ask_secret,
    checklist,
    confirm,
    is_interactive,
    select,
    set_non_interactive,
    skip,
    step,
    success,
    warning,
)

set_non_interactive(True)

check("is_interactive returns False when forced", not is_interactive())
check("ask returns default", ask("test", default="abc") == "abc")
check("ask_secret returns empty", ask_secret("pwd") == "")
check("confirm returns default True", confirm("ok?") is True)
check("confirm returns default False", confirm("ok?", default=False) is False)
check("select returns default option", select("pick", ["a", "b", "c"], default=1) == "b")
check("select empty list returns empty", select("pick", []) == "")
check("checklist returns all when no defaults", checklist("pick", ["x", "y"]) == ["x", "y"])
check("checklist respects defaults", checklist("pick", ["x", "y", "z"], defaults=[True, False, True]) == ["x", "z"])
check("ask_path returns expanded default", ask_path("dir", default="~") == Path("~").expanduser())
check("ask_path returns None when no default", ask_path("dir") is None)

# step/success/warning/skip should not crash in non-interactive
step(1, 5, "test step")
success("ok")
warning("warn")
skip("skipped")
check("output helpers run without crash", True)

set_non_interactive(False)  # reset

# ============================================================
# prompt_runtime — redaction
# ============================================================
_header("prompt_runtime — redaction")

from socc.cli.prompt_runtime import _redact_value, _should_redact

check("should_redact API_KEY", _should_redact("ANTHROPIC_API_KEY"))
check("should_redact TOKEN", _should_redact("SOCC_VANTAGE_BEARER_TOKEN"))
check("should_redact PASSWORD", _should_redact("TI_API_PASS"))
check("should not redact normal key", not _should_redact("OLLAMA_URL"))
check("redact short value", _redact_value("abc") == "****")
check("redact long value preserves ends", _redact_value("sk-ant-1234567890").startswith("sk-a") and _redact_value("sk-ant-1234567890").endswith("7890"))

# ============================================================
# config_loader — backup and batch
# ============================================================
_header("config_loader — backup, batch, read, remove")

from socc.utils.config_loader import (
    _backup_env,
    batch_update_env,
    read_all_env,
    read_env_value,
    remove_env_assignment,
    update_env_assignment,
)

with tempfile.TemporaryDirectory() as tmpdir:
    env_path = Path(tmpdir) / ".env"
    env_path.write_text("FOO=bar\nBAZ=123\n", encoding="utf-8")

    # backup
    backup = _backup_env(env_path)
    check("backup created", backup is not None and backup.exists())
    check("backup content matches", backup.read_text() == "FOO=bar\nBAZ=123\n")

    # backup of non-existent file
    check("backup of missing file returns None", _backup_env(Path(tmpdir) / "nope") is None)

    # update with backup
    update_env_assignment(env_path, "FOO", "updated")
    check("update_env writes value", "FOO=updated" in env_path.read_text())

    # batch update
    batch_update_env(env_path, {"BAZ": "456", "NEW_KEY": "hello"})
    content = env_path.read_text()
    check("batch updates existing key", "BAZ=456" in content)
    check("batch adds new key", "NEW_KEY=hello" in content)

    # read helpers
    check("read_env_value finds key", read_env_value(env_path, "FOO") == "updated")
    check("read_env_value missing key", read_env_value(env_path, "NOPE") is None)
    check("read_env_value missing file", read_env_value(Path(tmpdir) / "nope", "X") is None)

    all_vals = read_all_env(env_path)
    check("read_all_env returns dict", isinstance(all_vals, dict))
    check("read_all_env has keys", "FOO" in all_vals and "BAZ" in all_vals and "NEW_KEY" in all_vals)

    # remove
    remove_env_assignment(env_path, "FOO")
    content = env_path.read_text()
    check("remove comments out key", "# FOO=updated" in content)
    check("remove preserves other keys", "BAZ=456" in content)

    # read_all_env ignores comments
    all_after = read_all_env(env_path)
    check("read_all_env skips commented keys", "FOO" not in all_after)

# ============================================================
# config_loader — batch on empty file
# ============================================================
_header("config_loader — batch on fresh file")

with tempfile.TemporaryDirectory() as tmpdir:
    env_path = Path(tmpdir) / "sub" / ".env"
    batch_update_env(env_path, {"A": "1", "B": "2"})
    check("batch creates parent dirs", env_path.exists())
    content = env_path.read_text()
    check("batch writes to new file", "A=1" in content and "B=2" in content)

# ============================================================
# main.py — new subcommands parse
# ============================================================
_header("main.py — new subcommand parsing")

from socc.cli.main import _build_parser

parser = _build_parser()

args = parser.parse_args(["configure", "show"])
check("configure show parses", args.command == "configure" and args.configure_command == "show")

args = parser.parse_args(["configure", "set", "FOO", "bar"])
check("configure set parses", args.key == "FOO" and args.value == "bar")

args = parser.parse_args(["configure", "unset", "FOO"])
check("configure unset parses", args.key == "FOO")

args = parser.parse_args(["configure", "validate"])
check("configure validate parses", args.configure_command == "validate")

args = parser.parse_args(["models", "list"])
check("models list parses", args.command == "models" and args.models_command == "list")

args = parser.parse_args(["models", "set", "qwen3.5:9b", "--balanced"])
check("models set --balanced parses", args.model == "qwen3.5:9b" and args.balanced)

args = parser.parse_args(["models", "test"])
check("models test parses", args.models_command == "test")

args = parser.parse_args(["onboard", "--no-interactive"])
check("onboard --no-interactive parses", args.no_interactive)

args = parser.parse_args(["models", "fallback", "list"])
check("models fallback list parses", args.fallback_command == "list")

args = parser.parse_args(["models", "fallback", "add", "anthropic"])
check("models fallback add parses", args.provider == "anthropic")

args = parser.parse_args(["models", "fallback", "remove"])
check("models fallback remove parses", args.fallback_command == "remove")

# ============================================================
# doctor_interactive — category evaluation
# ============================================================
_header("doctor_interactive — category evaluation")

from socc.cli.doctor_interactive import _evaluate_category, _CATEGORY_ORDER

mock_payload = {
    "paths": {"runtime_home": "/tmp", "agent_home": "/tmp", "env_file": "/nonexistent-path-xyz",
              "manifest_file": "/tmp", "intel_registry": "/tmp", "intel_index": "/tmp"},
    "checks": {"runtime_home_exists": True, "env_file_exists": False, "agent_home_exists": True},
    "runtime": {"runtime": {"enabled": True, "backend": "ollama", "backend_label": "Ollama",
                             "provider": "ollama", "model": "qwen3.5:9b", "device": "gpu",
                             "gpu_available": True, "fallback_provider": "anthropic", "max_concurrency": 2},
                "safety": {"log_redaction_enabled": True, "prompt_audit_enabled": False, "prompt_preview_chars": 160}},
    "intel": {"version": "rag-index-v1", "indexed_documents": 42, "indexed_chunks": 256},
    "vantage": {"enabled": False, "configured": False, "base_url": "", "auth_mode": "none", "selected_modules": []},
    "features": {"analyze_api": True, "chat_api": True},
    "probe": {"reachable": True, "latency_ms": 15},
}

# All categories should evaluate without error
for cat in _CATEGORY_ORDER:
    ev = _evaluate_category(cat, mock_payload)
    check(f"eval {cat} has status/items/fixes", "status" in ev and "items" in ev and "fixes" in ev)

# Paths: env_file doesn't exist → should produce a warning or fix
ev_paths = _evaluate_category("paths", mock_payload)
check("paths detects missing env_file", any(not item["ok"] for item in ev_paths["items"] if item["key"] == "env_file"))

# Checks: env_file_exists=False → should produce fix
ev_checks = _evaluate_category("checks", mock_payload)
check("checks status is warn/error for missing env", ev_checks["status"] in ("warn", "error"))
check("checks suggests fix", len(ev_checks["fixes"]) > 0)

# Runtime: all good → should be ok
ev_rt = _evaluate_category("runtime", mock_payload)
check("runtime is ok when enabled", ev_rt["status"] == "ok")

# Runtime: disabled → should be error
bad_rt = dict(mock_payload)
bad_rt["runtime"] = {"runtime": {"enabled": False, "model": ""}}
ev_rt_bad = _evaluate_category("runtime", bad_rt)
check("runtime errors when disabled", ev_rt_bad["status"] == "error")
check("runtime fix suggests configure", any("configure" in f for f in ev_rt_bad["fixes"]))

# KB: 42 docs → ok
ev_kb = _evaluate_category("knowledge_base", mock_payload)
check("KB ok with docs", ev_kb["status"] == "ok")

# KB: 0 docs → warn
empty_kb = dict(mock_payload)
empty_kb["intel"] = {"indexed_documents": 0, "indexed_chunks": 0}
ev_kb_empty = _evaluate_category("knowledge_base", empty_kb)
check("KB warns when empty", ev_kb_empty["status"] == "warn")
check("KB fix suggests intel add", any("intel" in f for f in ev_kb_empty["fixes"]))

# Vantage: disabled → ok
ev_vantage = _evaluate_category("vantage", mock_payload)
check("vantage ok when disabled", ev_vantage["status"] == "ok")

# Vantage: enabled but not configured → warn
bad_vantage = dict(mock_payload)
bad_vantage["vantage"] = {"enabled": True, "configured": False}
ev_vantage_bad = _evaluate_category("vantage", bad_vantage)
check("vantage warns when enabled unconfigured", ev_vantage_bad["status"] == "warn")

# Probe: reachable → ok
ev_probe = _evaluate_category("probe", mock_payload)
check("probe ok when reachable", ev_probe["status"] == "ok")

# Probe: not done → skip
ev_probe_empty = _evaluate_category("probe", {})
check("probe skip when absent", ev_probe_empty["status"] == "skip")

# Probe: unreachable → error
bad_probe = dict(mock_payload)
bad_probe["probe"] = {"reachable": False, "error": "Connection refused"}
ev_probe_bad = _evaluate_category("probe", bad_probe)
check("probe errors when unreachable", ev_probe_bad["status"] == "error")

# Security: should always evaluate
ev_sec = _evaluate_category("security", mock_payload)
check("security evaluates ok", ev_sec["status"] == "ok")
check("security has items", len(ev_sec["items"]) >= 2)

# Features: all ok
ev_feat = _evaluate_category("features", mock_payload)
check("features ok", ev_feat["status"] == "ok")

# ============================================================
# doctor_interactive — non-interactive returns early
# ============================================================
_header("doctor_interactive — non-interactive fallback")

set_non_interactive(True)
from socc.cli.doctor_interactive import run_interactive_doctor as _run_doc

doc_result = _run_doc(mock_payload)
check("doctor non-interactive returns False", doc_result.get("interactive") is False)
set_non_interactive(False)

# ============================================================
# onboard_wizard — helpers
# ============================================================
_header("onboard_wizard — helpers")

from socc.cli.onboard_wizard import _count_indexable_files, _scan_candidate_kb_paths

with tempfile.TemporaryDirectory() as tmpdir:
    (Path(tmpdir) / "a.md").write_text("test")
    (Path(tmpdir) / "b.txt").write_text("test")
    (Path(tmpdir) / "c.py").write_text("test")
    (Path(tmpdir) / "sub").mkdir()
    (Path(tmpdir) / "sub" / "d.json").write_text("{}")

    count = _count_indexable_files(Path(tmpdir))
    check("count_indexable_files finds md+txt+json", count == 3)

# ============================================================
# onboard_wizard — non-interactive returns early
# ============================================================
_header("onboard_wizard — non-interactive fallback")

set_non_interactive(True)
from socc.cli.onboard_wizard import run_onboard_wizard

result = run_onboard_wizard()
check("wizard returns non-interactive payload", result.get("wizard") is False)
check("wizard explains reason", "non-interactive" in result.get("reason", ""))
set_non_interactive(False)

# ============================================================
# Summary
# ============================================================
print(f"\n{'='*60}")
print(f"  Aprovados : {passed}/{passed + failed}")
print(f"  Falhas    : {failed}/{passed + failed}")
print(f"{'='*60}")
if failed:
    print("\n  Há falhas nos testes.")
    raise SystemExit(1)
else:
    print("\n  Todos os checks passaram.")
