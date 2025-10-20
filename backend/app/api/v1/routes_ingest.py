"""Ingestion endpoints for question imports (TICKET 1)."""
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_authenticated_session
from app.core.logging import get_logger
from app.domain.schemas import (
    QuestionImportRequest,
    QuestionImportResponse,
)
from app.domain.services.ingest_service import IngestService

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1", tags=["ingest"])


@router.post("/question-sets:import", response_model=QuestionImportResponse)
async def import_questions(
    data: QuestionImportRequest,
    session: AsyncSession = Depends(get_authenticated_session),
):
    """Import questions from agent (TICKET 1).
    
    Accepts JSONL or JSON array with campaign, topic, persona, question data.
    Handles large imports (≥140 items) efficiently.
    Idempotent - re-POSTing same batch won't duplicate rows.
    """
    logger.info("import_request", item_count=len(data.items))

    # Create ingest service
    service = IngestService(session)

    # Import questions
    imported, skipped, errors = await service.import_questions(data.items)

    response = QuestionImportResponse(
        imported=imported,
        skipped=skipped,
        errors=errors,
    )

    logger.info(
        "import_completed",
        imported=imported,
        skipped=skipped,
        errors=len(errors)
    )

    return response


