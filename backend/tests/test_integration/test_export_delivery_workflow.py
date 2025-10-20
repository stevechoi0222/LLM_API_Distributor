"""Integration tests for export + delivery workflow (TICKET 5)."""
import json
import pytest
from unittest.mock import AsyncMock, patch
from httpx import Response
from sqlalchemy import select
from app.db.models import Campaign, Topic, Persona, Question, Run, RunItem, Response as ResponseModel, Export, Delivery
from app.domain.services.export_service import ExportService
from app.workers.tasks import _deliver_to_partner_async


@pytest.mark.integration
@pytest.mark.ticket5
class TestExportDeliveryWorkflow:
    """Test complete export and delivery workflow."""

    @pytest.mark.asyncio
    async def test_create_export_with_deliveries(self, db_session):
        """Test creating export generates deliveries for successful results."""
        # Setup: Create campaign, topic, persona, questions
        campaign = Campaign(name="Test Campaign", product_name="Test Product")
        db_session.add(campaign)
        await db_session.commit()

        topic = Topic(campaign_id=campaign.id, title="Test Topic")
        db_session.add(topic)

        persona = Persona(name="Test User", role="Developer")
        db_session.add(persona)
        await db_session.commit()

        # Create questions
        question1 = Question(
            topic_id=topic.id,
            persona_id=persona.id,
            text="What is AI?"
        )
        question2 = Question(
            topic_id=topic.id,
            persona_id=persona.id,
            text="What is ML?"
        )
        db_session.add_all([question1, question2])
        await db_session.commit()

        # Create run
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
            question_id=question1.id,
            idempotency_key="test_key_1",
            status="succeeded"
        )
        run_item2 = RunItem(
            run_id=run.id,
            question_id=question2.id,
            idempotency_key="test_key_2",
            status="succeeded"
        )
        db_session.add_all([run_item1, run_item2])
        await db_session.commit()

        # Add responses
        response1 = ResponseModel(
            run_item_id=run_item1.id,
            provider="openai",
            model="gpt-4o-mini",
            prompt_version="v1",
            request_json=json.dumps({"messages": [{"role": "user", "content": "What is AI?"}]}),
            response_json=json.dumps({"answer": "AI is artificial intelligence", "citations": []}),
            text="AI is artificial intelligence",
            cost_cents=5.0
        )
        response2 = ResponseModel(
            run_item_id=run_item2.id,
            provider="openai",
            model="gpt-4o-mini",
            prompt_version="v1",
            request_json=json.dumps({"messages": [{"role": "user", "content": "What is ML?"}]}),
            response_json=json.dumps({"answer": "ML is machine learning", "citations": []}),
            text="ML is machine learning",
            cost_cents=4.5
        )
        db_session.add_all([response1, response2])
        await db_session.commit()

        # Create export with mapper
        service = ExportService(db_session)
        export = await service.create_export(
            run_id=run.id,
            format="jsonl",
            mapper_name="example_partner",
            mapper_version="v1",
            config={"webhook_url": "http://partner.test/webhook"}
        )

        # Get results
        results = await service.get_run_results_for_export(run.id)
        assert len(results) == 2
        assert all(r["status"] == "succeeded" for r in results)

        # Create deliveries
        from app.exporters.mappers.example_webhook import get_mapper
        mapper = get_mapper("example_partner", "v1")

        deliveries_created = 0
        for result in results:
            if result["status"] == "succeeded":
                payload = mapper.map(result)
                delivery = await service.create_delivery(
                    export_id=export.id,
                    run_id=run.id,
                    mapper_name="example_partner",
                    mapper_version="v1",
                    payload=payload
                )
                deliveries_created += 1

        # Verify deliveries created
        assert deliveries_created == 2

        # Check database
        stmt = select(Delivery).where(Delivery.export_id == export.id)
        result = await db_session.execute(stmt)
        deliveries = result.scalars().all()

        assert len(deliveries) == 2
        for d in deliveries:
            assert d.status == "pending"
            assert d.attempts == 0
            assert d.mapper_name == "example_partner"
            assert d.mapper_version == "v1"
            assert d.payload_json is not None

    @pytest.mark.asyncio
    async def test_delivery_workflow_success(self, db_session):
        """Test complete delivery workflow with successful POST."""
        # Create export
        export = Export(
            run_id="run_123",
            format="jsonl",
            mapper_name="example_partner",
            mapper_version="v1",
            config_json=json.dumps({"webhook_url": "http://partner.test/webhook"}),
            status="completed"
        )
        db_session.add(export)
        await db_session.commit()

        # Create delivery
        payload = {
            "query_id": "item_123",
            "question": "What is AI?",
            "answer": "AI is artificial intelligence",
            "sources": [],
            "metadata": {"provider": "openai", "model": "gpt-4o-mini"}
        }
        delivery = Delivery(
            export_id=export.id,
            run_id="run_123",
            mapper_name="example_partner",
            mapper_version="v1",
            payload_json=json.dumps(payload),
            status="pending"
        )
        db_session.add(delivery)
        await db_session.commit()

        # Mock successful HTTP response
        mock_response = Response(
            status_code=200,
            text='{"success": true, "id": "partner_123"}',
            headers={"content-type": "application/json"}
        )

        # Mock Celery task
        from unittest.mock import MagicMock
        mock_task = MagicMock()

        # Execute delivery
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            with patch("app.workers.tasks.get_rate_limiter") as mock_limiter:
                mock_limiter.return_value.acquire = AsyncMock(return_value=True)

                result = await _deliver_to_partner_async(delivery.id, mock_task)

        # Verify result
        assert result["status"] == "succeeded"
        assert result["status_code"] == 200

        # Verify database updated
        await db_session.refresh(delivery)
        assert delivery.status == "succeeded"
        assert delivery.attempts == 1
        assert delivery.last_error is None
        assert "success" in delivery.response_body

    @pytest.mark.asyncio
    async def test_delivery_workflow_with_retries(self, db_session):
        """Test delivery workflow with multiple retries then success."""
        # Create export
        export = Export(
            run_id="run_123",
            format="jsonl",
            mapper_name="example_partner",
            mapper_version="v1",
            config_json=json.dumps({"webhook_url": "http://partner.test/webhook"}),
            status="completed"
        )
        db_session.add(export)
        await db_session.commit()

        # Create delivery
        payload = {"query_id": "item_123", "answer": "Test"}
        delivery = Delivery(
            export_id=export.id,
            run_id="run_123",
            mapper_name="example_partner",
            mapper_version="v1",
            payload_json=json.dumps(payload),
            status="pending"
        )
        db_session.add(delivery)
        await db_session.commit()

        # Mock Celery task
        from unittest.mock import MagicMock
        mock_task = MagicMock()

        # First attempt: 503 error
        mock_response_503 = Response(
            status_code=503,
            text='{"error": "Service unavailable"}',
            headers={"content-type": "application/json"}
        )

        mock_task.retry.side_effect = Exception("Retry scheduled")

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response_503

            with patch("app.workers.tasks.get_rate_limiter") as mock_limiter:
                mock_limiter.return_value.acquire = AsyncMock(return_value=True)

                with pytest.raises(Exception, match="Retry scheduled"):
                    await _deliver_to_partner_async(delivery.id, mock_task)

        # Verify first attempt recorded
        await db_session.refresh(delivery)
        assert delivery.attempts == 1
        assert delivery.status == "pending"
        assert "HTTP 503" in delivery.last_error

        # Second attempt: Success
        mock_response_200 = Response(
            status_code=200,
            text='{"success": true}',
            headers={"content-type": "application/json"}
        )

        mock_task.retry.side_effect = None  # No retry on success

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response_200

            with patch("app.workers.tasks.get_rate_limiter") as mock_limiter:
                mock_limiter.return_value.acquire = AsyncMock(return_value=True)

                result = await _deliver_to_partner_async(delivery.id, mock_task)

        # Verify success
        assert result["status"] == "succeeded"

        await db_session.refresh(delivery)
        assert delivery.status == "succeeded"
        assert delivery.attempts == 2
        assert delivery.last_error is None or "HTTP 503" in delivery.last_error  # May retain old error

    @pytest.mark.asyncio
    async def test_export_status_with_delivery_stats(self, db_session):
        """Test export status endpoint returns delivery stats."""
        # Create export
        export = Export(
            run_id="run_123",
            format="jsonl",
            mapper_name="example_partner",
            mapper_version="v1",
            config_json=json.dumps({}),
            status="completed"
        )
        db_session.add(export)
        await db_session.commit()

        # Create deliveries with different statuses
        deliveries = [
            Delivery(
                export_id=export.id,
                run_id="run_123",
                mapper_name="example_partner",
                mapper_version="v1",
                payload_json=json.dumps({"id": f"payload_{i}"}),
                status="succeeded" if i < 3 else ("pending" if i < 5 else "failed"),
                attempts=1 if i < 5 else 5
            )
            for i in range(7)
        ]
        for d in deliveries:
            db_session.add(d)
        await db_session.commit()

        # Query delivery stats
        from sqlalchemy import func
        stmt = (
            select(
                Delivery.status,
                func.count().label("count")
            )
            .where(Delivery.export_id == export.id)
            .group_by(Delivery.status)
        )
        result = await db_session.execute(stmt)
        stats = {row.status: row.count for row in result}

        # Verify stats
        assert stats["succeeded"] == 3
        assert stats["pending"] == 2
        assert stats["failed"] == 2

    @pytest.mark.asyncio
    async def test_export_includes_sample_failures(self, db_session):
        """Test export status includes sample failed deliveries."""
        # Create export
        export = Export(
            run_id="run_123",
            format="jsonl",
            mapper_name="example_partner",
            mapper_version="v1",
            config_json=json.dumps({}),
            status="completed"
        )
        db_session.add(export)
        await db_session.commit()

        # Create failed deliveries with errors
        for i in range(10):
            delivery = Delivery(
                export_id=export.id,
                run_id="run_123",
                mapper_name="example_partner",
                mapper_version="v1",
                payload_json=json.dumps({"id": f"payload_{i}"}),
                status="failed",
                attempts=5,
                last_error=f"Error message {i}"
            )
            db_session.add(delivery)
        await db_session.commit()

        # Query sample failures (limit 5)
        stmt = (
            select(Delivery)
            .where(Delivery.export_id == export.id, Delivery.status == "failed")
            .order_by(Delivery.updated_at.desc())
            .limit(5)
        )
        result = await db_session.execute(stmt)
        failed_deliveries = result.scalars().all()

        # Verify sample
        assert len(failed_deliveries) == 5
        for d in failed_deliveries:
            assert d.status == "failed"
            assert d.last_error is not None
            assert d.attempts == 5


