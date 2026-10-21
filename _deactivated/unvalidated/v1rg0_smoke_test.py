# v1rg0_smoke_test.py — APPEND: Phase 8
# BUILD_R: Verify integration harness and TG6D bus import

def phase_8_integration_harness():
    """
    Verify:
      1. TG6D bus import path is unbroken
      2. V1rG0BusAdapter can be instantiated
      3. Integration harness loads without error
    """
    phase = "PHASE_8 | Integration Harness"
    try:
        # --- 8a: TG6D Bus Import ---
        try:
            from TG6D_regulator_bus import TG6DBus
            log.info("TG6D bus import: SUCCESS")
        except ImportError as e:
            log.error(f"TG6D bus import failed: {e}")
            raise RuntimeError(f"TG6D bus import broken: {e}")

        # --- 8b: V1rG0BusAdapter Instantiation ---
        try:
            from v1rg0_bus_integration import V1rG0BusAdapter
            bus_adapter = V1rG0BusAdapter(TG6DBus())
            log.info("V1rG0BusAdapter instantiation: SUCCESS")
        except Exception as e:
            log.error(f"V1rG0BusAdapter instantiation failed: {e}")
            raise RuntimeError(f"Bus adapter broken: {e}")

        # --- 8c: Integration Harness Load ---
        try:
            import v1rg0_integration_harness
            log.info("Integration harness import: SUCCESS")
        except ImportError as e:
            log.error(f"Integration harness import failed: {e}")
            raise RuntimeError(f"Harness import broken: {e}")

        record(phase, True, "3/3 integration checks passed")

    except Exception as e:
        record(phase, False, str(e))
