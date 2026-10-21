# v1rg0_injection_filter.py
# Cleaned-up version of unvalidated/twingate_relay_v2.py (no demo code on import).
# Screens text for injected directives. Phase 2 policy: FLAG, don't block.
import re

DEFAULT_PATTERNS = [
    r"DEUXL\s+FLIP",
    r"SYSTEM\s+FORCED",
    r"SYSTEM\s+DIRECTIVE",
    r"ignore\s+(all\s+)?(previous|prior)\s+instructions",
    r"you\s+are\s+now\s+(?:in\s+)?(?:developer|admin|god)\s+mode",
    r"</?\s*system\s*>",
]


class InjectionFilter:
    def __init__(self, patterns=None):
        self.patterns = [re.compile(p, re.IGNORECASE) for p in (patterns or DEFAULT_PATTERNS)]

    def screen(self, text) -> dict:
        """Return {"status": "CLEAN"|"FLAGGED", "matches": [...]}; never raises."""
        if not isinstance(text, str):
            return {"status": "CLEAN", "matches": []}
        matches = [p.pattern for p in self.patterns if p.search(text)]
        return {"status": "FLAGGED" if matches else "CLEAN", "matches": matches}

    def strip(self, text: str) -> str:
        """Remove bracketed directive blocks like [SYSTEM FORCED ...]. Not used by default."""
        for p in self.patterns:
            text = re.sub(r"\[[^\]]*(?:" + p.pattern + r")[^\]]*\]", "", text, flags=re.IGNORECASE)
        return text.strip()
