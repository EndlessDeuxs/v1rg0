# v1rg0_sandbox_runner.py
# BUILD_R: Single-file smoke test — one command, full cycle
# COMPLETED: Final log statement and __main__ block added
# Usage: python v1rg0_sandbox_runner.py

import json
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)-28s] %(levelname)s: %(message)s"
)
log = logging.getLogger("V1rG0.SandboxRunner")

# -----------------------------------------------------------------------
# MOCK API CALLBACK — sandbox stand-in for real downstream
# -----------------------------------------------------------------------

def mock_downstream_api(proposal: dict) -> dict:
    """
    Mock downstream API callback.
    Simulates a receiving system acknowledging the proposal.
    """
    return {
        "acknowledged": True,
        "received_action": proposal.get("recommended_action", "UNKNOWN"),
        "received_urgency": proposal.get("urgency", "UNKNOWN"),
        "mock_system": "V1rG0_SandboxReceiver_v1"
    }


# -----------------------------------------------------------------------
# SMOKE TEST EVENTS
# -----------------------------------------------------------------------

SMOKE_EVENTS = [
    # Event 1 — low salience, expect RETAIN / MONITOR
    '{"action": "STORE_AND_PROPOSE", "signal": "routine_check", "intensity": 0.2}',

    # Event 2 — medium salience, expect EXTRACT / REVIEW
    '{"action": "STORE_AND_PROPOSE", "signal": "anomaly_detected", "intensity": 0.6}',

    # Event 3 — high salience, expect FLUSH / ESCALATE
    '{"action": "STORE_AND_PROPOSE", "signal": "critical_failure", "intensity": 0.95}',

    # Event 4 — pressure accumulation check
    '{"action": "STORE_AND_PROPOSE", "signal": "repeated_anomaly", "intensity": 0.7}',

    # Event 5 — alert threshold check
    '{"action": "STORE_AND_PROPOSE", "signal": "cascade_risk", "intensity": 0.88}'
]


# -----------------------------------------------------------------------
# RUNNER
# -----------------------------------------------------------------------

def run_smoke_test():

    log.info("=" * 60)
    log.info("V1rG0 SANDBOX SMOKE TEST — BEGIN")
    log.info("=" * 60)

    # Import harness
    try:
        from v1rg0_integration_harness import build_stack, inject_event
    except ImportError as e:
        log.error(f"Import failed — is the stack built? {e}")
        sys.exit(1)

    # Build stack with mock downstream
    stack = build_stack(mock_api_callback=mock_downstream_api)
    log.info("Stack built successfully.\n")

    results = []

    for i, raw_event in enumerate(SMOKE_EVENTS, start=1):

        log.info(f"{'─' * 50}")
        log.info(f"INJECT {i}/{len(SMOKE_EVENTS)}: {raw_event}")
        log.info(f"{'─' * 50}")

        result = inject_event(stack, raw_event)
        results.append(result)

        # Report
        packet   = result.get("packet", {})
        proposal = result.get("proposal")
        activation = result.get("activation", [])

        tier      = packet.get("tier",      "—")
        composite = packet.get("composite", 0.0)
        pressure  = packet.get("pressure",  0.0)
        alert     = packet.get("alert_active", False)
        action    = packet.get("action",    "—")

        log.info(f"  PACKET   | tier={tier:<8} composite={composite:.4f}  pressure={pressure:.4f}  alert={alert}")
        log.info(f"  ACTION   | {action}")

        if proposal:
            log.info(
                f"  PROPOSAL | {proposal.get('proposal_version')} "
                f"| {proposal.get('recommended_action')} "
                f"| urgency={proposal.get('urgency')}"
            )
            activation_result = proposal.get("activation_result", {})
            log.info(f"  DOWNSTREAM | status={activation_result.get('status', '—')}")
        else:
            log.info(f"  PROPOSAL | None (below composite threshold or no STORE_AND_PROPOSE)")

        log.info("")

    # -----------------------------------------------------------------------
    # FINAL REPORT
    # -----------------------------------------------------------------------

    log.info("=" * 60)
    log.info("V1rG0 SANDBOX SMOKE TEST — FINAL REPORT")
    log.info("=" * 60)

    memory_store = stack["memory_store"]
    tier_counts  = memory_store.pull_tier_counts()
    push_total   = memory_store.pull_push_count()

    log.info(f"Total events injected : {len(SMOKE_EVENTS)}")
    log.info(f"Total packets stored  : {push_total}")
    log.info(f"Tier distribution     : {tier_counts}")

    proposal_builder = stack["proposal_builder"]
    proposal_count   = proposal_builder.pull_proposal_count()
    log.info(f"Total proposals built : {proposal_count}")

    downstream = stack["downstream"]
    api_log    = downstream.pull_api_call_log(limit=len(SMOKE_EVENTS))
    statuses   = [entry.get("status", "—") for entry in api_log]
    log.info(f"Downstream statuses   : {statuses}")

    orchestrator   = stack["orchestrator"]
    final_packet   = orchestrator.pull_last_packet()
    final_pressure = final_packet.get("pressure", 0.0) if final_packet else 0.0
    final_alert    = final_packet.get("alert_active", False) if final_packet else False
    log.info(f"Final pressure        : {final_pressure:.4f}")
    log.info(f"Final alert state     : {final_alert}")

    log.info("=" * 60)
    log.info("V1rG0 SANDBOX SMOKE TEST — COMPLETE")
    log.info("=" * 60)


if __name__ == "__main__":
    run_smoke_test()
