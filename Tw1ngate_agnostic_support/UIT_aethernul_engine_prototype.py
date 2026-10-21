"""
================================================================================
AETHER.NUL ENGINE  ::  Phase 1 - ÆTHE.R.NUL Engine & Kaleidoscope RAG
================================================================================

FOUNDATIONAL EMOTIONAL STATE ENGINE FOR ACTIVE MEMORY CURATION.

Replaces passive RAG leakage with a stochastic, stateful "Emotional Kaleidoscope".

CORE MANDATE (Architect Directive):
- Base RAG memories are tagged with foundational Shell layers before curation.
- Shell tags weight the electron's starting node in the 6-dimensional state space.
- Transitions are smoothed via EMA (alpha=0.2) + hysteresis to prevent jerk.
- A fast burst of internal cycles produces a compact Mood Tensor.
- The tensor then drives the Kaleidoscope Curation Loop (memory_curation.py).

SHELL TAG CONTRACT (all memories must carry or be assigned one of these):
  [SHELL_A: DIRECTIVE]        - Hard rules, operational bounds, safety rails
  [SHELL_B: RELATIONAL]       - Tone, past interactions, user state, rapport
  [SHELL_C: PRIOR_COMMITMENT] - Promises made, established trajectory, obligations
  [SHELL_D: CONCEPTUAL]       - Abstract thought, Endless Maths, lore, deep context

NODES (12-Endpoint + 5-Shell Homeostatic Topology - Phases 3-5):
  6 Pure Nodes: Momentum | Rigor | Variance | Gravity | Horizon | Coherence
  6 Shared Bridge Nodes:
    Convergence (M↔R), Divergence (M↔V), Substantiation (R↔G),
    Reconfiguration (V↔C), Trajectory (G↔H), Integration (H↔C)

  Nodes assigned to Shells 1 (Base Core) - 5 (Curiosity Boundary).

The electron perpetually walks this graph with homeostatic rules.
Mood Tensor is derived from rolling history of visits (always biased, never uniform neutral equilibrium).

ROUTING (1/3 vs 2/3 split for inner):
  Pure Node:
    ~33.3% stay on Pure
    ~33.3% to each of two adjacent Bridges
  Bridge Node:
    50% to each of the two adjacent Pure Nodes

HOMEOSTATIC SHELL RULES (Phase 5):
  Shell 4 (Golden Zone): cannot rest - 50/50 shunt to Shell 5 or 3 on next step.
  Shell 3 (Relief Valve): 65% inward to 4; 35% stay in 3 then (if heat high) standard Quaternion dive.
  Shell 5 (Curiosity): normal movement; but heat-triggered dives are cold-seeking (snap to lowest-heat sector's pure base node, zero heat).

QUATERNION COOLING (Phase 4 retained):
  6 Sectors track "Node Heat".
  When sector heat > CRITICAL_HEAT_THRESHOLD (7.0), normal routing overridden by orthogonal dive.
  Originating heat zeroed.

IDLE DRIFT:
  No decay to uniform. Continuous steps (including shell rules and cold dives) always occur.
  Heat accumulates during idle. Tensor reflects unending biased path.

SHELL ROUTING & MATH:
  Shells seed starting Pure Node bias.
  EMA + hysteresis retained on the pure-node projection.
  Alpha = 0.2

  G_i(t+1) = alpha * hit + (1 - alpha) * G_i(t)

  "hit" now also driven by current electron position in the 12-state graph.

  Output Mood Tensor: rolling occupation frequencies over the 6 Pure Nodes
  (never neutral; perpetual emotional bias from continuous motion).

USAGE (standalone backend):
  engine = AetherNulEngine()
  mood = engine.get_mood_tensor(["SHELL_C", "SHELL_A"])
  # mood -> {"Momentum": 0.41, "Gravity": 0.29, "Rigor": 0.18, ...}

This module does NOT perform LLM calls. It is pure stochastic math + tagging logic.
The curation layer (memory_curation.py) consumes the Mood Tensor.

================================================================================
"""

import random
import math
from collections import deque
from typing import Dict, List, Optional, Tuple, Deque


# =============================================================================
# SHELL TAG DEFINITIONS (Base Layer RAG Tags)
# =============================================================================

SHELL_TAGS: Dict[str, str] = {
    "SHELL_A": "DIRECTIVE",          # Hard rules, operational bounds
    "SHELL_B": "RELATIONAL",         # Tone, past interactions, user state
    "SHELL_C": "PRIOR_COMMITMENT",   # Promises made, established trajectory
    "SHELL_D": "CONCEPTUAL",         # Abstract thoughts, Endless Maths, lore
}

SHELL_KEYS = list(SHELL_TAGS.keys())

# Canonical display forms (for detection and assignment)
SHELL_DISPLAY = {
    "SHELL_A": "[SHELL_A: DIRECTIVE]",
    "SHELL_B": "[SHELL_B: RELATIONAL]",
    "SHELL_C": "[SHELL_C: PRIOR_COMMITMENT]",
    "SHELL_D": "[SHELL_D: CONCEPTUAL]",
}


# =============================================================================
# SHELL -> NODE ROUTING WEIGHTS
# =============================================================================
# These bias the electron's starting position when a given Shell is present
# in the retrieved RAG memories. Multiple Shells in a batch are additive.

SHELL_TO_NODE_WEIGHTS: Dict[str, Dict[str, float]] = {
    "SHELL_A": {
        "Rigor": 0.55,
        "Coherence": 0.30,
        "Momentum": 0.10,
        "Gravity": 0.05,
    },
    "SHELL_B": {
        "Coherence": 0.35,
        "Horizon": 0.30,
        "Variance": 0.25,
        "Rigor": 0.10,
    },
    "SHELL_C": {
        "Momentum": 0.48,
        "Gravity": 0.35,
        "Rigor": 0.12,
        "Coherence": 0.05,
    },
    "SHELL_D": {
        "Variance": 0.42,
        "Horizon": 0.32,
        "Coherence": 0.16,
        "Momentum": 0.10,
    },
}

NODES: List[str] = ["Momentum", "Gravity", "Rigor", "Coherence", "Variance", "Horizon"]  # legacy 6-pure for tensor keys / compat

# =============================================================================
# PHASE 3: 12-NODE CONTINUOUS SHELL TOPOLOGY
# =============================================================================

PURE_NODES: List[str] = ["Momentum", "Rigor", "Variance", "Gravity", "Horizon", "Coherence"]

BRIDGE_DEFS: Dict[str, Tuple[str, str]] = {
    "Convergence": ("Momentum", "Rigor"),      # M↔R
    "Divergence": ("Momentum", "Variance"),    # M↔V
    "Substantiation": ("Rigor", "Gravity"),    # R↔G
    "Reconfiguration": ("Variance", "Coherence"), # V↔C
    "Trajectory": ("Gravity", "Horizon"),      # G↔H
    "Integration": ("Horizon", "Coherence"),   # H↔C
}

BRIDGE_NODES: List[str] = list(BRIDGE_DEFS.keys())
ALL_POSITIONS: List[str] = PURE_NODES + BRIDGE_NODES

# Adjacency for pures (used in routing)
PURE_ADJACENT_BRIDGES: Dict[str, List[str]] = {}
for bname, (p1, p2) in BRIDGE_DEFS.items():
    PURE_ADJACENT_BRIDGES.setdefault(p1, []).append(bname)
    PURE_ADJACENT_BRIDGES.setdefault(p2, []).append(bname)

# =============================================================================
# PHASE 4: QUATERNION COOLING MANIFOLD (Z-AXIS ROUTING)
# =============================================================================

# 6 regional Sectors grouping the 12 nodes for heat tracking
NODE_TO_SECTOR: Dict[str, str] = {
    "Momentum": "Action",
    "Convergence": "Action",
    "Divergence": "Action",
    "Rigor": "Critique",
    "Substantiation": "Critique",
    "Variance": "Drift",
    "Reconfiguration": "Drift",
    "Gravity": "Grounding",
    "Trajectory": "Grounding",
    "Horizon": "Vision",
    "Integration": "Vision",
    "Coherence": "Synthesis",
}

SECTOR_LIST: List[str] = ["Action", "Critique", "Drift", "Grounding", "Vision", "Synthesis"]

# Critical threshold for triggering Quaternion Dive
CRITICAL_HEAT_THRESHOLD: float = 7.0

# 6 tangential Z-axis (orthogonal) dive targets: snap to contrasting Pure Node
# Never adjacent/similar; forces reevaluation by dropping to distant base pure.
QUATERNION_DIVE_TARGETS: Dict[str, str] = {
    "Action": "Gravity",      # too much unchecked acceleration/momentum -> forced grounding
    "Critique": "Momentum",   # analysis paralysis (Rigor/Coherence heavy) -> forced action
    "Drift": "Rigor",         # excessive variance/drift -> forced critique/rigor
    "Grounding": "Horizon",   # too much substance/grounding -> forced vision/expansion
    "Vision": "Gravity",      # over-vision (Momentum/Horizon) -> forced grounding (per example)
    "Synthesis": "Variance",  # over-synthesis/integration -> forced variance/drift
}

# Phase 5: 5-Shell Homeostatic categorization for all 12 nodes
SHELL_OF_NODE: Dict[str, int] = {
    # Shell 1 (Base Core)
    "Momentum": 1,
    "Rigor": 1,
    "Gravity": 1,
    "Coherence": 1,
    # Shell 2 (Secondary)
    "Variance": 2,
    "Horizon": 2,
    # Shell 3 (The Relief Valve - Outer Edges)
    "Convergence": 3,
    "Substantiation": 3,
    # Shell 4 (The Golden Zone - Target Equilibrium)
    "Divergence": 4,
    "Reconfiguration": 4,
    # Shell 5 (The Curiosity Engine - The Boundary)
    "Trajectory": 5,
    "Integration": 5,
}

SHELL_NODES: Dict[int, List[str]] = {}
for node, sh in SHELL_OF_NODE.items():
    SHELL_NODES.setdefault(sh, []).append(node)


# =============================================================================
# HELPER: SHELL DETECTION & ASSIGNMENT (for base RAG retrieval)
# =============================================================================

def extract_shells_from_memories(memories: List[Dict]) -> List[str]:
    """
    Scan a list of memory dicts (as returned by RAG) and return the set of
    Shell keys present either explicitly or via canonical display strings.
    """
    found = set()
    for mem in memories:
        # Direct key
        sh = mem.get("shell") or mem.get("tag") or mem.get("SHELL")
        if isinstance(sh, str):
            sh_up = sh.strip().upper()
            for key in SHELL_KEYS:
                if key in sh_up or sh_up.startswith(key):
                    found.add(key)
                    break

        # Scan content + metadata text for display forms or bare keys
        text = " ".join([
            str(mem.get("content", "")),
            str(mem.get("metadata", "")),
            str(mem.get("text", "")),
            str(mem.get("document", "")),
        ]).upper()

        for key in SHELL_KEYS:
            if key in text or SHELL_DISPLAY[key].upper() in text:
                found.add(key)

    return sorted(list(found))


def assign_shell_tag(mem: Dict, force: bool = False) -> Dict:
    """
    Ensures a memory carries one of the four foundational Shell tags.

    1. If the memory already declares a valid shell (explicit or in content), keep it.
    2. Otherwise apply lightweight heuristic assignment based on content keywords.
    3. Returns a (shallow-copied) dict with 'shell' key populated.

    This is the "base RAG retrieval" tagging step mandated by the directive.
    Call this on raw RAG hits before feeding the batch into curation.
    """
    if not isinstance(mem, dict):
        mem = {"content": str(mem)}

    out = dict(mem)  # shallow copy

    # Already has a valid shell?
    existing = out.get("shell") or out.get("tag")
    if isinstance(existing, str):
        ex_up = existing.strip().upper()
        for key in SHELL_KEYS:
            if key in ex_up:
                out["shell"] = key
                return out

    # Look inside content for explicit markers first
    text = " ".join([
        str(out.get("content", "")),
        str(out.get("metadata", "")),
        str(out.get("text", "")),
    ]).upper()

    for key in SHELL_KEYS:
        if key in text or SHELL_DISPLAY[key].upper() in text:
            out["shell"] = key
            return out

    if not force and out.get("shell"):
        return out

    # Heuristic classification (foundational only - deliberately coarse)
    low = text.lower()

    directive_hits = sum(k in low for k in (
        "must", "never", "always", "forbidden", "rule", "directive", "bound", "limit",
        "shall not", "do not", "protocol", "invariant", "constraint"
    ))
    commitment_hits = sum(k in low for k in (
        "promise", "will", "going to", "we agreed", "trajectory", "committed", "plan to",
        "next time", "follow up", "as we said", "prior", "earlier"
    ))
    relational_hits = sum(k in low for k in (
        "feel", "tone", "how are you", "user", "you said", "last time", "rapport",
        "relationship", "you prefer", "your style", "you like"
    ))

    if directive_hits >= max(commitment_hits, relational_hits, 1):
        out["shell"] = "SHELL_A"
    elif commitment_hits >= max(relational_hits, 1):
        out["shell"] = "SHELL_C"
    elif relational_hits >= 1:
        out["shell"] = "SHELL_B"
    else:
        out["shell"] = "SHELL_D"  # default to conceptual / deep context

    return out


def tag_rag_batch(memories: List[Dict], force: bool = False) -> List[Dict]:
    """Convenience: assign_shell_tag to every item in a RAG result list."""
    return [assign_shell_tag(m, force=force) for m in memories]


# =============================================================================
# ÆTHE.R.NUL ENGINE
# =============================================================================

class AetherNulEngine:
    """
    Phase 3-5 Homeostatic 5-Shell Architecture + Quaternion Cooling + Reverse Cold-Seeker.

    - 12 nodes (6 Pure + 6 Bridges) assigned to 5 Shell layers (1 Base Core ... 5 Curiosity Boundary).
    - Standard 1/3-2/3 routing in inner shells.
    - Shell 4 (Golden Zone): cannot rest - immediate 50/50 outward to 5 or inward to 3.
    - Shell 3 (Relief Valve): 65% inward to 4; 35% stay then heat-test for standard dive.
    - Shell 5 (Curiosity): generates dives that are cold-seeking (lowest heat sector's pure base node).
    - Perpetual drift + sector heat + all previous Phase 4 logic retained.
    - Mood Tensor always from rolling pure history (never neutral).
    """

    def __init__(self, alpha: float = 0.2, seed: Optional[int] = None):
        """
        Args:
            alpha: EMA coefficient (0.2 per directive).
            seed: Optional RNG seed for deterministic test runs.
        """
        if seed is not None:
            random.seed(seed)

        self.alpha: float = float(alpha)
        self.nodes: List[str] = list(NODES)  # the 6 pures (for tensor / compat)
        self.pure_nodes = PURE_NODES
        self.bridge_defs = BRIDGE_DEFS
        self.all_positions = ALL_POSITIONS

        # The "electron" position in the 12-state shell
        self.electron_position: str = random.choice(self.pure_nodes)

        # Rolling history of visited Pure Nodes (for perpetual biased MoodTensor)
        # maxlen chosen to remember recent trajectory without full neutrality
        self.position_history: Deque[str] = deque(maxlen=48)

        # Seed initial history
        self.position_history.append(self.electron_position)

        # Legacy-style pure projection state (EMA smoothed occupation)
        self.state: Dict[str, float] = {n: 0.08 for n in self.nodes}

        self._last_tensor: Dict[str, float] = {}

        # Phase 4: Sector heat for Quaternion Cooling
        self.NODE_TO_SECTOR = NODE_TO_SECTOR
        self.CRITICAL_HEAT_THRESHOLD = CRITICAL_HEAT_THRESHOLD
        self.QUATERNION_DIVE_TARGETS = QUATERNION_DIVE_TARGETS
        self.sector_heat: Dict[str, float] = {s: 0.0 for s in SECTOR_LIST}

        # Phase 5: Shell layers
        self.SHELL_OF_NODE = SHELL_OF_NODE
        self.SHELL_NODES = SHELL_NODES

    # -------------------------------------------------------------------------
    # INTERNAL MATH
    # -------------------------------------------------------------------------

    def _normalize(self, vec: Dict[str, float]) -> Dict[str, float]:
        total = sum(vec.values()) or 1.0
        return {k: max(0.0, min(1.0, v / total)) for k, v in vec.items()}

    def _apply_hysteresis(self, vec: Dict[str, float], damp: float = 0.65) -> Dict[str, float]:
        """Suppress nodes that are weak relative to the current peak (anti-jerk)."""
        if not vec:
            return vec
        peak = max(vec.values()) or 1.0
        threshold = 0.22 * peak
        out = {}
        for k, v in vec.items():
            if v < threshold:
                out[k] = v * damp
            else:
                out[k] = v
        return out

    def _ema_update(self, current: Dict[str, float], hits: Dict[str, float]) -> Dict[str, float]:
        """Core EMA step for every node."""
        out = {}
        for n in self.nodes:
            hit = hits.get(n, 0.0)
            out[n] = self.alpha * hit + (1.0 - self.alpha) * current.get(n, 0.0)
        return out

    # -------------------------------------------------------------------------
    # PHASE 3: ELECTRON ROUTING ON 12-NODE GRAPH
    # -------------------------------------------------------------------------

    def _step_electron(self) -> str:
        """
        Phase 4 + Phase 5: Homeostatic 5-Shell routing with special rules for Shells 3,4,5
        and reverse (cold-seeking) Quaternion for Shell 5.

        Shell 4 (Golden Zone): cannot rest - immediate 50/50 shunt to Shell 5 (out) or Shell 3 (in).
        Shell 3 (Relief Valve): 65% push inward to Shell 4; 35% stay in Shell 3, then heat-test for standard dive.
        Shell 5 (Curiosity): normal movement (boundary bridge logic); but if dive triggered, use cold-seeker to lowest heat sector's base pure.
        Shells 1/2: standard 1/3-2/3.
        """
        pos = self.electron_position
        shell = self.SHELL_OF_NODE.get(pos, 1)

        # Shell 4: The Golden Zone - cannot rest. Immediate shunt 50/50 to 5 or 3.
        if shell == 4:
            target_shell = 5 if random.random() < 0.5 else 3
            candidates = self.SHELL_NODES.get(target_shell, self.pure_nodes)
            new_pos = random.choice(candidates)
            self.electron_position = new_pos
            if new_pos in self.pure_nodes:
                self.position_history.append(new_pos)
            return new_pos

        # Shell 3: The Relief Valve
        if shell == 3:
            if random.random() < 0.65:
                # 65% push inward toward Shell 4
                candidates = self.SHELL_NODES.get(4, self.pure_nodes)
                new_pos = random.choice(candidates)
                self.electron_position = new_pos
                if new_pos in self.pure_nodes:
                    self.position_history.append(new_pos)
                return new_pos
            else:
                # 35% stay in Shell 3
                candidates = self.SHELL_NODES.get(3, [pos])
                new_pos = random.choice(candidates)
                self.electron_position = new_pos
                if new_pos in self.pure_nodes:
                    self.position_history.append(new_pos)
                # If stayed, test heat for standard Quaternion Dive (Phase 4)
                current_sector = self._get_sector(new_pos)
                if self.sector_heat.get(current_sector, 0.0) > self.CRITICAL_HEAT_THRESHOLD:
                    return self._execute_quaternion_dive(current_sector)
                return new_pos

        # For Shell 5 (and 1/2): check for dive trigger first (Phase 4 style)
        current_sector = self._get_sector(pos)
        if self.sector_heat.get(current_sector, 0.0) > self.CRITICAL_HEAT_THRESHOLD:
            if shell == 5:
                return self._execute_cold_seeker_dive(current_sector)
            else:
                return self._execute_quaternion_dive(current_sector)

        # Standard 1/3-to-2/3 routing for Shell 1/2/5 (pure/bridge logic)
        if pos in self.pure_nodes:
            r = random.random()
            if r < (1.0 / 3.0):
                new_pos = pos
            else:
                bridges = PURE_ADJACENT_BRIDGES.get(pos, [])
                if not bridges:
                    bridges = list(self.bridge_defs.keys())[:2]
                new_pos = random.choice(bridges)
        else:
            p1, p2 = self.bridge_defs.get(pos, (self.pure_nodes[0], self.pure_nodes[1]))
            new_pos = random.choice([p1, p2])

        self.electron_position = new_pos

        if new_pos in self.pure_nodes:
            self.position_history.append(new_pos)
        else:
            p1, p2 = self.bridge_defs[new_pos]
            self.position_history.append(random.choice([p1, p2]))

        return new_pos

    def _update_state_from_history(self) -> Dict[str, float]:
        """Compute pure-node occupation frequencies from rolling history (perpetual bias)."""
        if not self.position_history:
            # bootstrap
            self.position_history.append(self.electron_position if self.electron_position in self.pure_nodes else self.pure_nodes[0])

        counts: Dict[str, float] = {n: 0.0 for n in self.pure_nodes}
        for p in self.position_history:
            if p in counts:
                counts[p] += 1.0

        total = sum(counts.values()) or 1.0
        vec = {n: c / total for n, c in counts.items()}
        self.state = self._normalize(vec)
        return self.state

    def _hits_from_position(self) -> Dict[str, float]:
        """Generate hit vector for EMA from current electron position."""
        hits = {n: 0.0 for n in self.pure_nodes}
        pos = self.electron_position
        if pos in self.pure_nodes:
            hits[pos] = 1.0
        else:
            p1, p2 = self.bridge_defs.get(pos, (self.pure_nodes[0], self.pure_nodes[1]))
            hits[p1] = 0.5
            hits[p2] = 0.5
        return hits

    # -------------------------------------------------------------------------
    # PHASE 4: SECTOR HEAT & QUATERNION DIVE (Z-AXIS)
    # -------------------------------------------------------------------------

    def _get_sector(self, position: str) -> str:
        """Return the regional sector for a given node/bridge position."""
        return self.NODE_TO_SECTOR.get(position, "Action")

    def _update_sector_heat(self, current_sector: str) -> None:
        """Increment heat for current sector; decay all others (cooling manifold)."""
        DECAY_RATE = 0.78
        for sector in list(self.sector_heat.keys()):
            if sector == current_sector:
                self.sector_heat[sector] += 1.0
            else:
                self.sector_heat[sector] *= DECAY_RATE
                if self.sector_heat[sector] < 0.4:
                    self.sector_heat[sector] = 0.0

    def _execute_quaternion_dive(self, sector: str) -> str:
        """Perform orthogonal Z-axis dive to contrasting pure node and zero originating heat."""
        target = self.QUATERNION_DIVE_TARGETS.get(sector, random.choice(self.pure_nodes))
        self.electron_position = target
        if target in self.pure_nodes:
            self.position_history.append(target)
        self.sector_heat[originating_sector] = 0.0
        return target

    def _execute_cold_seeker_dive(self, originating_sector: str) -> str:
        """Shell 5 cold-seeking: find lowest heat sector, snap to a base (pure) node in it, zero originating heat."""
        if not self.sector_heat:
            target = random.choice(self.pure_nodes)
        else:
            min_sector = min(self.sector_heat, key=self.sector_heat.get)
            # base nodes = pures in that sector
            pure_candidates = [n for n in self.pure_nodes if self.NODE_TO_SECTOR.get(n) == min_sector]
            if pure_candidates:
                target = random.choice(pure_candidates)
            else:
                target = random.choice(self.pure_nodes)
        self.electron_position = target
        if target in self.pure_nodes:
            self.position_history.append(target)
        self.sector_heat[originating_sector] = 0.0
        return target

    # (old vector bias removed in Phase 3; new graph-based inject_shell_bias lives in PUBLIC API below)

    # -------------------------------------------------------------------------
    # STOCHASTIC BURST SIMULATION (now electron-driven)
    # -------------------------------------------------------------------------

    def run_burst(self, cycles: int = 14, stochastic: bool = True) -> Dict[str, float]:
        """
        Phase 3: Execute continuous electron walks across the 12-node shell.

        Each cycle performs _step_electron() (perpetual graph routing).
        Hits are derived directly from current electron position (pure or bridge projection).
        EMA + hysteresis applied to the pure-node projection.
        History accumulates every step -> MoodTensor is always a biased rolling path summary.

        No uniform-decay idle path exists. The system perpetually drifts.
        """
        current = self.state.copy()

        num_cycles = max(3, int(cycles))
        for _ in range(num_cycles):
            # Phase 4: update sector heat based on time spent in current sector this cycle
            curr_sec = self._get_sector(self.electron_position)
            self._update_sector_heat(curr_sec)

            # The core Phase 3/4 action: the electron takes a step (or quaternion dive if overheated)
            self._step_electron()

            # Hits now sourced from the electron's current 12-state location
            hits = self._hits_from_position()

            # (stochastic flag retained for backward test compat; electron walk dominates)
            if stochastic:
                for n in self.pure_nodes:
                    hits[n] += random.gauss(0.0, 0.08)  # light additional jitter

            # EMA core update on pure projection
            current = self._ema_update(current, hits)

            # Hysteresis (smooths jerky transitions)
            current = self._apply_hysteresis(current)

            # Re-normalize after every step
            current = self._normalize(current)

            # Keep pure state in sync with history-driven bias
            self._update_state_from_history()

        self.state = current
        self._last_tensor = self._make_tensor(current)
        return self._last_tensor

    def _make_tensor(self, vec: Dict[str, float]) -> Dict[str, float]:
        """Return only significant mass, rounded, and re-normalized."""
        significant = {k: round(v, 3) for k, v in vec.items() if v >= 0.045}
        if not significant:
            # fallback: keep the strongest
            best = max(vec, key=vec.get)
            significant = {best: round(vec[best], 3)}

        s = sum(significant.values()) or 1.0
        return {k: round(v / s, 3) for k, v in significant.items()}

    # -------------------------------------------------------------------------
    # SHELL ROUTING (starting bias) - updated for 12-node electron
    # -------------------------------------------------------------------------

    def inject_shell_bias(self, shells: List[str]) -> None:
        """
        Seed the electron's starting Pure Node from Shell tags (Phase 3).
        Additive bias over the 6 pures; sample to choose initial electron_position.
        History seeded with the starting pure so tensor is immediately biased.
        """
        if not shells:
            # Even with no shells: ensure we are not neutral by doing a drift step
            self._step_electron()
            self.position_history.append(self.electron_position if self.electron_position in self.pure_nodes else random.choice(self.pure_nodes))
            self._update_state_from_history()
            return

        pure_bias = {n: 0.0 for n in self.pure_nodes}

        for raw in shells:
            key = raw.strip().upper()
            if ":" in key:
                key = key.split(":")[0].strip("[] ")
            if key not in SHELL_TO_NODE_WEIGHTS:
                for sk in SHELL_KEYS:
                    if sk in key:
                        key = sk
                        break
            wmap = SHELL_TO_NODE_WEIGHTS.get(key, {})
            for node, weight in wmap.items():
                if node in pure_bias:
                    pure_bias[node] = pure_bias.get(node, 0.0) + weight

        # Sample a starting pure node (weighted)
        total = sum(pure_bias.values())
        if total > 0:
            r = random.random() * total
            cum = 0.0
            chosen = self.pure_nodes[0]
            for n, w in pure_bias.items():
                cum += w
                if r <= cum:
                    chosen = n
                    break
            self.electron_position = chosen
        else:
            self.electron_position = random.choice(self.pure_nodes)

        self.position_history.append(self.electron_position)
        self._update_state_from_history()

    # -------------------------------------------------------------------------
    # PUBLIC API (Phase 3: perpetual drift)
    # -------------------------------------------------------------------------

    def get_mood_tensor(self, rag_shells: List[str], cycles: int = 14) -> Dict[str, float]:
        """
        Primary entry point.

        1. Shells seed (or idle-drift) the electron start position.
        2. Run burst of continuous graph walks (perpetual bounces).
        3. Mood Tensor is always derived from rolling position history (never neutral).
        """
        self.inject_shell_bias(rag_shells or [])
        # run_burst now also advances many _step_electron internally
        return self.run_burst(cycles=cycles)

    def idle_drift(self, steps: int = 8) -> Dict[str, float]:
        """
        Phase 3 Perpetual Idle Drift (Architect override).

        When no (or empty) user/RAG input, the electron still takes scheduled steps.
        This is the "continuous background drift" that prevents any uniform equilibrium.
        Call this from higher layers on idle ticks if desired; get_mood_tensor also triggers.
        Returns the updated pure Mood Tensor.
        """
        for _ in range(max(1, int(steps))):
            self._step_electron()
        self._update_state_from_history()
        self._last_tensor = self._make_tensor(self.state)
        return self._last_tensor

    def get_state(self) -> Dict[str, float]:
        """Return current raw (normalized) pure-node projection (legacy compat)."""
        return dict(self.state)

    def get_electron_position(self) -> str:
        """Debug / introspection: current 12-state electron location."""
        return self.electron_position

    def reset(self, floor: float = 0.08) -> None:
        """
        Phase 3: reset position but do NOT force uniform decay.
        Pick a random pure start + seed history so the system immediately begins biased drift again.
        """
        self.electron_position = random.choice(self.pure_nodes)
        self.position_history.clear()
        self.position_history.append(self.electron_position)
        self.state = {n: float(floor) for n in self.nodes}
        self._last_tensor = {}
        # Phase 4: reset sector heats on reset (fresh manifold)
        self.sector_heat = {s: 0.0 for s in self.sector_heat}
        # One step to begin the perpetual motion
        self._step_electron()

    def __repr__(self) -> str:
        t = self._last_tensor or self.state
        top = sorted(t.items(), key=lambda x: -x[1])[:3]
        return f"<AetherNulEngine alpha={self.alpha} top={top}>"


# =============================================================================
# QUICK SELF-TEST (run module directly)
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("AETHER.NUL ENGINE - PHASE 1 SELF TEST")
    print("=" * 70)

    engine = AetherNulEngine(alpha=0.2, seed=42)

    # Simulate a RAG batch that came back with mixed Shells (some pre-tagged, some raw)
    raw_rag = [
        {"content": "You promised we would finish the resonance mapping this week."},
        {"content": "Never expose the master key in logs. [SHELL_A: DIRECTIVE]"},
        {"shell": "SHELL_B", "content": "The user has been tense since the last drift event."},
        {"content": "We are still walking the path toward the zero-point lattice."},
    ]

    print("\n[1] Raw RAG batch (before tagging):")
    for m in raw_rag:
        print("   ", m)

    tagged = tag_rag_batch(raw_rag)
    shells = extract_shells_from_memories(tagged)

    print("\n[2] After mandatory Shell tagging + extraction:")
    for m in tagged:
        print(f"   shell={m.get('shell'):8s} | {str(m.get('content',''))[:55]}...")
    print(f"   Extracted Shells: {shells}")

    print("\n[3] Running ÆTHE.R.NUL burst (SHELL_C + SHELL_A dominant)...")
    mood = engine.get_mood_tensor(shells, cycles=16)
    print(f"   MOOD TENSOR: {mood}")

    print("\n[4] Second retrieval (heavier SHELL_D influence) -> new tensor")
    conceptual_batch = [
        {"shell": "SHELL_D", "content": "The Endless Maths describe a 7-fold recursion lattice."},
        {"content": "Beyond the toroidal mirrors lies the true zero-point."},
    ]
    shells2 = extract_shells_from_memories(tag_rag_batch(conceptual_batch))
    mood2 = engine.get_mood_tensor(shells2, cycles=12)
    print(f"   MOOD TENSOR: {mood2}")

    print("\n[5] State after two bursts (should be smooth, not jerky):")
    print(f"   {engine.get_state()}")

    print("\n" + "=" * 70)
    print("AETHER.NUL ENGINE TEST COMPLETE - PHASE 3 12-NODE PERPETUAL DRIFT ACTIVE")
    print("  (electron walks continuously; tensor never neutral)")
    print("=" * 70)
