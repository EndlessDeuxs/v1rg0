#Communications_Pathways
# FILENAME: UIT_comms_synthesizor.py
"""
UIT Synthesiz.or Comms – Beat 5 Handoff
Dedicated interface for the final synthesis step.
"""
from typing import Dict, Optional
from .UIT_interfaces import IntentPacket, UnknownGradient, UnknownType
from .UIT_function_translate import UITranslator
from .UIT_registry_core import UIRegistry

class SynthesizorComms:
    def __init__(self, translator: Optional[UITranslator] = None):
        self.translator = translator or UITranslator()

    def prepare_for_output(self, council_synthesis: str, wcr_tick: str = "", upstream_confidence: float = 0.9) -> Dict:
        packet = IntentPacket(
            payload=council_synthesis,
            source="synthesizor",
            target="ui_output",
            confidence=upstream_confidence,
            wcr_tick=wcr_tick
        )
        translated, confidence = self.translator.translate(packet)
        output = {
            "synthesis": translated.payload,
            "confidence": confidence,
            "unknowns": [u.to_dict() for u in translated.unknowns],
            "wcr_tick": wcr_tick,
            "status": "finalized"
        }
        return output