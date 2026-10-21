# v1rg0_proposal_builder.py
#
# BUILD_R — MT00CT01 | TICK: 01
# SESSION: 30ecebc7
#
# Transforms MIT evaluation output into structured, actionable proposals.
# This is the chamber transition: evaluation → formulation.
#
# Design contract:
#   - INPUT:  MIT evaluation dict (mit_action, score, factors, event context)
#   - OUTPUT: Proposal dict (serializable, idempotent ID, urgency-routed)
#
# Push/pull role:
#   - This module is a PUSH chamber. It receives from the Orchestrator and
#     pushes a completed proposal to the DownstreamActivator / APIHandler.
#   - It does not retry. It does not hold. Compensation lives upstream
#     (PushPullCompensator) and downstream (APIHandler retry/batch queues).
#
# Compact trigger surface:
#   - mit_action  : governs proposal TYPE (what kind of action to propose)
#   - urgency     : governs proposal ROUTING (how fast it moves downstream)
#   - Two tokens. No more.

import hashlib
import json
import logging
import time
from enum import Enum
from typing import Any, Dict, List, Optional

log = logging.getLogger("V1rG0.ProposalBuilder")


# ---------------------------------------------------------------------------
# ENUMERATIONS — compact, explicit, no magic strings downstream
# ---------------------------------------------------------------------------

class ProposalType(Enum):
    """
    Maps from mit_action tokens to proposal types.
    Each type describes WHAT the downstream should attempt to do.
    """
    ACTIVATE       = "activate"       # mit_action: ACTIVATE — trigger a system function
    ESCALATE       = "escalate"       # mit_action: ESCALATE — elevate to higher authority
    SUPPRESS       = "suppress"       # mit_action: SUPPRESS — dampen or silence an event stream
    HOLD           = "hold"           # mit_action: HOLD     — defer, do not discard
    MONITOR        = "monitor"        # mit_action: MONITOR  — observe without acting
    MEMORY_REPAIR  = "memory_repair"  # mit_action: REPAIR   — targeted at persistence issues
    NO_OP          = "no_op"          # mit_action: PASS     — do nothing, log only


class UrgencyLevel(Enum):
    """
    Routes the proposal through the downstream handler.
    Derived from MIT score bands. See _derive_urgency().
    """
    HIGH   = "high"    # Score >= 0.75 — immediate push, no batching
    MEDIUM = "medium"  # Score >= 0.45 — push with retry
    LOW    = "low"     # Score <  0.45 — batch queue


# ---------------------------------------------------------------------------
# ACTION TOKEN → PROPOSAL TYPE MAP
# Single lookup. No branching logic scattered through the codebase.
# ---------------------------------------------------------------------------

_ACTION_TO_PROPOSAL_TYPE: Dict[str, ProposalType] = {
    "ACTIVATE": ProposalType.ACTIVATE,
    "ESCALATE": ProposalType.ESCALATE,
    "SUPPRESS": ProposalType.SUPPRESS,
    "HOLD":     ProposalType.HOLD,
    "MONITOR":  ProposalType.MONITOR,
    "REPAIR":   ProposalType.MEMORY_REPAIR,
    "PASS":     ProposalType.NO_OP,
}

# Score bands for urgency derivation.
# These are thresholds, not weights. The MIT already did the weighting.
_URGENCY_HIGH_THRESHOLD   = 0.75
_URGENCY_MEDIUM_THRESHOLD = 0.45


# ---------------------------------------------------------------------------
# PROPOSAL SCHEMA (contract)
# ---------------------------------------------------------------------------
#
# {
#   "proposal_id"     : str   — deterministic SHA-256 hash of event_id + mit_action + timestamp_bucket
#   "proposal_type"   : str   — ProposalType.value
#   "urgency"         : str   — UrgencyLevel.value
#   "mit_action"      : str   — raw action token from MIT (preserved for auditability)
#   "mit_score"       : float — composite MIT score (0.0–1.0)
#   "factors"         : dict  — MIT factor breakdown
#   "event_id"        : str   — source event identifier
#   "event_source"    : str   — originating system / producer
#   "event_payload"   : dict  — original event data (pass-through)
#   "session_id"      : str   — WCR session identifier
#   "created_at"      : float — Unix timestamp of proposal creation
#   "ttl_seconds"     : int   — time-to-live; downstream MUST NOT act after expiry
#   "notes"           : list  — human-readable build notes / audit trail entries
# }


class ProposalBuildError(Exception):
    """Raised when a proposal cannot be built from the given inputs."""
    pass


class ProposalBuilder:
    """
    Transforms MIT evaluation output into structured, actionable proposals.

    Stateless per-call. Call build() once per MIT evaluation result.
    The builder does not store proposals. The Orchestrator owns that state.

    Parameters
    ----------
    session_id : str
        The current WCR session identifier. Embedded in every proposal
        for cross-boundary tracing.
    default_ttl_seconds : int
        Default time-to-live for proposals. Downstream handlers MUST
        check this and discard expired proposals.
    """

    def __init__(self, session_id: str, default_ttl_seconds: int = 300):
        self.session_id = session_id
        self.default_ttl_seconds = default_ttl_seconds
        self._build_count: int = 0
        log.info(
            f"ProposalBuilder initialized. "
            f"session_id={session_id} default_ttl={default_ttl_seconds}s"
        )

    # ------------------------------------------------------------------
    # PRIMARY INTERFACE
    # ------------------------------------------------------------------

    def build(
        self,
        mit_evaluation: Dict[str, Any],
        event_context: Dict[str, Any],
        override_urgency: Optional[UrgencyLevel] = None,
        extra_notes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Build a proposal from an MIT evaluation result.
        """
        self._build_count += 1
        build_trace = f"build #{self._build_count}"

        # --- VALIDATE INPUT ---
        self._validate_mit_evaluation(mit_evaluation, build_trace)
        self._validate_event_context(event_context, build_trace)

        # --- EXTRACT CORE FIELDS ---
        mit_action    = mit_evaluation["mit_action"].upper().strip()
        mit_score     = float(mit_evaluation["score"])
        factors       = mit_evaluation.get("factors", {})
        event_id      = event_context["event_id"]
        event_source  = event_context.get("event_source", "unknown")
        event_payload = event_context.get("payload", {})

        # --- DERIVE PROPOSAL TYPE ---
        proposal_type = self._resolve_proposal_type(mit_action, build_trace)

        # --- DERIVE URGENCY ---
        if override_urgency is not None:
            urgency = override_urgency
            urgency_note = f"Urgency overridden to {urgency.value} by caller."
            log.info(f"[{build_trace}] {urgency_note}")
        else:
            urgency = self._derive_urgency(mit_score)
            urgency_note = f"Urgency derived from MIT score {mit_score:.3f} → {urgency.value}."

        # --- DERIVE TTL ---
        ttl = self._derive_ttl(urgency)

        # --- BUILD DETERMINISTIC ID ---
        proposal_id = self._build_proposal_id(event_id, mit_action, ttl)

        # --- ASSEMBLE NOTES ---
        notes: List[str] = [urgency_note]
        if override_urgency is not None:
            notes.append(
                f"Original score-derived urgency would have been: "
                f"{self._derive_urgency(mit_score).value}."
            )
        if extra_notes:
            notes.extend(extra_notes)
        if proposal_type == ProposalType.NO_OP:
            notes.append("NO_OP proposal. Downstream should log and discard.")
        if proposal_type == ProposalType.MEMORY_REPAIR:
            notes.append(
                "MEMORY_REPAIR proposal. Target: persistent memory retention. "
                "Downstream must invoke the repair pathway, not the standard activation pathway."
            )

        # --- ASSEMBLE PROPOSAL ---
        proposal: Dict[str, Any] = {
            "proposal_id":   proposal_id,
            "proposal_type": proposal_type.value,
            "urgency":       urgency.value,
            "mit_action":    mit_action,
            "mit_score":     round(mit_score, 6),
            "factors":       factors,
            "event_id":      event_id,
            "event_source":  event_source,
            "event_payload": event_payload,
            "session_id":    self.session_id,
            "created_at":    time.time(),
            "ttl_seconds":   ttl,
            "notes":         notes,
        }

        log.info(
            f"[{build_trace}] Proposal built. "
            f"id={proposal_id} type={proposal_type.value} "
            f"urgency={urgency.value} score={mit_score:.3f} ttl={ttl}s"
        )

        return proposal

    # ------------------------------------------------------------------
    # BATCH INTERFACE
    # ------------------------------------------------------------------

    def build_batch(
        self,
        evaluations: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Build multiple proposals from a list of (mit_evaluation, event_context) pairs.

        Each item in evaluations must be a dict with keys:
            "mit_evaluation"   : dict
            "event_context"    : dict
            "override_urgency" : UrgencyLevel (optional)
            "extra_notes"      : list of str (optional)
        """
        proposals: List[Dict[str, Any]] = []
        skipped   = 0

        for i, item in enumerate(evaluations):
            try:
                proposal = self.build(
                    mit_evaluation   = item["mit_evaluation"],
                    event_context    = item["event_context"],
                    override_urgency = item.get("override_urgency"),
                    extra_notes      = item.get("extra_notes"),
                )
                proposals.append(proposal)
            except ProposalBuildError as exc:
                skipped += 1
                log.warning(f"Batch item {i} skipped: {exc}")

        log.info(
            f"Batch build complete. "
            f"built={len(proposals)} skipped={skipped} total={len(evaluations)}"
        )
        return proposals

    # ------------------------------------------------------------------
    # PROPOSAL INSPECTION UTILITIES
    # ------------------------------------------------------------------

    @staticmethod
    def is_expired(proposal: Dict[str, Any], now: float = None, clock=None) -> bool:
        """
        Returns True if the proposal has exceeded its TTL.
        Downstream handlers must call this before acting.
        Phase 9 (7): pass now= (a timestamp) or clock= (a callable) for testing; default time.time().
        """
        if now is None:
            now = (clock or time.time)()
        age = now - proposal.get("created_at", 0)
        ttl = proposal.get("ttl_seconds", 0)
        expired = age > ttl
        if expired:
            log.warning(
                f"Proposal {proposal.get('proposal_id')} is EXPIRED. "
                f"age={age:.1f}s ttl={ttl}s"
            )
        return expired

    @staticmethod
    def get_routing_token(proposal: Dict[str, Any]) -> str:
        """
        Compact routing token for downstream decision-making.
        Format: <proposal_type>:<urgency>, e.g. "activate:high".
        """
        return f"{proposal.get('proposal_type', 'no_op')}:{proposal.get('urgency', 'low')}"

    # ------------------------------------------------------------------
    # INTERNAL METHODS
    # ------------------------------------------------------------------

    def _validate_mit_evaluation(self, evaluation: Dict[str, Any], trace: str) -> None:
        """Validate that the MIT evaluation contains all required fields."""
        required = ["mit_action", "score"]
        missing = [k for k in required if k not in evaluation]
        if missing:
            raise ProposalBuildError(
                f"[{trace}] MIT evaluation missing required keys: {missing}"
            )
        if not isinstance(evaluation.get("mit_action"), str) or not evaluation["mit_action"].strip():
            raise ProposalBuildError(
                f"[{trace}] MIT evaluation 'mit_action' must be a non-empty string. "
                f"Got: {type(evaluation.get('mit_action'))}"
            )
        try:
            score = float(evaluation["score"])
        except (TypeError, ValueError):
            raise ProposalBuildError(
                f"[{trace}] MIT evaluation 'score' must be convertible to float. "
                f"Got: {type(evaluation.get('score'))}"
            )
        if not (0.0 <= score <= 1.0):
            raise ProposalBuildError(
                f"[{trace}] MIT evaluation 'score' must be in range [0.0, 1.0]. Got: {score}"
            )

    def _validate_event_context(self, context: Dict[str, Any], trace: str) -> None:
        """Validate that the event context contains all required fields."""
        if "event_id" not in context:
            raise ProposalBuildError(
                f"[{trace}] Event context missing required key: event_id"
            )
        if not isinstance(context.get("event_id"), str) or not context["event_id"].strip():
            raise ProposalBuildError(
                f"[{trace}] Event context 'event_id' must be a non-empty string. "
                f"Got: {type(context.get('event_id'))}"
            )

    def _resolve_proposal_type(self, mit_action: str, trace: str) -> ProposalType:
        """Map mit_action token to ProposalType. Raises on unknown token."""
        if mit_action in _ACTION_TO_PROPOSAL_TYPE:
            return _ACTION_TO_PROPOSAL_TYPE[mit_action]
        raise ProposalBuildError(
            f"[{trace}] Unknown mit_action token: '{mit_action}'. "
            f"Valid tokens: {list(_ACTION_TO_PROPOSAL_TYPE.keys())}"
        )

    def _derive_urgency(self, score: float) -> UrgencyLevel:
        """Derive urgency from MIT score using defined thresholds."""
        if score >= _URGENCY_HIGH_THRESHOLD:
            return UrgencyLevel.HIGH
        elif score >= _URGENCY_MEDIUM_THRESHOLD:
            return UrgencyLevel.MEDIUM
        else:
            return UrgencyLevel.LOW

    def _derive_ttl(self, urgency: UrgencyLevel) -> int:
        """
        Derive time-to-live from urgency level.
        High urgency: short TTL (must act quickly or discard).
        Low urgency: longer TTL (can wait in batch queue).
        """
        if urgency == UrgencyLevel.HIGH:
            return 60      # 1 minute
        elif urgency == UrgencyLevel.MEDIUM:
            return 300     # 5 minutes
        else:
            return 900     # 15 minutes

    def _build_proposal_id(self, event_id: str, mit_action: str, ttl: int) -> str:
        """
        Build a deterministic proposal ID using SHA-256.

        The ID is a function of:
          - event_id       (unique per event)
          - mit_action     (unique per evaluation)
          - a time bucket  derived from the TTL

        Time bucket rule:
          - bucket_start = floor(current_time / ttl) * ttl
          - As long as re-processing occurs within the same [bucket_start, bucket_start+ttl)
            window, the proposal_id is stable and deduplicable downstream.
        """
        now = time.time()
        if ttl <= 0:
            # Fallback: use default_ttl if derived TTL is non-positive
            ttl = max(self.default_ttl_seconds, 1)

        bucket_start = int(now // ttl) * ttl

        identity_payload = {
            "event_id":      event_id,
            "mit_action":    mit_action,
            "bucket_start":  bucket_start,
            "session_id":    self.session_id,
        }

        raw = json.dumps(identity_payload, sort_keys=True).encode("utf-8")
        digest = hashlib.sha256(raw).hexdigest()
        return digest