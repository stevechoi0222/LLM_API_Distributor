"""Run execution endpoints."""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_authenticated_session
from app.core.logging import get_logger
from app.db.models import Run, RunItem
from app.domain.schemas import (
    RunCreate,
    RunResponse,
    RunItemResponse,
    RunStatusCounts,
    RunItemsResponse,
)
from app.domain.services.run_service import RunService
from app.domain.providers.registry import provider_registry
from app.workers.tasks import execute_run_item

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1", tags=["runs"])


@router.post("/runs", response_model=RunResponse, status_code=201)
async def create_run(
    data: RunCreate,
    session: AsyncSession = Depends(get_authenticated_session),
):
    """Create a new run.
    
    Validates that providers are enabled (TICKET 4).
    """
    # Validate providers are enabled (TICKET 4)
    for provider_config in data.providers:
        if not provider_registry.is_enabled(provider_config.name):
            raise HTTPException(
                status_code=400,
                detail=f"Provider '{provider_config.name}' is not enabled. "
                       f"Enabled providers: {', '.join(provider_registry.get_enabled_providers())}"
            )

    # Create run
    service = RunService(session)
    run = await service.create_run(
        campaign_id=data.campaign_id,
        providers=data.providers,
        prompt_version=data.prompt_version,
        label=data.label,
    )

    # Get counts
    counts = await service.get_run_status_counts(run.id)

    return RunResponse(
        id=run.id,
        campaign_id=run.campaign_id,
        label=run.label,
        status=run.status,
        cost_cents=float(run.cost_cents) if run.cost_cents else 0.0,
        counts=counts,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        errors=[],
    )


@router.post("/runs/{run_id}/start", status_code=202)
async def start_run(
    run_id: str,
    session: AsyncSession = Depends(get_authenticated_session),
):
    """Start run execution by materializing and enqueuing run items."""
    # Get run
    stmt = select(Run).where(Run.id == run_id)
    result = await session.execute(stmt)
    run = result.scalar_one_or_none()

    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    # Materialize run items
    service = RunService(session)
    items_created = await service.materialize_run_items(run)

    # Enqueue tasks for all pending items
    stmt = select(RunItem).where(
        RunItem.run_id == run_id,
        RunItem.status == "pending"
    )
    result = await session.execute(stmt)
    pending_items = result.scalars().all()

    for item in pending_items:
        execute_run_item.delay(item.id)

    logger.info(
        "run_started",
        run_id=run_id,
        items_created=items_created,
        items_enqueued=len(pending_items)
    )

    return {
        "run_id": run_id,
        "status": "started",
        "items_created": items_created,
        "items_enqueued": len(pending_items),
    }


@router.post("/runs/{run_id}/resume", status_code=202)
async def resume_run(
    run_id: str,
    session: AsyncSession = Depends(get_authenticated_session),
):
    """Resume run by re-enqueuing failed items."""
    # Get failed items
    stmt = select(RunItem).where(
        RunItem.run_id == run_id,
        RunItem.status == "failed"
    )
    result = await session.execute(stmt)
    failed_items = result.scalars().all()

    # Re-enqueue
    for item in failed_items:
        item.status = "pending"
        execute_run_item.delay(item.id)

    await session.commit()

    logger.info("run_resumed", run_id=run_id, items_resumed=len(failed_items))

    return {
        "run_id": run_id,
        "status": "resumed",
        "items_resumed": len(failed_items),
    }


@router.get("/runs/{run_id}", response_model=RunResponse)
async def get_run_status(
    run_id: str,
    session: AsyncSession = Depends(get_authenticated_session),
):
    """Get run status with cost rollup (TICKET 3)."""
    # Get run
    stmt = select(Run).where(Run.id == run_id)
    result = await session.execute(stmt)
    run = result.scalar_one_or_none()

    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    # Get counts
    service = RunService(session)
    counts = await service.get_run_status_counts(run_id)

    # Update cost
    cost_cents = await service.update_run_cost(run_id)

    # Get errors
    stmt = (
        select(RunItem)
        .where(RunItem.run_id == run_id, RunItem.status == "failed")
        .limit(10)
    )
    result = await session.execute(stmt)
    failed_items = result.scalars().all()

    errors = [
        {"run_item_id": item.id, "message": item.last_error}
        for item in failed_items
    ]

    return RunResponse(
        id=run.id,
        campaign_id=run.campaign_id,
        label=run.label,
        status=run.status,
        cost_cents=cost_cents,
        counts=counts,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        errors=errors,
    )


@router.get("/runs/{run_id}/items", response_model=RunItemsResponse)
async def get_run_items(
    run_id: str,
    limit: int = Query(100, le=1000),
    offset: int = Query(0, ge=0),
    status: str | None = Query(None),
    session: AsyncSession = Depends(get_authenticated_session),
):
    """Get paginated run items."""
    # Build query
    stmt = select(RunItem).where(RunItem.run_id == run_id)
    
    if status:
        stmt = stmt.where(RunItem.status == status)
    
    # Count total
    from sqlalchemy import func
    count_stmt = select(func.count()).select_from(stmt.subquery())
    count_result = await session.execute(count_stmt)
    total = count_result.scalar()

    # Get page
    stmt = stmt.limit(limit).offset(offset).order_by(RunItem.created_at)
    result = await session.execute(stmt)
    items = result.scalars().all()

    return RunItemsResponse(
        items=[
            RunItemResponse(
                id=item.id,
                run_id=item.run_id,
                question_id=item.question_id,
                status=item.status,
                attempt_count=item.attempt_count,
                last_error=item.last_error,
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
            for item in items
        ],
        total=total,
        limit=limit,
        offset=offset,
        has_more=(offset + len(items)) < total,
    )


