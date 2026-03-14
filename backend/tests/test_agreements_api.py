from fastapi.testclient import TestClient
import pytest

from app.api.deps import reset_demo_storage
from app.main import create_app


@pytest.fixture(autouse=True)
def _clear_storage() -> None:
    reset_demo_storage()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app())


def test_create_agreement_then_trigger_manual_analysis(client: TestClient) -> None:
    create_payload = {
        "title": "Demo Terms",
        "source_url": "https://demo.example/terms",
        "terms_text": (
            "These terms include arbitration and a class action waiver. "
            "The subscription renews automatically unless canceled."
        ),
    }
    create_response = client.post(
        "/api/v1/agreements",
        json=create_payload,
        headers={"X-Session-Id": "session-a"},
    )
    assert create_response.status_code == 201
    agreement = create_response.json()
    assert agreement["id"]
    assert agreement["title"] == "Demo Terms"

    analyze_response = client.post(
        f"/api/v1/agreements/{agreement['id']}/analyses",
        json={"trigger": "manual"},
        headers={"X-Session-Id": "session-a"},
    )
    assert analyze_response.status_code == 201
    report = analyze_response.json()
    assert report["summary"]
    assert report["trust_score"] >= 0
    assert report["flagged_clauses"] != []


def test_create_agreement_rejects_short_terms_text(client: TestClient) -> None:
    response = client.post(
        "/api/v1/agreements",
        json={"terms_text": "too short"},
        headers={"X-Session-Id": "session-a"},
    )
    assert response.status_code == 422


def test_trigger_manual_analysis_rejects_invalid_trigger(client: TestClient) -> None:
    create_response = client.post(
        "/api/v1/agreements",
        json={"terms_text": "This is a valid terms body with enough characters."},
        headers={"X-Session-Id": "session-a"},
    )
    agreement_id = create_response.json()["id"]

    response = client.post(
        f"/api/v1/agreements/{agreement_id}/analyses",
        json={"trigger": "automatic"},
        headers={"X-Session-Id": "session-a"},
    )
    assert response.status_code == 400
    assert "manual" in response.json()["detail"]
