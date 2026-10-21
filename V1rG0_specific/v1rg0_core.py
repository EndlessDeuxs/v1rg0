# ============================================================
# V1rG0 SYSTEM — FULL BUILD
# SESSION: 74f53998
# ============================================================

import hashlib
import threading
import json
import os
from collections import deque
from enum import Enum, auto
from typing import Callable, Optional


# ============================================================
# v1rg0_proposal_builder.py
# ============================================================

class DeterministicIDGenerator:
    def __init__(self):
        self._sequence_counters = {}
        self._lock = threading.Lock()

    def generate_deterministic_id(self, source: str, timestamp: int) -> str:
        source_hash = hashlib.sha256(source.encode()).hexdigest()[:16]
        with self._lock:
            self._sequence_counters.setdefault(source_hash, 0)
            self._sequence_counters[source_hash] += 1
            sequence = self._sequence_counters[source_hash]
        raw_id = f"{source_hash}:{timestamp}:{sequence}"
        return hashlib.sha256(raw_id.encode()).hexdigest()[:32]

    def reset_sequence(self, source: str):
        source_hash = hashlib.sha256(source.encode()).hexdigest()[:16]
        with self._lock:
            self._sequence_counters[source_hash] = 0


# ============================================================
# v1rg0_session_persistence.py
# ============================================================

class PersistentQueue:
    def __init__(self, queue_path: Optional[str] = None):
        if queue_path is None:
            queue_path = os.path.join(os.environ.get("V1RG0_DATA_DIR", "/workspace/V1rG0_data"), "queue_state.json")
        self.queue_path = queue_path
        os.makedirs(os.path.dirname(queue_path), exist_ok=True)
        self._queue = deque()
        self._lock = threading.Lock()
        self._load_queue()

    def enqueue(self, item: dict):
        with self._lock:
            self._queue.append(item)
            self._save_queue()

    def dequeue(self) -> Optional[dict]:
        with self._lock:
            if self._queue:
                item = self._queue.popleft()
                self._save_queue()
                return item
            return None

    def flush(self):
        with self._lock:
            self._queue.clear()
            self._save_queue()

    def _save_queue(self):
        tmp_path = self.queue_path + ".tmp"
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(list(self._queue), f, default=str)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, self.queue_path)

    def _load_queue(self):
        try:
            with open(self.queue_path, 'r', encoding='utf-8') as f:
                self._queue = deque(json.load(f))
        except (FileNotFoundError, json.JSONDecodeError):
            self._queue = deque()


# ============================================================
# v1rg0_orchestrator.py
# ============================================================

class OrchestratorState(Enum):
    OPEN                 = auto()
    CLOSED               = auto()
    PENDING_COMPENSATION = auto()
    ESCALATED            = auto()
    FALLBACK_ACTIVE      = auto()
    HOLD_ACTIVE          = auto()


class OrchestratorStateMachine:
    def __init__(self, session_id: str, persistent_queue: PersistentQueue):
        self.session_id        = session_id
        self.queue             = persistent_queue
        self._state            = OrchestratorState.OPEN
        self._lock             = threading.Lock()
        self._retry_count      = 0
        self._compensation_id: Optional[str] = None
        self.MAX_RETRIES       = 3
        self.MAX_HOLD_TIME     = 300
        self._transitions      = self._build_transition_table()

    def _build_transition_table(self) -> dict:
        S = OrchestratorState
        non_terminal = [
            S.OPEN,
            S.PENDING_COMPENSATION,
            S.ESCALATED,
            S.FALLBACK_ACTIVE,
            S.HOLD_ACTIVE,
        ]
        table = {
            (S.OPEN,                 "compensation_dispatched")  : S.PENDING_COMPENSATION,
            (S.PENDING_COMPENSATION, "ack_received")             : S.CLOSED,
            (S.PENDING_COMPENSATION, "ack_timeout_retry")        : S.PENDING_COMPENSATION,
            (S.PENDING_COMPENSATION, "ack_timeout_escalate")     : S.ESCALATED,
            (S.ESCALATED,            "human_override")           : S.FALLBACK_ACTIVE,
            (S.ESCALATED,            "human_abort")              : S.CLOSED,
            (S.FALLBACK_ACTIVE,      "fallback_success")         : S.CLOSED,
            (S.FALLBACK_ACTIVE,      "fallback_failure")         : S.ESCALATED,
            (S.OPEN,                 "dependency_wait")          : S.HOLD_ACTIVE,
            (S.HOLD_ACTIVE,          "dependency_met")           : S.OPEN,
            (S.HOLD_ACTIVE,          "dependency_timeout")       : S.ESCALATED,
        }
        for state in non_terminal:
            table[(state, "session_abort")]   = S.CLOSED
            table[(state, "system_shutdown")] = S.CLOSED
        return table

    def transition(self, event: str, guard: bool = True,
                   action: Optional[Callable] = None) -> bool:
        with self._lock:
            key    = (self._state, event)
            target = self._transitions.get(key)
            if target is None:
                self._log(f"INVALID TRANSITION: {self._state.name} + '{event}' — rejected")
                return False
            if not guard:
                self._log(f"GUARD FAILED: {self._state.name} + '{event}' — blocked")
                return False
            prev         = self._state
            self._state  = target
            self.queue.enqueue({
                "session_id" : self.session_id,
                "event"      : event,
                "from_state" : prev.name,
                "to_state"   : target.name,
            })
            if action:
                action()
            self._log(f"TRANSITION: {prev.name} → {target.name} on '{event}'")
            return True

    def handle_dependency_wait(self, dependency_fn: Callable[[], bool]) -> bool:
        with self._lock:
            if dependency_fn():
                self._log("HOLD bypassed — dependency pre-satisfied")
                return True
        return self.transition(
            event  = "dependency_wait",
            guard  = True,
            action = self._suspend_session,
        )

    def shutdown(self, dispatch_confirmed: bool = False):
        if dispatch_confirmed:
            self.queue.flush()

    @property
    def state(self) -> OrchestratorState:
        return self._state

    def _suspend_session(self):
        self._log("Session suspended — awaiting external dependency")

    def _log(self, message: str):
        print(f"[ORCHESTRATOR:{self.session_id}] {message}")


# ============================================================
# regression_harness_state_machine.py
# ============================================================

class StateMachineValidator:
    def __init__(self, state_machine: OrchestratorStateMachine):
        self.transition_table = state_machine._transitions
        self.validation_log   = []

    def validate_transition(self, from_state: OrchestratorState,
                             event: str,
                             to_state: OrchestratorState,
                             guard: bool) -> bool:
        key      = (from_state, event)
        expected = self.transition_table.get(key)
        if expected is None:
            self.validation_log.append(
                f"UNKNOWN: {from_state.name}+'{event}' — not in table")
            return False
        if expected != to_state:
            self.validation_log.append(
                f"MISMATCH: {from_state.name}+'{event}' "
                f"expected {expected.name}, got {to_state.name}")
            return False
        if not guard:
            self.validation_log.append(
                f"GUARD_FAIL: {from_state.name}+'{event}' → {to_state.name}")
            return False
        self.validation_log.append(
            f"PASS: {from_state.name}+'{event}' → {to_state.name}")
        return True

    def run_full_suite(self) -> dict:
        S = OrchestratorState
        cases = [
            (S.OPEN,                 "compensation_dispatched",  S.PENDING_COMPENSATION, True),
            (S.PENDING_COMPENSATION, "ack_received",             S.CLOSED,               True),
            (S.PENDING_COMPENSATION, "ack_timeout_retry",        S.PENDING_COMPENSATION, True),
            (S.PENDING_COMPENSATION, "ack_timeout_escalate",     S.ESCALATED,            True),
            (S.ESCALATED,            "human_override",           S.FALLBACK_ACTIVE,      True),
            (S.ESCALATED,            "human_abort",              S.CLOSED,               True),
            (S.FALLBACK_ACTIVE,      "fallback_success",         S.CLOSED,               True),
            (S.FALLBACK_ACTIVE,      "fallback_failure",         S.ESCALATED,            True),
            (S.OPEN,                 "dependency_wait",          S.HOLD_ACTIVE,          True),
            (S.HOLD_ACTIVE,          "dependency_met",           S.OPEN,                 True),
            (S.HOLD_ACTIVE,          "dependency_timeout",       S.ESCALATED,            True),
            (S.OPEN,                 "session_abort",            S.CLOSED,               True),
            (S.OPEN,                 "system_shutdown",          S.CLOSED,               True),
            (S.PENDING_COMPENSATION, "session_abort",            S.CLOSED,               True),
            (S.PENDING_COMPENSATION, "system_shutdown",          S.CLOSED,               True),
            (S.ESCALATED,            "session_abort",            S.CLOSED,               True),
            (S.FALLBACK_ACTIVE,      "session_abort",            S.CLOSED,               True),
            (S.HOLD_ACTIVE,          "session_abort",            S.CLOSED,               True),
        ]
        for from_s, event, to_s, guard in cases:
            self.validate_transition(from_s, event, to_s, guard)
        return self.get_report()

    def get_report(self) -> dict:
        passed = sum(1 for e in self.validation_log if e.startswith("PASS"))
        failed = len(self.validation_log) - passed
        return {
            "total"  : len(self.validation_log),
            "passed" : passed,
            "failed" : failed,
            "log"    : self.validation_log,
        }