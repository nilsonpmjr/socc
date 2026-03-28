"""
input_adapter.py
Responsável por receber a entrada bruta (texto, JSON, CSV) e normalizar
para um dicionário comum antes do parser_engine processar.
"""
from __future__ import annotations

import csv
import io
import json
import re


_KV_LINE_RE = re.compile(r"^\s*([^:=]{2,120}?)\s*[:=]\s*(.+?)\s*$")

# FortiGate/syslog inline key=value ou key="value"
_FGT_KV_RE = re.compile(r'(\w+)=("(?:[^"\\]|\\.)*"|[^\s"=]+)')
_FGT_MARKERS = ("logver=", "devid=", "vd=", "logid=", "devname=", "subtype=", "eventtype=")


def _is_fortigate_syslog(raw: str) -> bool:
    """Detecta log FortiGate ou syslog com pares key=value inline em linha única."""
    sample = raw[:600].lower()
    return sum(1 for m in _FGT_MARKERS if m in sample) >= 3


def _parse_fortigate_syslog(raw: str) -> dict[str, str]:
    """Extrai pares key=value de logs FortiGate/syslog inline (múltiplos por linha)."""
    fields: dict[str, str] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        for m in _FGT_KV_RE.finditer(line):
            key = m.group(1)
            val = m.group(2)
            if val.startswith('"') and val.endswith('"'):
                val = val[1:-1]
            if key and val:
                fields.setdefault(key, val)  # primeira ocorrência vence
    return fields


def _flatten_json(data, prefix: str = "") -> dict[str, str]:
    """
    Achata JSONs simples/nested em um dicionário de chaves -> valor textual.
    Mantém tanto o nome completo do caminho quanto a última chave para facilitar o parser.
    """
    flat: dict[str, str] = {}

    if isinstance(data, dict):
        for key, value in data.items():
            key_str = str(key).strip()
            if not key_str:
                continue
            nested_prefix = f"{prefix}.{key_str}" if prefix else key_str
            for nested_key, nested_value in _flatten_json(value, nested_prefix).items():
                flat.setdefault(nested_key, nested_value)
    elif isinstance(data, list):
        for idx, item in enumerate(data):
            nested_prefix = f"{prefix}[{idx}]" if prefix else f"[{idx}]"
            for nested_key, nested_value in _flatten_json(item, nested_prefix).items():
                flat.setdefault(nested_key, nested_value)
    else:
        value = "" if data is None else str(data).strip()
        if prefix:
            flat.setdefault(prefix, value)
            last = prefix.split(".")[-1].split("[")[0]
            flat.setdefault(last, value)

    return flat


def _try_parse_json(raw: str):
    raw = raw.strip()
    if not raw:
        return None

    candidates = [raw]
    if raw.startswith("\ufeff"):
        candidates.append(raw.lstrip("\ufeff"))

    for candidate in candidates:
        if not candidate:
            continue
        if candidate.startswith("{") or candidate.startswith("["):
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue

    return None


def _try_parse_csv(raw: str):
    if "\n" not in raw:
        return None

    text = raw.lstrip("\ufeff")
    for delimiter in (",", ";", "\t"):
        try:
            reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
            rows = list(reader)
            if rows and reader.fieldnames and len(reader.fieldnames) >= 2:
                return rows
        except Exception:
            continue

    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
        reader = csv.DictReader(io.StringIO(text), dialect=dialect)
        rows = list(reader)
        if rows and reader.fieldnames and len(reader.fieldnames) >= 2:
            return rows
    except Exception:
        pass

    return None


def _normalize_csv_row(rows: list[dict]) -> dict[str, str]:
    if not rows:
        return {}

    normalized: dict[str, str] = {}
    first = rows[0]
    for key, value in first.items():
        key_str = str(key).strip() if key is not None else ""
        if not key_str:
            continue
        normalized[key_str] = value.strip() if isinstance(value, str) else ("" if value is None else str(value))

    if len(rows) > 1:
        normalized["_csv_row_count"] = str(len(rows))

    return normalized


def _parse_key_value_text(raw: str) -> dict[str, str]:
    """
    Extrai pares chave:valor ou chave=valor de texto livre, mantendo apenas linhas confiáveis.
    """
    fields: dict[str, str] = {}

    for line in raw.splitlines():
        line = line.strip()
        if not line or len(line) < 3:
            continue
        match = _KV_LINE_RE.match(line)
        if not match:
            continue
        key = match.group(1).strip()
        value = match.group(2).strip()
        if len(key) > 120 or not value:
            continue
        fields[key] = value

    return fields


def detect_and_parse(raw: str) -> tuple[str, dict | list]:
    """
    Detecta o formato e faz o parse inicial.
    Retorna (formato, dado_parseado).
    formato: 'json' | 'csv' | 'text'
    """
    raw = raw.strip()
    if not raw:
        return "text", {}

    parsed_json = _try_parse_json(raw)
    if parsed_json is not None:
        return "json", parsed_json

    # FortiGate/syslog inline KV — detectar antes do CSV para evitar falso positivo
    if _is_fortigate_syslog(raw):
        return "fortigate", _parse_fortigate_syslog(raw)

    parsed_csv = _try_parse_csv(raw)
    if parsed_csv is not None:
        return "csv", parsed_csv

    return "text", _parse_key_value_text(raw)


def normalize_from_csv(rows: list[dict]) -> dict[str, str]:
    """
    Usa a primeira linha como base de campos estruturados,
    preservando o número total de linhas para contexto.
    """
    return _normalize_csv_row(rows)


def normalize_from_json(data: dict | list) -> dict[str, str]:
    """
    Normaliza JSON (dict ou lista) em um mapa achatado de campos.
    """
    if isinstance(data, list):
        if not data:
            return {}
        if len(data) == 1:
            data = data[0]
        else:
            return _flatten_json(data[0])

    if not isinstance(data, dict):
        return {}

    return _flatten_json(data)


def adapt(raw: str) -> tuple[str, dict[str, str], str]:
    """
    Ponto de entrada principal.
    Retorna (formato, campos_brutos, raw_original).
    campos_brutos: dict com chaves originais ou achatadas do payload.
    """
    fmt, parsed = detect_and_parse(raw)
    if fmt == "json":
        campos = normalize_from_json(parsed)
    elif fmt == "csv":
        campos = normalize_from_csv(parsed)
    elif fmt == "fortigate":
        campos = parsed  # já é dict[str, str] com todos os KV extraídos
    else:
        campos = parsed if isinstance(parsed, dict) else {}

    campos["_source_format"] = fmt
    return fmt, campos, raw
