# v1rg0_compensation.py
import time

class PushPullCompensator:
    def __init__(self, event_log, base_delay=0.5, max_attempts=3, drain_threshold=100, drain_delay=0.05):
        self.event_log = event_log
        self.base_delay = base_delay
        self.max_attempts = max_attempts
        self.drain_threshold = drain_threshold
        self.drain_delay = drain_delay
        self._queue_depth = 0
        self._drain_mode = False

    def _check_drain_mode(self):
        if self._queue_depth >= self.drain_threshold:
            if not self._drain_mode:
                self._drain_mode = True
                self.event_log.record({
                    'event': 'drain_mode_engaged',
                    'queue_depth': self._queue_depth,
                    'drain_threshold': self.drain_threshold
                })
        elif self._queue_depth < self.drain_threshold // 2:
            if self._drain_mode:
                self._drain_mode = False
                self.event_log.record({
                    'event': 'drain_mode_disengaged',
                    'queue_depth': self._queue_depth
                })

    def _adaptive_delay(self, attempt, queue_depth):
        if self._drain_mode:
            return self.drain_delay
        exponential = self.base_delay * (2 ** attempt)
        queue_penalty = (queue_depth // 10) * 0.1
        return min(3.0, exponential + queue_penalty)

    def set_queue_depth(self, depth):
        self._queue_depth = depth
        self._check_drain_mode()

    def route(self, action, packet):
        path = 'direct' if action == 'pass' else 'hold'
        retries = 0
        success = False
        attempts = 1 if self._drain_mode else self.max_attempts
        for attempt in range(attempts):
            try:
                if path == 'direct':
                    self._emit_direct(packet)
                else:
                    self._emit_hold(packet)
                success = True
                if path == 'hold':
                    self._queue_depth = max(0, self._queue_depth - 1)
                    self._check_drain_mode()
                break
            except Exception as e:
                retries += 1
                delay = self._adaptive_delay(attempt, self._queue_depth)
                self.event_log.record({
                    'event': 'retry',
                    'attempt': attempt + 1,
                    'delay': delay,
                    'queue_depth': self._queue_depth,
                    'drain_mode': self._drain_mode,
                    'error': str(e)
                })
                time.sleep(delay)
        return {
            'path': path,
            'retries': retries,
            'success': success,
            'drain_mode': self._drain_mode
        }

    def _emit_direct(self, packet):
        pass

    def _emit_hold(self, packet):
        self._queue_depth += 1

class CompensationEventLog:
    def __init__(self):
        self.entries = []
    def record(self, event):
        self.entries.append(event)