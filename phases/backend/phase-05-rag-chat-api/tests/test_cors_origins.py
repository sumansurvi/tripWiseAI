"""CORS origin helper for local + Vercel."""

import os

from tripwise_p5.app import _cors_origins


def test_cors_includes_localhost_by_default(monkeypatch):
    monkeypatch.delenv("TRIPWISE_CORS_ORIGINS", raising=False)
    monkeypatch.delenv("VERCEL_URL", raising=False)
    origins = _cors_origins()
    assert "http://localhost:3000" in origins
    assert "http://127.0.0.1:3000" in origins


def test_cors_adds_env_and_vercel_url(monkeypatch):
    monkeypatch.setenv(
        "TRIPWISE_CORS_ORIGINS",
        "https://tripwise.vercel.app, https://preview.example.com/",
    )
    monkeypatch.setenv("VERCEL_URL", "tripwise-git-main.vercel.app")
    origins = _cors_origins()
    assert "https://tripwise.vercel.app" in origins
    assert "https://preview.example.com" in origins
    assert "https://tripwise-git-main.vercel.app" in origins
