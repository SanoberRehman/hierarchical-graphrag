"""Settings parsing — guards the CORS_ORIGINS env handling.

Regression: pydantic-settings JSON-decodes list fields from the environment
before validators run, so a plain comma-separated ``CORS_ORIGINS`` (as set by
docker-compose) raised a SettingsError on startup. ``NoDecode`` + the CSV
validator fixes it. This exercises the exact env path CI otherwise never set.
"""

from __future__ import annotations

from app.config import Settings


def test_cors_origins_parses_plain_env_string(monkeypatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000")
    assert Settings().cors_origins == ["http://localhost:3000"]


def test_cors_origins_parses_csv_env_string(monkeypatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000, https://app.example.com")
    assert Settings().cors_origins == ["http://localhost:3000", "https://app.example.com"]


def test_cors_origins_defaults_without_env(monkeypatch) -> None:
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    assert Settings().cors_origins == ["http://localhost:3000"]
