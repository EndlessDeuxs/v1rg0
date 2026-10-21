# v1rg0_memory_store.py — PATCHED
# INSPEC_TOR B2.1: Packet structure validation gate
# INSPEC_TOR B2.3: flush_tier consistency — clears both tier queue and main store

import logging
from collections import deque
from typing import Dict, Optional, List, Set

log = logging.getLogger("V1rG0.MemoryStore")


class MemoryStore:
    """
    Persistent (in-session) memory store for V1rG0 packets.

    PUSH: memory_store.push_memory(packet)
    PULL: memory_store.pull_latest()
          memory_store.pull_by_tier(tier)
          memory_store.pull_recent(limit)
          memory_store.pull_tier_counts()

    Tier-aware: dedicated queues for RETAIN / EXTRACT / FLUSH / UNKNOWN.

    B2.1: Validates required packet keys on push — warns on missing, stores anyway.
    B2.3: flush_tier clears both tier queue and main store for consistency.
    """

    VALID_TIERS:    Set[str] = {"RETAIN", "EXTRACT", "FLUSH", "UNKNOWN"}
    REQUIRED_KEYS:  Set[str] = {"tier", "composite", "salience", "pressure"}
    MAX_PER_TIER:   int      = 50
    MAX_TOTAL:      int      = 200

    def __init__(self, max_packets: Optional[int] = None):
        # Phase 9 (6): max_packets caps the main store (oldest dropped). Disk persistence (JSON in
        # V1RG0_DATA_DIR/memory.json) is done by the MemoryStore adapter in v1rg0_orchestrator_core.py.
        self.MAX_TOTAL = int(max_packets) if max_packets else self.MAX_TOTAL
        self._store: deque          = deque(maxlen=self.MAX_TOTAL)
        self._tier_queues: Dict[str, deque] = {
            tier: deque(maxlen=self.MAX_PER_TIER)
            for tier in self.VALID_TIERS
        }
        self._push_count: int       = 0
        self._latest: Optional[Dict] = None

    # ------------------------------------------------------------------
    # PUSH
    # ------------------------------------------------------------------

    def push_memory(self, packet: Dict) -> bool:
        """
        PUSH: Store a packet.
        B2.1: Validates required keys — warns on missing, stores anyway.
        Routes to tier queue based on packet['tier'].
        Returns True on success, False on type rejection.
        """

        # Type gate
        if not isinstance(packet, dict):
            log.warning("MemoryStore.push_memory: non-dict received — rejected.")
            return False

        # B2.1 — Structure validation
        missing = self.REQUIRED_KEYS - packet.keys()
        if missing:
            log.warning(
                f"MemoryStore.push_memory: packet missing keys {missing} "
                f"— storing with defaults applied."
            )
            # Apply safe defaults for missing keys
            defaults = {
                "tier":      "UNKNOWN",
                "composite": 0.0,
                "salience":  {},
                "pressure":  0.0
            }
            packet = {**{k: defaults[k] for k in missing}, **packet}

        # Tier normalization
        tier = packet.get("tier", "UNKNOWN")
        if tier not in self.VALID_TIERS:
            log.warning(
                f"MemoryStore.push_memory: unrecognized tier '{tier}' "
                f"— routing to UNKNOWN."
            )
            tier = "UNKNOWN"
            packet = {**packet, "tier": tier}

        # Store
        self._store.append(packet)
        self._tier_queues[tier].append(packet)
        self._latest = packet
        self._push_count += 1

        log.info(
            f"MemoryStore: stored | tier={tier} "
            f"| composite={packet.get('composite', 0.0):.4f} "
            f"| total_pushed={self._push_count}"
        )
        return True

    # ------------------------------------------------------------------
    # PULL INTERFACE
    # ------------------------------------------------------------------

    def pull_latest(self) -> Optional[Dict]:
        """PULL: Return the most recently stored packet."""
        return self._latest

    def pull_by_tier(self, tier: str, limit: int = 10) -> List[Dict]:
        """PULL: Return recent packets for a specific tier."""
        if tier not in self.VALID_TIERS:
            log.warning(f"MemoryStore.pull_by_tier: invalid tier '{tier}'")
            return []
        return list(self._tier_queues[tier])[-limit:]

    def pull_recent(self, limit: int = 10) -> List[Dict]:
        """PULL: Return recent packets across all tiers."""
        return list(self._store)[-limit:]

    def pull_tier_counts(self) -> Dict[str, int]:
        """PULL: Return count of stored packets per tier."""
        return {tier: len(q) for tier, q in self._tier_queues.items()}

    def pull_push_count(self) -> int:
        """PULL: Return total successful pushes this session."""
        return self._push_count

    # ------------------------------------------------------------------
    # UTILITY
    # ------------------------------------------------------------------

    def is_empty(self) -> bool:
        """True if no packets have been stored."""
        return self._push_count == 0

    def flush_tier(self, tier: str) -> int:
        """
        Clear a specific tier queue.
        B2.3: Also removes matching packets from main _store for consistency.
        Returns count of packets cleared from tier queue.
        """
        if tier not in self.VALID_TIERS:
            log.warning(f"MemoryStore.flush_tier: invalid tier '{tier}'")
            return 0

        count = len(self._tier_queues[tier])

        # B2.3 — Rebuild main store without flushed tier
        surviving = deque(
            (p for p in self._store if p.get("tier") != tier),
            maxlen=self.MAX_TOTAL
        )
        self._store = surviving

        # Clear tier queue
        self._tier_queues[tier].clear()

        # Rebuild _latest if it was in the flushed tier
        if self._latest and self._latest.get("tier") == tier:
            self._latest = self._store[-1] if self._store else None

        log.info(
            f"MemoryStore.flush_tier: tier={tier} cleared "
            f"| {count} removed from tier queue "
            f"| main store rebuilt ({len(self._store)} remaining)"
        )
        return count
