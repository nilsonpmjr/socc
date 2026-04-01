"""
Tests for socc/tools/file.py — read, write, edit tools with sandbox.
"""
from __future__ import annotations

import pytest
from pathlib import Path

from socc.core.tools_registry import clear_registry, invoke_tool, list_tools


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_registry():
    """Clear registry and re-register file tools before each test."""
    clear_registry()
    from socc.tools.file import register_file_tools
    register_file_tools()
    yield
    clear_registry()


@pytest.fixture
def tmp_file(tmp_path: Path) -> Path:
    """A temp file within the tmp_path sandbox."""
    f = tmp_path / "sample.txt"
    f.write_text("line1\nline2\nline3\n", encoding="utf-8")
    return f


@pytest.fixture(autouse=True)
def _chdir_tmp(tmp_path: Path, monkeypatch):
    """Run each test with cwd = tmp_path so sandbox checks pass."""
    monkeypatch.chdir(tmp_path)


# ---------------------------------------------------------------------------
# read
# ---------------------------------------------------------------------------

class TestReadTool:
    def test_registered(self):
        assert "read" in list_tools()

    def test_read_full_file(self, tmp_file: Path):
        result = invoke_tool("read", {"file_path": str(tmp_file)})
        assert result.ok
        assert "line1" in result.output["content"]
        assert result.output["total_lines"] == 3
        assert result.output["truncated"] is False

    def test_read_with_offset(self, tmp_file: Path):
        result = invoke_tool("read", {"file_path": str(tmp_file), "offset": 1})
        assert result.ok
        assert "line2" in result.output["content"]
        assert "line1" not in result.output["content"]

    def test_read_with_limit(self, tmp_file: Path):
        result = invoke_tool("read", {"file_path": str(tmp_file), "limit": 1})
        assert result.ok
        assert result.output["lines_read"] == 1
        assert result.output["truncated"] is True

    def test_read_nonexistent_file(self, tmp_path: Path):
        result = invoke_tool("read", {"file_path": str(tmp_path / "missing.txt")})
        assert not result.ok
        assert "not found" in result.error.lower() or "FileNotFoundError" in result.error

    def test_read_outside_sandbox(self):
        result = invoke_tool("read", {"file_path": "/etc/passwd"})
        assert not result.ok
        assert "PermissionError" in result.error or "outside" in result.error.lower()

    def test_read_directory_fails(self, tmp_path: Path):
        result = invoke_tool("read", {"file_path": str(tmp_path)})
        assert not result.ok


# ---------------------------------------------------------------------------
# write
# ---------------------------------------------------------------------------

class TestWriteTool:
    def test_registered(self):
        assert "write" in list_tools()

    def test_write_new_file(self, tmp_path: Path):
        target = tmp_path / "new.txt"
        result = invoke_tool("write", {"file_path": str(target), "content": "hello world"})
        assert result.ok
        assert result.output["created"] is True
        assert target.read_text() == "hello world"

    def test_write_overwrites_existing(self, tmp_file: Path):
        result = invoke_tool("write", {"file_path": str(tmp_file), "content": "new content"})
        assert result.ok
        assert result.output["created"] is False
        assert tmp_file.read_text() == "new content"

    def test_write_creates_parents(self, tmp_path: Path):
        target = tmp_path / "deep" / "dir" / "file.txt"
        result = invoke_tool("write", {"file_path": str(target), "content": "deep"})
        assert result.ok
        assert target.exists()

    def test_write_outside_sandbox(self):
        result = invoke_tool("write", {"file_path": "/tmp/evil.txt", "content": "x"})
        assert not result.ok
        assert "PermissionError" in result.error or "outside" in result.error.lower()

    def test_write_returns_bytes_written(self, tmp_path: Path):
        content = "abc"
        result = invoke_tool("write", {"file_path": str(tmp_path / "f.txt"), "content": content})
        assert result.ok
        assert result.output["bytes_written"] == len(content.encode())


# ---------------------------------------------------------------------------
# edit
# ---------------------------------------------------------------------------

class TestEditTool:
    def test_registered(self):
        assert "edit" in list_tools()

    def test_edit_replaces_unique_string(self, tmp_file: Path):
        result = invoke_tool("edit", {
            "file_path": str(tmp_file),
            "old_string": "line2",
            "new_string": "LINE_TWO",
        })
        assert result.ok
        assert "LINE_TWO" in tmp_file.read_text()
        assert "line2" not in tmp_file.read_text()

    def test_edit_not_found(self, tmp_file: Path):
        result = invoke_tool("edit", {
            "file_path": str(tmp_file),
            "old_string": "DOES_NOT_EXIST",
            "new_string": "x",
        })
        assert not result.ok
        assert "not found" in result.error.lower() or "ValueError" in result.error

    def test_edit_duplicate_string_fails(self, tmp_path: Path):
        f = tmp_path / "dup.txt"
        f.write_text("foo\nfoo\nbar\n")
        result = invoke_tool("edit", {
            "file_path": str(f),
            "old_string": "foo",
            "new_string": "baz",
        })
        assert not result.ok
        assert "2" in result.error or "twice" in result.error.lower() or "times" in result.error

    def test_edit_outside_sandbox(self):
        result = invoke_tool("edit", {
            "file_path": "/etc/hosts",
            "old_string": "localhost",
            "new_string": "x",
        })
        assert not result.ok

    def test_edit_nonexistent_file(self, tmp_path: Path):
        result = invoke_tool("edit", {
            "file_path": str(tmp_path / "ghost.txt"),
            "old_string": "x",
            "new_string": "y",
        })
        assert not result.ok
