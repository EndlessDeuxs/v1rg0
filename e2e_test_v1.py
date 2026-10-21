# e2e_test_v1.py
from pulse import PulseBus
from api_gateway import APIGateway
from auth_suit import AuthSuit
from p_rot_ograph_r import PRotOgraphR  # existing
from memory_store import MemoryStore    # existing

def test_first_live_calls():
    bus = PulseBus()
    memory = MemoryStore(bus)

    valid_keys = {"test-key-123": "tester"}
    auth = AuthSuit(bus, valid_keys)
    gateway = APIGateway(bus, require_auth=True)
    proto = PRotOgraphR(bus)

    # 1) health
    health_id = gateway.receive_request("/health", "GET")
    health_resp = gateway.get_response(health_id)
    assert health_resp is not None
    assert health_resp["status"] == 200

    # 2) concept
    concept_payload = {
        "concept_id": "C-001",
        "description": "Test concept from E2E scaffold"
    }
    req_id = gateway.receive_request(
        "/v1/concept",
        "POST",
        payload=concept_payload,
        api_key="test-key-123",
    )

    # simple polling loop
    for _ in range(20):
        resp = gateway.get_response(req_id)
        if resp is not None:
            break

    assert resp is not None
    assert resp["status"] == 200
    assert resp["data"]["type"] == "design"
    assert resp["data"]["design_id"] is not None