"""Run orchestration service."""
import json
from typing import Any, Dict, List
from datetime import datetime
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.logging import get_logger
from app.db.models import Run, RunItem, Question, Campaign, Response
from app.domain.schemas import ProviderConfig, RunStatusCounts
from app.utils.hashing import compute_idempotency_hash

logger = get_logger(__name__)


class RunService:
    """Service for run orchestration."""

    def __init__(self, session: AsyncSession):
        """Initialize run service.
        
        Args:
            session: Database session
        """
        self.session = session

    async def create_run(
        self,
        campaign_id: str,
        providers: List[ProviderConfig],
        prompt_version: str = "v1",
        label: str | None = None,
    ) -> Run:
        """Create a new run.
        
        Args:
            campaign_id: Campaign ID
            providers: List of provider configurations
            prompt_version: Prompt version
            label: Optional label
            
        Returns:
            Created run
        """
        # Verify campaign exists
        stmt = select(Campaign).where(Campaign.id == campaign_id)
        result = await self.session.execute(stmt)
        campaign = result.scalar_one_or_none()
        
        if not campaign:
            raise ValueError(f"Campaign {campaign_id} not found")

        # Create run
        provider_settings = {
            "providers": [p.model_dump() for p in providers],
            "prompt_version": prompt_version,
        }

        run = Run(
            campaign_id=campaign_id,
            label=label,
            provider_settings_json=json.dumps(provider_settings),
            status="pending",
        )
        self.session.add(run)
        await self.session.commit()

        logger.info("run_created", run_id=run.id, campaign_id=campaign_id)

        return run

    async def materialize_run_items(
        self,
        run: Run,
    ) -> int:
        """Materialize run_items for all questions × providers.
        
        Args:
            run: Run instance
            
        Returns:
            Number of items created
        """
        # Get provider settings
        settings = json.loads(run.provider_settings_json)
        providers = settings.get("providers", [])
        prompt_version = settings.get("prompt_version", "v1")

        # Get all questions for campaign
        stmt = (
            select(Question)
            .join(Question.topic)
            .where(Question.topic.has(campaign_id=run.campaign_id))
        )
        result = await self.session.execute(stmt)
        questions = result.scalars().all()

        logger.info(
            "materializing_run_items",
            run_id=run.id,
            question_count=len(questions),
            provider_count=len(providers)
        )

        items_created = 0

        for question in questions:
            for provider_config in providers:
                # Generate idempotency key
                metadata = json.loads(question.metadata_json) if question.metadata_json else {}
                provider_overrides = metadata.get("provider_overrides", {})
                
                # Merge provider settings
                merged_settings = {**provider_config, **provider_overrides}

                idempotency_key = compute_idempotency_hash(
                    provider=provider_config["name"],
                    model=provider_config["model"],
                    prompt_version=prompt_version,
                    question_id=question.id,
                    persona_id=question.persona_id,
                    question_text=question.text,
                    provider_settings=merged_settings,
                )

                # Check if already exists
                stmt = select(RunItem).where(RunItem.idempotency_key == idempotency_key)
                result = await self.session.execute(stmt)
                existing = result.scalar_one_or_none()

                if existing:
                    logger.debug(
                        "run_item_skipped_duplicate",
                        idempotency_key=idempotency_key[:16]
                    )
                    continue

                # Create run item
                run_item = RunItem(
                    run_id=run.id,
                    question_id=question.id,
                    idempotency_key=idempotency_key,
                    status="pending",
                )
                self.session.add(run_item)
                items_created += 1

        await self.session.commit()

        logger.info("run_items_materialized", run_id=run.id, items_created=items_created)

        return items_created

    async def get_run_status_counts(self, run_id: str) -> RunStatusCounts:
        """Get status counts for a run.
        
        Args:
            run_id: Run ID
            
        Returns:
            Status counts
        """
        stmt = (
            select(
                func.count().label("total"),
                func.sum(func.case((RunItem.status == "pending", 1), else_=0)).label("pending"),
                func.sum(func.case((RunItem.status == "running", 1), else_=0)).label("running"),
                func.sum(func.case((RunItem.status == "succeeded", 1), else_=0)).label("succeeded"),
                func.sum(func.case((RunItem.status == "failed", 1), else_=0)).label("failed"),
                func.sum(func.case((RunItem.status == "skipped", 1), else_=0)).label("skipped"),
            )
            .where(RunItem.run_id == run_id)
        )
        result = await self.session.execute(stmt)
        row = result.one()

        return RunStatusCounts(
            total=row.total or 0,
            pending=row.pending or 0,
            running=row.running or 0,
            succeeded=row.succeeded or 0,
            failed=row.failed or 0,
            skipped=row.skipped or 0,
        )

    async def update_run_cost(self, run_id: str) -> float:
        """Update run cost from responses (TICKET 3).
        
        Args:
            run_id: Run ID
            
        Returns:
            Total cost in cents
        """
        # Sum costs from all responses
        stmt = (
            select(func.sum(Response.cost_cents))
            .join(Response.run_item)
            .where(RunItem.run_id == run_id)
        )
        result = await self.session.execute(stmt)
        total_cost = result.scalar() or 0

        # Update run
        stmt = select(Run).where(Run.id == run_id)
        result = await self.session.execute(stmt)
        run = result.scalar_one_or_none()

        if run:
            run.cost_cents = total_cost
            await self.session.commit()

        logger.debug("run_cost_updated", run_id=run_id, cost_cents=float(total_cost))

        return float(total_cost)

    async def update_run_status(self, run_id: str) -> None:
        """Update run status based on run_items.
        
        Args:
            run_id: Run ID
        """
        counts = await self.get_run_status_counts(run_id)

        # Determine run status
        stmt = select(Run).where(Run.id == run_id)
        result = await self.session.execute(stmt)
        run = result.scalar_one_or_none()

        if not run:
            return

        if counts.total == 0:
            new_status = "pending"
        elif counts.succeeded + counts.failed + counts.skipped == counts.total:
            new_status = "completed"
            run.finished_at = datetime.utcnow()
        elif counts.running > 0 or counts.succeeded > 0:
            new_status = "running"
            if not run.started_at:
                run.started_at = datetime.utcnow()
        else:
            new_status = "pending"

        if run.status != new_status:
            run.status = new_status
            await self.session.commit()
            logger.info("run_status_updated", run_id=run_id, status=new_status)


