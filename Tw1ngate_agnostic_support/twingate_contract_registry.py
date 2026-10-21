# contract_registry.py
from __future__ import annotations
from functools import wraps
from typing import Any, Callable
import logging

logger = logging.getLogger(__name__)

class ContractViolationError(Exception):
    pass

class ContractRegistry:
    _instance: ContractRegistry | None = None
    _contracts: dict[str, dict] = {}

    def __new__(cls) -> ContractRegistry:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._contracts = {}
        return cls._instance

    def register_suit(self, suit_id: str, contract: dict) -> None:
        self._contracts[suit_id] = contract

    def validate(self, suit_id: str, direction: str, data: dict) -> tuple[bool, list[str]]:
        contract = self._contracts.get(suit_id)
        if not contract:
            return False, [f"No contract registered for suit: {suit_id}"]
        schema = contract.get(direction)
        if not schema:
            return True, []
        issues: list[str] = []
        expected_type = schema.get("type")
        if expected_type and data.get("type") != expected_type:
            issues.append(f"Type mismatch: expected '{expected_type}', got '{data.get('type')}'")
        for f in schema.get("required_fields", []):
            if f not in data:
                issues.append(f"Missing required field: '{f}'")
        for f, constraint in schema.get("constraints", {}).items():
            if f in data:
                if "max_length" in constraint and len(str(data[f])) > constraint["max_length"]:
                    issues.append(f"Field '{f}' exceeds max_length={constraint['max_length']}")
        return len(issues) == 0, issues

    def registered_suits(self) -> list[str]:
        return list(self._contracts.keys())

def enforce_contract(suit_id: str, direction: str) -> Callable:
    registry = ContractRegistry()
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            data_candidate = args[0] if args else kwargs.get("data", {})
            payload = getattr(data_candidate, "payload", data_candidate)
            valid, issues = registry.validate(suit_id, direction, payload)
            if not valid:
                raise ContractViolationError(f"{suit_id}.{direction} contract violated: {issues}")
            result = func(*args, **kwargs)
            if direction == "input" and result is not None:
                out_valid, out_issues = registry.validate(suit_id, "output", result if isinstance(result, dict) else {})
                if not out_valid:
                    raise ContractViolationError(f"{suit_id}.output contract violated: {out_issues}")
            return result
        return wrapper
    return decorator

def attach_contract_middleware(pulse_bus, suit_id: str) -> None:
    registry = ContractRegistry()
    original_subscribe = pulse_bus.subscribe
    def guarded_subscribe(event_type: str, handler: Callable) -> None:
        @wraps(handler)
        def contract_aware_handler(signal) -> None:
            valid, issues = registry.validate(suit_id, "input", signal.payload)
            if not valid:
                pulse_bus.emit(suit_id, "contract_violation", {
                    "suit_id": suit_id,
                    "event_type": event_type,
                    "signal_id": signal.signal_id,
                    "issues": issues,
                })
                return
            handler(signal)
        original_subscribe(event_type, contract_aware_handler)
    pulse_bus.subscribe = guarded_subscribe