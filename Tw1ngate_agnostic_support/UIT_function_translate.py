#Communications_Pathways
# FILENAME: UIT_function_translate.py
"""
UIT Translation Engine – The Decoder Ring in Action
Source → Baseline → Target translation with confidence tracking.
"""
from typing import Optional, Tuple
from .UIT_interfaces import IntentPacket, UnknownGradient, UnknownType, RegistryEntry
from .UIT_registry_core import UIRegistry
from .UIT_registry_unknowns import UnknownRegistry

class UITranslator:
    def __init__(self, registry: Optional[UIRegistry] = None):
        self.registry = registry or UIRegistry()
        self.unknown_registry = UnknownRegistry()

    def translate(self, packet: IntentPacket) -> Tuple[IntentPacket, float]:
        source_profile = self.registry.get(packet.source)
        target_profile = self.registry.get(packet.target)

        if not source_profile:
            self.unknown_registry.log(UnknownGradient(UnknownType.AMBIGUITY, 0.7, f"Unknown source: {packet.source}"))
            return packet, 0.4
        if not target_profile:
            raise KeyError(f"[ERR-WCR-04] / [SEV-3: ELEVATED]: UIT_DIALECT_FAULT - Unknown target profile: {packet.target}")

        decoded = self._apply_source_bias(packet, source_profile)
        translated = self._apply_target_bias(decoded, target_profile)
        confidence = self._compute_confidence(packet, translated, source_profile, target_profile)

        return translated, confidence

    def _apply_source_bias(self, packet: IntentPacket, profile: RegistryEntry) -> IntentPacket:
        adjusted_unknowns = []
        for u in packet.unknowns:
            adjusted_mag = min(1.0, u.magnitude + (0.1 * (1 - profile.bias_vector[0])))
            adjusted_unknowns.append(UnknownGradient(u.type, adjusted_mag, u.context_note))

        return IntentPacket(
            payload=packet.payload, source=packet.source, target=packet.target,
            confidence=packet.confidence, unknowns=adjusted_unknowns,
            wcr_tick=packet.wcr_tick, mood=packet.mood
        )

    def _apply_target_bias(self, packet: IntentPacket, profile: RegistryEntry) -> IntentPacket:
        adjusted_unknowns = []
        for u in packet.unknowns:
            adapted_mag = min(1.0, u.magnitude * (0.9 + 0.1 * profile.bias_vector[1]))
            adjusted_unknowns.append(UnknownGradient(u.type, adapted_mag, u.context_note))

        return IntentPacket(
            payload=packet.payload, source=packet.source, target=packet.target,
            confidence=packet.confidence, unknowns=adjusted_unknowns,
            wcr_tick=packet.wcr_tick, mood=packet.mood
        )

    def _compute_confidence(self, original: IntentPacket, translated: IntentPacket, source: RegistryEntry, target: RegistryEntry) -> float:
        base_conf = original.confidence
        dialect_diff = 1.0 - (source.dialect == target.dialect)
        mismatch_penalty = 0.15 * (dialect_diff)
        unknown_penalty = min(0.3, 0.05 * len(original.unknowns))
        return max(0.1, min(1.0, base_conf - mismatch_penalty - unknown_penalty))