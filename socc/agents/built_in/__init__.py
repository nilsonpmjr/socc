"""Built-in SOC agent specifications."""

from .ir_agent import IR_AGENT_SPEC
from .soc_analyst import SOC_ANALYST_SPEC
from .threat_hunt import THREAT_HUNT_SPEC

ALL_BUILT_IN_AGENTS = [SOC_ANALYST_SPEC, IR_AGENT_SPEC, THREAT_HUNT_SPEC]

__all__ = [
    "ALL_BUILT_IN_AGENTS",
    "IR_AGENT_SPEC",
    "SOC_ANALYST_SPEC",
    "THREAT_HUNT_SPEC",
]
