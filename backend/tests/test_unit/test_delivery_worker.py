"""Unit tests for delivery worker task (TICKET 5)."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import Response, TimeoutException, NetworkError
from app.workers.tasks import _deliver_to_partner_async, _calculate_backoff_with_jitter
from app.db.models import Delivery, Export
from app.core.config import settings


@pytest.mark.unit
@pytest.mark.ticket5
class TestDeliveryWorker:
    """Test delivery worker task behavior."""

    @pytest.mark.asyncio
    async def test_delivery_success_2xx(self, db_session):
        """Test successful delivery with 2xx response."""
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
        payload = {"query_id": "test", "answer": "Test answer"}
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

        # Mock HTTP response
        mock_response = Response(
            status_code=200,
            text='{"success": true}',
            headers={"content-type": "application/json"}
        )

        # Mock Celery task
        mock_task = MagicMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            with patch("app.workers.tasks.get_rate_limiter") as mock_limiter:
                mock_limiter.return_value.acquire = AsyncMock(return_value=True)

                result = await _deliver_to_partner_async(delivery.id, mock_task)

        # Verify result
        assert result["status"] == "succeeded"
        assert result["status_code"] == 200

        # Verify database state
        await db_session.refresh(delivery)
        assert delivery.status == "succeeded"
        assert delivery.attempts == 1
        assert delivery.response_body == '{"success": true}'
        assert delivery.last_error is None

    @pytest.mark.asyncio
    async def test_delivery_client_error_4xx_no_retry(self, db_session):
        """Test delivery with 4xx response does not retry."""
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
        payload = {"query_id": "test", "answer": "Test answer"}
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

        # Mock HTTP response (400 Bad Request)
        mock_response = Response(
            status_code=400,
            text='{"error": "Invalid payload"}',
            headers={"content-type": "application/json"}
        )

        # Mock Celery task
        mock_task = MagicMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            with patch("app.workers.tasks.get_rate_limiter") as mock_limiter:
                mock_limiter.return_value.acquire = AsyncMock(return_value=True)

                result = await _deliver_to_partner_async(delivery.id, mock_task)

        # Verify result
        assert result["status"] == "failed"
        assert result["status_code"] == 400

        # Verify database state
        await db_session.refresh(delivery)
        assert delivery.status == "failed"
        assert delivery.attempts == 1
        assert "HTTP 400" in delivery.last_error
        assert delivery.response_body == '{"error": "Invalid payload"}'

        # Verify no retry was attempted
        mock_task.retry.assert_not_called()

    @pytest.mark.asyncio
    async def test_delivery_server_error_5xx_retries(self, db_session):
        """Test delivery with 5xx response retries with backoff."""
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
        payload = {"query_id": "test", "answer": "Test answer"}
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

        # Mock HTTP response (503 Service Unavailable)
        mock_response = Response(
            status_code=503,
            text='{"error": "Service temporarily unavailable"}',
            headers={"content-type": "application/json"}
        )

        # Mock Celery task
        mock_task = MagicMock()
        mock_task.retry.side_effect = Exception("Retry called")

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            with patch("app.workers.tasks.get_rate_limiter") as mock_limiter:
                mock_limiter.return_value.acquire = AsyncMock(return_value=True)

                with pytest.raises(Exception, match="Retry called"):
                    await _deliver_to_partner_async(delivery.id, mock_task)

        # Verify database state
        await db_session.refresh(delivery)
        assert delivery.status == "pending"  # Still pending, will retry
        assert delivery.attempts == 1
        assert "HTTP 503" in delivery.last_error

        # Verify retry was called with countdown
        mock_task.retry.assert_called_once()
        call_kwargs = mock_task.retry.call_args.kwargs
        assert "countdown" in call_kwargs
        assert call_kwargs["countdown"] > 0

    @pytest.mark.asyncio
    async def test_delivery_network_timeout_retries(self, db_session):
        """Test delivery timeout triggers retry."""
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
        payload = {"query_id": "test", "answer": "Test answer"}
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
        mock_task = MagicMock()
        mock_task.retry.side_effect = Exception("Retry called")

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = TimeoutException("Request timeout")

            with patch("app.workers.tasks.get_rate_limiter") as mock_limiter:
                mock_limiter.return_value.acquire = AsyncMock(return_value=True)

                with pytest.raises(Exception, match="Retry called"):
                    await _deliver_to_partner_async(delivery.id, mock_task)

        # Verify database state
        await db_session.refresh(delivery)
        assert delivery.status == "pending"
        assert delivery.attempts == 1
        assert "Timeout" in delivery.last_error

        # Verify retry was called
        mock_task.retry.assert_called_once()

    @pytest.mark.asyncio
    async def test_delivery_network_error_retries(self, db_session):
        """Test network error triggers retry."""
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
        payload = {"query_id": "test", "answer": "Test answer"}
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
        mock_task = MagicMock()
        mock_task.retry.side_effect = Exception("Retry called")

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = NetworkError("Connection refused")

            with patch("app.workers.tasks.get_rate_limiter") as mock_limiter:
                mock_limiter.return_value.acquire = AsyncMock(return_value=True)

                with pytest.raises(Exception, match="Retry called"):
                    await _deliver_to_partner_async(delivery.id, mock_task)

        # Verify database state
        await db_session.refresh(delivery)
        assert delivery.status == "pending"
        assert delivery.attempts == 1
        assert "Network error" in delivery.last_error

        # Verify retry was called
        mock_task.retry.assert_called_once()

    @pytest.mark.asyncio
    async def test_delivery_max_attempts_exhausted(self, db_session):
        """Test delivery fails after max attempts."""
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

        # Create delivery with max attempts already reached
        payload = {"query_id": "test", "answer": "Test answer"}
        delivery = Delivery(
            export_id=export.id,
            run_id="run_123",
            mapper_name="example_partner",
            mapper_version="v1",
            payload_json=json.dumps(payload),
            status="pending",
            attempts=settings.max_delivery_attempts - 1  # One more attempt left
        )
        db_session.add(delivery)
        await db_session.commit()

        # Mock HTTP response (503)
        mock_response = Response(
            status_code=503,
            text='{"error": "Service unavailable"}',
            headers={"content-type": "application/json"}
        )

        # Mock Celery task
        mock_task = MagicMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            with patch("app.workers.tasks.get_rate_limiter") as mock_limiter:
                mock_limiter.return_value.acquire = AsyncMock(return_value=True)

                result = await _deliver_to_partner_async(delivery.id, mock_task)

        # Verify result
        assert result["status"] == "failed"
        assert "Max attempts" in result["error"]

        # Verify database state
        await db_session.refresh(delivery)
        assert delivery.status == "failed"
        assert delivery.attempts == settings.max_delivery_attempts

        # Verify no retry was attempted (max reached)
        mock_task.retry.assert_not_called()

    @pytest.mark.asyncio
    async def test_delivery_uses_custom_headers(self, db_session):
        """Test delivery uses custom headers from config."""
        # Create export with custom headers
        export = Export(
            run_id="run_123",
            format="jsonl",
            mapper_name="example_partner",
            mapper_version="v1",
            config_json=json.dumps({
                "webhook_url": "http://partner.test/webhook",
                "headers": {"X-Custom-Header": "custom-value"}
            }),
            status="completed"
        )
        db_session.add(export)
        await db_session.commit()

        # Create delivery
        payload = {"query_id": "test", "answer": "Test answer"}
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

        # Mock HTTP response
        mock_response = Response(status_code=200, text='{"success": true}')

        # Mock Celery task
        mock_task = MagicMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            with patch("app.workers.tasks.get_rate_limiter") as mock_limiter:
                mock_limiter.return_value.acquire = AsyncMock(return_value=True)

                result = await _deliver_to_partner_async(delivery.id, mock_task)

        # Verify custom header was used
        call_kwargs = mock_post.call_args.kwargs
        assert "headers" in call_kwargs
        assert call_kwargs["headers"]["X-Custom-Header"] == "custom-value"
        assert call_kwargs["headers"]["Content-Type"] == "application/json"

    @pytest.mark.asyncio
    async def test_delivery_rate_limited(self, db_session):
        """Test delivery respects rate limiting."""
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
        payload = {"query_id": "test", "answer": "Test answer"}
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
        mock_task = MagicMock()
        mock_task.retry.side_effect = Exception("Retry called")

        with patch("app.workers.tasks.get_rate_limiter") as mock_limiter:
            # Rate limit not acquired
            mock_limiter.return_value.acquire = AsyncMock(return_value=False)

            with pytest.raises(Exception, match="Retry called"):
                await _deliver_to_partner_async(delivery.id, mock_task)

        # Verify retry was called due to rate limit
        mock_task.retry.assert_called_once()
        call_kwargs = mock_task.retry.call_args.kwargs
        assert "countdown" in call_kwargs


@pytest.mark.unit
class TestBackoffCalculation:
    """Test exponential backoff with jitter calculation."""

    def test_backoff_increases_exponentially(self):
        """Test backoff increases with attempts."""
        attempt_1 = _calculate_backoff_with_jitter(1)
        attempt_2 = _calculate_backoff_with_jitter(2)
        attempt_3 = _calculate_backoff_with_jitter(3)

        # Should increase (accounting for jitter variance)
        assert attempt_1 < attempt_3
        assert attempt_2 < attempt_3 * 1.5  # Allow for jitter

    def test_backoff_capped_at_max(self):
        """Test backoff is capped at maximum delay."""
        # Large attempt should be capped at 60 seconds
        delay = _calculate_backoff_with_jitter(10)
        assert delay <= 60

    def test_backoff_has_jitter(self):
        """Test backoff includes jitter (variance)."""
        # Run multiple times and verify variance
        delays = [_calculate_backoff_with_jitter(3) for _ in range(10)]
        
        # Should have some variance (not all the same)
        assert len(set(delays)) > 1

    def test_backoff_minimum(self):
        """Test backoff has reasonable minimum."""
        delay = _calculate_backoff_with_jitter(1)
        
        # Should be at least 1 second (with jitter)
        assert delay >= 1
        assert delay <= 5  # With base=2 and jitter, should be < 5


@pytest.mark.unit
@pytest.mark.ticket5
class TestDeliveryMapper:
    """Test mapper integration with delivery."""

    def test_mapper_transforms_payload(self):
        """Test mapper correctly transforms result to payload."""
        from app.exporters.mappers.example_webhook import ExampleWebhookMapperV1

        mapper = ExampleWebhookMapperV1()

        result = {
            "run_item_id": "item_123",
            "question_text": "What is AI?",
            "response": {
                "answer": "AI is artificial intelligence",
                "citations": ["https://example.com/ai"]
            },
            "provider": "openai",
            "model": "gpt-4o-mini",
            "cost_cents": 10.5,
            "latency_ms": 2000,
        }

        payload = mapper.map(result)

        assert payload["query_id"] == "item_123"
        assert payload["question"] == "What is AI?"
        assert payload["answer"] == "AI is artificial intelligence"
        assert payload["sources"] == ["https://example.com/ai"]
        assert payload["metadata"]["provider"] == "openai"
        assert payload["metadata"]["model"] == "gpt-4o-mini"
        assert payload["metadata"]["cost_usd"] == 0.105  # cents to dollars
        assert payload["metadata"]["latency_ms"] == 2000


