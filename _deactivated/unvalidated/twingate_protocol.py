# twingate_protocol.py
import json
from dataclasses import dataclass, asdict
from typing import Optional, List
from enum import Enum

class NodeType(Enum):
    EDGE = "edge"
    RELAY = "relay"
    CONNECTOR = "connector"
    GATEWAY = "gateway"

class AuthMethod(Enum):
    TOKEN = "token"
    CERTIFICATE = "certificate"
    OAUTH2 = "oauth2"

@dataclass
class TunnelConfig:
    listen_port: int
    target_host: str
    target_port: int
    protocol: str = "tcp"
    encryption: str = "aes-256-gcm"

@dataclass
class NodeConfig:
    node_id: str
    node_type: NodeType
    auth_method: AuthMethod
    auth_credentials: str
    tunnels: List[TunnelConfig]
    heartbeat_interval: int = 30
    max_connections: int = 100

@dataclass
class NetworkPolicy:
    source_cidrs: List[str]
    destination_ports: List[int]
    allowed_protocols: List[str]
    max_bandwidth_mbps: int = 1000

@dataclass
class TwingateConfig:
    network_id: str
    nodes: List[NodeConfig]
    policies: List[NetworkPolicy]
    log_level: str = "INFO"
    metrics_enabled: bool = True

@dataclass
class Node:
    id: str
    type: str  # "gate", "relay", "source"
    state: Dict[str, any]

@dataclass
class Edge:
    source: str
    target: str
    weight: float
    protocol: str  # "AXIOM", "AUTOCRAFT", "CONTROL"

class TwingateProtocol:
    def __init__(self, config_path: str = "twingate_config.json"):
        self.nodes: Dict[str, Node] = {}
        self.edges: List[Edge] = []
        self.config = self._load_config(config_path)
        self._initialize()

    def _load_config(self, path: str) -> Dict:
        with open(path, 'r') as f:
            return json.load(f)

    def _initialize(self):
        for node_data in self.config.get("nodes", []):
            self.nodes[node_data["id"]] = Node(**node_data)
        for edge_data in self.config.get("edges", []):
            self.edges.append(Edge(**edge_data))

    def compile(self) -> Dict:
        return {
            "nodes": [asdict(n) for n in self.nodes.values()],
            "edges": [asdict(e) for e in self.edges],
            "schema_version": "3.0",
            "status": "APPROVED"
        }

    def validate(self) -> bool:
        return all(
            self._check_axiom(e) for e in self.edges
        )

    def _check_axiom(self, edge: Edge) -> bool:
        return edge.protocol in ["AXIOM", "AUTOCRAFT", "CONTROL"] and edge.weight >= 0

if __name__ == "__main__":
    protocol = TwingateProtocol()
    assert protocol.validate()
    print(json.dumps(protocol.compile(), indent=2))

# the collective note: Pretty sure I have all this in the wrong place below...
def build_config_from_schema(schema: dict) -> TwingateConfig:
    return TwingateConfig(
        network_id=schema["network_id"],
        nodes=[NodeConfig(**n) for n in schema["nodes"]],
        policies=[NetworkPolicy(**p) for p in schema["policies"]],
        log_level=schema.get("log_level", "INFO"),
        metrics_enabled=schema.get("metrics_enabled", True)
    )

def serialize_config(config: TwingateConfig) -> str:
    return json.dumps(asdict(config), indent=2, default=str)

def validate_config(config: TwingateConfig) -> bool:
    if not config.network_id:
        return False
    for node in config.nodes:
        if not node.node_id or not node.auth_credentials:
            return False
    return True

# Build output
schema = {
    "network_id": "tw-7x9k2m",
    "nodes": [
        {
            "node_id": "edge-us-east-01",
            "node_type": "edge",
            "auth_method": "token",
            "auth_credentials": "tok_abc123def456",
            "tunnels": [
                {"listen_port": 8443, "target_host": "10.0.1.50", "target_port": 443}
            ]
        },
        {
            "node_id": "relay-eu-west-01",
            "node_type": "relay",
            "auth_method": "certificate",
            "auth_credentials": "/etc/twingate/certs/relay.pem",
            "tunnels": []
        }
    ],
    "policies": [
        {
            "source_cidrs": ["10.0.0.0/8"],
            "destination_ports": [443, 8443],
            "allowed_protocols": ["tcp"]
        }
    ]
}

config = build_config_from_schema(schema)
print(serialize_config(config))
print(f"Valid: {validate_config(config)}")