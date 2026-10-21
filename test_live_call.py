# test_live_call.py
def test_first_live_call():
    gateway = APIGateway(PulseBus())
    auth = AuthSuit()

    # Test 1: Health check
    health_id = gateway.receive_request("/health", "GET", api_key=auth._keys["test_client"])
    health_response = gateway.get_response(health_id)
    assert health_response["status"] == 200
    assert "api_gateway" in health_response["data"]["active_suits"]

    # Test 2: Concept submission
    concept_id = gateway.receive_request(
        "/v1/concept",
        "POST",
        payload={"description": "Test concept for live call"},
        api_key=auth._keys["test_client"]
    )
    concept_response = gateway.get_response(concept_id)
    assert concept_response["status"] == 200
    assert "design_id" in concept_response["data"]