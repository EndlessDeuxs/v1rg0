#Communications_Pathways
# FILENAME: UIT_interfaces.py
"""
UIT Shared Interfaces – Type Definitions
Clean contracts for the UIT translation pipeline.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum

class UnknownType(Enum):
    THREAT = "Threat"
    NOVEL_IDEA = "Novel_Idea"
    INTEGRITY_RISK = "Integrity_Risk"
    COMM_DEGRADED = "Comm_Degraded"
    AMBIGUITY = "Ambiguity"
    RESONANCE = "Resonance"
    DRIFT = "Drift"

@dataclass
class UnknownGradient:
    type: UnknownType
    magnitude: float
    context_note: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type.value if isinstance(self.type, UnknownType) else self.type,
            "magnitude": self.magnitude,
            "context_note": self.context_note
        }

@dataclass
class IntentPacket:
    payload: Any
    source: str
    target: str
    confidence: float
    unknowns: List[UnknownGradient] = field(default_factory=list)
    wcr_tick: str = ""
    mood: Dict[str, float] = field(default_factory=dict)

@dataclass
class RegistryEntry:
    name: str
    dialect: str
    """
    bias_vector: List[float] of length 8.
    [0] source_unknown_prominence: How strongly outgoing packets inflate unknown magnitudes.
    [1] target_unknown_tolerance: How strongly incoming unknowns are suppressed.
    [2-7] Reserved for future calibration: semantic drift resistance, metaphor affinity, etc.
    """
    bias_vector: List[float]
    base_intent: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None