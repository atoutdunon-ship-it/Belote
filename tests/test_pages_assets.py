"""Regression tests for the static web interface on FastAPI and GitHub Pages."""

from fastapi.testclient import TestClient

from tbr.main import app


def test_root_page_uses_portable_relative_assets():
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert './styles.css' in response.text
    assert './runtime-config.js' in response.text
    assert './app.js' in response.text


def test_root_scoped_web_assets_are_available():
    paths = (
        "/styles.css",
        "/app.js",
        "/runtime-config.js",
        "/manifest.webmanifest",
        "/service-worker.js",
        "/icon.svg",
        "/icon-192.png",
        "/icon-512.png",
        "/apple-touch-icon.png",
    )
    with TestClient(app) as client:
        for path in paths:
            response = client.get(path)
            assert response.status_code == 200, path


def test_github_pages_runtime_configuration_defaults_to_same_origin():
    with TestClient(app) as client:
        response = client.get("/runtime-config.js")
    assert response.status_code == 200
    assert "window.TBR_API_BASE = '';" in response.text
