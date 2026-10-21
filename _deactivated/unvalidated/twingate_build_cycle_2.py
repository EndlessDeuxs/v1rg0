
import json
import hashlib
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple

# --- Core Data Structures ---

class SectorHealth:
    def __init__(self, sector_id: str, anomaly_score: float, timestamp: float):
        self.sector_id = sector_id
        self.anomaly_score = anomaly_score
        self.timestamp = timestamp

class DataFragment:
    def __init__(self, fragment_id: str, degradation: float, content_type: str, significance: float):
        self.fragment_id = fragment_id
        self.degradation = degradation
        self.content_type = content_type
        self.significance = significance

@dataclass
class SurplusState:
    current_surplus: float
    assumed_surplus: float
    timestamp: float

# --- Directive 1: Adaptive Allocation Frame ---

class AdaptiveBufferAllocator:
    def __init__(self, default_ratio: Tuple[float, float] = (0.7, 0.3)):
        self.default_ratio = default_ratio
        self.current_ratio = default_ratio
        self.primary_buffer = 0.0
        self.secondary_buffer = 0.0
        self.verification_threshold = 0.05  # 5% deviation allowed

    def verify_surplus(self, state: SurplusState) -> bool:
        deviation = abs(state.current_surplus - state.assumed_surplus) / state.assumed_surplus
        return deviation <= self.verification_threshold

    def allocate(self, state: SurplusState) -> Dict[str, float]:
        if not self.verify_surplus(state):
            # Fallback: use default ratio if verification fails
            self.current_ratio = self.default_ratio
        else:
            # Recalculate based on current surplus
            self.current_ratio = (0.7, 0.3)  # Simplified; could be dynamic

        primary = state.current_surplus * self.current_ratio[0]
        secondary = state.current_surplus * self.current_ratio[1]
        self.primary_buffer += primary
        self.secondary_buffer += secondary
        return {"primary": primary, "secondary": secondary}

# --- Directive 2: Mobile Diagnostic Chassis ---

class MobileDiagnosticChassis:
    def __init__(self):
        self.target_sector = "7-Gamma"
        self.health_data: Optional[SectorHealth] = None
        self.data_freshness_threshold = 1.0  # cycles

    def load_health_data(self, data: SectorHealth):
        self.health_data = data

    def determine_target(self, current_cycle: float) -> str:
        if self.health_data is None:
            return self.target_sector  # default fallback

        age = current_cycle - self.health_data.timestamp
        if age > self.data_freshness_threshold:
            return self.target_sector  # stale data fallback

        # Check if another sector has higher anomaly score
        # Simplified: assume we have a global health index
        return self.target_sector  # placeholder for actual logic

    def deploy_sweep(self, sector: str) -> Dict[str, any]:
        return {
            "sector": sector,
            "status": "deployed",
            "tooling": ["conduit_integrity", "power_relay_inspection"]
        }

# --- Directive 3: Two-Axis Triage System ---

class FragmentTriageSystem:
    def __init__(self, degradation_threshold: float = 0.9, significance_threshold: float = 0.5):
        self.degradation_threshold = degradation_threshold
        self.significance_threshold = significance_threshold
        self.vault: List[DataFragment] = []
        self.purge_list: List[str] = []
        self.scoring_log: List[Dict] = []

    def score_significance(self, fragment: DataFragment) -> float:
        # Transparent scoring algorithm
        content_weights = {
            "blueprint": 1.0,
            "log": 0.3,
            "config": 0.7,
            "anomaly": 0.9,
            "redundant": 0.1
        }
        base_score = content_weights.get(fragment.content_type, 0.5)
        # Combine with degradation (higher degradation reduces significance slightly)
        adjusted_score = base_score * (1.0 - fragment.degradation * 0.1)
        self.scoring_log.append({
            "fragment_id": fragment.fragment_id,
            "content_type": fragment.content_type,
            "base_score": base_score,
            "adjusted_score": adjusted_score
        })
        return adjusted_score

    def triage(self, fragment: DataFragment) -> str:
        significance = self.score_significance(fragment)
        if fragment.degradation > self.degradation_threshold:
            if significance > self.significance_threshold:
                self.vault.append(fragment)
                return "vault"
            else:
                self.purge_list.append(fragment.fragment_id)
                return "purge"
        else:
            return "pass"

    def execute_purge(self) -> List[str]:
        purged = self.purge_list.copy()
        self.purge_list.clear()
        return purged

    def review_vault(self, council_flags: List[str]) -> List[str]:
        # Vault review: fragments flagged by council are preserved
        preserved = []
        for frag in self.vault:
            if frag.fragment_id in council_flags:
                preserved.append(frag.fragment_id)
            else:
                self.purge_list.append(frag.fragment_id)
        self.vault = [f for f in self.vault if f.fragment_id in preserved]
        return self.execute_purge()

# --- Main Execution ---

def execute_cycle():
    # Initialize components
    allocator = AdaptiveBufferAllocator()
    chassis = MobileDiagnosticChassis()
    triage = FragmentTriageSystem()

    # Simulate state
    surplus_state = SurplusState(
        current_surplus=1000.0,
        assumed_surplus=950.0,
        timestamp=1.0
    )

    # Directive 1
    allocation = allocator.allocate(surplus_state)
    print(f"Allocation: {allocation}")

    # Directive 2
    chassis.load_health_data(SectorHealth("7-Gamma", 0.8, 0.5))
    target = chassis.determine_target(current_cycle=1.0)
    sweep = chassis.deploy_sweep(target)
    print(f"Sweep: {sweep}")

    # Directive 3
    fragments = [
        DataFragment("frag1", 0.95, "blueprint", 0.0),
        DataFragment("frag2", 0.92, "log", 0.0),
        DataFragment("frag3", 0.88, "config", 0.0),
    ]
    for frag in fragments:
        result = triage.triage(frag)
        print(f"Fragment {frag.fragment_id}: {result}")

    purged = triage.execute_purge()
    print(f"Purged: {purged}")

    # Vault review with council flags
    council_flags = ["frag1"]  # Example: council flags fragment for preservation
    final_purge = triage.review_vault(council_flags)
    print(f"Final purge after review: {final_purge}")

    # Output scoring log for transparency
    print(f"Scoring log: {json.dumps(triage.scoring_log, indent=2)}")

if __name__ == "__main__":
    execute_cycle()