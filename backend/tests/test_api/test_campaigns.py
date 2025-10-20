"""Test campaign endpoints."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_campaign(client: AsyncClient, auth_headers: dict):
    """Test creating a campaign."""
    payload = {
        "name": "Test Campaign",
        "product_name": "Test Product"
    }
    
    response = await client.post("/api/v1/campaigns", json=payload, headers=auth_headers)
    assert response.status_code == 201
    
    data = response.json()
    assert data["name"] == "Test Campaign"
    assert data["product_name"] == "Test Product"
    assert "id" in data


@pytest.mark.asyncio
async def test_create_campaign_without_auth(client: AsyncClient):
    """Test creating campaign without authentication fails."""
    payload = {"name": "Test"}
    
    response = await client.post("/api/v1/campaigns", json=payload)
    assert response.status_code == 401


