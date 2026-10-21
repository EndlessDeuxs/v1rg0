# api_gateway.py
# V1rG0 API Gateway with Council Patches Applied
# Patches from WCR set 2026-07-03 integrated for stability
# Standardized on V1rG0 pulse bus (from pulse import PulseBus, PulseSignal)
# Async-first design with synchronous fallback patterns where needed

import json
import uuid
import hmac
import hashlib
import time
import re
import threading
from datetime import datetime
from pulse import PulseBus, PulseSignal
from contract_registry import ContractRegistry, attach_contract_middleware

# =============================================================================
# PATCH NOTES (from council - applied below)
# 1. Response echo loop fix (pop before emit + source guard)
# 2. _handle_response source check
# 3. /v1/ prefix normalization + explicit 404 fallthrough with route_error
# 4. TTL eviction for _completed_requests
# 5. DLQ backoff helper (for dlq_handler integration)
# 6. Terminal failure mapping (example _handle_concept_error pattern)
# =============================================================================

class AuthSuit:
    SUIT_ID = "auth_suit"
    _keys = {"test_key_001": "test_secret_001"}
    
    @classmethod
    def validate_request(cls, api_key: str, signature: str, payload: str, timestamp: int) -> bool:
        if api_key not in cls._keys:
            return False
        if abs(time.time() - timestamp) > 300:
            return False
        expected = hmac.new(
            cls._keys[api_key].encode(), 
            f"{timestamp}{payload}".encode(), 
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

class APIGateway:
    SUIT_ID = "api_gateway"
    
    def __init__(self, pulse_bus: PulseBus):
        self.pulse_bus = pulse_bus
        # Patch 1 & 4: Separate pending and completed for safe response handling
        self._pending_requests: dict[str, dict] = {}
        self._completed_requests: dict[str, dict] = {}
        
        ContractRegistry().register_suit(self.SUIT_ID, {
            "input": {"type": "api_request", "required_fields": ["endpoint", "method", "payload"]},
            "output": {"type": "api_response", "required_fields": ["request_id", "status", "data"]}
        })
        attach_contract_middleware(pulse_bus, self.SUIT_ID)
        
        # Subscribe to responses (with guard in handler)
        pulse_bus.subscribe("api_response", self._handle_response)
        pulse_bus.subscribe("design_ready", self._handle_design)
        pulse_bus.subscribe("validation_result", self._handle_validation)
        # Example terminal error subscriptions (Patch 6 pattern)
        pulse_bus.subscribe("concept_transform_failed", self._handle_concept_error)
        # Add more as downstream suits emit *_failed events
    
    # PATCH 1: Pop BEFORE emit to break echo loop. Also calls eviction (Patch 4)
    def _return_response(self, request_id: str, status: int, data: dict):
        if request_id not in self._pending_requests:
            return  # Already resolved or never existed
        
        record = self._pending_requests.pop(request_id)
        record["status"] = "completed"
        record["response"] = {"status": status, "data": data}
        self._completed_requests[request_id] = record
        
        # Patch 4: Schedule TTL eviction from completed
        self._schedule_eviction(request_id, 300)
        
        # NOW emit - no longer in pending, loop broken
        self.pulse_bus.emit(
            self.SUIT_ID,
            "api_response",
            {
                "request_id": request_id,
                "status": status,
                "data": data,
                "timestamp": datetime.now().isoformat(),
            },
        )
    
    # PATCH 2: Guard against processing our own emissions
    def _handle_response(self, signal: PulseSignal):
        if signal.source_suit == self.SUIT_ID:
            return  # Do not process our own api_response emissions
        p = signal.payload
        rid = p.get("request_id")
        if rid and rid in self._pending_requests:
            # Move to completed via _return_response pattern or direct
            # For signals coming from bus, we can update directly
            record = self._pending_requests.pop(rid)
            record["status"] = "completed"
            record["response"] = {"status": p.get("status", 200), "data": p.get("data", {})}
            self._completed_requests[rid] = record
            self._schedule_eviction(rid, 300)
    
    def _handle_design(self, signal: PulseSignal):
        p = signal.payload
        rid = p.get("request_id")
        if rid and rid in self._pending_requests:
            self._return_response(rid, 200, {
                "type": "design", 
                "design_id": p.get("design_id"), 
                "specification": p.get("specification"), 
                "timestamp": p.get("timestamp")
            })
    
    def _handle_validation(self, signal: PulseSignal):
        p = signal.payload
        rid = p.get("request_id")
        if rid and rid in self._pending_requests:
            status = 200 if p.get("valid") else 400
            self._return_response(rid, status, {
                "type": "validation", 
                "design_id": p.get("design_id"), 
                "valid": p.get("valid", False), 
                "issues": p.get("issues", [])
            })
    
    # PATCH 6 pattern: Terminal failure from downstream
    def _handle_concept_error(self, signal: PulseSignal):
        payload = signal.payload
        request_id = payload.get("request_id")
        if request_id and request_id in self._pending_requests:
            self._return_response(
                request_id,
                500,
                {"error": "concept_transform_failed", "reason": payload.get("reason")}
            )
    
    # PATCH 3: Normalize version prefix so internal routing stays clean
    def _normalize_endpoint(self, endpoint: str) -> str:
        return re.sub(r"^/v\d+", "", endpoint)
    
    # PATCH 3: Explicit fallthrough with route_error event + 404 response
    def _route_internal(self, endpoint: str, request_id: str, payload: dict):
        normalized = self._normalize_endpoint(endpoint)
        
        if normalized.startswith("/concept"):
            self.pulse_bus.emit(self.SUIT_ID, "transform_concept", {
                "request_id": request_id, 
                "type": "concept", 
                "concept_id": payload.get("concept_id", f"CON-{request_id}"), 
                "description": payload.get("description", ""), 
                "source": "api_gateway"
            })
        elif normalized.startswith("/design"):
            self.pulse_bus.emit(self.SUIT_ID, "validate_design", {
                "request_id": request_id, 
                "design_id": payload.get("design_id"), 
                "specification": payload.get("specification", {})
            })
        elif normalized.startswith("/proposal"):
            self.pulse_bus.emit(self.SUIT_ID, "propose", {
                "request_id": request_id, 
                "proposal_id": payload.get("proposal_id"), 
                "signal_id": payload.get("signal_id")
            })
        elif normalized.startswith("/health"):
            self._return_response(request_id, 200, {
                "status": "healthy", 
                "timestamp": datetime.now().isoformat()
            })
        # NOTE: /memory shelved per council for this sprint (no query-response path yet)
        else:
            # Explicit fallthrough - no silent hangs, emit error event too
            self.pulse_bus.emit(
                self.SUIT_ID,
                "route_error",
                {
                    "request_id": request_id,
                    "endpoint": endpoint,
                    "reason": "no_matching_route",
                    "timestamp": datetime.now().isoformat(),
                },
            )
            self._return_response(
                request_id, 404, {"error": "endpoint_not_found", "endpoint": endpoint}
            )
    
    # PATCH 4: TTL eviction from _completed_requests
    def _schedule_eviction(self, request_id: str, ttl_seconds: int = 300):
        def evict():
            self._completed_requests.pop(request_id, None)
        t = threading.Timer(ttl_seconds, evict)
        t.daemon = True
        t.start()
    
    # PATCH 5 helper (for dlq_handler integration - returns ms, capped 30s)
    def _calculate_retry_delay(self, attempt: int) -> int:
        return min((2 ** attempt) * 100, 30000)
    
    def receive(self, endpoint: str, method: str, payload: dict = None, 
                api_key: str = None, signature: str = None, timestamp: int = 0) -> str:
        rid = str(uuid.uuid4())[:12]
        if api_key and not AuthSuit.validate_request(api_key, signature, json.dumps(payload or {}), timestamp):
            self._return_response(rid, 401, {"error": "unauthorized"})
            return rid
        
        self._pending_requests[rid] = {
            "endpoint": endpoint, 
            "method": method, 
            "payload": payload, 
            "timestamp": datetime.now().isoformat(), 
            "status": "processing"
        }
        
        self.pulse_bus.emit(self.SUIT_ID, "api_request", {
            "request_id": rid, 
            "endpoint": endpoint, 
            "method": method, 
            "payload": payload or {}, 
            "timestamp": self._pending_requests[rid]["timestamp"]
        })
        
        self._route_internal(endpoint, rid, payload or {})
        return rid
    
    def get_response(self, rid: str) -> dict | None:
        # Per Patch 1: Prefer completed, fall back to pending if still processing
        if rid in self._completed_requests:
            return self._completed_requests[rid].get("response")
        return self._pending_requests.get(rid, {}).get("response")

# End of patched APIGateway
# Usage: pulse_bus = PulseBus(); gateway = APIGateway(pulse_bus)
# Then gateway.receive(...) and poll get_response(rid)