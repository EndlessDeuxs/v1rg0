# v1rg0_mit.py
# BUILD_R: Real MIT implementation — Monitor-Integrate-Trigger
# Evaluates events and produces UAT scores + action tokens
# Based on intensity, priority, source reliability, and temporal patterns

import logging
import math
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

log = logging.getLogger("V1rG0.MIT")


class MIT:
    """
    Monitor-Integrate-Trigger — the evaluation engine.
    
    Transforms raw events into structured evaluations with:
      - uat_score: 0.0–1.0 confidence that action is needed
      - action: one of "suppress", "hold", "emit", "escalate"
    
    Evaluation factors:
      1. Payload intensity (primary)
      2. Event priority
      3. Source reliability (tracked over time)
      4. Temporal clustering (recent similar events increase score)
    """

    # Action thresholds
    ESCALATE_THRESHOLD = 0.80
    EMIT_THRESHOLD = 0.40
    HOLD_THRESHOLD = 0.15
    # Below HOLD_THRESHOLD → suppress

    # Priority multiplier
    PRIORITY_WEIGHT = 0.15

    # Temporal decay (in seconds)
    TEMPORAL_HALF_LIFE = 300.0  # 5 minutes

    def __init__(self):
        self.source_reliability: Dict[str, float] = {}
        self.recent_events: List[Dict[str, Any]] = []
        self.event_count = 0

    def evaluate(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluate a single event and return structured report.
        
        Args:
            event: dict with keys:
                - event_type (str)
                - source (str)
                - payload (dict) — must contain "intensity" (0.0–1.0)
                - timestamp (str, ISO-8601)
                - priority (int, 1–10)
        
        Returns:
            dict with:
                - uat_score (float, 0.0–1.0)
                - action (str)
                - confidence (float, 0.0–1.0)
                - factors (dict) — breakdown of score components
        """
        self.event_count += 1

        # Extract fields with defaults
        payload = event.get("payload", {})
        intensity = payload.get("intensity", 0.0)
        priority = event.get("priority", 5)
        source = event.get("source", "unknown")
        event_type = event.get("event_type", "unknown")
        timestamp_str = event.get("timestamp", "")

        # Parse timestamp
        try:
            timestamp = datetime.fromisoformat(timestamp_str)
        except (ValueError, TypeError):
            timestamp = datetime.now(timezone.utc)

        # --- Factor 1: Base intensity score ---
        intensity_score = min(max(intensity, 0.0), 1.0)

        # --- Factor 2: Priority bonus ---
        priority_bonus = (priority - 1) / 9.0 * self.PRIORITY_WEIGHT

        # --- Factor 3: Source reliability ---
        rel = self.source_reliability.get(source, 0.5)
        source_confidence = rel
        # Update reliability (slight increase for consistent sources)
        self._update_source_reliability(source, intensity_score)

        # --- Factor 4: Temporal clustering ---
        cluster_bonus = self._compute_temporal_cluster(
            event_type=event_type,
            source=source,
            current_time=timestamp
        )

        # --- Composite UAT score ---
        uat_score = min(
            intensity_score + priority_bonus + cluster_bonus,
            1.0
        )

        # --- Action determination ---
        if uat_score >= self.ESCALATE_THRESHOLD:
            action = "escalate"
        elif uat_score >= self.EMIT_THRESHOLD:
            action = "emit"
        elif uat_score >= self.HOLD_THRESHOLD:
            action = "hold"
        else:
            action = "suppress"

        # --- Confidence ---
        confidence = min(
            source_confidence * (0.5 + 0.5 * intensity_score),
            1.0
        )

        # --- Record event for temporal tracking ---
        self.recent_events.append({
            "event_type": event_type,
            "source": source,
            "timestamp": timestamp,
            "intensity": intensity_score
        })
        # Prune old events
        self._prune_old_events(current_time=timestamp)

        result = {
            "uat_score": round(uat_score, 4),
            "action": action,
            "confidence": round(confidence, 4),
            "factors": {
                "intensity": round(intensity_score, 4),
                "priority_bonus": round(priority_bonus, 4),
                "cluster_bonus": round(cluster_bonus, 4),
                "source_reliability": round(source_confidence, 4)
            }
        }

        log.debug(
            f"MIT evaluation | "
            f"source={source} | "
            f"type={event_type} | "
            f"intensity={intensity_score:.3f} | "
            f"score={uat_score:.3f} | "
            f"action={action}"
        )

        return result

    def _update_source_reliability(
        self,
        source: str,
        intensity: float
    ) -> None:
        """
        Update source reliability based on event intensity.
        Consistent high-intensity events increase reliability.
        Wild fluctuations decrease it.
        """
        current = self.source_reliability.get(source, 0.5)
        # Simple moving average
        alpha = 0.1
        # Reliability increases when intensity is consistent with expectations
        if intensity > 0.8:
            # High-intensity events from known sources are reliable
            updated = current * (1 - alpha) + 0.9 * alpha
        elif intensity < 0.1:
            # Very low intensity may indicate noise
            updated = current * (1 - alpha) + 0.3 * alpha
        else:
            # Normal range — maintain
            updated = current * (1 - alpha) + 0.6 * alpha
        self.source_reliability[source] = round(updated, 4)

    def _compute_temporal_cluster(
        self,
        event_type: str,
        source: str,
        current_time: datetime
    ) -> float:
        """
        Compute temporal clustering bonus.
        
        If multiple similar events occurred recently,
        the score gets a small bonus (max 0.15).
        """
        if not self.recent_events:
            return 0.0

        # Count recent events of same type from same source
        count = 0
        for evt in self.recent_events:
            if evt["event_type"] == event_type and evt["source"] == source:
                age = (current_time - evt["timestamp"]).total_seconds()
                if age > 0:
                    # Exponential decay
                    weight = math.exp(-age / self.TEMPORAL_HALF_LIFE)
                    count += weight

        # Bonus: 0.03 per weighted event, max 0.15
        bonus = min(count * 0.03, 0.15)
        return bonus

    def _prune_old_events(self, current_time: datetime) -> None:
        """Remove events older than 2 half-lives."""
        cutoff = current_time.timestamp() - 2 * self.TEMPORAL_HALF_LIFE
        self.recent_events = [
            e for e in self.recent_events
            if e["timestamp"].timestamp() > cutoff
        ]
        # Keep list bounded
        if len(self.recent_events) > 1000:
            self.recent_events = self.recent_events[-1000:]

    def get_source_reliability_report(self) -> Dict[str, float]:
        """Return current source reliability scores."""
        return dict(self.source_reliability)

    def reset(self) -> None:
        """Reset all internal state."""
        self.source_reliability.clear()
        self.recent_events.clear()
        self.event_count = 0
        log.info("MIT state reset")
