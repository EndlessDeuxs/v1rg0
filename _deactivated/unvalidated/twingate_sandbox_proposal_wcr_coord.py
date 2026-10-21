# sandbox_proposal_wcr_coord.py
# Version: 0.2.beta
# Token budget: 5/5

COORDINATION_PROTOCOL = {
    "protocol_id": "WCR_COORD_v1",
    "atomic_units": True,
    "max_concurrent": 3,
    "queue_depth": 8,
    "mutex": {
        "enabled": True,
        "scope": "quest_id"
    },
    "instruction_format": {
        "type": "json",
        "schema": {
            "quest_id": "string",
            "action": "enum[PARSE,EXECUTE,REPORT]",
            "payload": "dict",
            "token_budget": "integer<=5"
        }
    },
    "state_machine": {
        "states": ["IDLE", "PROCESSING", "BLOCKED", "COMPLETE"],
        "transitions": {
            "IDLE": "PROCESSING",
            "PROCESSING": ["COMPLETE", "BLOCKED"],
            "BLOCKED": "IDLE",
            "COMPLETE": "IDLE"
        }
    },
    "policies": {
        "narrative_allowed": False,
        "strict_json": True,
        "token_enforcement": "split_block",
        "queue_policy": {
            "type": "fifo",
            "overflow": "drop_oldest"
        }
    }
}