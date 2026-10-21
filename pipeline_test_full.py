# ============================================================
# Twingate Pipeline Test Scaffold - v0.1.0
# Chamber: BUILD_R
# Collectick: 08 | Tick: 06 | Depth: 3 (FINAL)
# Status: CONSTRUCTING
# Target: GAP_01 — End-to-End Integration Coverage
# ============================================================

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List


# ── Minimal stubs (until real imports are wired) ────────────
class PulseType(str, Enum):
    HEARTBEAT  = "HEARTBEAT"
    SYNTHESIS  = "SYNTHESIS"
    DLQ_SIGNAL = "DLQ_SIGNAL"


@dataclass
class Pulse:
    type:    PulseType | str
    source:  str              = "TEST"
    payload: Optional[dict]   = None


@dataclass
class PulseResult:
    status:    str
    dlq_count: int             = 0
    depth:     Optional[int]   = None
    continuity_flag: bool      = False


@dataclass
class SynthesisResult:
    depth:            int
    continuity_flag:  bool
    source_state:     dict = field(default_factory=dict)


# ── Fixtures ────────────────────────────────────────────────
@pytest.fixture
def mock_chamber():
    """Single chamber stub with heartbeat acknowledgement."""
    chamber = MagicMock()
    chamber.heartbeat_ack = False

    async def _receive(pulse):
        if pulse.type == PulseType.HEARTBEAT:
            chamber.heartbeat_ack = True
        return True

    chamber.receive = _receive
    return chamber


@pytest.fixture
def mock_api_handler():
    """APIHandler stub with DLQ tracking."""
    handler        = MagicMock()
    handler._dlq   = []

    async def _handle(pulse):
        handler._dlq.append(pulse)

    handler.handle     = AsyncMock(side_effect=_handle)
    handler.dlq_size   = lambda: len(handler._dlq)
    handler.dlq_drain  = lambda: handler._dlq.clear()
    return handler


@pytest.fixture
def mock_pipeline(mock_chamber, mock_api_handler):
    """
    Lightweight pipeline stub.
    Replaces live Pipeline until real module is wired.
    Remove this fixture once `twingate.pipeline` is importable.
    """
    pipeline               = MagicMock()
    pipeline.chambers      = [mock_chamber]
    pipeline.api_handler   = mock_api_handler
    pipeline.initialized   = False

    # --- initialize / shutdown ---
    async def _init():
        pipeline.initialized = True

    async def _shutdown():
        pipeline.initialized = False

    pipeline.initialize = _init
    pipeline.shutdown   = _shutdown

    # --- process ---
    async def _process(pulse: Pulse) -> PulseResult:
        if not isinstance(pulse.type, PulseType):
            # Malformed — route to DLQ
            try:
                raise ValueError(f"Unknown pulse type: {pulse.type!r}")
            except ValueError:
                pipeline.api_handler._dlq.append(pulse)
                return PulseResult(status="dlq", dlq_count=len(pipeline.api_handler._dlq))

        for chamber in pipeline.chambers:
            await chamber.receive(pulse)

        return PulseResult(status="delivered")

    # --- synthesize ---
    async def _synthesize(state: dict) -> SynthesisResult:
        next_depth = state.get("wcr_depth", 0) + 1
        return SynthesisResult(
            depth           = next_depth,
            continuity_flag = True,
            source_state    = state,
        )

    pipeline.process    = _process
    pipeline.synthesize = _synthesize
    return pipeline


# ── Lifecycle helper ─────────────────────────────────────────
@pytest.fixture
async def pipeline(mock_pipeline):
    """Managed pipeline lifecycle (async fixture)."""
    await mock_pipeline.initialize()
    yield mock_pipeline
    await mock_pipeline.shutdown()


# ════════════════════════════════════════════════════════════
# TEST SUITE: TestPipelineEndToEnd
# ════════════════════════════════════════════════════════════
class TestPipelineEndToEnd:
    """
    End-to-end pipeline integrity verification.

    Covers GAP_01 vectors:
        [1] HEARTBEAT propagation across all chambers
        [2] SYNTHESIS depth continuity
        [3] DLQ recovery on malformed pulses
    """

    # ── [1] HEARTBEAT ────────────────────────────────────────
    @pytest.mark.asyncio
    async def test_heartbeat_propagation(self, pipeline):
        """
        HEARTBEAT pulses must traverse every registered chamber.
        All chambers must set heartbeat_ack=True upon receipt.
        """
        test_pulse = Pulse(type=PulseType.HEARTBEAT, source="ANALYTICS")

        result = await pipeline.process(test_pulse)

        assert result.status == "delivered", (
            f"Expected 'delivered', got {result.status!r}"
        )
        assert all(
            chamber.heartbeat_ack for chamber in pipeline.chambers
        ), "One or more chambers failed to acknowledge HEARTBEAT"

    # ── [2] SYNTHESIS continuity ─────────────────────────────
    @pytest.mark.asyncio
    async def test_synthesis_continuity(self, pipeline):
        """
        SYNTHESIS must increment depth and preserve continuity flag
        when transitioning from Depth 2 → 3.
        """
        depth_2_state = {
            "wcr_depth":  2,
            "collectick": 8,
            "tick":       5,
        }

        result = await pipeline.synthesize(depth_2_state)

        assert result.depth == 3, (
            f"Expected depth 3, got {result.depth}"
        )
        assert result.continuity_flag is True, (
            "Continuity flag must survive depth transition"
        )
        assert result.source_state["wcr_depth"] == 2, (
            "Source state must be preserved unmodified"
        )

    # ── [3] DLQ recovery ─────────────────────────────────────
    @pytest.mark.asyncio
    async def test_dlq_recovery_malformed_type(self, pipeline):
        """
        Pulses with invalid types must be intercepted and
        routed to the dead letter queue without crashing.
        """
        bad_pulse = Pulse(type="INVALID", payload=None)

        result = await pipeline.process(bad_pulse)

        assert result.status == "dlq", (
            f"Expected status 'dlq', got {result.status!r}"
        )
        assert result.dlq_count == 1, (
            f"Expected 1 dead letter, got {result.dlq_count}"
        )
        assert pipeline.api_handler.dlq_size() == 1, (
            "APIHandler DLQ must reflect the failed pulse"
        )

    @pytest.mark.asyncio
    async def test_dlq_accumulation_multiple_failures(self, pipeline):
        """
        Multiple consecutive bad pulses must each increment the DLQ.
        Queue depth must be monotonically increasing.
        """
        bad_pulses = [
            Pulse(type="BAD_1", payload=None),
            Pulse(type="BAD_2", payload=None),
            Pulse(type="BAD_3", payload={"poison": True}),
        ]

        for i, pulse in enumerate(bad_pulses, start=1):
            result = await pipeline.process(pulse)
            assert result.dlq_count == i, (
                f"DLQ count mismatch at pulse {i}: got {result.dlq_count}"
            )

        assert pipeline.api_handler.dlq_size() == len(bad_pulses)

    @pytest.mark.asyncio
    async def test_dlq_does_not_block_valid_pulse(self, pipeline):
        """
        A DLQ event must not corrupt the pipeline for subsequent valid pulses.
        System must remain operational after recovery.
        """
        bad_pulse   = Pulse(type="CORRUPT", payload=None)
        good_pulse  = Pulse(type=PulseType.HEARTBEAT, source="BUILD_R")

        await pipeline.process(bad_pulse)
        result = await pipeline.process(good_pulse)

        assert result.status == "delivered", (
            "Pipeline must recover and deliver valid pulses post-DLQ event"
        )
        assert pipeline.api_handler.dlq_size() == 1, (
            "DLQ must not absorb valid pulses"
        )


# ════════════════════════════════════════════════════════════
# TEST SUITE: TestPipelineLifecycle
# ════════════════════════════════════════════════════════════
class TestPipelineLifecycle:
    """Verify initialize/shutdown contract."""

    @pytest.mark.asyncio
    async def test_initialize_sets_ready_state(self, mock_pipeline):
        assert mock_pipeline.initialized is False
        await mock_pipeline.initialize()
        assert mock_pipeline.initialized is True

    @pytest.mark.asyncio
    async def test_shutdown_clears_ready_state(self, mock_pipeline):
        await mock_pipeline.initialize()
        await mock_pipeline.shutdown()
        assert mock_pipeline.initialized is False
