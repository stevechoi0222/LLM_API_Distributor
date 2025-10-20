"""Integration tests for user_excel_v0_1 export workflow (TKT-013)."""
import os
import pytest
import pandas as pd
from unittest.mock import AsyncMock, patch
from sqlalchemy import select
from app.db.models import Campaign, Topic, Persona, Question, Run, RunItem, Response, Export
from app.domain.services.export_service import ExportService


@pytest.mark.integration
@pytest.mark.tkt013
class TestUserExcelExportWorkflow:
    """Test complete user_excel_v0_1 export workflow."""

    @pytest.mark.asyncio
    async def test_export_creates_xlsx_with_both_sheets(self, db_session):
        """Test export creates XLSX with AI_API_04_QUERY and AI_API_08_CITATION sheets."""
        # Setup: Create campaign, topic, persona, questions
        campaign = Campaign(name="Excel Export Test")
        db_session.add(campaign)
        await db_session.commit()

        topic = Topic(campaign_id=campaign.id, title="AI Topics")
        db_session.add(topic)

        persona = Persona(name="Data Scientist", role="Analyst")
        db_session.add(persona)
        await db_session.commit()

        # Create 2 questions
        q1 = Question(topic_id=topic.id, persona_id=persona.id, text="What is AI?")
        q2 = Question(topic_id=topic.id, persona_id=persona.id, text="What is ML?")
        db_session.add_all([q1, q2])
        await db_session.commit()

        # Create run
        import json
        run = Run(
            campaign_id=campaign.id,
            label="Test Run",
            provider_settings_json=json.dumps({
                "providers": [{"name": "openai", "model": "gpt-4o-mini"}],
                "prompt_version": "v1"
            }),
            status="completed"
        )
        db_session.add(run)
        await db_session.commit()

        # Create run items with responses
        run_item1 = RunItem(
            run_id=run.id,
            question_id=q1.id,
            idempotency_key="test_key_1",
            status="succeeded"
        )
        run_item2 = RunItem(
            run_id=run.id,
            question_id=q2.id,
            idempotency_key="test_key_2",
            status="succeeded"
        )
        db_session.add_all([run_item1, run_item2])
        await db_session.commit()

        # Add responses with citations
        response1 = Response(
            run_item_id=run_item1.id,
            provider="openai",
            model="gpt-4o-mini",
            prompt_version="v1",
            request_json=json.dumps({"messages": []}),
            response_json=json.dumps({
                "answer": "AI is artificial intelligence",
                "citations": ["https://ai.example.com", "https://ml.example.com"]
            }),
            text="AI is artificial intelligence",
            citations_json=json.dumps(["https://ai.example.com", "https://ml.example.com"]),
            token_usage_json=json.dumps({"prompt_tokens": 100, "completion_tokens": 50}),
            latency_ms=1500,
            cost_cents=5.5
        )
        response2 = Response(
            run_item_id=run_item2.id,
            provider="openai",
            model="gpt-4o-mini",
            prompt_version="v1",
            request_json=json.dumps({"messages": []}),
            response_json=json.dumps({
                "answer": "ML is machine learning",
                "citations": []  # No citations
            }),
            text="ML is machine learning",
            citations_json=json.dumps([]),
            token_usage_json=json.dumps({"prompt_tokens": 80, "completion_tokens": 40}),
            latency_ms=1200,
            cost_cents=4.0
        )
        db_session.add_all([response1, response2])
        await db_session.commit()

        # Create export with user_excel_v0_1 mapper
        service = ExportService(db_session)
        export = await service.create_export(
            run_id=run.id,
            format="xlsx",
            mapper_name="user_excel_v0_1",
            mapper_version="v1"
        )

        # Execute export
        file_path = await service.export_to_file(export.id, output_dir="artefacts")

        # Verify file exists
        assert os.path.exists(file_path)
        assert file_path.endswith(f"user_excel_v0_1_{run.id}.xlsx")

        # Read Excel file and verify sheets
        xl = pd.ExcelFile(file_path)
        assert "AI_API_04_QUERY" in xl.sheet_names
        assert "AI_API_08_CITATION" in xl.sheet_names

        # Verify QUERY sheet
        query_df = pd.read_excel(file_path, sheet_name="AI_API_04_QUERY")
        assert len(query_df) == 2  # 2 questions
        
        # Check exact headers
        expected_query_headers = [
            "campaign", "run_id", "question_id", "persona_name", "question_text",
            "provider", "model", "response_text", "latency_ms",
            "prompt_tokens", "completion_tokens", "cost_cents", "status"
        ]
        assert list(query_df.columns) == expected_query_headers
        
        # Check data
        assert query_df.iloc[0]["campaign"] == "Excel Export Test"
        assert query_df.iloc[0]["persona_name"] == "Data Scientist"
        assert query_df.iloc[0]["provider"] == "openai"
        assert query_df.iloc[0]["response_text"] == "AI is artificial intelligence"

        # Verify CITATION sheet
        citation_df = pd.read_excel(file_path, sheet_name="AI_API_08_CITATION")
        assert len(citation_df) == 2  # 2 citations from first question
        
        # Check exact headers
        expected_citation_headers = [
            "run_id", "question_id", "provider", "citation_index", "citation_url"
        ]
        assert list(citation_df.columns) == expected_citation_headers
        
        # Check data
        assert citation_df.iloc[0]["citation_index"] == 0
        assert citation_df.iloc[0]["citation_url"] == "https://ai.example.com"
        assert citation_df.iloc[1]["citation_index"] == 1
        assert citation_df.iloc[1]["citation_url"] == "https://ml.example.com"

        # Cleanup
        if os.path.exists(file_path):
            os.remove(file_path)

    @pytest.mark.asyncio
    async def test_export_multi_provider(self, db_session):
        """Test export with multiple providers."""
        # Setup
        campaign = Campaign(name="Multi Provider Test")
        db_session.add(campaign)
        await db_session.commit()

        topic = Topic(campaign_id=campaign.id, title="Test Topic")
        db_session.add(topic)

        persona = Persona(name="Tester")
        db_session.add(persona)
        await db_session.commit()

        question = Question(topic_id=topic.id, persona_id=persona.id, text="Test question")
        db_session.add(question)
        await db_session.commit()

        import json
        run = Run(
            campaign_id=campaign.id,
            label="Multi Provider Run",
            provider_settings_json=json.dumps({
                "providers": [
                    {"name": "openai", "model": "gpt-4o-mini"},
                    {"name": "gemini", "model": "gemini-pro"}
                ]
            }),
            status="completed"
        )
        db_session.add(run)
        await db_session.commit()

        # Create run items for each provider
        run_item_openai = RunItem(
            run_id=run.id,
            question_id=question.id,
            idempotency_key="test_key_openai",
            status="succeeded"
        )
        run_item_gemini = RunItem(
            run_id=run.id,
            question_id=question.id,
            idempotency_key="test_key_gemini",
            status="succeeded"
        )
        db_session.add_all([run_item_openai, run_item_gemini])
        await db_session.commit()

        # Add responses
        response_openai = Response(
            run_item_id=run_item_openai.id,
            provider="openai",
            model="gpt-4o-mini",
            prompt_version="v1",
            request_json=json.dumps({}),
            response_json=json.dumps({"answer": "OpenAI answer", "citations": ["https://openai.com"]}),
            text="OpenAI answer",
            citations_json=json.dumps(["https://openai.com"]),
            token_usage_json=json.dumps({"prompt_tokens": 100, "completion_tokens": 50}),
            latency_ms=1500,
            cost_cents=5.0
        )
        response_gemini = Response(
            run_item_id=run_item_gemini.id,
            provider="gemini",
            model="gemini-pro",
            prompt_version="v1",
            request_json=json.dumps({}),
            response_json=json.dumps({"answer": "Gemini answer", "citations": ["https://google.com"]}),
            text="Gemini answer",
            citations_json=json.dumps(["https://google.com"]),
            token_usage_json=json.dumps({"prompt_tokens": 90, "completion_tokens": 45}),
            latency_ms=1800,
            cost_cents=4.5
        )
        db_session.add_all([response_openai, response_gemini])
        await db_session.commit()

        # Export
        service = ExportService(db_session)
        export = await service.create_export(
            run_id=run.id,
            format="xlsx",
            mapper_name="user_excel_v0_1",
            mapper_version="v1"
        )

        file_path = await service.export_to_file(export.id, output_dir="artefacts")

        # Verify
        assert os.path.exists(file_path)
        
        query_df = pd.read_excel(file_path, sheet_name="AI_API_04_QUERY")
        
        # Should have 2 rows (one per provider)
        assert len(query_df) == 2
        
        # Check both providers present
        providers = query_df["provider"].tolist()
        assert "openai" in providers
        assert "gemini" in providers
        
        # Check models
        models = query_df["model"].tolist()
        assert "gpt-4o-mini" in models
        assert "gemini-pro" in models

        # Check citations
        citation_df = pd.read_excel(file_path, sheet_name="AI_API_08_CITATION")
        assert len(citation_df) == 2  # 1 citation per provider

        # Cleanup
        if os.path.exists(file_path):
            os.remove(file_path)

    @pytest.mark.asyncio
    async def test_export_with_api_endpoint(self, client, auth_headers, db_session):
        """Test export via API endpoint."""
        # Setup minimal data
        campaign = Campaign(name="API Test")
        db_session.add(campaign)
        await db_session.commit()

        topic = Topic(campaign_id=campaign.id, title="Test")
        db_session.add(topic)

        persona = Persona(name="User")
        db_session.add(persona)
        await db_session.commit()

        question = Question(topic_id=topic.id, persona_id=persona.id, text="Test?")
        db_session.add(question)
        await db_session.commit()

        import json
        run = Run(
            campaign_id=campaign.id,
            label="API Test Run",
            provider_settings_json=json.dumps({
                "providers": [{"name": "openai", "model": "gpt-4o-mini"}]
            }),
            status="completed"
        )
        db_session.add(run)
        await db_session.commit()

        run_item = RunItem(
            run_id=run.id,
            question_id=question.id,
            idempotency_key="api_test_key",
            status="succeeded"
        )
        db_session.add(run_item)
        await db_session.commit()

        response_obj = Response(
            run_item_id=run_item.id,
            provider="openai",
            model="gpt-4o-mini",
            prompt_version="v1",
            request_json=json.dumps({}),
            response_json=json.dumps({"answer": "Test answer", "citations": []}),
            text="Test answer",
            citations_json=json.dumps([]),
            token_usage_json=json.dumps({"prompt_tokens": 50, "completion_tokens": 25}),
            latency_ms=1000,
            cost_cents=2.0
        )
        db_session.add(response_obj)
        await db_session.commit()

        # Create export via API
        response = await client.post(
            "/api/v1/exports",
            headers=auth_headers,
            json={
                "run_id": run.id,
                "format": "xlsx",
                "mapper_name": "user_excel_v0_1",
                "mapper_version": "v1"
            }
        )

        assert response.status_code == 201
        data = response.json()
        export_id = data["id"]

        # Get export status
        response = await client.get(
            f"/api/v1/exports/{export_id}",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["mapper_name"] == "user_excel_v0_1"
        assert data["file_url"] is not None
        assert f"user_excel_v0_1_{run.id}.xlsx" in data["file_url"]

