"""Export and delivery endpoints (TICKET 5, TICKET 7)."""
import os
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_authenticated_session
from app.core.logging import get_logger
from app.db.models import Export, Delivery
from app.domain.schemas import ExportCreate, ExportResponse, DeliveryResponse
from app.domain.services.export_service import ExportService
from app.workers.tasks import export_job, deliver_to_partner

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1", tags=["exports"])


@router.get("/runs/{run_id}/results:download")
async def download_run_results(
    run_id: str,
    format: str = Query(..., pattern="^(csv|xlsx|jsonl)$"),
    session: AsyncSession = Depends(get_authenticated_session),
):
    """Download run results in specified format.
    
    Creates export on-the-fly and returns file.
    """
    # Create export service
    service = ExportService(session)

    # Create export
    export = await service.create_export(
        run_id=run_id,
        format=format,
    )

    # Execute export synchronously (for direct download)
    file_path = await service.export_to_file(export.id)

    # Return file
    if not os.path.exists(file_path):
        raise HTTPException(status_code=500, detail="Export file not found")

    return FileResponse(
        path=file_path,
        filename=os.path.basename(file_path),
        media_type="application/octet-stream",
    )


@router.post("/exports", response_model=ExportResponse, status_code=201)
async def create_export(
    data: ExportCreate,
    session: AsyncSession = Depends(get_authenticated_session),
):
    """Create export job with optional mapper (TICKET 7).
    
    If mapper is specified, creates deliveries for partner API (TICKET 5).
    """
    # Create export service
    service = ExportService(session)

    # Create export
    export = await service.create_export(
        run_id=data.run_id,
        format=data.format,
        mapper_name=data.mapper_name,
        mapper_version=data.mapper_version,
        config=data.config,
    )

    # Enqueue export job
    export_job.delay(export.id)

    # If mapper specified, create deliveries
    if data.mapper_name:
        # Get results
        results = await service.get_run_results_for_export(data.run_id)

        # Import mapper
        from app.exporters.mappers.example_webhook import get_mapper
        
        try:
            mapper = get_mapper(data.mapper_name, data.mapper_version)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        # Create delivery for each result
        deliveries_created = 0
        for result in results:
            if result.get("status") == "succeeded":
                # Map payload
                payload = mapper.map(result)

                # Create delivery
                delivery = await service.create_delivery(
                    export_id=export.id,
                    run_id=data.run_id,
                    mapper_name=data.mapper_name,
                    mapper_version=data.mapper_version,
                    payload=payload,
                )

                # Enqueue delivery
                deliver_to_partner.delay(delivery.id)
                deliveries_created += 1

        logger.info(
            "export_deliveries_enqueued",
            export_id=export.id,
            deliveries_created=deliveries_created
        )

    return ExportResponse(
        id=export.id,
        run_id=export.run_id,
        format=export.format,
        mapper_name=export.mapper_name,
        mapper_version=export.mapper_version,
        status=export.status,
        file_url=export.file_url,
        created_at=export.created_at,
        deliveries_created=deliveries_created if data.mapper_name else None,
    )


@router.get("/exports/{export_id}", response_model=ExportResponse)
async def get_export_status(
    export_id: str,
    session: AsyncSession = Depends(get_authenticated_session),
):
    """Get export status with delivery stats and sample failures (TICKET 5)."""
    # Get export
    stmt = select(Export).where(Export.id == export_id)
    result = await session.execute(stmt)
    export = result.scalar_one_or_none()

    if not export:
        raise HTTPException(status_code=404, detail="Export not found")

    # Get delivery stats
    stmt = (
        select(
            Delivery.status,
            func.count().label("count")
        )
        .where(Delivery.export_id == export_id)
        .group_by(Delivery.status)
    )
    result = await session.execute(stmt)
    delivery_stats = {row.status: row.count for row in result}

    # Get sample failures (up to 5)
    sample_failures = []
    if delivery_stats.get("failed", 0) > 0:
        stmt = (
            select(Delivery)
            .where(Delivery.export_id == export_id, Delivery.status == "failed")
            .order_by(Delivery.updated_at.desc())
            .limit(5)
        )
        result = await session.execute(stmt)
        failed_deliveries = result.scalars().all()
        
        sample_failures = [
            {
                "id": d.id,
                "last_error": d.last_error,
                "attempts": d.attempts,
                "updated_at": d.updated_at.isoformat() if d.updated_at else None
            }
            for d in failed_deliveries
        ]

    return ExportResponse(
        id=export.id,
        run_id=export.run_id,
        format=export.format,
        mapper_name=export.mapper_name,
        mapper_version=export.mapper_version,
        status=export.status,
        file_url=export.file_url,
        created_at=export.created_at,
        delivery_stats=delivery_stats,
        sample_failures=sample_failures if sample_failures else None,
    )


@router.get("/deliveries/{delivery_id}", response_model=DeliveryResponse)
async def get_delivery_status(
    delivery_id: str,
    session: AsyncSession = Depends(get_authenticated_session),
):
    """Get delivery status (TICKET 5)."""
    stmt = select(Delivery).where(Delivery.id == delivery_id)
    result = await session.execute(stmt)
    delivery = result.scalar_one_or_none()

    if not delivery:
        raise HTTPException(status_code=404, detail="Delivery not found")

    return DeliveryResponse(
        id=delivery.id,
        export_id=delivery.export_id,
        run_id=delivery.run_id,
        mapper_name=delivery.mapper_name,
        mapper_version=delivery.mapper_version,
        status=delivery.status,
        attempts=delivery.attempts,
        last_error=delivery.last_error,
        response_body=delivery.response_body,
        created_at=delivery.created_at,
        updated_at=delivery.updated_at,
    )


