"""
Valida streaming incremental do chat e persistencia do fechamento da conversa.
"""
from __future__ import annotations

import json as jsonlib
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from soc_copilot import config as cfg
from soc_copilot.modules import chat_service, persistence

PASS = "PASS"
FAIL = "FAIL"
resultados: list[tuple[str, str, str]] = []


def check(nome: str, condicao: bool, detalhe: str = "") -> None:
    status = PASS if condicao else FAIL
    resultados.append((status, nome, detalhe))


class FakeStreamResponse:
    def __init__(self, lines: list[str]) -> None:
        self._lines = lines

    def raise_for_status(self) -> None:
        return None

    def iter_lines(self, decode_unicode: bool = True):
        for line in self._lines:
            yield line if decode_unicode else line.encode("utf-8")

    def close(self) -> None:
        return None


tmpdir = tempfile.TemporaryDirectory()
db_path = Path(tmpdir.name) / "test_chat_stream.db"
persistence.DB_PATH = db_path
persistence.init_db()

original_enabled = cfg.LLM_ENABLED
original_provider = cfg.LLM_PROVIDER
original_timeout = cfg.LLM_TIMEOUT
original_url = cfg.OLLAMA_URL
original_model = cfg.OLLAMA_MODEL
original_post = chat_service.requests.post
original_cpu_guard = os.environ.get("SOCC_CPU_GUARD_ENABLED")


try:
    cfg.LLM_ENABLED = False
    events = list(
        chat_service.stream_chat_reply_events(
            "Quais formatos de log sao suportados?",
            session_id="stream-fallback",
            cliente="Cliente Teste",
        )
    )
    final_event = next((item for item in events if item.get("event") == "final"), {})
    delta_events = [item for item in events if item.get("event") == "delta"]
    messages = persistence.list_chat_messages("stream-fallback", limit=10)

    check("stream_fallback_has_meta", events[0].get("event") == "meta")
    check("stream_fallback_has_deltas", len(delta_events) >= 1)
    check(
        "stream_fallback_final_message",
        isinstance(final_event.get("data"), dict)
        and final_event["data"].get("type") == "message"
        and "Resumo do pedido" in final_event["data"].get("content", ""),
    )
    check("stream_fallback_persisted_exchange", len(messages) == 2)
except Exception as exc:
    check("stream_fallback_flow", False, str(exc))


try:
    cfg.LLM_ENABLED = True
    cfg.LLM_PROVIDER = "ollama"
    cfg.OLLAMA_URL = "http://ollama.test"
    cfg.OLLAMA_MODEL = "qwen2.5:3b"
    cfg.LLM_TIMEOUT = 5
    os.environ["SOCC_CPU_GUARD_ENABLED"] = "false"

    def fake_post(url: str, json: dict, timeout: float, stream: bool = False):
        check("stream_ollama_uses_stream_flag", stream is True, str(stream))
        check("stream_ollama_hits_chat_api", url.endswith("/api/chat"), url)
        return FakeStreamResponse(
            [
                json_module
                for json_module in (
                    jsonlib.dumps({"message": {"content": "Resposta "}, "done": False}),
                    jsonlib.dumps({"message": {"content": "incremental"}, "done": False}),
                    jsonlib.dumps({"message": {"content": "."}, "done": True}),
                )
            ]
        )

    chat_service.requests.post = fake_post
    events = list(
        chat_service.stream_chat_reply_events(
            "Explique este alerta em uma frase.",
            session_id="stream-ollama",
            cliente="Cliente Teste",
        )
    )
    delta_text = "".join(item.get("delta", "") for item in events if item.get("event") == "delta")
    final_event = next((item for item in events if item.get("event") == "final"), {})
    final_data = final_event.get("data") if isinstance(final_event.get("data"), dict) else {}
    messages = persistence.list_chat_messages("stream-ollama", limit=10)

    check("stream_ollama_has_multiple_deltas", delta_text == "Resposta incremental.")
    check(
        "stream_ollama_final_matches_deltas",
        isinstance(final_data, dict) and final_data.get("content") == delta_text,
    )
    check(
        "stream_ollama_persisted_assistant",
        len(messages) == 2 and any(
            item.get("role") == "assistant" and item.get("content") == "Resposta incremental."
            for item in messages
        ),
    )
except Exception as exc:
    check("stream_ollama_flow", False, str(exc))
finally:
    cfg.LLM_ENABLED = original_enabled
    cfg.LLM_PROVIDER = original_provider
    cfg.LLM_TIMEOUT = original_timeout
    cfg.OLLAMA_URL = original_url
    cfg.OLLAMA_MODEL = original_model
    chat_service.requests.post = original_post
    if original_cpu_guard is None:
        os.environ.pop("SOCC_CPU_GUARD_ENABLED", None)
    else:
        os.environ["SOCC_CPU_GUARD_ENABLED"] = original_cpu_guard


print(f"\n{'='*60}")
print(f"SOC Copilot — Chat Streaming  ({len(resultados)} checks)")
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

tmpdir.cleanup()
sys.exit(1 if falhas else 0)
