# v1rg0_core/v1rg0_salience_engine.py
# V1rG0 - Autonomic Memory System (Push/Pull Core)
# Token budget: 5/5

from dataclasses import dataclass, asdict
from typing import Dict, Optional

@dataclass
class SalienceScore:
    survival: float = 0.0
    resonance: float = 0.0
    routine: float = 0.0

    def composite(self) -> float:
        return (self.survival * 0.55 + self.resonance * 0.35 + self.routine * 0.10)

class UAT:
    """Unified Acceptance Threshold - Salience Scoring (Push/Pull)"""

    def __init__(self):
        self.last_score: Optional[SalienceScore] = None

    def assess(self, event: Dict) -> SalienceScore:
        """Primary PUSH: Score an event and push the result."""
        score = SalienceScore()
        score.survival = self._assess_survival(event)
        score.resonance = self._assess_resonance(event)
        score.routine = self._assess_routine(event)
        self.last_score = score
        return score

    def pull_assessment(self) -> Optional[SalienceScore]:
        """PULL: Return the last assessment if requested by Orchestrator."""
        return self.last_score

    def _assess_survival(self, event: Dict) -> float:
        severity = event.get("severity", 0)
        cascade = event.get("cascade_risk", False)
        if severity >= 4 or cascade:
            return 1.0
        return severity * 0.25

    def _assess_resonance(self, event: Dict) -> float:
        truth = event.get("truth_density", 0)
        axiom = event.get("axiom_alignment", False)
        return (truth * 0.7) + (0.3 if axiom else 0)

    def _assess_routine(self, event: Dict) -> float:
        pattern = event.get("pattern_match_rate", 1.0)
        return 1.0 - pattern  # Inverse: high pattern = low salience
