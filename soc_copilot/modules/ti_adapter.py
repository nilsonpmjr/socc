"""
ti_adapter.py
Gerencia a consulta de Threat Intelligence seguindo as regras do MVP:
  - IOC único IP externo -> threat_check.py --dashboard {ioc}
  - IOC único domínio/hash -> API do backend TI
  - Múltiplos IOCs externos -> API do backend TI
  - fallback seguro -> consulta individual respeitando o tipo do IOC
Evita consultar o mesmo IOC duas vezes e registra falhas sem inventar reputação.
"""
from __future__ import annotations

import ipaddress
import subprocess
import sys
import time
from pathlib import Path

import requests

from soc_copilot.config import (
    MAX_TI_IOCS,
    THREAT_CHECK_SCRIPT,
    TI_API_BASE_URL,
    TI_API_PASS,
    TI_API_USER,
)

_TIMEOUT_SINGLE = 30
_TIMEOUT_BATCH_SUBMIT = 10
_TIMEOUT_BATCH_POLL = 60
_SUPPORTED_KEYS = ("ips_externos", "dominios", "hashes")


def _normalize_target(value: str) -> str:
    target = str(value or "").strip()
    if not target:
        return ""

    normalized = target
    try:
        normalized = str(ipaddress.ip_address(target))
        return normalized
    except ValueError:
        pass

    if len(target) in (32, 40, 64) and all(ch in "0123456789abcdefABCDEF" for ch in target):
        return target.lower()

    return target.lower().strip(".")


def _ioc_type(ioc: str) -> str:
    try:
        ipaddress.ip_address(ioc)
        return "ip"
    except ValueError:
        pass

    if len(ioc) in (32, 40, 64) and all(ch in "0123456789abcdefABCDEF" for ch in ioc):
        return "hash"

    return "domain"


def _query_single(ioc: str) -> str:
    script = Path(THREAT_CHECK_SCRIPT)
    if not script.exists():
        return f"[AVISO] threat_check.py não encontrado em: {script}"
    try:
        result = subprocess.run(
            [sys.executable, str(script), "--dashboard", ioc],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SINGLE,
        )
        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()
        if stdout:
            return stdout
        if stderr:
            return f"[AVISO] {stderr}"
        return "Sem retorno da ferramenta."
    except subprocess.TimeoutExpired:
        return f"[AVISO] Timeout ao consultar {ioc}."
    except Exception as exc:
        return f"[ERRO] Falha ao consultar {ioc}: {exc}"


def _get_ti_session() -> requests.Session | None:
    session = requests.Session()
    try:
        resp = session.post(
            f"{TI_API_BASE_URL}/api/auth/login",
            data={"username": TI_API_USER, "password": TI_API_PASS},
            timeout=_TIMEOUT_BATCH_SUBMIT,
        )
        if resp.status_code == 200:
            return session
        return None
    except Exception:
        return None


def _query_batch_api(iocs: list[str]) -> dict[str, str]:
    session = _get_ti_session()
    if session is None:
        return {ioc: "[AVISO] Não foi possível autenticar no backend TI." for ioc in iocs}

    try:
        submit = session.post(
            f"{TI_API_BASE_URL}/api/v1/analyze/batch",
            json={"targets": iocs, "lang": "pt"},
            timeout=_TIMEOUT_BATCH_SUBMIT,
        )
        if submit.status_code != 202:
            return {ioc: f"[AVISO] Erro ao submeter lote: {submit.status_code}" for ioc in iocs}
        job_id = submit.json()["job_id"]
    except Exception as exc:
        return {ioc: f"[ERRO] Falha ao submeter lote: {exc}" for ioc in iocs}

    deadline = time.time() + _TIMEOUT_BATCH_POLL
    while time.time() < deadline:
        try:
            status_resp = session.get(
                f"{TI_API_BASE_URL}/api/v1/analyze/batch/{job_id}",
                timeout=10,
            )
            if status_resp.status_code == 200:
                data = status_resp.json()
                if data.get("status") == "done":
                    results: dict[str, str] = {}
                    for item in data.get("results", []):
                        target = item.get("target", "")
                        verdict = item.get("verdict", "N/A")
                        score = item.get("risk_score", "N/A")
                        cached = "cache" if item.get("from_cache") else "nova consulta"
                        results[target] = f"Veredito: {verdict} | Score: {score} ({cached})"
                    return {ioc: results.get(ioc, "Sem resultado retornado no lote.") for ioc in iocs}
        except Exception:
            pass
        time.sleep(2)

    return {ioc: "[AVISO] Timeout aguardando resposta do lote TI." for ioc in iocs}


def _collect_targets(iocs: dict) -> list[str]:
    targets: list[str] = []
    seen: set[str] = set()

    for key in _SUPPORTED_KEYS:
        for item in iocs.get(key, []) or []:
            normalized = _normalize_target(str(item))
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            targets.append(normalized)

    return targets[:MAX_TI_IOCS]


def _all_failed(results: dict[str, str]) -> bool:
    if not results:
        return True
    return all(("[AVISO]" in value) or ("[ERRO]" in value) for value in results.values())


def _query_target_individually(target: str) -> str:
    if _ioc_type(target) == "ip":
        return _query_single(target)

    api_results = _query_batch_api([target])
    if not _all_failed(api_results):
        return api_results.get(target, "Sem resultado retornado no backend TI.")

    return (
        f"[AVISO] IOC do tipo {_ioc_type(target)} sem suporte confirmado no "
        "threat_check.py e backend TI indisponível."
    )


def enrich(iocs: dict) -> dict[str, str]:
    """
    Recebe o dict de IOCs do parser_engine e consulta apenas artefatos externos.
    Regras (TOOLS.md):
      - IOC único IP     : threat_check.py --dashboard
      - IOC único não-IP : API do backend TI
      - Múltiplos  : API do backend TI (estruturado por target)
      - Fallback   : consultas individuais respeitando o tipo do IOC
      - Duplicidade: proibida (_collect_targets deduplica)
    """
    targets = _collect_targets(iocs)
    if not targets:
        return {}

    if len(targets) == 1:
        target = targets[0]
        return {target: _query_target_individually(target)}

    # Múltiplos: API estruturada primeiro
    api_results = _query_batch_api(targets)
    if not _all_failed(api_results):
        return api_results

    # Fallback: individuais sequenciais respeitando o tipo do IOC
    fallback: dict[str, str] = {}
    for target in targets:
        fallback[target] = _query_target_individually(target)
    return fallback
