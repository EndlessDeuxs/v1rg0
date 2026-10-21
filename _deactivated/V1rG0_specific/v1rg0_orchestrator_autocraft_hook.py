# v1rg0_orchestrator_autocraft_hook.py

from autocraft_core import AutocraftBusAdapter

class OrchestratorWithAutocraft(Orchestrator):
    """
    Orchestrator extended with Autocraft mechanical dispatch.
    Uses the same compact trigger surface (mit_action).
    """

    def __init__(self, mit, proposal_builder, activator, bus_adapter, autocraft_adapter: AutocraftBusAdapter):
        super().__init__(mit, proposal_builder, activator, bus_adapter)
        self.autocraft_adapter = autocraft_adapter

    def ingest_event(self, parsed_event: dict) -> dict:
        base_result = super().ingest_event(parsed_event)

        # Mechanical dispatch hook — compact, trigger-driven
        self.autocraft_adapter.dispatch_mechanical(
            mit_action=base_result["mit_action"],
            packet=base_result["packet"],
            proposal=base_result["proposal"]
        )

        return base_result
