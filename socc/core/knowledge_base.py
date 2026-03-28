from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from socc.cli.installer import runtime_home


INDEX_VERSION = "rag-index-v1"
REGISTRY_FILENAME = "sources.json"
INDEX_FILENAME = "index.jsonl"
MANIFEST_FILENAME = "manifest.json"
SUPPORTED_EXTENSIONS = {
    ".txt",
    ".md",
    ".log",
    ".json",
    ".csv",
    ".xml",
    ".yaml",
    ".yml",
    ".html",
    ".htm",
}
_SEARCH_STOPWORDS = {
    "a",
    "as",
    "o",
    "os",
    "e",
    "de",
    "da",
    "do",
    "das",
    "dos",
    "para",
    "por",
    "com",
    "sem",
    "que",
    "em",
    "no",
    "na",
    "nos",
    "nas",
    "um",
    "uma",
    "ao",
    "aos",
    "the",
    "and",
    "from",
    "this",
    "that",
    "alert",
    "evento",
    "payload",
    "security",
    "log",
    "json",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(value: str, *, fallback: str = "source") -> str:
    text = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return text or fallback


def _safe_tags(tags: list[str] | None) -> list[str]:
    cleaned: list[str] = []
    for item in tags or []:
        tag = _slug(item, fallback="")
        if tag and tag not in cleaned:
            cleaned.append(tag)
    return cleaned


def _json_dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _json_load(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def knowledge_base_home(home: Path | None = None) -> Path:
    return runtime_home(home) / "intel"


def registry_path(home: Path | None = None) -> Path:
    return knowledge_base_home(home) / REGISTRY_FILENAME


def raw_dir(home: Path | None = None) -> Path:
    return knowledge_base_home(home) / "raw"


def normalized_dir(home: Path | None = None) -> Path:
    return knowledge_base_home(home) / "normalized"


def index_dir(home: Path | None = None) -> Path:
    return knowledge_base_home(home) / "index"


def index_path(home: Path | None = None) -> Path:
    return index_dir(home) / INDEX_FILENAME


def manifest_path(home: Path | None = None) -> Path:
    return index_dir(home) / MANIFEST_FILENAME


def chunk_chars() -> int:
    try:
        return max(300, int(os.getenv("SOCC_RAG_CHUNK_CHARS", "900")))
    except ValueError:
        return 900


def chunk_overlap() -> int:
    try:
        return max(0, int(os.getenv("SOCC_RAG_CHUNK_OVERLAP", "120")))
    except ValueError:
        return 120


def max_file_bytes() -> int:
    try:
        return max(4_096, int(os.getenv("SOCC_RAG_MAX_FILE_BYTES", "5242880")))
    except ValueError:
        return 5_242_880


def retrieval_top_k() -> int:
    try:
        return max(1, min(10, int(os.getenv("SOCC_RAG_TOP_K", "3"))))
    except ValueError:
        return 3


def retrieval_max_terms() -> int:
    try:
        return max(4, min(40, int(os.getenv("SOCC_RAG_MAX_TERMS", "18"))))
    except ValueError:
        return 18


def retrieval_context_chars() -> int:
    try:
        return max(400, min(8_000, int(os.getenv("SOCC_RAG_CONTEXT_CHARS", "1800"))))
    except ValueError:
        return 1800


def ensure_knowledge_base(home: Path | None = None) -> dict[str, str]:
    base = knowledge_base_home(home)
    for path in (base, raw_dir(home), normalized_dir(home), index_dir(home)):
        path.mkdir(parents=True, exist_ok=True)
    if not registry_path(home).exists():
        _json_dump(
            registry_path(home),
            {
                "version": INDEX_VERSION,
                "created_at": _utc_now(),
                "sources": [],
            },
        )
    if not manifest_path(home).exists():
        _json_dump(
            manifest_path(home),
            {
                "version": INDEX_VERSION,
                "created_at": _utc_now(),
                "chunk_chars": chunk_chars(),
                "chunk_overlap": chunk_overlap(),
                "indexed_documents": 0,
                "indexed_chunks": 0,
                "sources": {},
            },
        )
    if not index_path(home).exists():
        index_path(home).write_text("", encoding="utf-8")
    return {
        "base": str(base),
        "registry": str(registry_path(home)),
        "index": str(index_path(home)),
        "manifest": str(manifest_path(home)),
    }


def load_registry(home: Path | None = None) -> dict[str, Any]:
    ensure_knowledge_base(home)
    payload = _json_load(registry_path(home), {"version": INDEX_VERSION, "sources": []})
    if not isinstance(payload, dict):
        raise ValueError("Registry de fontes inválido.")
    payload.setdefault("version", INDEX_VERSION)
    payload.setdefault("sources", [])
    return payload


def save_registry(payload: dict[str, Any], home: Path | None = None) -> dict[str, Any]:
    ensure_knowledge_base(home)
    payload["updated_at"] = _utc_now()
    _json_dump(registry_path(home), payload)
    return payload


def list_sources(home: Path | None = None) -> list[dict[str, Any]]:
    payload = load_registry(home)
    sources = payload.get("sources") or []
    return sources if isinstance(sources, list) else []


def get_source(source_id: str, home: Path | None = None) -> dict[str, Any] | None:
    target = _slug(source_id)
    for source in list_sources(home):
        if _slug(source.get("id", "")) == target:
            return source
    return None


def register_source(
    *,
    source_id: str,
    name: str,
    kind: str = "document_set",
    trust: str = "internal",
    path: str = "",
    tags: list[str] | None = None,
    description: str = "",
    home: Path | None = None,
) -> dict[str, Any]:
    source_key = _slug(source_id)
    if not source_key:
        raise ValueError("source_id inválido.")
    if not str(name or "").strip():
        raise ValueError("name é obrigatório.")

    registry = load_registry(home)
    sources = list_sources(home)
    existing = next((item for item in sources if _slug(item.get("id", "")) == source_key), None)
    normalized_path = str(Path(path).expanduser().resolve()) if str(path or "").strip() else ""
    entry = {
        "id": source_key,
        "name": str(name).strip(),
        "kind": _slug(kind, fallback="document-set").replace("-", "_"),
        "trust": _slug(trust, fallback="internal").replace("-", "_"),
        "path": normalized_path,
        "tags": _safe_tags(tags),
        "description": str(description or "").strip(),
        "updated_at": _utc_now(),
    }
    if existing:
        existing.update(entry)
        created = False
    else:
        entry["created_at"] = _utc_now()
        entry["documents"] = 0
        entry["chunks"] = 0
        entry["last_ingested_at"] = ""
        sources.append(entry)
        created = True

    registry["sources"] = sorted(sources, key=lambda item: str(item.get("id", "")))
    save_registry(registry, home)
    return {
        "created": created,
        "source": get_source(source_key, home),
    }


def normalize_document_text(text: str) -> str:
    normalized = str(text or "").replace("\x00", "")
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.replace("\t", "  ")
    normalized_lines: list[str] = []
    blank_count = 0
    for raw_line in normalized.split("\n"):
        line = re.sub(r"[ \u00a0]+$", "", raw_line)
        line = re.sub(r"^[ \u00a0]+", "", line)
        if not line:
            blank_count += 1
            if blank_count <= 2:
                normalized_lines.append("")
            continue
        blank_count = 0
        normalized_lines.append(line)
    cleaned = "\n".join(normalized_lines).strip()
    return re.sub(r"\n{3,}", "\n\n", cleaned)


def chunk_document(text: str, *, max_chars: int | None = None, overlap: int | None = None) -> list[str]:
    content = normalize_document_text(text)
    if not content:
        return []

    max_len = max_chars or chunk_chars()
    carry = overlap if overlap is not None else chunk_overlap()
    paragraphs = [item.strip() for item in content.split("\n\n") if item.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = paragraph if not current else f"{current}\n\n{paragraph}"
        if len(candidate) <= max_len:
            current = candidate
            continue
        if current:
            chunks.append(current)
        if len(paragraph) <= max_len:
            current = paragraph
            continue
        start = 0
        while start < len(paragraph):
            end = min(len(paragraph), start + max_len)
            chunk = paragraph[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end >= len(paragraph):
                break
            start = max(0, end - min(carry, max_len // 3))
        current = ""
    if current:
        chunks.append(current)
    return chunks


def _iter_source_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    if not path.exists():
        raise FileNotFoundError(f"Fonte não encontrada: {path}")
    files = [item for item in path.rglob("*") if item.is_file() and item.suffix.lower() in SUPPORTED_EXTENSIONS]
    return sorted(files)


def _source_bucket(base: Path, source_id: str) -> Path:
    bucket = base / _slug(source_id)
    bucket.mkdir(parents=True, exist_ok=True)
    return bucket


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def _tokenize_search_text(value: Any) -> list[str]:
    text = str(value or "").strip().lower()
    if not text:
        return []
    tokens = re.findall(r"[a-z0-9][a-z0-9@._:/\\-]{1,127}", text)
    return tokens


def _is_priority_term(term: str) -> bool:
    if "@" in term or "." in term or ":" in term or "/" in term or "\\" in term:
        return True
    return len(term) >= 24 and all(char in "0123456789abcdef" for char in term.lower())


def build_search_terms(
    *,
    query_text: str = "",
    fields: dict[str, Any] | None = None,
    max_terms: int | None = None,
) -> list[str]:
    limit = max_terms or retrieval_max_terms()
    candidates: list[str] = []
    seen: set[str] = set()

    def add_term(term: str) -> None:
        cleaned = str(term or "").strip().lower()
        if not cleaned or cleaned in seen:
            return
        if cleaned in _SEARCH_STOPWORDS:
            return
        if len(cleaned) < 3 and not _is_priority_term(cleaned):
            return
        seen.add(cleaned)
        candidates.append(cleaned)

    for token in _tokenize_search_text(query_text):
        add_term(token)

    payload_fields = fields or {}
    for key, value in payload_fields.items():
        if key == "IOCs":
            continue
        if isinstance(value, (list, tuple, set)):
            for item in value:
                for token in _tokenize_search_text(item):
                    add_term(token)
            continue
        if isinstance(value, (str, int, float)):
            for token in _tokenize_search_text(value):
                add_term(token)

    iocs = payload_fields.get("IOCs") or {}
    if isinstance(iocs, dict):
        for values in iocs.values():
            if not isinstance(values, list):
                continue
            for item in values:
                add_term(str(item))

    prioritized = [item for item in candidates if _is_priority_term(item)]
    regular = [item for item in candidates if item not in prioritized]
    ordered = prioritized + regular
    return ordered[:limit]


def _score_index_record(record: dict[str, Any], search_terms: list[str]) -> tuple[int, list[str]]:
    haystack = " ".join(
        [
            str(record.get("text") or "").lower(),
            str(record.get("title") or "").lower(),
            " ".join(str(item).lower() for item in (record.get("tags") or [])),
            str(record.get("source_name") or "").lower(),
        ]
    )
    matched_terms: list[str] = []
    score = 0
    for term in search_terms:
        if term not in haystack:
            continue
        matched_terms.append(term)
        score += 5 if _is_priority_term(term) else 2
        if term in str(record.get("title") or "").lower():
            score += 1
    return score, matched_terms


def search_knowledge_base(
    *,
    query_text: str = "",
    fields: dict[str, Any] | None = None,
    limit: int | None = None,
    home: Path | None = None,
) -> dict[str, Any]:
    ensure_knowledge_base(home)
    index_file = index_path(home)
    search_terms = build_search_terms(query_text=query_text, fields=fields)
    top_k = limit or retrieval_top_k()
    if not search_terms or not index_file.exists():
        return {"query_terms": search_terms, "matches": [], "sources": []}

    matches: list[dict[str, Any]] = []
    for raw_line in index_file.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        try:
            record = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        score, matched_terms = _score_index_record(record, search_terms)
        if score <= 0:
            continue
        text = normalize_document_text(str(record.get("text") or ""))
        matches.append(
            {
                "source_id": str(record.get("source_id") or ""),
                "source_name": str(record.get("source_name") or ""),
                "title": str(record.get("title") or ""),
                "path": str(record.get("path") or ""),
                "normalized_path": str(record.get("normalized_path") or ""),
                "tags": list(record.get("tags") or []),
                "trust": str(record.get("trust") or ""),
                "chunk_hash": str(record.get("chunk_hash") or ""),
                "chunk_index": int(record.get("chunk_index") or 0),
                "char_count": int(record.get("char_count") or len(text)),
                "score": score,
                "matched_terms": matched_terms,
                "text": text,
            }
        )

    matches.sort(
        key=lambda item: (
            -int(item.get("score") or 0),
            -len(item.get("matched_terms") or []),
            str(item.get("source_name") or ""),
            int(item.get("chunk_index") or 0),
        )
    )

    selected: list[dict[str, Any]] = []
    seen_chunks: set[str] = set()
    for item in matches:
        chunk_hash = str(item.get("chunk_hash") or "")
        if chunk_hash and chunk_hash in seen_chunks:
            continue
        if chunk_hash:
            seen_chunks.add(chunk_hash)
        selected.append(item)
        if len(selected) >= top_k:
            break

    sources: list[dict[str, Any]] = []
    seen_sources: set[str] = set()
    for item in selected:
        source_key = str(item.get("source_id") or "")
        if source_key in seen_sources:
            continue
        seen_sources.add(source_key)
        sources.append(
            {
                "source_id": source_key,
                "source_name": str(item.get("source_name") or ""),
                "title": str(item.get("title") or ""),
                "path": str(item.get("path") or ""),
                "score": int(item.get("score") or 0),
            }
        )

    return {
        "query_terms": search_terms,
        "matches": selected,
        "sources": sources,
    }


def format_retrieval_context(
    retrieval: dict[str, Any] | None,
    *,
    max_chars: int | None = None,
) -> str:
    payload = retrieval or {}
    matches = payload.get("matches") or []
    if not isinstance(matches, list) or not matches:
        return ""

    limit = max_chars or retrieval_context_chars()
    parts: list[str] = []
    total = 0
    for index, item in enumerate(matches, start=1):
        snippet = normalize_document_text(str((item or {}).get("text") or ""))
        snippet = re.sub(r"\s+", " ", snippet).strip()
        if len(snippet) > 320:
            snippet = snippet[:317].rstrip() + "..."
        source_name = str((item or {}).get("source_name") or "fonte-local")
        title = str((item or {}).get("title") or "")
        matched = ", ".join((item or {}).get("matched_terms") or [])
        line = f"{index}. Fonte: {source_name}"
        if title:
            line += f" | Documento: {title}"
        if matched:
            line += f" | Termos: {matched}"
        line += f"\nTrecho: {snippet}"
        projected = total + len(line) + 2
        if parts and projected > limit:
            break
        parts.append(line)
        total = projected
    return "\n\n".join(parts)


def _load_manifest(home: Path | None = None) -> dict[str, Any]:
    ensure_knowledge_base(home)
    payload = _json_load(manifest_path(home), {})
    if not isinstance(payload, dict):
        raise ValueError("Manifest de indexação inválido.")
    payload.setdefault("version", INDEX_VERSION)
    payload.setdefault("chunk_chars", chunk_chars())
    payload.setdefault("chunk_overlap", chunk_overlap())
    payload.setdefault("sources", {})
    payload.setdefault("indexed_documents", 0)
    payload.setdefault("indexed_chunks", 0)
    return payload


def _save_manifest(payload: dict[str, Any], home: Path | None = None) -> None:
    _json_dump(manifest_path(home), payload)


def _rewrite_index_excluding_source(source_id: str, home: Path | None = None) -> None:
    current_index = index_path(home)
    if not current_index.exists():
        return
    target = _slug(source_id)
    kept_lines: list[str] = []
    for raw_line in current_index.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        try:
            payload = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if _slug(payload.get("source_id", "")) == target:
            continue
        kept_lines.append(json.dumps(payload, ensure_ascii=False))
    current_index.write_text(("".join(f"{line}\n" for line in kept_lines)), encoding="utf-8")


def ingest_source(
    *,
    source_id: str,
    input_path: str | Path | None = None,
    home: Path | None = None,
) -> dict[str, Any]:
    ensure_knowledge_base(home)
    source = get_source(source_id, home)
    if not source:
        raise LookupError("source_id não encontrado no registry.")

    configured_path = input_path or source.get("path") or ""
    if not str(configured_path).strip():
        raise ValueError("A fonte não possui path configurado para ingestão.")

    resolved_path = Path(configured_path).expanduser().resolve()
    files = _iter_source_files(resolved_path)
    if not files:
        raise ValueError("Nenhum documento suportado encontrado para ingestão.")

    manifest = _load_manifest(home)
    _rewrite_index_excluding_source(source_id, home)
    raw_bucket = _source_bucket(raw_dir(home), source_id)
    normalized_bucket = _source_bucket(normalized_dir(home), source_id)
    source_entries: list[dict[str, Any]] = []
    total_chunks = 0

    with index_path(home).open("a", encoding="utf-8") as handle:
        for file_path in files:
            size = file_path.stat().st_size
            if size > max_file_bytes():
                continue
            original_text = file_path.read_text(encoding="utf-8", errors="replace")
            normalized_text = normalize_document_text(original_text)
            if not normalized_text.strip():
                continue

            relative_name = file_path.name
            doc_hash = _hash_text(f"{source_id}:{file_path}:{normalized_text}")
            raw_target = raw_bucket / f"{doc_hash[:16]}-{relative_name}"
            normalized_target = normalized_bucket / f"{doc_hash[:16]}-{relative_name}.txt"
            raw_target.write_text(original_text, encoding="utf-8")
            normalized_target.write_text(normalized_text, encoding="utf-8")

            chunks = chunk_document(normalized_text)
            for index, chunk in enumerate(chunks):
                chunk_hash = _hash_text(f"{doc_hash}:{index}:{chunk}")
                record = {
                    "version": INDEX_VERSION,
                    "source_id": source.get("id"),
                    "source_name": source.get("name"),
                    "document_hash": doc_hash,
                    "chunk_hash": chunk_hash,
                    "chunk_index": index,
                    "path": str(file_path),
                    "normalized_path": str(normalized_target),
                    "title": file_path.stem,
                    "tags": source.get("tags", []),
                    "trust": source.get("trust"),
                    "text": chunk,
                    "char_count": len(chunk),
                    "indexed_at": _utc_now(),
                }
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")

            total_chunks += len(chunks)
            source_entries.append(
                {
                    "path": str(file_path),
                    "document_hash": doc_hash,
                    "chunks": len(chunks),
                    "bytes": size,
                    "normalized_path": str(normalized_target),
                }
            )

    updated = register_source(
        source_id=source.get("id", source_id),
        name=source.get("name", source_id),
        kind=source.get("kind", "document_set"),
        trust=source.get("trust", "internal"),
        path=str(resolved_path),
        tags=source.get("tags", []),
        description=source.get("description", ""),
        home=home,
    )["source"]
    updated["documents"] = len(source_entries)
    updated["chunks"] = total_chunks
    updated["last_ingested_at"] = _utc_now()

    registry = load_registry(home)
    registry["sources"] = [
        updated if _slug(item.get("id", "")) == _slug(source_id) else item
        for item in list_sources(home)
    ]
    save_registry(registry, home)

    manifest["chunk_chars"] = chunk_chars()
    manifest["chunk_overlap"] = chunk_overlap()
    manifest["indexed_documents"] = sum(int(item.get("documents", 0) or 0) for item in list_sources(home))
    manifest["indexed_chunks"] = sum(int(item.get("chunks", 0) or 0) for item in list_sources(home))
    manifest["updated_at"] = _utc_now()
    manifest["sources"][updated["id"]] = {
        "name": updated["name"],
        "path": updated.get("path", ""),
        "documents": len(source_entries),
        "chunks": total_chunks,
        "last_ingested_at": updated["last_ingested_at"],
        "index_version": INDEX_VERSION,
    }
    _save_manifest(manifest, home)

    return {
        "source": updated,
        "documents": source_entries,
        "documents_indexed": len(source_entries),
        "chunks_indexed": total_chunks,
        "index_path": str(index_path(home)),
        "manifest_path": str(manifest_path(home)),
    }


def inspect_index(home: Path | None = None) -> dict[str, Any]:
    ensure_knowledge_base(home)
    manifest = _load_manifest(home)
    return {
        "manifest": manifest,
        "sources": list_sources(home),
        "paths": {
            "registry": str(registry_path(home)),
            "index": str(index_path(home)),
            "manifest": str(manifest_path(home)),
        },
    }
