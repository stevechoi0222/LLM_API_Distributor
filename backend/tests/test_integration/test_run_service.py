"""Test run service and orchestration."""
import json
import pytest
from sqlalchemy import select
from app.domain.services.run_service import RunService
from app.domain.schemas import ProviderConfig
from app.db.models import Run, RunItem, Campaign, Topic, Persona, Question


@pytest.mark.integration
class TestRunService:
    """Test run orchestration service."""

    @pytest.mark.asyncio
    async def test_create_run(self, db_session):
        """Test creating a run."""
        # Create campaign first
        campaign = Campaign(name="Test Campaign")
        db_session.add(campaign)
        await db_session.commit()
        
        service = RunService(db_session)
        providers = [ProviderConfig(name="openai", model="gpt-4o-mini")]
        
        run = await service.create_run(
            campaign_id=campaign.id,
            providers=providers,
            prompt_version="v1",
            label="Test Run"
        )
        
        assert run.id is not None
        assert run.campaign_id == campaign.id
        assert run.status == "pending"
        assert run.label == "Test Run"

    @pytest.mark.asyncio
    async def test_materialize_run_items(self, db_session):
        """Test materializing run items from questions."""
        # Setup: campaign, topic, persona, questions
        campaign = Campaign(name="Test")
        db_session.add(campaign)
        await db_session.flush()
        
        topic = Topic(campaign_id=campaign.id, title="Topic 1")
        db_session.add(topic)
        await db_session.flush()
        
        persona = Persona(name="Persona 1")
        db_session.add(persona)
        await db_session.flush()
        
        # Add 3 questions
        for i in range(3):
            question = Question(
                topic_id=topic.id,
                persona_id=persona.id,
                text=f"Question {i}?",
                metadata_json=json.dumps({"external_id": f"Q{i}"})
            )
            db_session.add(question)
        
        await db_session.commit()
        
        # Create run
        service = RunService(db_session)
        providers = [ProviderConfig(name="openai", model="gpt-4o-mini")]
        run = await service.create_run(
            campaign_id=campaign.id,
            providers=providers
        )
        
        # Materialize items
        items_created = await service.materialize_run_items(run)
        
        assert items_created == 3  # 3 questions × 1 provider
        
        # Verify in DB
        stmt = select(RunItem).where(RunItem.run_id == run.id)
        result = await db_session.execute(stmt)
        run_items = result.scalars().all()
        
        assert len(run_items) == 3
        for item in run_items:
            assert item.status == "pending"
            assert item.idempotency_key is not None

    @pytest.mark.asyncio
    async def test_materialize_multiple_providers(self, db_session):
        """Test materializing with multiple providers creates items for each."""
        # Setup minimal data
        campaign = Campaign(name="Test")
        db_session.add(campaign)
        await db_session.flush()
        
        topic = Topic(campaign_id=campaign.id, title="Topic")
        persona = Persona(name="Persona")
        db_session.add_all([topic, persona])
        await db_session.flush()
        
        question = Question(
            topic_id=topic.id,
            persona_id=persona.id,
            text="Test?",
            metadata_json=json.dumps({"external_id": "Q1"})
        )
        db_session.add(question)
        await db_session.commit()
        
        # Create run with 2 providers
        service = RunService(db_session)
        providers = [
            ProviderConfig(name="openai", model="gpt-4o-mini"),
            ProviderConfig(name="openai", model="gpt-4o"),  # Different model
        ]
        run = await service.create_run(campaign_id=campaign.id, providers=providers)
        
        items_created = await service.materialize_run_items(run)
        
        assert items_created == 2  # 1 question × 2 providers

    @pytest.mark.asyncio
    async def test_get_run_status_counts(self, db_session):
        """Test getting status counts for a run."""
        # Create run with items
        campaign = Campaign(name="Test")
        db_session.add(campaign)
        await db_session.flush()
        
        run = Run(
            campaign_id=campaign.id,
            provider_settings_json=json.dumps({"providers": []}),
            status="running"
        )
        db_session.add(run)
        await db_session.flush()
        
        # Add run items with different statuses
        items = [
            RunItem(run_id=run.id, question_id="q1", idempotency_key="key1", status="pending"),
            RunItem(run_id=run.id, question_id="q2", idempotency_key="key2", status="succeeded"),
            RunItem(run_id=run.id, question_id="q3", idempotency_key="key3", status="failed"),
        ]
        db_session.add_all(items)
        await db_session.commit()
        
        service = RunService(db_session)
        counts = await service.get_run_status_counts(run.id)
        
        assert counts.total == 3
        assert counts.pending == 1
        assert counts.succeeded == 1
        assert counts.failed == 1

