# v1rg0_core/agentman_registry.py
# V1rG0 - Agent Registry (Push/Pull Balanced)
# REFINED: Active push on threshold breach + downstream signaling
# Token budget: 5/5

from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
import json

@dataclass
class AgentState:
    agent_id: str
    last_proposal: Optional[Dict] = None
    memory_count: int = 0
    pressure: float = 0.0
    integrity_score: float = 0.0
    alert_active: bool = False

class AgentManRegistry:
    """
    Agent registry with push/pull balance.
    Pulls proposals from builder, pushes alerts on threshold breach.
    """

    ALERT_THRESHOLD = 0.8  # Pressure threshold for alert push
    
    def __init__(self, registry_path: str = "agentman_registry.json"):
        self.registry_path = registry_path
        self.agents: Dict[str, AgentState] = {}
        self.alert_history: List[Dict] = []
        self._load_registry()
    
    def register_agent(self, agent_id: str) -> None:
        """Push/Pull balanced: Register a new agent."""
        if agent_id not in self.agents:
            self.agents[agent_id] = AgentState(agent_id=agent_id)
            self._persist_registry()
    
    def pull_agent(self, agent_id: str) -> Optional[AgentState]:
        """PULL: Retrieve agent state by ID."""
        return self.agents.get(agent_id)
    
    def pull_all_agents(self) -> List[Dict]:
        """PULL: Return all registered agents."""
        return [asdict(agent) for agent in self.agents.values()]
    
    def update_from_proposal(self, agent_id: str, proposal: Dict) -> None:
        """
        PUSH receiver: Accept a proposal and update agent state.
        Also PUSHES alert if pressure threshold breached.
        """
        if agent_id not in self.agents:
            self.register_agent(agent_id)
        
        agent = self.agents[agent_id]
        agent.last_proposal = proposal
        agent.pressure = proposal.get("pressure_at_trigger", 0.0)
        agent.memory_count += 1
        agent.integrity_score = self._compute_integrity(proposal)
        
        # Check for alert condition and PUSH if needed
        if agent.pressure >= self.ALERT_THRESHOLD and not agent.alert_active:
            agent.alert_active = True
            self._push_alert(agent_id, agent.pressure, proposal)
        elif agent.pressure < self.ALERT_THRESHOLD and agent.alert_active:
            agent.alert_active = False
        
        self._persist_registry()
    
    def _push_alert(self, agent_id: str, pressure: float, proposal: Dict) -> None:
        """PUSH: Send alert when pressure threshold breached."""
        alert = {
            "type": "PRESSURE_THRESHOLD_BREACH",
            "agent_id": agent_id,
            "pressure": pressure,
            "proposal_urgency": proposal.get("urgency", "UNKNOWN"),
            "timestamp": self._get_timestamp()
        }
        self.alert_history.append(alert)
        # In production, this would push to a notification system
    
    def pull_alerts(self, limit: int = 10) -> List[Dict]:
        """PULL: Return recent alerts."""
        return self.alert_history[-limit:]
    
    def pull_registry_health(self) -> Dict:
        """PULL: Return registry health metrics."""
        return {
            "total_agents": len(self.agents),
            "active_proposals": sum(
                1 for a in self.agents.values()
                if a.last_proposal is not None
            ),
            "active_alerts": sum(
                1 for a in self.agents.values()
                if a.alert_active
            ),
            "total_memories": sum(
                a.memory_count for a in self.agents.values()
            ),
            "average_integrity": (
                sum(a.integrity_score for a in self.agents.values())
                / max(len(self.agents), 1)
            )
        }
    
    def _compute_integrity(self, proposal: Dict) -> float:
        urgency_map = {
            "CRITICAL": 0.95,
            "HIGH": 0.85,
            "STANDARD": 0.75,
            "LOW": 0.60
        }
        return urgency_map.get(proposal.get("urgency", "LOW"), 0.60)
    
    def _load_registry(self) -> None:
        if os.path.exists(self.registry_path):
            try:
                with open(self.registry_path, 'r') as f:
                    data = json.load(f)
                    for agent_id, state in data.items():
                        self.agents[agent_id] = AgentState(**state)
            except (json.JSONDecodeError, IOError):
                self.agents = {}
    
    def _persist_registry(self) -> None:
        try:
            with open(self.registry_path, 'w') as f:
                data = {
                    agent_id: asdict(agent)
                    for agent_id, agent in self.agents.items()
                }
                json.dump(data, f, indent=2)
        except IOError:
            pass
    
    def _get_timestamp(self) -> float:
        import time
        return time.time()
