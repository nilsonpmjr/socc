"""
Valida registry e ingestao local da base de conhecimento para RAG.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from socc.core.knowledge_base import (
    chunk_document,
    ensure_knowledge_base,
    format_retrieval_context,
    ingest_source,
    inspect_index,
    normalize_document_text,
    register_source,
    search_knowledge_base,
)

PASS = "PASS"
FAIL = "FAIL"
resultados: list[tuple[str, str, str]] = []


def check(nome: str, condicao: bool, detalhe: str = "") -> None:
    status = PASS if condicao else FAIL
    resultados.append((status, nome, detalhe))


tmpdir = tempfile.TemporaryDirectory()
runtime_root = Path(tmpdir.name) / ".socc-test"
docs_root = Path(tmpdir.name) / "docs"

try:
    docs_root.mkdir(parents=True, exist_ok=True)
    (docs_root / "runbook.md").write_text(
        "# Runbook\n\n IOC principal: evil.example.com \r\n\r\n Ação: isolar host.\n\n\n Coletar evidências.\n",
        encoding="utf-8",
    )
    (docs_root / "notes.txt").write_text(
        "Primeiro parágrafo relevante.\n\nSegundo parágrafo com contexto adicional de investigação.\n",
        encoding="utf-8",
    )

    ensure_knowledge_base(runtime_root)
    registered = register_source(
        source_id="sops-internos",
        name="SOPs Internos",
        path=str(docs_root),
        tags=["sop", "runbook"],
        home=runtime_root,
    )
    source = registered.get("source", {})
    check("intel_registry_source_created", registered.get("created") is True)
    check("intel_registry_source_id", source.get("id") == "sops-internos")
    check("intel_registry_source_tags", source.get("tags") == ["sop", "runbook"])

    normalized = normalize_document_text("linha 1\r\n\r\n\r\nlinha 2\t\t")
    check("intel_registry_normalize_newlines", normalized == "linha 1\n\nlinha 2")

    chunks = chunk_document("A" * 1200, max_chars=500, overlap=100)
    check("intel_registry_chunk_count", len(chunks) >= 2)

    ingested = ingest_source(source_id="sops-internos", home=runtime_root)
    check("intel_registry_documents_indexed", ingested.get("documents_indexed") == 2)
    check("intel_registry_chunks_indexed", int(ingested.get("chunks_indexed") or 0) >= 2)
    check("intel_registry_index_exists", Path(ingested.get("index_path", "")).exists())

    index_lines = Path(ingested.get("index_path", "")).read_text(encoding="utf-8").splitlines()
    manifest = inspect_index(runtime_root).get("manifest", {})
    sample = json.loads(index_lines[0]) if index_lines else {}
    check("intel_registry_index_line_source", sample.get("source_id") == "sops-internos")
    check("intel_registry_manifest_docs", manifest.get("indexed_documents") == 2)
    check("intel_registry_manifest_chunks", int(manifest.get("indexed_chunks") or 0) >= 2)

    reingested = ingest_source(source_id="sops-internos", home=runtime_root)
    reindex_lines = Path(reingested.get("index_path", "")).read_text(encoding="utf-8").splitlines()
    check("intel_registry_reingest_no_dup", len(reindex_lines) == len(index_lines))

    retrieval = search_knowledge_base(
        query_text="evil.example.com isolar host",
        fields={"Assunto": "Runbook IOC evil.example.com", "IOCs": {"dominios": ["evil.example.com"]}},
        home=runtime_root,
    )
    retrieval_context = format_retrieval_context(retrieval)
    top_match = (retrieval.get("matches") or [{}])[0]
    check("intel_registry_retrieval_has_match", bool(retrieval.get("matches")))
    check("intel_registry_retrieval_source", top_match.get("source_id") == "sops-internos")
    check("intel_registry_retrieval_context", "evil.example.com" in retrieval_context and "SOPs Internos" in retrieval_context)
except Exception as exc:
    check("intel_registry_flow", False, str(exc))
finally:
    tmpdir.cleanup()


print(f"\n{'='*60}")
print(f"SOCC Runtime — Intel Registry  ({len(resultados)} checks)")
print("=" * 60)
falhas = [(n, d) for s, n, d in resultados if s == FAIL]
aprovados = len(resultados) - len(falhas)
print(f"  Aprovados : {aprovados}/{len(resultados)}")
print(f"  Falhas    : {len(falhas)}/{len(resultados)}")
print()
for nome, detalhe in falhas:
    extra = f" — {detalhe}" if detalhe else ""
    print(f"  FALHA: {nome}{extra}")
if not falhas:
    print("  Todos os checks passaram.")
print()

sys.exit(1 if falhas else 0)
