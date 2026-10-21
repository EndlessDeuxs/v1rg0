# auth_suit.py
from __future__ import annotations
from typing import Dict
from pulse import PulseBus, PulseSignal
from contract_registry import ContractRegistry

class AuthSuit:
    SUIT_ID = "auth_suit"

    def __init__(self, pulse_bus: PulseBus, valid_keys: Dict[str, str]):
        """
        valid_keys: {api_key: principal_id}
        """
        self.pulse_bus = pulse_bus
        self.valid_keys = valid_keys

        ContractRegistry().register_suit(
            self.SUIT_ID,
            {
                "input": {
                    "type": "auth_request",
                    "required_fields": [
                        "request_id", "endpoint", "method", "payload",
                        "api_key", "timestamp"
                    ],
                },
                "output": {
                    "type": "auth_result",
                    "required_fields": ["request_id", "authorized", "principal"],
                },
            }
        )

        pulse_bus.subscribe("auth_request", self._handle_auth_request)

    def _handle_auth_request(self, signal: PulseSignal):
        payload = signal.payload
        api_key = payload.get("api_key")
        request_id = payload.get("request_id")

        principal = self.valid_keys.get(api_key)
        authorized = principal is not None

        self.pulse_bus.emit(
            self.SUIT_ID,
            "auth_result",
            {
                "request_id": request_id,
                "authorized": authorized,
                "principal": principal,
                "reason": None if authorized else "invalid_api_key",
            }
        )

class APIGateway:
    SUIT_ID = "api_gateway"

    def __init__(self, pulse_bus: PulseBus, require_auth: bool = True):
        self.pulse_bus = pulse_bus
        self.require_auth = require_auth
        self._pending_requests: dict[str, dict] = {}

        ContractRegistry().register_suit(
            self.SUIT_ID,
            {
                "input": {
                    "type": "api_request",
                    "required_fields": [
                        "endpoint", "method", "payload",
                        # gateway-level view; auth fields are treated as metadata
                    ],
                },
                "output": {
                    "type": "api_response",
                    "required_fields": ["request_id", "status", "data"],
                },
            }
        )

        attach_contract_middleware(pulse_bus, self.SUIT_ID)

        pulse_bus.subscribe("api_response", self._handle_response)
        pulse_bus.subscribe("design_ready", self._handle_design_response)
        pulse_bus.subscribe("validation_result", self._handle_validation_response)
        pulse_bus.subscribe("auth_result", self._handle_auth_result)

    def receive_request(
        self,
        endpoint: str,
        method: str,
        payload: dict | None = None,
        api_key: str | None = None,
    ) -> str:
        request_id = str(uuid.uuid4())[:12]
        timestamp = datetime.now().isoformat()
        payload = payload or {}

        self._pending_requests[request_id] = {
            "endpoint": endpoint,
            "method": method,
            "payload": payload,
            "api_key": api_key,
            "timestamp": timestamp,
            "status": "processing",
            "authorized": not self.require_auth,  # bypass for health if needed
        }

        # MemoryStore logging via api_request
        self.pulse_bus.emit(
            self.SUIT_ID,
            "api_request",
            {
                "request_id": request_id,
                "endpoint": endpoint,
                "method": method,
                "payload": payload,
                "timestamp": timestamp,
            }
        )

        # Short-circuit health: no auth required
        if endpoint == "/health":
            self._route_internal(endpoint, request_id, payload)
            return request_id

        if self.require_auth:
            # delegate to AuthSuit
            self.pulse_bus.emit(
                self.SUIT_ID,
                "auth_request",
                {
                    "request_id": request_id,
                    "endpoint": endpoint,
                    "method": method,
                    "payload": payload,
                    "api_key": api_key,
                    "timestamp": timestamp,
                }
            )
        else:
            self._route_internal(endpoint, request_id, payload)

        return request_id

    def _handle_auth_result(self, signal: PulseSignal):
        payload = signal.payload
        request_id = payload.get("request_id")
        if not request_id or request_id not in self._pending_requests:
            return

        if not payload.get("authorized", False):
            self._return_response(
                request_id,
                401,
                {"error": "unauthorized", "reason": payload.get("reason")},
            )
            return

        # mark as authorized and proceed with routing
        self._pending_requests[request_id]["authorized"] = True
        record = self._pending_requests[request_id]
        self._route_internal(
            record["endpoint"], request_id, record["payload"]
        )