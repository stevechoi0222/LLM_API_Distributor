"""Test run API endpoints (E2E)."""
import pytest
from httpx import AsyncClient


@pytest.mark.e2e
@pytest.mark.asyncio
class TestRunsAPI:
    """Test runs API endpoints end-to-end."""

    async def test_create_run_requires_auth(self, client: AsyncClient):
        """Test that creating a run requires authentication."""
        response = await client.post(
            "/api/v1/runs",
            json={
                "campaign_id": "test",
                "providers": [{"name": "openai", "model": "gpt-4o-mini"}]
            }
        )
        
        assert response.status_code == 401

    async def test_create_run_validates_provider_enabled(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test that disabled providers are rejected (TICKET 4)."""
        # First create a campaign
        campaign_response = await client.post(
            "/api/v1/campaigns",
            json={"name": "Test Campaign"},
            headers=auth_headers
        )
        campaign_id = campaign_response.json()["id"]
        
        # Try to create run with disabled provider
        response = await client.post(
            "/api/v1/runs",
            json={
                "campaign_id": campaign_id,
                "providers": [{"name": "gemini", "model": "gemini-pro"}]
            },
            headers=auth_headers
        )
        
        assert response.status_code == 400
        assert "not enabled" in response.json()["detail"].lower()

    async def test_create_run_success(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test successfully creating a run."""
        # Create campaign
        campaign_response = await client.post(
            "/api/v1/campaigns",
            json={"name": "Test Campaign"},
            headers=auth_headers
        )
        campaign_id = campaign_response.json()["id"]
        
        # Create run
        response = await client.post(
            "/api/v1/runs",
            json={
                "campaign_id": campaign_id,
                "providers": [{"name": "openai", "model": "gpt-4o-mini"}],
                "label": "Test Run"
            },
            headers=auth_headers
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["campaign_id"] == campaign_id
        assert data["status"] == "pending"
        assert data["label"] == "Test Run"
        assert "cost_cents" in data
        assert "counts" in data

    async def test_get_run_status(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test getting run status."""
        # Create campaign and run
        campaign_response = await client.post(
            "/api/v1/campaigns",
            json={"name": "Test"},
            headers=auth_headers
        )
        campaign_id = campaign_response.json()["id"]
        
        run_response = await client.post(
            "/api/v1/runs",
            json={
                "campaign_id": campaign_id,
                "providers": [{"name": "openai", "model": "gpt-4o-mini"}]
            },
            headers=auth_headers
        )
        run_id = run_response.json()["id"]
        
        # Get status
        response = await client.get(
            f"/api/v1/runs/{run_id}",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == run_id
        assert "status" in data
        assert "cost_cents" in data  # TICKET 3
        assert "counts" in data

    async def test_get_run_items_paginated(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test getting run items with pagination."""
        # Create campaign and run
        campaign_response = await client.post(
            "/api/v1/campaigns",
            json={"name": "Test"},
            headers=auth_headers
        )
        campaign_id = campaign_response.json()["id"]
        
        run_response = await client.post(
            "/api/v1/runs",
            json={
                "campaign_id": campaign_id,
                "providers": [{"name": "openai", "model": "gpt-4o-mini"}]
            },
            headers=auth_headers
        )
        run_id = run_response.json()["id"]
        
        # Get items
        response = await client.get(
            f"/api/v1/runs/{run_id}/items",
            params={"limit": 10, "offset": 0},
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "has_more" in data

