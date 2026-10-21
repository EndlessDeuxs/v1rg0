# v1rg0_compensation.py
# BUILD_R: Push/pull compensation layer
# Ensures flow continues when a component stalls

import logging
from typing import Dict, Any, Optional, Callable
from enum import Enum

log = logging.getLogger("V1rG0.Compensation")


class CompensationStrategy(Enum):
    """Available compensation strategies for stalled components."""
    RETRY = "retry"              # Retry the push/pull N times
    ESCALATE = "escalate"        # Escalate to downstream activator
    FALLBACK = "fallback"        # Use a default value
    BYPASS = "bypass"            # Skip the stalled component
    HOLD = "hold"                # Hold the packet and retry later


class PushPullCompensator:
    """
    Compensation layer for the V1rG0 push/pull chain.
    
    If a component stalls (push fails or pull returns empty),
    the compensator applies a strategy to keep the flow moving.
    
    Strategies:
        RETRY:     Retry the operation N times with exponential backoff
        ESCALATE:  Push the packet to a higher-priority handler
        FALLBACK:  Return a default value and continue
        BYPASS:    Skip the stalled component entirely
        HOLD:      Queue the packet for retry on next tick
    """
    
    def __init__(self, max_retries: int = 3, backoff_seconds: float = 0.1):
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.hold_queue: list = []
        self.fallback_values: Dict[str, Any] = {}
    
    def push_with_compensation(
        self,
        push_fn: Callable[[], Any],
        strategy: CompensationStrategy = CompensationStrategy.RETRY,
        fallback: Any = None,
        context: str = "unknown"
    ) -> Any:
        """
        Execute a push operation with compensation.
        
        If the push fails, apply the specified strategy.
        Returns the result of the push or the compensated value.
        """
        if strategy == CompensationStrategy.RETRY:
            return self._retry_push(push_fn, context)
        elif strategy == CompensationStrategy.ESCALATE:
            return self._escalate_push(push_fn, context)
        elif strategy == CompensationStrategy.FALLBACK:
            return self._fallback_push(push_fn, fallback, context)
        elif strategy == CompensationStrategy.BYPASS:
            return self._bypass_push(push_fn, context)
        elif strategy == CompensationStrategy.HOLD:
            return self._hold_push(push_fn, context)
        else:
            log.warning(f"Unknown compensation strategy: {strategy}")
            return push_fn()
    
    def pull_with_compensation(
        self,
        pull_fn: Callable[[], Any],
        strategy: CompensationStrategy = CompensationStrategy.FALLBACK,
        fallback: Any = None,
        context: str = "unknown"
    ) -> Any:
        """
        Execute a pull operation with compensation.
        
        If the pull returns None/empty, apply the specified strategy.
        Returns the pulled value or the compensated value.
        """
        result = pull_fn()
        
        if result is not None and result != [] and result != {}:
            return result  # Pull succeeded — return normally
        
        # Pull returned empty — apply compensation
        if strategy == CompensationStrategy.RETRY:
            return self._retry_pull(pull_fn, context)
        elif strategy == CompensationStrategy.FALLBACK:
            log.info(f"Pull compensation: using fallback for {context}")
            return fallback
        elif strategy == CompensationStrategy.HOLD:
            self.hold_queue.append({"pull_fn": pull_fn, "context": context})
            log.info(f"Pull compensation: held {context} for retry")
            return fallback
        else:
            log.warning(f"Pull compensation: no strategy for {context}")
            return fallback
    
    def _retry_push(self, push_fn: Callable, context: str) -> Any:
        """Retry a push operation with exponential backoff."""
        import time
        for attempt in range(self.max_retries):
            try:
                return push_fn()
            except Exception as e:
                if attempt < self.max_retries - 1:
                    wait = self.backoff_seconds * (2 ** attempt)
                    log.warning(
                        f"Push retry {attempt + 1}/{self.max_retries} "
                        f"for {context}: {e} — waiting {wait:.2f}s"
                    )
                    time.sleep(wait)
                else:
                    log.error(
                        f"Push failed after {self.max_retries} retries "
                        f"for {context}: {e}"
                    )
                    raise
    
    def _retry_pull(self, pull_fn: Callable, context: str) -> Any:
        """Retry a pull operation with exponential backoff."""
        import time
        for attempt in range(self.max_retries):
            result = pull_fn()
            if result is not None and result != [] and result != {}:
                return result
            if attempt < self.max_retries - 1:
                wait = self.backoff_seconds * (2 ** attempt)
                log.warning(
                    f"Pull retry {attempt + 1}/{self.max_retries} "
                    f"for {context}: returned empty — waiting {wait:.2f}s"
                )
                time.sleep(wait)
        log.warning(
            f"Pull failed after {self.max_retries} retries "
            f"for {context}: returning None"
        )
        return None
    
    def _escalate_push(self, push_fn: Callable, context: str) -> Any:
        """Escalate a push operation to a higher-priority handler."""
        try:
            return push_fn()
        except Exception as e:
            log.warning(
                f"Push escalation for {context}: {e} — "
                f"packet will be flagged for manual review"
            )
            return {"escalated": True, "context": context, "error": str(e)}
    
    def _fallback_push(self, push_fn: Callable, fallback: Any, context: str) -> Any:
        """Execute a push with a fallback value on failure."""
        try:
            return push_fn()
        except Exception as e:
            log.warning(
                f"Push fallback for {context}: {e} — using default"
            )
            return fallback
    
    def _bypass_push(self, push_fn: Callable, context: str) -> Any:
        """Skip a push operation entirely and return None."""
        log.info(f"Push bypass for {context}: component skipped")
        return None
    
    def _hold_push(self, push_fn: Callable, context: str) -> Any:
        """Queue a push operation for retry on next tick."""
        self.hold_queue.append({"push_fn": push_fn, "context": context})
        log.info(f"Push hold for {context}: queued for retry")
        return None
    
    def process_hold_queue(self) -> int:
        """
        Retry all held operations.
        Returns the number of successfully processed holds.
        """
        processed = 0
        remaining = []
        
        for item in self.hold_queue:
            try:
                item["push_fn"]()
                processed += 1
            except Exception as e:
                log.warning(
                    f"Hold retry failed for {item['context']}: {e} — "
                    f"keeping in queue"
                )
                remaining.append(item)
        
        self.hold_queue = remaining
        return processed
    
    def register_fallback(self, key: str, value: Any) -> None:
        """Register a fallback value for a specific context."""
        self.fallback_values[key] = value
        log.debug(f"Fallback registered: {key} = {value}")
