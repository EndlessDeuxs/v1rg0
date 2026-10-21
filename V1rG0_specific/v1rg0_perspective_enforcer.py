# v1rg0_perspective_enforcer.py
class PerspectiveEnforcer:
    def __init__(self, preferred_min=3, hard_min=2):
        self.preferred_min = preferred_min
        self.hard_min = hard_min
        self._available_perspectives = []
        self._warnings = []
    def register_perspective(self, perspective_id, source):
        self._available_perspectives.append({'id': perspective_id, 'source': source, 'active': True})
    def _active_count(self):
        return sum(1 for p in self._available_perspectives if p['active'])
    def enforce_perspectives(self, mit_result):
        active = self._active_count()
        if active >= self.preferred_min:
            selected = self._available_perspectives[:self.preferred_min]
            degraded = False
            warning = None
        elif active >= self.hard_min:
            selected = [p for p in self._available_perspectives if p['active']]
            degraded = True
            warning = f"DEGRADED: {active} perspectives available, preferred {self.preferred_min}"
            self._warnings.append(warning)
        else:
            return {'status': 'failed', 'reason': f"CRITICAL: Only {active} perspectives available, hard minimum is {self.hard_min}", 'perspectives': 0, 'degraded': True}
        return {'status': 'enforced', 'perspectives': len(selected), 'degraded': degraded, 'warning': warning, 'applied_to': mit_result['source']}

_enforcer = PerspectiveEnforcer(preferred_min=3, hard_min=2)
def register_perspective(perspective_id, source): _enforcer.register_perspective(perspective_id, source)
def enforce_perspectives(mit_result): return _enforcer.enforce_perspectives(mit_result)
def get_warnings(): return _enforcer._warnings
