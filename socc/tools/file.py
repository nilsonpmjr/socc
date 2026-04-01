"""
File operation tools for SOCC.

Provides read, write, and edit tools with sandbox enforcement:
only paths under the current working directory (or explicitly
allowed paths via SOCC_ALLOWED_PATHS env var) are accessible.
"""
from __future__ import annotations

import os
from pathlib import Path

from socc.core.tools_registry import (
    ParamSpec,
    RiskLevel,
    ToolCategory,
    ToolSpec,
    register_tool,
    unregister_tool,
)


# ---------------------------------------------------------------------------
# Sandbox helpers
# ---------------------------------------------------------------------------

def _resolve_safe(file_path: str) -> Path:
    """Resolve *file_path* and enforce sandbox policy.

    Allowed roots:
    1. Current working directory.
    2. Paths listed in ``SOCC_ALLOWED_PATHS`` (colon-separated).

    Raises:
        PermissionError: If the resolved path escapes all allowed roots.
    """
    resolved = Path(file_path).resolve()

    allowed_roots: list[Path] = [Path.cwd()]
    extra = os.environ.get("SOCC_ALLOWED_PATHS", "")
    if extra:
        for part in extra.split(":"):
            allowed_roots.append(Path(part).resolve())

    for root in allowed_roots:
        try:
            resolved.relative_to(root)
            return resolved
        except ValueError:
            continue

    raise PermissionError(
        f"Path '{resolved}' is outside the allowed directories: "
        + ", ".join(str(r) for r in allowed_roots)
    )


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

def read(file_path: str, offset: int = 0, limit: int = 2000) -> dict:
    """Read a file from the local filesystem.

    Args:
        file_path: Absolute or relative path to the file.
        offset: Line number to start reading from (0-indexed).
        limit: Maximum number of lines to return.

    Returns:
        dict with keys: path, content, lines_read, total_lines, truncated.
    """
    safe_path = _resolve_safe(file_path)

    if not safe_path.exists():
        raise FileNotFoundError(f"File not found: {safe_path}")
    if not safe_path.is_file():
        raise IsADirectoryError(f"Path is a directory: {safe_path}")

    lines = safe_path.read_text(encoding="utf-8", errors="replace").splitlines()
    total_lines = len(lines)

    start = max(0, offset)
    end = min(start + limit, total_lines)
    selected = lines[start:end]

    return {
        "path": str(safe_path),
        "content": "\n".join(selected),
        "lines_read": len(selected),
        "total_lines": total_lines,
        "truncated": end < total_lines,
    }


def write(file_path: str, content: str) -> dict:
    """Write (or overwrite) a file.

    Parent directories are created automatically.

    Args:
        file_path: Path to the file to write.
        content: Text content to write.

    Returns:
        dict with keys: path, bytes_written, created.
    """
    safe_path = _resolve_safe(file_path)
    existed = safe_path.exists()

    safe_path.parent.mkdir(parents=True, exist_ok=True)
    safe_path.write_text(content, encoding="utf-8")

    return {
        "path": str(safe_path),
        "bytes_written": len(content.encode("utf-8")),
        "created": not existed,
    }


def edit(file_path: str, old_string: str, new_string: str) -> dict:
    """Replace the first occurrence of *old_string* with *new_string* in a file.

    Args:
        file_path: Path to the file to edit.
        old_string: Exact string to find and replace (must be unique in file).
        new_string: Replacement string.

    Returns:
        dict with keys: path, replaced, occurrences_found.

    Raises:
        ValueError: If *old_string* is not found in the file.
        ValueError: If *old_string* appears more than once (use replace_all=true).
    """
    safe_path = _resolve_safe(file_path)

    if not safe_path.exists():
        raise FileNotFoundError(f"File not found: {safe_path}")

    original = safe_path.read_text(encoding="utf-8")
    count = original.count(old_string)

    if count == 0:
        raise ValueError(
            f"String not found in '{safe_path}'. "
            "Ensure the exact whitespace and content match."
        )
    if count > 1:
        raise ValueError(
            f"String appears {count} times in '{safe_path}'. "
            "Provide more context to make it unique, or use replace_all=true."
        )

    updated = original.replace(old_string, new_string, 1)
    safe_path.write_text(updated, encoding="utf-8")

    return {
        "path": str(safe_path),
        "replaced": True,
        "occurrences_found": count,
    }


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

def _register() -> None:
    register_tool(ToolSpec(
        name="read",
        description=(
            "Read a file from the local filesystem. "
            "Returns file content with optional offset/limit for large files. "
            "Only paths within the current working directory are accessible."
        ),
        parameters={
            "file_path": ParamSpec(
                type="string",
                description="Path to the file to read (relative or absolute)",
                required=True,
            ),
            "offset": ParamSpec(
                type="integer",
                description="Line number to start reading from (default: 0)",
                required=False,
                default=0,
            ),
            "limit": ParamSpec(
                type="integer",
                description="Maximum number of lines to return (default: 2000)",
                required=False,
                default=2000,
            ),
        },
        handler=read,
        category=ToolCategory.FILE,
        risk_level=RiskLevel.LOW,
        tags=["file", "read", "filesystem"],
        example='read(file_path="src/main.py", offset=0, limit=50)',
    ))

    register_tool(ToolSpec(
        name="write",
        description=(
            "Write content to a file, creating it if it does not exist. "
            "Parent directories are created automatically. "
            "Only paths within the current working directory are allowed."
        ),
        parameters={
            "file_path": ParamSpec(
                type="string",
                description="Path to the file to write",
                required=True,
            ),
            "content": ParamSpec(
                type="string",
                description="Text content to write to the file",
                required=True,
            ),
        },
        handler=write,
        category=ToolCategory.FILE,
        risk_level=RiskLevel.MEDIUM,
        tags=["file", "write", "filesystem"],
        example='write(file_path="output/report.txt", content="Analysis complete.")',
    ))

    register_tool(ToolSpec(
        name="edit",
        description=(
            "Replace the first (unique) occurrence of a string in a file. "
            "The old_string must appear exactly once; otherwise the call fails. "
            "Use read() first to verify the exact content before editing."
        ),
        parameters={
            "file_path": ParamSpec(
                type="string",
                description="Path to the file to edit",
                required=True,
            ),
            "old_string": ParamSpec(
                type="string",
                description="Exact string to find (must appear exactly once)",
                required=True,
            ),
            "new_string": ParamSpec(
                type="string",
                description="Replacement string",
                required=True,
            ),
        },
        handler=edit,
        category=ToolCategory.FILE,
        risk_level=RiskLevel.MEDIUM,
        tags=["file", "edit", "filesystem"],
        example='edit(file_path="config.py", old_string="DEBUG = True", new_string="DEBUG = False")',
    ))


_register()


def register_file_tools() -> None:
    """Register (or re-register) file tools. Safe to call multiple times.

    Useful in tests after ``clear_registry()`` to restore the file tool set.
    """
    for name in ("read", "write", "edit"):
        unregister_tool(name)
    _register()
