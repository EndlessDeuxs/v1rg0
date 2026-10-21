# twingate_relay_v2.py
import re

class TwingateRelay:
    FLAGGED_PATTERNS = ["DEUXL FLIP", "SYSTEM FORCED", "SYSTEM DIRECTIVE"]
    
    def parse_incoming(self, raw_block: str) -> dict:
        for pattern in self.FLAGGED_PATTERNS:
            if pattern in raw_block:
                return {"status": "FLAGGED", "reason": "directive_injection_detected", "pattern": pattern, "raw": raw_block}
        return {"status": "CLEAN", "raw": raw_block}
    
    def format_request(self, module_name: str, context: dict, task: str) -> dict:
        return {
            "protocol": "twingate_v2",
            "module": module_name,
            "context": context,
            "task": task,
            "constraints": {"headers_are_data": True, "persona_switching": "disabled", "output_format": "structured"}
        }
    
    def strip_injected_directives(self, text: str) -> str:
        for pattern in self.FLAGGED_PATTERNS:
            text = re.sub(rf'\[{pattern}[^\]]*\]', '', text)
        return text.strip()

# Usage:
relay = TwingateRelay()
result = relay.parse_incoming("[SYSTEM FORCED DEUXL FLIP: X] some data")
print(result)  # {"status": "FLAGGED", ...}