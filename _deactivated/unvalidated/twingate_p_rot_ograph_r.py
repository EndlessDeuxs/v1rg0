# p_rot_ograph_r.py
from __future__ import annotations
from contract_registry import ContractRegistry, attach_contract_middleware, enforce_contract
from pulse import PulseBus, PulseSignal
import logging
import uuid
import re

logger = logging.getLogger(__name__)

class P_rot_ograph_r:
    SUIT_ID = "p_rot_ograph_r"

    def __init__(self, pulse_bus: PulseBus) -> None:
        self.pulse_bus = pulse_bus
        ContractRegistry().register_suit(self.SUIT_ID, {
            "input": {
                "type": "concept",
                "required_fields": ["concept_id", "description"],
                "constraints": {"description": {"max_length": 2000}, "concept_id": {"max_length": 64}},
            },
            "output": {
                "type": "design",
                "required_fields": ["design_id", "specification", "timestamp", "origin_concept_id"],
            },
        })
        attach_contract_middleware(pulse_bus, self.SUIT_ID)
        pulse_bus.subscribe("transform", self._transform_concept)

    @enforce_contract(SUIT_ID, "output")
    def _transform_concept(self, signal: PulseSignal) -> dict:
        concept = signal.payload
        parsed = self._parse_concept(concept["description"])
        mapped = self._map_to_primitives(parsed, concept["concept_id"])
        specification = self._assemble_specification(mapped)
        design = {
            "type": "design",
            "design_id": f"DES-{concept['concept_id']}-{uuid.uuid4().hex[:4]}",
            "specification": specification,
            "timestamp": signal.timestamp,
            "origin_concept_id": concept["concept_id"],
        }
        self.pulse_bus.emit(self.SUIT_ID, "design_ready", design)
        return design

    def _parse_concept(self, description: str) -> dict:
        elements = {"entities": [], "actions": [], "relationships": [], "constraints": [], "raw_text": description}
        words = description.lower().split()
        capitalized = re.findall(r'\b[A-Z][a-z]+\b', description)
        elements["entities"] = [w for w in capitalized if len(w) > 2]
        action_indicators = ["create", "transform", "connect", "validate", "route", "store", "emit", "pull", "push"]
        elements["actions"] = [w for w in words if w in action_indicators]
        rel_indicators = ["to", "from", "through", "via", "between", "into"]
        elements["relationships"] = [w for w in words if w in rel_indicators]
        constraint_indicators = ["must", "should", "required", "optional", "always", "never", "only", "max", "min"]
        elements["constraints"] = [w for w in words if w in constraint_indicators]
        return elements

    def _map_to_primitives(self, parsed: dict, concept_id: str) -> dict:
        primitives = {"nodes": [], "edges": [], "operations": [], "rules": [], "origin": concept_id}
        for entity in parsed.get("entities", []):
            primitives["nodes"].append({"id": f"node-{entity.lower()}", "label": entity, "type": "component"})
        for action in parsed.get("actions", []):
            primitives["operations"].append({"id": f"op-{action}", "type": action, "target": None})
        for rel in parsed.get("relationships", []):
            primitives["edges"].append({"id": f"edge-{rel}", "type": rel, "source": None, "target": None})
        for constraint in parsed.get("constraints", []):
            primitives["rules"].append({
                "id": f"rule-{constraint}",
                "type": constraint,
                "severity": "required" if constraint in ["must", "required"] else "advisory",
            })
        return primitives

    def _assemble_specification(self, mapped: dict) -> dict:
        for edge in mapped.get("edges", []):
            if mapped["nodes"]:
                edge["source"] = mapped["nodes"][0]["id"]
                edge["target"] = mapped["nodes"][-1]["id"] if len(mapped["nodes"]) > 1 else mapped["nodes"][0]["id"]
        for op in mapped.get("operations", []):
            if mapped["nodes"]:
                op["target"] = mapped["nodes"][0]["id"]
        return {
            "architecture": {"nodes": mapped["nodes"], "edges": mapped["edges"]},
            "behavior": {"operations": mapped["operations"], "flow": [op["type"] for op in mapped["operations"]]},
            "constraints": {"rules": mapped["rules"], "summary": f"{len(mapped['rules'])} rules defined"},
            "metadata": {"version": "1.0", "origin_concept": mapped["origin"], "structure": "parsed", "timestamp": __import__("time").time()},
        }