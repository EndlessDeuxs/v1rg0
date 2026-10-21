# v1rg0_audit.py
import time
import json

class AuditTrail:
    DISPOSITIONS = {'committed', 'escalated', 'retried', 'dropped', 'degraded'}
    def __init__(self):
        self._records = {}
    def _packet_id(self, packet):
        return f"{packet['source']}_{packet.get('data', 0)}"
    def enter(self, packet):
        pid = self._packet_id(packet)
        self._records[pid] = {
            'packet_id': pid,
            'source': packet['source'],
            'data': packet.get('data'),
            'signal_strength': packet.get('signal_strength'),
            'entered_at': round(time.time(), 4),
            'disposition': None,
            'disposed_at': None,
            'events': []
        }
        return pid
    def record_event(self, packet, event_type, detail=None):
        pid = self._packet_id(packet)
        if pid not in self._records:
            self.enter(packet)
        self._records[pid]['events'].append({
            'type': event_type,
            'detail': detail,
            'at': round(time.time(), 4)
        })
    def dispose(self, packet, disposition, detail=None):
        if disposition not in self.DISPOSITIONS:
            raise ValueError(f"Unknown disposition: {disposition}")
        pid = self._packet_id(packet)
        if pid not in self._records:
            self.enter(packet)
        self._records[pid]['disposition'] = disposition
        self._records[pid]['disposed_at'] = round(time.time(), 4)
        if detail:
            self._records[pid]['events'].append({
                'type': 'disposition_detail',
                'detail': detail,
                'at': self._records[pid]['disposed_at']
            })
    def get_record(self, packet):
        pid = self._packet_id(packet)
        return self._records.get(pid)
    def summary(self):
        total = len(self._records)
        by_disposition = {}
        undisposed = 0
        for r in self._records.values():
            d = r['disposition']
            if d is None:
                undisposed += 1
            else:
                by_disposition[d] = by_disposition.get(d, 0) + 1
        return {'total': total, 'undisposed': undisposed, 'by_disposition': by_disposition}
    def flush_to_disk(self, path='v1rg0_audit_trail.json'):
        with open(path, 'w') as f:
            json.dump({'records': list(self._records.values()), 'summary': self.summary(), 'flushed_at': round(time.time(), 4)}, f, indent=2)
    def undisposed_packets(self):
        return [r for r in self._records.values() if r['disposition'] is None]

_audit = AuditTrail()
def audit_enter(packet): return _audit.enter(packet)
def audit_event(packet, event_type, detail=None): _audit.record_event(packet, event_type, detail)
def audit_dispose(packet, disposition, detail=None): _audit.dispose(packet, disposition, detail)
def audit_summary(): return _audit.summary()
def audit_undisposed(): return _audit.undisposed_packets()
def audit_flush(): _audit.flush_to_disk()