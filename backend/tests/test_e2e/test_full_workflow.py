"""Test complete end-to-end workflow."""
import pytest
from httpx import AsyncClient


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.asyncio
class TestFullWorkflow:
    """Test complete workflow from import to export."""

    async def test_complete_workflow(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test the complete workflow: import → run → export."""
        
        # Step 1: Import questions (TICKET 1)
        import_response = await client.post(
            "/api/v1/question-sets:import",
            json={
                "items": [
                    {
                        "campaign": "E2E Test Campaign",
                        "topic": {"title": "Battery Life", "description": "Battery tests"},
                        "persona": {"name": "Tech Reviewer", "role": "Reviewer", "tone": "neutral"},
                        "question": {
                            "id": "E2E_Q001",
                            "text": "How long does the battery last?",
                            "metadata": {"tags": ["battery"]}
                        }
                    },
                    {
                        "campaign": "E2E Test Campaign",
                        "topic": {"title": "Battery Life"},
                        "persona": {"name": "Consumer", "role": "User"},
                        "question": {
                            "id": "E2E_Q002",
                            "text": "Is the battery life good for daily use?"
                        }
                    }
                ]
            },
            headers=auth_headers
        )
        
        assert import_response.status_code == 200
        import_data = import_response.json()
        assert import_data["imported"] == 2
        assert import_data["skipped"] == 0
        
        # Step 2: Get campaign ID
        # We need to find the campaign we just created
        # In a real test, we'd query /api/v1/campaigns or store the ID
        # For now, we'll create it explicitly
        campaign_response = await client.get(
            "/api/v1/campaigns",
            headers=auth_headers
        )
        # Assume we get campaigns and find ours, or create it
        
        # Create campaign explicitly for the run
        campaign_create = await client.post(
            "/api/v1/campaigns",
            json={"name": "E2E Test Campaign"},
            headers=auth_headers
        )
        campaign_id = campaign_create.json()["id"]
        
        # Step 3: Create run
        run_response = await client.post(
            "/api/v1/runs",
            json={
                "campaign_id": campaign_id,
                "providers": [
                    {
                        "name": "openai",
                        "model": "gpt-4o-mini",
                        "allow_sampling": False  # TICKET 6 - determinism
                    }
                ],
                "prompt_version": "v1",
                "label": "E2E Test Run"
            },
            headers=auth_headers
        )
        
        assert run_response.status_code == 201
        run_data = run_response.json()
        run_id = run_data["id"]
        assert run_data["status"] == "pending"
        
        # Step 4: Check run status
        status_response = await client.get(
            f"/api/v1/runs/{run_id}",
            headers=auth_headers
        )
        
        assert status_response.status_code == 200
        status_data = status_response.json()
        assert status_data["id"] == run_id
        assert "cost_cents" in status_data  # TICKET 3
        
        # Step 5: Export results (even if run hasn't executed yet)
        export_response = await client.get(
            f"/api/v1/runs/{run_id}/results:download",
            params={"format": "jsonl"},
            headers=auth_headers
        )
        
        # Should succeed even with no results
        assert export_response.status_code == 200
    
    async def test_idempotent_import(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test that re-importing same questions is idempotent (TICKET 1)."""
        
        payload = {
            "items": [
                {
                    "campaign": "Idempotency Test",
                    "topic": {"title": "Test Topic"},
                    "persona": {"name": "Test Persona"},
                    "question": {
                        "id": "IDEM_Q001",
                        "text": "Idempotency test question?"
                    }
                }
            ]
        }
        
        # First import
        response1 = await client.post(
            "/api/v1/question-sets:import",
            json=payload,
            headers=auth_headers
        )
        
        assert response1.status_code == 200
        data1 = response1.json()
        assert data1["imported"] == 1
        assert data1["skipped"] == 0
        
        # Second import (same data)
        response2 = await client.post(
            "/api/v1/question-sets:import",
            json=payload,
            headers=auth_headers
        )
        
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["imported"] == 0
        assert data2["skipped"] == 1  # Should skip duplicate

