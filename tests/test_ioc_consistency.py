"""
Valida consistencia de IOC entre parser, contrato estruturado e camada de TI.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from soc_copilot.modules.analysis_contract import build_structured_analysis
from soc_copilot.modules.ti_adapter import _collect_targets
from socc.core.engine import _infer_ioc_type
from socc.core.parser import extract_iocs

PASS = "PASS"
FAIL = "FAIL"
resultados: list[tuple[str, str, str]] = []


def check(nome: str, condicao: bool, detalhe: str = "") -> None:
    status = PASS if condicao else FAIL
    resultados.append((status, nome, detalhe))


try:
    raw_text = """
    src=8[.]8[.]8[.]8 dst=10.0.0.5
    url=hxxps://EVIL[.]Example[.]com/Login
    domain=evil.example.com
    hash=ABCDEF1234567890ABCDEF1234567890ABCDEF1234567890ABCDEF1234567890
    ipv6=2001:4860:4860::8888
    """
    iocs = extract_iocs(raw_text)

    check("ioc_consistency_ip_defanged", "8.8.8.8" in iocs.get("ips_externos", []))
    check("ioc_consistency_ipv6", "2001:4860:4860::8888" in iocs.get("ips_externos", []))
    check("ioc_consistency_url_normalized", "https://evil.example.com/Login" in iocs.get("urls", []))
    check("ioc_consistency_domain_dedup_from_url", "evil.example.com" not in iocs.get("dominios", []), str(iocs.get("dominios")))
    check(
        "ioc_consistency_hash_lower",
        "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890" in iocs.get("hashes", []),
        str(iocs.get("hashes")),
    )

    structured = build_structured_analysis(
        analysis={"classificacao_sugerida": {"tipo": "TP", "confianca": 0.8, "racional": "IOC externo observado."}},
        fields={
            "Assunto": "IOC externo detectado",
            "Hash_Observado": "ABCDEF1234567890ABCDEF1234567890ABCDEF1234567890ABCDEF1234567890",
            "URL_Completa": "https://evil.example.com/Login",
            "HTTP_Host": "evil.example.com",
            "IOCs": iocs,
        },
        ti_results={},
    )
    structured_iocs = structured.get("iocs", [])
    url_values = [item.get("value") for item in structured_iocs if item.get("type") == "url"]
    domain_values = [item.get("value") for item in structured_iocs if item.get("type") == "domain"]
    hash_values = [item.get("value") for item in structured_iocs if item.get("type") == "hash"]
    check("ioc_consistency_structured_url_unique", url_values.count("https://evil.example.com/Login") == 1, str(url_values))
    check("ioc_consistency_structured_domain_unique", domain_values.count("evil.example.com") == 1, str(domain_values))
    check(
        "ioc_consistency_structured_hash_unique",
        hash_values.count("ABCDEF1234567890ABCDEF1234567890ABCDEF1234567890ABCDEF1234567890") == 1
        or hash_values.count("abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890") == 1,
        str(hash_values),
    )

    ti_targets = _collect_targets(
        {
            "ips_externos": ["8.8.8.8", "8.8.8.8"],
            "dominios": ["EVIL.EXAMPLE.COM", "evil.example.com"],
            "hashes": [
                "ABCDEF1234567890ABCDEF1234567890ABCDEF1234567890ABCDEF1234567890",
                "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
            ],
        }
    )
    check("ioc_consistency_ti_targets_dedup", len(ti_targets) == 3, str(ti_targets))
    check("ioc_consistency_ti_domain_lower", "evil.example.com" in ti_targets, str(ti_targets))
    check(
        "ioc_consistency_ti_hash_lower",
        "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890" in ti_targets,
        str(ti_targets),
    )

    check("ioc_consistency_infer_ipv6", _infer_ioc_type("2001:4860:4860::8888") == "ip")
    check("ioc_consistency_infer_url", _infer_ioc_type("https://evil.example.com/Login") == "url")
except Exception as exc:
    check("ioc_consistency_flow", False, str(exc))


print(f"\n{'='*60}")
print(f"SOCC Runtime — IOC Consistency  ({len(resultados)} checks)")
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
