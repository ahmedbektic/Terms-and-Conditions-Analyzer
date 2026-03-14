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


def test_submit_analyze_and_fetch_history(client: TestClient) -> None:
    payload = {
        "title": "Acme Terms",
        "source_url": "https://acme.example/terms",
        "terms_text": (
            "These terms include mandatory arbitration and a class action waiver. "
            "The subscription renews automatically unless canceled. "
            "We may change these terms at any time without notice."
        ),
    }

    create_response = client.post(
        "/api/v1/reports/analyze",
        json=payload,
        headers={"X-Session-Id": "session-a"},
    )
    assert create_response.status_code == 201
    created_report = create_response.json()

    assert created_report["summary"]
    assert created_report["source_type"] == "url"
    assert created_report["source_value"] == payload["source_url"]
    assert 0 <= created_report["trust_score"] <= 100
    assert len(created_report["flagged_clauses"]) >= 1

    list_response = client.get("/api/v1/reports", headers={"X-Session-Id": "session-a"})
    assert list_response.status_code == 200
    report_list = list_response.json()
    assert len(report_list) == 1
    assert report_list[0]["id"] == created_report["id"]

    get_response = client.get(
        f"/api/v1/reports/{created_report['id']}",
        headers={"X-Session-Id": "session-a"},
    )
    assert get_response.status_code == 200
    fetched_report = get_response.json()
    assert fetched_report["id"] == created_report["id"]


def test_reports_are_scoped_by_session_owner(client: TestClient) -> None:
    response = client.post(
        "/api/v1/reports/analyze",
        json={"source_url": "https://example.com/terms"},
        headers={"X-Session-Id": "session-a"},
    )
    assert response.status_code == 201

    list_owner_a = client.get("/api/v1/reports", headers={"X-Session-Id": "session-a"})
    list_owner_b = client.get("/api/v1/reports", headers={"X-Session-Id": "session-b"})

    assert list_owner_a.status_code == 200
    assert list_owner_b.status_code == 200
    assert len(list_owner_a.json()) == 1
    assert list_owner_b.json() == []


def test_submit_analyze_requires_session_header(client: TestClient) -> None:
    response = client.post(
        "/api/v1/reports/analyze",
        json={"terms_text": "This content is valid and sufficiently long for analysis."},
    )
    assert response.status_code == 400
    assert "X-Session-Id" in response.json()["detail"]


def test_submit_analyze_rejects_missing_input(client: TestClient) -> None:
    response = client.post(
        "/api/v1/reports/analyze",
        json={},
        headers={"X-Session-Id": "session-a"},
    )
    assert response.status_code == 422


def test_get_report_returns_404_when_report_not_found(client: TestClient) -> None:
    response = client.get(
        "/api/v1/reports/11111111-1111-1111-1111-111111111111",
        headers={"X-Session-Id": "session-a"},
    )
    assert response.status_code == 404
