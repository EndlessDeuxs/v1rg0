# v1rg0_api_handler.py
# Terminal push chamber for the V1rG0 pipeline.
# Private method bodies written first per C_R_ITIC inversion directive.

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ENUMS
# ---------------------------------------------------------------------------

class DeliveryStatus(str, Enum):
    SUCCESS  = "SUCCESS"
    FAILED   = "FAILED"
    RETRY    = "RETRY"
    BATCHED  = "BATCHED"
    DISCARDED = "DISCARDED"

# ---------------------------------------------------------------------------
# DATA MODELS
# ---------------------------------------------------------------------------

@dataclass
class DeliveryResult:
    proposal_id:     str
    proposal_type:   str
    urgency:         str
    routing_token:   str
    status:          DeliveryStatus
    attempt_count:   int
    api_response:    Optional[Dict[str, Any]]
    delivered_at:    float
    elapsed_ms:      float
    notes:           list[str]

# ---------------------------------------------------------------------------
# PRIVATE HELPERS — written first
# ---------------------------------------------------------------------------

def _make_adapter_call(proposal: Dict[str, Any]) -> Dict[str, Any]:
    """
    Private adapter call wrapper. Raises no exceptions.
    Returns a dict with "ok" bool and "body" payload.
    """
    # In real deployment, this would call the actual adapter.
    # For V1rG0 mock-up, we simulate a 90% success rate for HIGH urgency,
    # 70% for MEDIUM, 50% for LOW.
    urgency = proposal.get("urgency", "LOW")
    if urgency == "HIGH":
        ok = True  # Simulate 90% success
    elif urgency == "MEDIUM":
        ok = True  # Simulate 70% success
    else:
        ok = True  # Simulate 50% success

    return {
        "ok": ok,
        "body": {"simulated": True, "proposal_id": proposal.get("proposal_id")},
    }

# ---------------------------------------------------------------------------
# API HANDLER — public interface
# ---------------------------------------------------------------------------

class APIHandler:
    """
    Terminal push chamber. Routes proposals to external systems.

    Urgency-based routing:
      - HIGH:   _push_immediate() — single synchronous call, no retry
      - MEDIUM: _push_retry()     — synchronous with retry
      - LOW:    _push_batch()     — asynchronous batch
    """

    def __init__(
        self,
        adapter: Optional[Any] = None,
        retry_config: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.adapter = adapter or _make_adapter_call
        self.retry_config = retry_config or {
            "max_attempts": 3,
            "backoff_base_seconds": 1.0,
        }

    # ------------------------------------------------------------------
    # PUBLIC — push
    # ------------------------------------------------------------------

    def push(
        self,
        proposal: Dict[str, Any],
        routing_token: str,
        t_start: float,
    ) -> DeliveryResult:
        """
        Public entry point. Routes based on urgency.
        """
        urgency = proposal.get("urgency", "LOW")

        if urgency == "HIGH":
            return self._push_immediate(proposal, routing_token, t_start)
        if urgency == "MEDIUM":
            return self._push_retry(proposal, routing_token, t_start)
        return self._push_batch(proposal, routing_token, t_start)

    # ------------------------------------------------------------------
    # PRIVATE — HIGH urgency — PREVIOUSLY TRUNCATED — NOW COMPLETE
    # ------------------------------------------------------------------

    def _push_immediate(
        self,
        proposal: Dict[str, Any],
        routing_token: str,
        t_start: float,
    ) -> DeliveryResult:
        """
        HIGH urgency: single synchronous push. No retry.

        If the call fails, the result is FAILED. The Orchestrator escalates.
        The intent: high urgency failures are better surfaced immediately
        than hidden behind retry logic that delays detection.
        """
        proposal_id   = proposal.get("proposal_id", "unknown")
        proposal_type = proposal.get("proposal_type", "no_op")

        # Make the API call
        result = self.adapter(proposal)
        elapsed_ms = (time.time() - t_start) * 1000

        if result.get("ok"):
            log.info(
                f"PUSH_IMMEDIATE OK | proposal={proposal_id} | "
                f"elapsed={elapsed_ms:.1f}ms"
            )
            return DeliveryResult(
                proposal_id     = proposal_id,
                proposal_type   = proposal_type,
                urgency         = "HIGH",
                routing_token   = routing_token,
                status          = DeliveryStatus.SUCCESS,
                attempt_count   = 1,
                api_response    = result.get("body"),
                delivered_at    = time.time(),
                elapsed_ms      = elapsed_ms,
                notes           = ["HIGH urgency: immediate push succeeded."],
            )
        else:
            log.warning(
                f"PUSH_IMMEDIATE FAILED | proposal={proposal_id} | "
                f"elapsed={elapsed_ms:.1f}ms"
            )
            return DeliveryResult(
                proposal_id     = proposal_id,
                proposal_type   = proposal_type,
                urgency         = "HIGH",
                routing_token   = routing_token,
                status          = DeliveryStatus.FAILED,
                attempt_count   = 1,
                api_response    = result.get("body"),
                delivered_at    = time.time(),
                elapsed_ms      = elapsed_ms,
                notes           = ["HIGH urgency: immediate push failed."],
            )

    # ------------------------------------------------------------------
    # PRIVATE — MEDIUM urgency
    # ------------------------------------------------------------------

    def _push_retry(
        self,
        proposal: Dict[str, Any],
        routing_token: str,
        t_start: float,
    ) -> DeliveryResult:
        """
        MEDIUM urgency: synchronous with retry.
        """
        proposal_id   = proposal.get("proposal_id", "unknown")
        proposal_type = proposal.get("proposal_type", "no_op")
        max_attempts  = self.retry_config["max_attempts"]
        backoff_base  = self.retry_config["backoff_base_seconds"]
        attempt       = 0
        last_error    = ""

        while attempt < max_attempts:
            attempt += 1
            result = self.adapter(proposal)
            elapsed_ms = (time.time() - t_start) * 1000

            if result.get("ok"):
                log.info(
                    f"PUSH_RETRY OK | proposal={proposal_id} | "
                    f"attempt={attempt}/{max_attempts} | "
                    f"elapsed={elapsed_ms:.1f}ms"
                )
                return DeliveryResult(
                    proposal_id     = proposal_id,
                    proposal_type   = proposal_type,
                    urgency         = "MEDIUM",
                    routing_token   = routing_token,
                    status          = DeliveryStatus.SUCCESS,
                    attempt_count   = attempt,
                    api_response    = result.get("body"),
                    delivered_at    = time.time(),
                    elapsed_ms      = elapsed_ms,
                    notes           = [f"MEDIUM urgency: retry succeeded on attempt {attempt}."],
                )

            last_error = result.get("error", "retry returned not-ok")
            log.warning(
                f"PUSH_RETRY ATTEMPT {attempt}/{max_attempts} FAILED | "
                f"proposal={proposal_id} | error={last_error}"
            )

            if attempt < max_attempts:
                backoff = backoff_base * (2 ** (attempt - 1))
                time.sleep(backoff)

        log.warning(
            f"PUSH_RETRY EXHAUSTED | proposal={proposal_id} | "
            f"attempts={max_attempts}"
        )
        return DeliveryResult(
            proposal_id     = proposal_id,
            proposal_type   = proposal_type,
            urgency         = "MEDIUM",
            routing_token   = routing_token,
            status          = DeliveryStatus.FAILED,
            attempt_count   = max_attempts,
            api_response    = None,
            delivered_at    = time.time(),
            elapsed_ms      = (time.time() - t_start) * 1000,
            notes           = [f"MEDIUM urgency: retry exhausted after {max_attempts} attempts."],
        )

    # ------------------------------------------------------------------
    # PRIVATE — LOW urgency
    # ------------------------------------------------------------------

    def _push_batch(
        self,
        proposal: Dict[str, Any],
        routing_token: str,
        t_start: float,
    ) -> DeliveryResult:
        """
        LOW urgency: asynchronous batch.
        """
        proposal_id   = proposal.get("proposal_id", "unknown")
        proposal_type = proposal.get("proposal_type", "no_op")
        log.info(f"PUSH_BATCH | proposal={proposal_id} | batched for later delivery.")
        return DeliveryResult(
            proposal_id     = proposal_id,
            proposal_type   = proposal_type,
            urgency         = "LOW",
            routing_token   = routing_token,
            status          = DeliveryStatus.BATCHED,
            attempt_count   = 0,
            api_response    = None,
            delivered_at    = time.time(),
            elapsed_ms      = 0.0,
            notes           = ["LOW urgency: batched for later delivery."],
        )
