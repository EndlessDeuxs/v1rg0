#Communications_Pathways
# FILENAME: UIT_registry_core.py
"""
UIT Core Registry – The Decoder Ring
Holds profiles for all known sources and targets.
"""
import json
import os
from typing import Dict, Optional
from .UIT_interfaces import RegistryEntry, IntentPacket

REGISTRY_PATH = os.path.join(os.path.dirname(__file__), "uit_registry.json")

DEFAULT_REGISTRY = {
    "user": RegistryEntry(name="user", dialect="casual", bias_vector=[0.5, 0.3, 0.2, 0.1, 0.1, 0.0, 0.0, 0.0], notes="Human user – often ambiguous, emotional, or fragmented."),
    "alpha": RegistryEntry(name="alpha", dialect="technical", bias_vector=[0.1, 0.2, 0.3, 0.4, 0.5, 0.3, 0.2, 0.1], notes="Planner – prefers structure, sequence, and clarity."),
    "beta": RegistryEntry(name="beta", dialect="critical", bias_vector=[0.3, 0.5, 0.4, 0.2, 0.1, 0.3, 0.4, 0.5], notes="Critic/Fracture – high sensitivity to edge cases and failure modes."),
    "gamma": RegistryEntry(name="gamma", dialect="fluid", bias_vector=[0.2, 0.1, 0.5, 0.4, 0.3, 0.5, 0.4, 0.3], notes="Drift – associative, metaphorical, context-sensitive."),
    "delta": RegistryEntry(name="delta", dialect="grounded", bias_vector=[0.6, 0.4, 0.1, 0.1, 0.2, 0.1, 0.2, 0.3], notes="Anchor – empirical, stable, reduces uncertainty."),
    "krypton": RegistryEntry(name="krypton", dialect="expansive", bias_vector=[0.2, 0.3, 0.2, 0.3, 0.5, 0.6, 0.5, 0.4], notes="Explorer – pushes boundaries, seeks novel connections."),
    "omega": RegistryEntry(name="omega", dialect="integrative", bias_vector=[0.1, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.5], notes="Condens.or – integrates, decides, closes loops."),
    "synthesiz_r": RegistryEntry(name="synthesiz_r", dialect="layman", bias_vector=[0.0, 0.1, 0.2, 0.5, 0.6, 0.7, 0.6, 0.5], notes="Synthesiz.r – highly accessible, strips jargon, highlights unknowns."),
    "analytics": RegistryEntry(name="analytics", dialect="analytical", bias_vector=[0.4, 0.5, 0.3, 0.2, 0.1, 0.1, 0.1, 0.1], notes="DeepSeek analytics – parses intent, tracks goals."),
    "ui_output": RegistryEntry(name="ui_output", dialect="concise", bias_vector=[0.1, 0.2, 0.3, 0.2, 0.3, 0.2, 0.3, 0.2], notes="External UI output – prioritizes clarity and explicit risk signaling. Unknowns are visible, not suppressed.")
}

class UIRegistry:
    def __init__(self, path: str = REGISTRY_PATH):
        self.path = path
        self.entries = self._load()

    def _load(self) -> Dict[str, RegistryEntry]:
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return {k: RegistryEntry(**v) for k, v in data.items()}
            except Exception:
                pass
        return DEFAULT_REGISTRY.copy()

    def save(self):
        data = {k: v.__dict__ for k, v in self.entries.items()}
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)

    def get(self, name: str) -> Optional[RegistryEntry]:
        return self.entries.get(name.lower())

    def update(self, name: str, entry: RegistryEntry):
        self.entries[name.lower()] = entry
        self.save()