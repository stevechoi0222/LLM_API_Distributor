"""Celery tasks for run execution and deliveries."""
import asyncio
import json
from datetime import datetime
from typing import Any, Dict
from sqlalchemy import select
from tenacity import retry, stop_after_attempt, wait_exponential
from app.core.config import settings
from app.core.logging import get_logger
from app.core.rate_limit import get_rate_limiter
from app.db.session import AsyncSessionLocal
from app.db.models import RunItem, Question, Response, Delivery
from app.domain.providers.registry import provider_registry
from app.domain.services.run_service import RunService
from app.domain.services.export_service import ExportService
from app.exporters.mappers.example_webhook import get_mapper
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(name="execute_run_item", bind=True, max_retries=3)
def execute_run_item(self, run_item_id: str) -> Dict[str, Any]:
    """Execute a single run item with provider call.
    
    Args:
        run_item_id: Run item ID
        
    Returns:
        Execution result
    """
    # Run async task in event loop
    return asyncio.run(_execute_run_item_async(run_item_id, self))


async def _execute_run_item_async(run_item_id: str, task) -> Dict[str, Any]:
    """Async implementation of run item execution."""
    async with AsyncSessionLocal() as session:
        try:
            # Get run item with question
            stmt = (
                select(RunItem)
                .where(RunItem.id == run_item_id)
            )
            result = await session.execute(stmt)
            run_item = result.scalar_one_or_none()

            if not run_item:
                logger.error("run_item_not_found", run_item_id=run_item_id)
                return {"status": "failed", "error": "Run item not found"}

            # Update status
            run_item.status = "running"
            run_item.attempt_count += 1
            await session.commit()

            logger.info(
                "run_item_started",
                run_item_id=run_item_id,
                attempt=run_item.attempt_count
            )

            # Get question with relations
            stmt = select(Question).where(Question.id == run_item.question_id)
            result = await session.execute(stmt)
            question = result.scalar_one_or_none()

            if not question:
                raise ValueError("Question not found")

            # Parse run settings
            stmt = select(RunItem.run).where(RunItem.id == run_item_id)
            run_result = await session.execute(stmt)
            run = run_result.scalar_one()
            
            provider_settings = json.loads(run.provider_settings_json)
            prompt_version = provider_settings.get("prompt_version", "v1")
            
            # Get provider config for this question
            # Extract from metadata or use first provider
            metadata = json.loads(question.metadata_json) if question.metadata_json else {}
            provider_overrides = metadata.get("provider_overrides", {})
            
            # Find matching provider config
            providers = provider_settings.get("providers", [])
            provider_config = providers[0]  # Simplified: use first provider
            # Merge with overrides
            merged_config = {**provider_config, **provider_overrides}

            provider_name = merged_config["name"]
            model = merged_config["model"]

            # Get provider client
            client = provider_registry.get(provider_name)

            # Apply rate limiting
            rate_limiter = get_rate_limiter()
            acquired = await rate_limiter.acquire(provider_name, tokens=1, timeout=60.0)
            
            if not acquired:
                raise Exception("Rate limit timeout")

            # Prepare prompt
            persona_data = {
                "name": question.persona.name,
                "role": question.persona.role,
                "locale": question.persona.locale,
                "tone": question.persona.tone,
            }
            topic_data = {
                "title": question.topic.title,
                "description": question.topic.description,
            }
            
            request = await client.prepare_prompt(
                question=question.text,
                persona=persona_data,
                topic=topic_data,
                prompt_version=prompt_version,
            )

            # Invoke provider
            provider_result = await client.invoke(request, **merged_config)

            # Store response
            response = Response(
                run_item_id=run_item_id,
                provider=provider_name,
                model=model,
                prompt_version=prompt_version,
                request_json=json.dumps(request),
                response_json=json.dumps(provider_result.validated_json or {}),
                text=provider_result.text,
                citations_json=json.dumps(provider_result.citations),
                token_usage_json=json.dumps(provider_result.usage),
                latency_ms=provider_result.latency_ms,
                cost_cents=provider_result.cost_cents,
            )
            session.add(response)

            # Update run item status
            run_item.status = "succeeded"
            run_item.last_error = None
            await session.commit()

            logger.info(
                "run_item_succeeded",
                run_item_id=run_item_id,
                provider=provider_name,
                cost_cents=provider_result.cost_cents
            )

            # Update run cost and status
            run_service = RunService(session)
            await run_service.update_run_cost(run.id)
            await run_service.update_run_status(run.id)

            return {
                "status": "succeeded",
                "cost_cents": provider_result.cost_cents,
                "latency_ms": provider_result.latency_ms,
            }

        except Exception as e:
            logger.error(
                "run_item_failed",
                run_item_id=run_item_id,
                error=str(e),
                attempt=run_item.attempt_count
            )

            # Update run item
            run_item.status = "failed"
            run_item.last_error = str(e)
            await session.commit()

            # Retry with exponential backoff
            if run_item.attempt_count < 3:
                raise task.retry(exc=e, countdown=2 ** run_item.attempt_count)

            return {"status": "failed", "error": str(e)}


@celery_app.task(name="export_job")
def export_job(export_id: str) -> Dict[str, Any]:
    """Execute export job.
    
    Args:
        export_id: Export ID
        
    Returns:
        Export result
    """
    return asyncio.run(_export_job_async(export_id))


async def _export_job_async(export_id: str) -> Dict[str, Any]:
    """Async implementation of export job."""
    async with AsyncSessionLocal() as session:
        try:
            export_service = ExportService(session)
            file_path = await export_service.export_to_file(export_id)
            
            return {"status": "completed", "file_path": file_path}

        except Exception as e:
            logger.error("export_job_failed", export_id=export_id, error=str(e))
            return {"status": "failed", "error": str(e)}


@celery_app.task(name="deliver_to_partner", bind=True, max_retries=settings.max_delivery_attempts)
def deliver_to_partner(self, delivery_id: str) -> Dict[str, Any]:
    """Deliver to partner API with retries (TICKET 5).
    
    Args:
        delivery_id: Delivery ID
        
    Returns:
        Delivery result
    """
    return asyncio.run(_deliver_to_partner_async(delivery_id, self))


@retry(
    stop=stop_after_attempt(settings.max_delivery_attempts),
    wait=wait_exponential(
        multiplier=1,
        min=settings.delivery_retry_backoff_base,
        max=60
    )
)
async def _deliver_to_partner_async(delivery_id: str, task) -> Dict[str, Any]:
    """Async implementation of partner delivery with retry."""
    async with AsyncSessionLocal() as session:
        try:
            # Get delivery
            stmt = select(Delivery).where(Delivery.id == delivery_id)
            result = await session.execute(stmt)
            delivery = result.scalar_one_or_none()

            if not delivery:
                logger.error("delivery_not_found", delivery_id=delivery_id)
                return {"status": "failed", "error": "Delivery not found"}

            # Update attempts
            delivery.attempts += 1
            await session.commit()

            logger.info(
                "delivery_started",
                delivery_id=delivery_id,
                attempt=delivery.attempts,
                mapper=delivery.mapper_name
            )

            # Get mapper
            mapper = get_mapper(delivery.mapper_name, version="v1")

            # Parse payload
            payload = json.loads(delivery.payload_json)

            # Get webhook URL from export config
            stmt = select(Delivery.export).where(Delivery.id == delivery_id)
            export_result = await session.execute(stmt)
            export = export_result.scalar_one()
            
            config = json.loads(export.config_json) if export.config_json else {}
            webhook_url = config.get("webhook_url")

            if not webhook_url:
                raise ValueError("webhook_url not configured")

            # Deliver
            response_data = await mapper.deliver(payload, webhook_url)

            # Update delivery
            delivery.status = "succeeded"
            delivery.response_body = response_data.get("body", "")
            await session.commit()

            logger.info(
                "delivery_succeeded",
                delivery_id=delivery_id,
                status_code=response_data.get("status_code")
            )

            return {"status": "succeeded", "response": response_data}

        except Exception as e:
            logger.error(
                "delivery_failed",
                delivery_id=delivery_id,
                error=str(e),
                attempt=delivery.attempts
            )

            # Update delivery
            delivery.status = "failed" if delivery.attempts >= settings.max_delivery_attempts else "pending"
            delivery.last_error = str(e)
            await session.commit()

            # Retry
            if delivery.attempts < settings.max_delivery_attempts:
                countdown = settings.delivery_retry_backoff_base ** delivery.attempts
                raise task.retry(exc=e, countdown=countdown)

            return {"status": "failed", "error": str(e)}


