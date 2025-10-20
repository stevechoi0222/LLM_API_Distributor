"""Test question import service (TICKET 1)."""
import time
import pytest
from sqlalchemy import select
from app.domain.services.ingest_service import IngestService
from app.domain.schemas import QuestionImportItem
from app.db.models import Campaign, Topic, Persona, Question


@pytest.mark.integration
@pytest.mark.ticket1
class TestQuestionImport:
    """Test question import from agent (TICKET 1)."""

    @pytest.mark.asyncio
    async def test_import_single_question(self, db_session):
        """Test importing a single question."""
        service = IngestService(db_session)
        
        items = [
            QuestionImportItem(
                campaign="Test Campaign",
                topic={"title": "Battery Life"},
                persona={"name": "Tech Reviewer", "role": "Reviewer"},
                question={"id": "Q001", "text": "How long does battery last?"}
            )
        ]
        
        imported, skipped, errors = await service.import_questions(items)
        
        assert imported == 1
        assert skipped == 0
        assert len(errors) == 0
        
        # Verify in DB
        stmt = select(Question)
        result = await db_session.execute(stmt)
        questions = result.scalars().all()
        assert len(questions) == 1

    @pytest.mark.asyncio
    async def test_import_140_questions_performance(self, db_session):
        """Test that importing 140 questions completes in <2s (TICKET 1 acceptance)."""
        service = IngestService(db_session)
        
        # Generate 140 test items
        items = []
        for i in range(140):
            items.append(
                QuestionImportItem(
                    campaign="Performance Test",
                    topic={"title": f"Topic {i // 10}"},
                    persona={"name": f"Persona {i % 5}", "role": "Tester"},
                    question={"id": f"Q{i:03d}", "text": f"Question {i}?"}
                )
            )
        
        start = time.time()
        imported, skipped, errors = await service.import_questions(items)
        duration = time.time() - start
        
        assert imported == 140
        assert skipped == 0
        assert len(errors) == 0
        assert duration < 2.0  # TICKET 1 requirement: <2s for ≥140 items

    @pytest.mark.asyncio
    async def test_import_idempotent(self, db_session):
        """Test that re-importing same questions skips duplicates (TICKET 1)."""
        service = IngestService(db_session)
        
        items = [
            QuestionImportItem(
                campaign="Test Campaign",
                topic={"title": "Battery"},
                persona={"name": "Reviewer"},
                question={"id": "Q001", "text": "Test question?"}
            )
        ]
        
        # First import
        imported1, skipped1, errors1 = await service.import_questions(items)
        assert imported1 == 1
        assert skipped1 == 0
        
        # Second import (same data)
        imported2, skipped2, errors2 = await service.import_questions(items)
        assert imported2 == 0
        assert skipped2 == 1  # Should skip duplicate
        
        # Verify only one question in DB
        stmt = select(Question)
        result = await db_session.execute(stmt)
        questions = result.scalars().all()
        assert len(questions) == 1

    @pytest.mark.asyncio
    async def test_import_upserts_campaign(self, db_session):
        """Test that import creates or reuses campaign."""
        service = IngestService(db_session)
        
        items = [
            QuestionImportItem(
                campaign="Shared Campaign",
                topic={"title": "Topic 1"},
                persona={"name": "P1"},
                question={"id": "Q1", "text": "Q1?"}
            ),
            QuestionImportItem(
                campaign="Shared Campaign",
                topic={"title": "Topic 2"},
                persona={"name": "P2"},
                question={"id": "Q2", "text": "Q2?"}
            ),
        ]
        
        await service.import_questions(items)
        
        # Should have only one campaign
        stmt = select(Campaign)
        result = await db_session.execute(stmt)
        campaigns = result.scalars().all()
        assert len(campaigns) == 1
        assert campaigns[0].name == "Shared Campaign"

    @pytest.mark.asyncio
    async def test_import_with_provider_overrides(self, db_session):
        """Test importing with provider overrides."""
        service = IngestService(db_session)
        
        items = [
            QuestionImportItem(
                campaign="Test",
                topic={"title": "Test"},
                persona={"name": "Test"},
                question={"id": "Q1", "text": "Test?"},
                provider_overrides={"temperature": 0.7}
            )
        ]
        
        imported, _, _ = await service.import_questions(items)
        assert imported == 1
        
        # Verify metadata stored
        stmt = select(Question)
        result = await db_session.execute(stmt)
        question = result.scalar_one()
        
        import json
        metadata = json.loads(question.metadata_json)
        assert metadata["provider_overrides"]["temperature"] == 0.7

    @pytest.mark.asyncio
    async def test_import_error_handling(self, db_session):
        """Test that import handles errors gracefully."""
        service = IngestService(db_session)
        
        items = [
            QuestionImportItem(
                campaign="Test",
                topic={},  # Missing title - should cause error
                persona={"name": "Test"},
                question={"id": "Q1", "text": "Test?"}
            )
        ]
        
        imported, skipped, errors = await service.import_questions(items)
        
        assert imported == 0
        assert len(errors) > 0

