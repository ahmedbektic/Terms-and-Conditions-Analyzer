from app.core import sentry as sentry_config


def test_before_send_scrubs_auth_and_policy_text_and_applies_tags() -> None:
    sentry_config._COMMON_EVENT_TAGS.clear()
    sentry_config._COMMON_EVENT_TAGS.update(
        {
            "service": "backend-api",
            "service_surface": "fastapi-api",
            "deployment_environment": "test",
            "release": "backend@test",
        }
    )
    event = {
        "request": {
            "url": "https://api.example.com/api/v1/reports/analyze",
            "headers": {
                "authorization": "Bearer secret-token",
                "content-type": "application/json",
            },
            "data": {"terms_text": "full private policy text"},
        },
        "extra": {
            "captured_text": "captured policy text",
            "source_value": "https://example.com/terms",
        },
    }

    sanitized = sentry_config._before_send(event, {})

    assert sanitized is not None
    assert sanitized["request"]["headers"]["authorization"] == "[Filtered]"
    assert sanitized["request"]["data"] == "[Filtered]"
    assert sanitized["extra"]["captured_text"] == "[Filtered]"
    assert sanitized["extra"]["source_value"] == "https://example.com/terms"
    assert sanitized["tags"]["service"] == "backend-api"
    assert sanitized["tags"]["deployment_environment"] == "test"
    assert sanitized["tags"]["release"] == "backend@test"


def test_before_send_transaction_drops_health_noise() -> None:
    event = {
        "transaction": "/health",
        "request": {
            "url": "https://api.example.com/health",
        },
    }

    assert sentry_config._before_send_transaction(event, {}) is None


def test_before_send_ignores_missing_event_payload() -> None:
    assert sentry_config._before_send(None, {}) is None


def test_before_send_transaction_ignores_missing_event_payload() -> None:
    assert sentry_config._before_send_transaction(None, {}) is None
