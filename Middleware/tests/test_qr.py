import pytest
from httpx import AsyncClient, ASGITransport
import base64
from main import app


async def _auth_headers(client):
    resp = await client.post("/auth/login", json={"username": "admin", "password": "admin"})
    assert resp.status_code == 200
    return {"X-Auth-Token": resp.json()["access_token"]}


@pytest.mark.asyncio
async def test_qr_generate_get(client):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        headers = await _auth_headers(ac)
        url = "https://qr.nspk.ru/AD100045V41B098K4J9H382D?type=02&bank=100000000004&crc=AB12"
        resp = await ac.get(f"/qr/generate?text={url}", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "png_base64" in data
        assert data["data_uri"].startswith("data:image/png;base64,")

        # Verify valid base64 PNG
        raw_png = base64.b64decode(data["png_base64"])
        assert raw_png.startswith(b"\x89PNG\r\n\x1a\n")


@pytest.mark.asyncio
async def test_qr_generate_post(client):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        headers = await _auth_headers(ac)
        resp = await ac.post("/qr/generate?text=TEST_PAYMENT_12345", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert len(data["png_base64"]) > 100


@pytest.mark.asyncio
async def test_qr_generate_requires_auth(client):
    """Генерация QR закрыта от анонимов."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/qr/generate?text=TEST")
        assert resp.status_code == 401
