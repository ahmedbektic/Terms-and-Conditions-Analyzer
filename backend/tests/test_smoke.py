from app.main import create_app


def test_backend_smoke() -> None:
    app = create_app()
    paths = {route.path for route in app.routes}

    assert "/health" in paths
    assert "/api/v1/agreements" in paths
    assert "/api/v1/reports" in paths
    assert "/api/v1/reports/analyze" in paths
