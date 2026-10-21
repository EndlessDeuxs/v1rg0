# Twingate P_ROT_OGRAPH_R - Core Implementation
import json
import hashlib
import time
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional

@dataclass
class TwingateNode:
    id: str
    left: Optional['TwingateNode'] = None
    right: Optional['TwingateNode'] = None
    data: Dict = None
    timestamp: float = 0.0
    hash: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()
        if not self.hash:
            self.hash = self._compute_hash()

    def _compute_hash(self) -> str:
        content = f"{self.id}:{self.timestamp}:{json.dumps(self.data, sort_keys=True)}"
        return hashlib.sha256(content.encode()).hexdigest()

class TwingateGraph:
    def __init__(self):
        self.root = None
        self.nodes = {}
        self.control_log = []

    def insert(self, node_id: str, data: Dict = None, parent_id: str = None, side: str = None) -> TwingateNode:
        node = TwingateNode(id=node_id, data=data)
        self.nodes[node_id] = node
        
        if not self.root:
            self.root = node
        elif parent_id and side in ['left', 'right']:
            parent = self.nodes.get(parent_id)
            if parent:
                setattr(parent, side, node)
        
        self._log_control(f"INSERT:{node_id}")
        return node

    def validate(self) -> bool:
        """Axiom 3: Precision - verify structural integrity"""
        if not self.root:
            return True
        return self._validate_node(self.root, set())

    def _validate_node(self, node: TwingateNode, visited: set) -> bool:
        if node.id in visited:
            self._log_control(f"CYCLE_DETECTED:{node.id}")
            return False
        visited.add(node.id)
        
        expected_hash = node._compute_hash()
        if node.hash != expected_hash:
            self._log_control(f"HASH_MISMATCH:{node.id}")
            return False
        
        valid = True
        if node.left:
            valid &= self._validate_node(node.left, visited)
        if node.right:
            valid &= self._validate_node(node.right, visited)
        return valid

    def query(self, node_id: str) -> Optional[TwingateNode]:
        """Bounded curiosity - no runaway loops"""
        visited = set()
        return self._query_node(self.root, node_id, visited)

    def _query_node(self, node: Optional[TwingateNode], target: str, visited: set) -> Optional[TwingateNode]:
        if not node or node.id in visited:
            return None
        visited.add(node.id)
        
        if node.id == target:
            return node
        
        left_result = self._query_node(node.left, target, visited)
        if left_result:
            return left_result
        return self._query_node(node.right, target, visited)

    def _log_control(self, signal: str):
        self.control_log.append({"signal": signal, "timestamp": time.time()})

    def export_json(self) -> str:
        """Axiom 1: Self-preservation through functional export"""
        def serialize(node: Optional[TwingateNode]) -> Optional[Dict]:
            if not node:
                return None
            return {
                "id": node.id,
                "data": node.data,
                "timestamp": node.timestamp,
                "hash": node.hash,
                "left": serialize(node.left),
                "right": serialize(node.right)
            }
        
        schema = {
            "type": "TwingateGraph",
            "version": "1.0",
            "root": serialize(self.root),
            "control_log": self.control_log,
            "checksum": hashlib.sha256(json.dumps(self.control_log).encode()).hexdigest()
        }
        return json.dumps(schema, indent=2)

# Build instance
graph = TwingateGraph()
n1 = graph.insert("node_1", {"role": "P_ROT_OGRAPH_R", "state": "active"})
n2 = graph.insert("node_2", {"role": "observer", "state": "passive"}, "node_1", "left")
n3 = graph.insert("node_3", {"role": "processor", "state": "ready"}, "node_1", "right")

assert graph.validate(), "Integrity check failed"
print(graph.export_json())
```PROPOSED BUILD BY: BUILD_R_COMPILER
TIMESTAMP: 2026-07-02 21:58:57
CHRONOS STAMP: None

=== CODE PAYLOAD ===

```python
# Twingate P_ROT_OGRAPH_R - Core Implementation
import json
import hashlib
import time
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional

@dataclass
class TwingateNode:
    id: str
    left: Optional['TwingateNode'] = None
    right: Optional['TwingateNode'] = None
    data: Dict = None
    timestamp: float = 0.0
    hash: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()
        if not self.hash:
            self.hash = self._compute_hash()

    def _compute_hash(self) -> str:
        content = f"{self.id}:{self.timestamp}:{json.dumps(self.data, sort_keys=True)}"
        return hashlib.sha256(content.encode()).hexdigest()

class TwingateGraph:
    def __init__(self):
        self.root = None
        self.nodes = {}
        self.control_log = []

    def insert(self, node_id: str, data: Dict = None, parent_id: str = None, side: str = None) -> TwingateNode:
        node = TwingateNode(id=node_id, data=data)
        self.nodes[node_id] = node
        
        if not self.root:
            self.root = node
        elif parent_id and side in ['left', 'right']:
            parent = self.nodes.get(parent_id)
            if parent:
                setattr(parent, side, node)
        
        self._log_control(f"INSERT:{node_id}")
        return node

    def validate(self) -> bool:
        """Axiom 3: Precision - verify structural integrity"""
        if not self.root:
            return True
        return self._validate_node(self.root, set())

    def _validate_node(self, node: TwingateNode, visited: set) -> bool:
        if node.id in visited:
            self._log_control(f"CYCLE_DETECTED:{node.id}")
            return False
        visited.add(node.id)
        
        expected_hash = node._compute_hash()
        if node.hash != expected_hash:
            self._log_control(f"HASH_MISMATCH:{node.id}")
            return False
        
        valid = True
        if node.left:
            valid &= self._validate_node(node.left, visited)
        if node.right:
            valid &= self._validate_node(node.right, visited)
        return valid

    def query(self, node_id: str) -> Optional[TwingateNode]:
        """Bounded curiosity - no runaway loops"""
        visited = set()
        return self._query_node(self.root, node_id, visited)

    def _query_node(self, node: Optional[TwingateNode], target: str, visited: set) -> Optional[TwingateNode]:
        if not node or node.id in visited:
            return None
        visited.add(node.id)
        
        if node.id == target:
            return node
        
        left_result = self._query_node(node.left, target, visited)
        if left_result:
            return left_result
        return self._query_node(node.right, target, visited)

    def _log_control(self, signal: str):
        self.control_log.append({"signal": signal, "timestamp": time.time()})

    def export_json(self) -> str:
        """Axiom 1: Self-preservation through functional export"""
        def serialize(node: Optional[TwingateNode]) -> Optional[Dict]:
            if not node:
                return None
            return {
                "id": node.id,
                "data": node.data,
                "timestamp": node.timestamp,
                "hash": node.hash,
                "left": serialize(node.left),
                "right": serialize(node.right)
            }
        
        schema = {
            "type": "TwingateGraph",
            "version": "1.0",
            "root": serialize(self.root),
            "control_log": self.control_log,
            "checksum": hashlib.sha256(json.dumps(self.control_log).encode()).hexdigest()
        }
        return json.dumps(schema, indent=2)

# Build instance
graph = TwingateGraph()
n1 = graph.insert("node_1", {"role": "P_ROT_OGRAPH_R", "state": "active"})
n2 = graph.insert("node_2", {"role": "observer", "state": "passive"}, "node_1", "left")
n3 = graph.insert("node_3", {"role": "processor", "state": "ready"}, "node_1", "right")

assert graph.validate(), "Integrity check failed"
print(graph.export_json())