# autocraft_core.py
# Mechanical execution tier for V1rG0/TG6D
# Maps logical packets & proposals to concrete mechanical routines

from enum import Enum
from typing import Dict, Any, Callable, Optional, List
import logging

log = logging.getLogger("Autocraft.Core")


class AutocraftMode(Enum):
    """Operating modes for the Autocraft tier."""
    SIMULATION = "simulation"      # Dry-run, no external side effects
    EXECUTION = "execution"        # Real mechanical / system effects
    DIAGNOSTIC = "diagnostic"      # Self-test and stress probes


class AutocraftTrigger(Enum):
    """Compact trigger surface, aligned with MIT actions."""
    ESCALATE = "escalate"          # High-impact mechanical routine
    EMIT = "emit"                  # Normal mechanical routine
    HOLD = "hold"                  # Queue for later mechanical run
    SUPPRESS = "suppress"          # No mechanical action


class AutocraftRoutine:
    """
    Single mechanical routine descriptor.
    Represents an atomic or small-batch mechanical action.
    """
    def __init__(
        self,
        name: str,
        input_schema: Dict[str, Any],
        execute_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
        mode: AutocraftMode = AutocraftMode.EXECUTION
    ):
        self.name = name
        self.input_schema = input_schema
        self.execute_fn = execute_fn
        self.mode = mode

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the routine. In SIMULATION mode, return a simulated result.
        """
        log.debug(f"AutocraftRoutine[{self.name}] mode={self.mode}")
        if self.mode == AutocraftMode.SIMULATION:
            return {
                "routine": self.name,
                "mode": self.mode.value,
                "simulated": True,
                "input": payload
            }
        return self.execute_fn(payload)


class AutocraftBusAdapter:
    """
    Autocraft-side adapter to the TG6D/V1rG0 bus.
    Consumes packets & proposals, emits mechanical jobs/routines.
    """
    def __init__(self):
        self.routines: Dict[str, AutocraftRoutine] = {}
        self.hold_queue: List[Dict[str, Any]] = []

    def register_routine(self, routine: AutocraftRoutine) -> None:
        self.routines[routine.name] = routine
        log.info(f"Autocraft: routine registered: {routine.name}")

    def dispatch_mechanical(
        self,
        mit_action: str,
        packet: Dict[str, Any],
        proposal: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Core entrypoint from V1rG0.
        Uses compact triggers mapped directly from mit_action.
        """
        trigger = self._map_mit_action(mit_action)
        if trigger == AutocraftTrigger.SUPPRESS:
            log.debug("Autocraft: SUPPRESS — no mechanical dispatch")
            return {"status": "suppressed"}

        job = self._build_mechanical_job(packet, proposal, trigger)

        if trigger == AutocraftTrigger.HOLD:
            self.hold_queue.append(job)
            log.info("Autocraft: job held for later execution")
            return {"status": "held", "job_id": job.get("job_id")}

        return self._execute_job(job)

    def process_hold_queue(self) -> int:
        """
        Execute all held mechanical jobs.
        Returns the number of successfully executed jobs.
        """
        processed = 0
        remaining = []
        for job in self.hold_queue:
            try:
                self._execute_job(job)
                processed += 1
            except Exception as e:
                log.warning(f"Autocraft: held job failed: {e}")
                remaining.append(job)
        self.hold_queue = remaining
        return processed

    def _map_mit_action(self, mit_action: str) -> AutocraftTrigger:
        """
        Compact mapping: MIT action → Autocraft trigger.
        Only ESCALATE and EMIT drive primary mechanical work.
        """
        if mit_action == "escalate":
            return AutocraftTrigger.ESCALATE
        if mit_action == "emit":
            return AutocraftTrigger.EMIT
        if mit_action == "hold":
            return AutocraftTrigger.HOLD
        return AutocraftTrigger.SUPPRESS

    def _build_mechanical_job(
        self,
        packet: Dict[str, Any],
        proposal: Optional[Dict[str, Any]],
        trigger: AutocraftTrigger
    ) -> Dict[str, Any]:
        """
        Construct a minimal mechanical job envelope.
        Compact, bus-friendly, ready for execution.
        """
        return {
            "job_id": packet.get("event_id"),
            "trigger": trigger.value,
            "resource": packet.get("resource_id"),
            "priority": packet.get("priority"),
            "proposal_snapshot": proposal,
            "payload": packet.get("payload", {})
        }

    def _execute_job(self, job: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute mechanical job by selecting routine based on resource/trigger.
        """
        routine_name = f"{job['resource']}:{job['trigger']}"
        routine = self.routines.get(routine_name)

        if not routine:
            log.warning(f"Autocraft: no routine for {routine_name}")
            return {"status": "no_routine", "routine": routine_name}

        result = routine.run(job["payload"])
        return {
            "status": "executed",
            "routine": routine_name,
            "result": result
        }
