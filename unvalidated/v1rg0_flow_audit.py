# v1rg0_core/v1rg0_flow_audit.py
# Token budget: 5/5

FLOW_AUDIT = {
    "push_paths": {
        "event_to_uat": "UAT.assess(event) — PUSHES event into salience scoring",
        "score_to_mit": "MIT.execute_action(score, event) — PUSHES score into decision engine",
        "packet_to_store": "MemoryStore.push_memory(packet) — PUSHES memory on STORE_AND_PROPOSE",
        "proposal_to_registry": "Registry.update_from_proposal() — PUSHES proposal into tracking"
    },
    "pull_paths": {
        "orchestrator_pulls_uat": "UAT.pull_assessment() — PULLS confirmed score",
        "builder_pulls_orchestrator": "ProposalBuilder.build() — PULLS last_packet",
        "registry_pulls_proposal": "AgentManRegistry.update_from_proposal() — PULLS proposal data",
        "external_pulls_pressure": "Orchestrator.pull_pressure() — PULLS system state"
    },
    "gaps": [
        "No PULL mechanism when MemoryStore is empty — cold start recovery is passive",
        "No PUSH from ProposalBuilder to trigger downstream agent activation",
        "Registry only PULLS on update, does not PUSH alerts when thresholds breached"
    ]
}
