"""Ingestion service for question imports (TICKET 1) and Excel/CSV parsing."""
import json
from typing import Any, Dict, List, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.logging import get_logger
from app.db.models import Campaign, Topic, Persona, Question
from app.domain.schemas import QuestionImportItem

logger = get_logger(__name__)


class IngestService:
    """Service for ingesting questions from agent or files."""

    def __init__(self, session: AsyncSession):
        """Initialize ingest service.
        
        Args:
            session: Database session
        """
        self.session = session

    async def import_questions(
        self,
        items: List[QuestionImportItem],
    ) -> Tuple[int, int, List[str]]:
        """Import questions from agent (TICKET 1).
        
        Large imports (≥140 items) should parse in <2s.
        Idempotent - re-POSTing same batch doesn't duplicate rows.
        
        Args:
            items: List of question import items
            
        Returns:
            (imported_count, skipped_count, errors)
        """
        logger.info("import_start", item_count=len(items))
        
        imported = 0
        skipped = 0
        errors = []

        # Track entities by key to avoid duplicates within batch
        campaigns_cache: Dict[str, Campaign] = {}
        topics_cache: Dict[str, Topic] = {}
        personas_cache: Dict[str, Persona] = {}

        for idx, item in enumerate(items):
            try:
                # 1. Upsert campaign
                campaign = await self._upsert_campaign(
                    item.campaign,
                    campaigns_cache
                )

                # 2. Upsert topic
                topic_data = item.topic
                topic = await self._upsert_topic(
                    campaign.id,
                    topic_data.get("title", f"Topic {idx}"),
                    topic_data.get("description"),
                    topics_cache
                )

                # 3. Upsert persona
                persona_data = item.persona
                persona = await self._upsert_persona(
                    persona_data,
                    personas_cache
                )

                # 4. Insert question (enforce uniqueness per campaign+topic)
                question_data = item.question
                question_id = question_data.get("id", f"Q_{idx}")
                
                # Check if question already exists
                existing = await self._get_question_by_external_id(
                    topic.id,
                    question_id
                )
                
                if existing:
                    logger.debug(
                        "question_skipped_duplicate",
                        question_id=question_id,
                        topic_id=topic.id
                    )
                    skipped += 1
                    continue

                # Create question
                question = Question(
                    topic_id=topic.id,
                    persona_id=persona.id,
                    text=question_data.get("text", ""),
                    metadata_json=json.dumps({
                        "external_id": question_id,
                        **question_data.get("metadata", {}),
                        "provider_overrides": item.provider_overrides or {},
                    })
                )
                self.session.add(question)
                imported += 1

            except Exception as e:
                error_msg = f"Item {idx}: {str(e)}"
                errors.append(error_msg)
                logger.error("import_item_failed", idx=idx, error=str(e))

        # Commit all changes
        await self.session.commit()

        logger.info(
            "import_complete",
            imported=imported,
            skipped=skipped,
            errors=len(errors)
        )

        return imported, skipped, errors

    async def _upsert_campaign(
        self,
        name: str,
        cache: Dict[str, Campaign],
    ) -> Campaign:
        """Upsert campaign by name.
        
        Args:
            name: Campaign name
            cache: In-memory cache
            
        Returns:
            Campaign instance
        """
        # Check cache
        if name in cache:
            return cache[name]

        # Check DB
        stmt = select(Campaign).where(Campaign.name == name)
        result = await self.session.execute(stmt)
        campaign = result.scalar_one_or_none()

        if not campaign:
            campaign = Campaign(name=name)
            self.session.add(campaign)
            await self.session.flush()  # Get ID
            logger.debug("campaign_created", name=name, id=campaign.id)

        cache[name] = campaign
        return campaign

    async def _upsert_topic(
        self,
        campaign_id: str,
        title: str,
        description: str | None,
        cache: Dict[str, Topic],
    ) -> Topic:
        """Upsert topic by campaign + title.
        
        Args:
            campaign_id: Campaign ID
            title: Topic title
            description: Topic description
            cache: In-memory cache
            
        Returns:
            Topic instance
        """
        cache_key = f"{campaign_id}:{title}"

        # Check cache
        if cache_key in cache:
            return cache[cache_key]

        # Check DB
        stmt = select(Topic).where(
            Topic.campaign_id == campaign_id,
            Topic.title == title
        )
        result = await self.session.execute(stmt)
        topic = result.scalar_one_or_none()

        if not topic:
            topic = Topic(
                campaign_id=campaign_id,
                title=title,
                description=description
            )
            self.session.add(topic)
            await self.session.flush()
            logger.debug("topic_created", title=title, id=topic.id)

        cache[cache_key] = topic
        return topic

    async def _upsert_persona(
        self,
        data: Dict[str, Any],
        cache: Dict[str, Persona],
    ) -> Persona:
        """Upsert persona by name.
        
        Args:
            data: Persona data
            cache: In-memory cache
            
        Returns:
            Persona instance
        """
        name = data.get("name", "Default")
        
        # Check cache
        if name in cache:
            return cache[name]

        # Check DB
        stmt = select(Persona).where(Persona.name == name)
        result = await self.session.execute(stmt)
        persona = result.scalar_one_or_none()

        if not persona:
            persona = Persona(
                name=name,
                role=data.get("role"),
                domain=data.get("domain"),
                locale=data.get("locale"),
                tone=data.get("tone"),
                extra_json=json.dumps(data.get("extra_json", {}))
            )
            self.session.add(persona)
            await self.session.flush()
            logger.debug("persona_created", name=name, id=persona.id)

        cache[name] = persona
        return persona

    async def _get_question_by_external_id(
        self,
        topic_id: str,
        external_id: str,
    ) -> Question | None:
        """Get question by topic + external ID.
        
        Args:
            topic_id: Topic ID
            external_id: External question ID
            
        Returns:
            Question if found
        """
        # Query questions with metadata containing external_id
        stmt = select(Question).where(Question.topic_id == topic_id)
        result = await self.session.execute(stmt)
        questions = result.scalars().all()

        for q in questions:
            try:
                metadata = json.loads(q.metadata_json) if q.metadata_json else {}
                if metadata.get("external_id") == external_id:
                    return q
            except json.JSONDecodeError:
                continue

        return None


