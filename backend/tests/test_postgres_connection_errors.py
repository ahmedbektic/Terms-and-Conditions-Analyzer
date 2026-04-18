import psycopg
import pytest

from app.persistence.postgres import _build_database_connection_error_message
from app.persistence.postgres import PostgresStorage


def test_connection_error_message_recommends_session_pooler_for_direct_supabase_host() -> None:
    message = _build_database_connection_error_message(
        "postgresql://postgres:secret@db.abcdefghijklmnopqrst.supabase.co:5432/postgres",
        Exception("connection to server failed: Network is unreachable"),
    )

    assert "db.abcdefghijklmnopqrst.supabase.co" in message
    assert "Session pooler" in message
    assert "SUPABASE_DATABASE_URL" in message


def test_connection_error_message_stays_generic_for_non_supabase_hosts() -> None:
    message = _build_database_connection_error_message(
        "postgresql://postgres:secret@postgres.internal:5432/postgres",
        Exception("connection refused"),
    )

    assert "postgres.internal" in message
    assert "Session pooler" not in message


def test_postgres_storage_connection_re_raises_with_session_pooler_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_connect(*args, **kwargs):
        raise psycopg.OperationalError("connection to server failed: Network is unreachable")

    monkeypatch.setattr("app.persistence.postgres.psycopg.connect", fake_connect)
    storage = PostgresStorage(
        database_url="postgresql://postgres:secret@db.abcdefghijklmnopqrst.supabase.co:5432/postgres",
        auto_create_schema=False,
    )

    with pytest.raises(psycopg.OperationalError) as exc_info:
        with storage.connection():
            pass

    assert "Session pooler" in str(exc_info.value)
