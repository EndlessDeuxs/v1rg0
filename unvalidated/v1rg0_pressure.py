# v1rg0_core/v1rg0_pressure.py
# BUILD_R: bounds validation added to PressureConfig

from typing import Dict
from dataclasses import dataclass, asdict

@dataclass
class PressureConfig:
    """
    Pressure model configuration.

    Bounds:
    - decay_rate: (0.0, 1.0] — must retain partial history, not amplify
    - gain_factor: [0.0, 1.0] — must not invert or exceed full weighting
    - baseline: [0.0, 1.0]   — neutral resting state
    - alert_threshold: (0.0, 1.0] — must be reachable

    Defaults validated against 8-event test harness and stress test:
    - 0.75 decay: pressure persists ~4-5 cycles for trend visibility
    - 0.25 gain: single event does not dominate; pattern required
    """
    decay_rate: float = 0.75
    gain_factor: float = 0.25
    baseline: float = 0.0
    alert_threshold: float = 0.8

    def __post_init__(self):
        if not (0.0 < self.decay_rate <= 1.0):
            raise ValueError(
                f"decay_rate must be in (0.0, 1.0], got {self.decay_rate}"
            )
        if not (0.0 <= self.gain_factor <= 1.0):
            raise ValueError(
                f"gain_factor must be in [0.0, 1.0], got {self.gain_factor}"
            )
        if not (0.0 <= self.baseline <= 1.0):
            raise ValueError(
                f"baseline must be in [0.0, 1.0], got {self.baseline}"
            )
        if not (0.0 < self.alert_threshold <= 1.0):
            raise ValueError(
                f"alert_threshold must be in (0.0, 1.0], got {self.alert_threshold}"
            )


class PressureModel:
    """Configurable pressure accumulator with validated config."""

    def __init__(self, config: PressureConfig = None):
        self.config = config or PressureConfig()
        self.pressure: float = self.config.baseline

    def update(self, composite: float) -> float:
        """
        Update pressure with new composite score.

        Formula:
        pressure = (pressure * decay_rate) + (composite * gain_factor)

        Exponential moving average:
        - Recent events weighted by gain_factor
        - Past pressure decays at decay_rate per cycle
        - Returns to baseline under sustained low input
        """
        delta = composite * self.config.gain_factor
        self.pressure = (self.pressure * self.config.decay_rate) + delta
        return self.pressure

    def reset(self) -> None:
        """Explicit reset to baseline."""
        self.pressure = self.config.baseline

    def is_alert(self) -> bool:
        return self.pressure >= self.config.alert_threshold

    def snapshot(self) -> Dict:
        return {
            "pressure": round(self.pressure, 6),
            "decay_rate": self.config.decay_rate,
            "gain_factor": self.config.gain_factor,
            "alert_threshold": self.config.alert_threshold,
            "alert_active": self.is_alert()
        }
