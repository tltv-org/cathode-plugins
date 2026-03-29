"""Test overlay plugin route registration and handler logic."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tests.conftest import FakeApp, _load_plugin


@pytest.fixture()
def overlay_app():
    """Create a FastAPI app with the overlay router mounted."""
    mod = _load_plugin("overlay")

    # Create a real FastAPI app and register the plugin
    app = FastAPI()
    result = mod.register(app, {})

    return app, result


@pytest.fixture()
async def client(overlay_app):
    """Async HTTP client for testing overlay routes."""
    app, _ = overlay_app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestOverlayRegistration:
    def test_registers_router(self):
        mod = _load_plugin("overlay")
        app = FakeApp()
        mod.register(app, {})
        assert len(app.routers) == 1, "Overlay should register exactly one router"

    def test_category_is_graphics(self):
        mod = _load_plugin("overlay")
        app = FakeApp()
        result = mod.register(app, {})
        assert result["category"] == "graphics"

    def test_overlay_elements_count(self):
        mod = _load_plugin("overlay")
        app = FakeApp()
        result = mod.register(app, {})
        assert len(result["overlay_elements"]) == 3

    def test_overlay_element_names(self):
        mod = _load_plugin("overlay")
        app = FakeApp()
        result = mod.register(app, {})
        names = [elem[1] for elem in result["overlay_elements"]]
        assert "text-overlay" in names
        assert "bug-overlay" in names
        assert "svg-overlay" in names


class TestOverlayRoutes:
    """Test overlay HTTP routes (engine not running — should return inactive)."""

    @pytest.mark.anyio
    async def test_status_no_engine(self, client):
        """With no engine running, status should show inactive."""
        resp = await client.get("/api/overlay/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["active"] is False

    @pytest.mark.anyio
    async def test_text_no_engine(self, client):
        """Setting text without engine should return 501."""
        resp = await client.post("/api/overlay/text", params={"text": "hello"})
        assert resp.status_code == 501

    @pytest.mark.anyio
    async def test_delete_text_no_engine(self, client):
        resp = await client.delete("/api/overlay/text")
        assert resp.status_code == 501

    @pytest.mark.anyio
    async def test_bug_no_engine(self, client):
        resp = await client.post("/api/overlay/bug", params={"path": "/tmp/logo.png"})
        assert resp.status_code == 501

    @pytest.mark.anyio
    async def test_delete_bug_no_engine(self, client):
        resp = await client.delete("/api/overlay/bug")
        assert resp.status_code == 501

    @pytest.mark.anyio
    async def test_svg_no_data(self, client):
        """SVG without data or path should return 400."""
        resp = await client.post("/api/overlay/svg")
        # Either 501 (no engine) or 400 (missing data) — depends on check order
        assert resp.status_code in (400, 501)

    @pytest.mark.anyio
    async def test_delete_svg_no_engine(self, client):
        resp = await client.delete("/api/overlay/svg")
        assert resp.status_code == 501
