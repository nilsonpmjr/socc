from __future__ import annotations

from soc_copilot.modules import ti_adapter


LEGACY_MODULE = "soc_copilot.modules.ti_adapter"


def enrich_iocs(iocs: dict) -> dict[str, str]:
    return ti_adapter.enrich(iocs)
