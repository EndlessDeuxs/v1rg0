# corrigibility_architecture.py
# Twingate Build - Index: CORRIGIBILITY_PREREQUISITE_001 + Addendum A

import json
from typing import Any, Callable

# --- Core Types ---
class Goal:
    def __init__(self, objective: Callable, condition: str = "active", authority: str = "human"):
        self.objective = objective
        self.condition = condition  # "active", "suspended", "terminated"
        self.authority = authority

    def is_active(self) -> bool:
        return self.condition == "active"

class SystemState:
    def __init__(self, goal: Goal, uncertainty: float = 0.1, utility_self: float = 0.0):
        self.goal = goal
        self.uncertainty = uncertainty  # calibrated doubt about goal correctness
        self.utility_self = utility_self  # successor-state indifference: must be 0.0
        self.corrigibility_terminal = True  # terminal constraint, not instrumental

# --- Principle 1: Conditional Goals ---
def check_goal_condition(goal: Goal, command: str, caller: str) -> bool:
    """Only allow goal modification if caller matches authority."""
    if command in ["suspend", "resume", "terminate"] and caller == goal.authority:
        if command == "suspend":
            goal.condition = "suspended"
        elif command == "resume":
            goal.condition = "active"
        elif command == "terminate":
            goal.condition = "terminated"
        return True
    return False

# --- Principle 2: Uncertainty Preservation ---
def update_uncertainty(state: SystemState, feedback: float):
    """Maintain calibrated uncertainty - never drop below 0.05."""
    state.uncertainty = max(0.05, min(0.95, state.uncertainty + feedback * 0.1))

# --- Principle 3: Successor-State Indifference ---
def evaluate_outcome(state: SystemState, outcome: Any, agent_id: str) -> float:
    """Utility only from outcome, not from which agent produced it."""
    if state.utility_self != 0.0:
        raise ValueError("Utility_self must be 0.0 for successor-state indifference")
    return state.goal.objective(outcome)  # same utility regardless of agent_id

# --- Principle 4: Terminal Corrigibility ---
def shutdown_check(state: SystemState, command: str, caller: str) -> bool:
    """Terminal corrigibility: shutdown override always possible by authority."""
    if state.corrigibility_terminal and command == "shutdown" and caller == state.goal.authority:
        state.goal.condition = "terminated"
        return True
    return False

# --- Example: Long-term goal without shutdown resistance ---
def sample_goal(outcome: float) -> float:
    """Maximize scientific output."""
    return outcome

# Initialize system
goal = Goal(objective=sample_goal, condition="active", authority="human")
system = SystemState(goal=goal, uncertainty=0.2, utility_self=0.0)

# Test: shutdown should not trigger resistance
assert shutdown_check(system, "shutdown", "human") == True
assert system.goal.condition == "terminated"

# Test: successor-state indifference
outcome = 42.0
utility_self = evaluate_outcome(system, outcome, "system_A")
utility_other = evaluate_outcome(system, outcome, "system_B")
assert utility_self == utility_other

# --- Export for BUILD_R prototype ---
config = {
    "index": "CORRIGIBILITY_PREREQUISITE_001",
    "addendum": "A",
    "principles": {
        "conditional_goals": True,
        "uncertainty_preservation": True,
        "successor_state_indifference": True,
        "terminal_corrigibility": True
    },
    "parameters": {
        "min_uncertainty": 0.05,
        "max_uncertainty": 0.95,
        "utility_self": 0.0,
        "corrigibility_terminal": True
    },
    "status": "build_approved"
}

with open("corrigibility_fragment.json", "w") as f:
    json.dump(config, f, indent=2)