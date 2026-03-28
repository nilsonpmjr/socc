from __future__ import annotations

from soc_copilot.modules import input_adapter


LEGACY_MODULE = "soc_copilot.modules.input_adapter"


def detect_and_parse(raw: str):
    return input_adapter.detect_and_parse(raw)


def normalize_from_csv(rows: list[dict]) -> dict[str, str]:
    return input_adapter.normalize_from_csv(rows)


def normalize_from_json(data: dict | list) -> dict[str, str]:
    return input_adapter.normalize_from_json(data)


def adapt(raw: str) -> tuple[str, dict[str, str], str]:
    return input_adapter.adapt(raw)
