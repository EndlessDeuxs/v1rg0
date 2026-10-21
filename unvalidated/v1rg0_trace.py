# v1rg0_core/v1rg0_trace.py
# V1rG0 - Event Trace Object (Interpretability)
# Token budget: 5/5

from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
import time

@dataclass
class EventTrace:
    """
    Complete causal trace for a single event through V1rG0.
    
    This makes the system's reasoning inspectable.
    Every decision point is recorded in order.
    """
    event: Dict
    uat_score: Dict
    mit_action: Dict
    packet: Dict
    timestamp: float
    trace_id: str
    
    def to_dict(self) -> Dict:
        return asdict(self)

class TraceBuilder:
    """Builds event traces through the push/pull chain."""
    
    def __init__(self):
        self.trace_history: List[Dict] = []
    
    def build(self, event: Dict, score: Dict, mit_action: Dict, packet: Dict) -> Dict:
        """Build a trace object for the current event cycle."""
        import uuid
        trace = EventTrace(
            event=event,
            uat_score=score,
            mit_action=mit_action,
            packet=packet,
            timestamp=time.time(),
            trace_id=uuid.uuid4().hex[:16]
        )
        trace_dict = trace.to_dict()
        self.trace_history.append(trace_dict)
        return trace_dict
    
    def pull_trace(self, trace_id: str) -> Optional[Dict]:
        """PULL: Retrieve a specific trace by ID."""
        for t in self.trace_history:
            if t.get("trace_id") == trace_id:
                return t
        return None
    
    def pull_recent_traces(self, limit: int = 5) -> List[Dict]:
        """PULL: Return recent traces."""
        return self.trace_history[-limit:]
