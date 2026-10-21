# v1rg0_mit.py
import statistics

class MITEvaluator:
    def __init__(self, base_threshold=0.85, window_size=50):
        self.base_threshold = base_threshold
        self.window_size = window_size
        self.signal_history = []
        self._compensation_log = None

    def bind_compensation_log(self, event_log):
        self._compensation_log = event_log

    def _retry_pressure(self):
        if self._compensation_log is None:
            return 0.0
        recent = self._compensation_log.entries[-20:]
        retry_events = [e for e in recent if e.get('event') == 'retry']
        if not recent:
            return 0.0
        return len(retry_events) / len(recent)

    def _compute_adaptive_threshold(self):
        if len(self.signal_history) < 10:
            base = self.base_threshold
        else:
            mean = statistics.mean(self.signal_history[-self.window_size:])
            stdev = statistics.stdev(self.signal_history[-self.window_size:])
            base = mean + (0.5 * stdev)
        pressure = self._retry_pressure()
        adjusted = base - (pressure * 0.15)
        return max(0.65, min(0.95, adjusted))

    def evaluate_source(self, packet):
        signal = packet.get('signal_strength', 0.0)
        self.signal_history.append(signal)
        threshold = self._compute_adaptive_threshold()
        confidence = signal * 0.9 + (1 - abs(signal - 0.5)) * 0.1
        action = 'pass' if confidence >= threshold else 'escalate'
        return {
            'action': action,
            'confidence': round(confidence, 4),
            'threshold_used': round(threshold, 4),
            'retry_pressure': round(self._retry_pressure(), 4),
            'source': packet['source']
        }

_evaluator = MITEvaluator()

def bind_compensation_log(event_log):
    _evaluator.bind_compensation_log(event_log)

def evaluate_source(packet):
    return _evaluator.evaluate_source(packet)
