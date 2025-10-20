"""Campaign, topic, and persona management endpoints."""
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_authenticated_session
from app.core.logging import get_logger
from app.db.models import Campaign, Topic, Persona
from app.domain.schemas import (
    CampaignCreate,
    CampaignResponse,
    TopicCreate,
    TopicResponse,
    PersonaCreate,
    PersonaResponse,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1", tags=["campaigns"])


@router.post("/campaigns", response_model=CampaignResponse, status_code=201)
async def create_campaign(
    data: CampaignCreate,
    session: AsyncSession = Depends(get_authenticated_session),
):
    """Create a new campaign."""
    campaign = Campaign(
        name=data.name,
        product_name=data.product_name,
    )
    session.add(campaign)
    await session.commit()
    await session.refresh(campaign)

    logger.info("campaign_created", campaign_id=campaign.id, name=campaign.name)

    return campaign


@router.get("/campaigns/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(
    campaign_id: str,
    session: AsyncSession = Depends(get_authenticated_session),
):
    """Get campaign by ID."""
    stmt = select(Campaign).where(Campaign.id == campaign_id)
    result = await session.execute(stmt)
    campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    return campaign


@router.post("/campaigns/{campaign_id}/topics", response_model=TopicResponse, status_code=201)
async def create_topic(
    campaign_id: str,
    data: TopicCreate,
    session: AsyncSession = Depends(get_authenticated_session),
):
    """Create topic for a campaign."""
    # Verify campaign exists
    stmt = select(Campaign).where(Campaign.id == campaign_id)
    result = await session.execute(stmt)
    campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    topic = Topic(
        campaign_id=campaign_id,
        title=data.title,
        description=data.description,
    )
    session.add(topic)
    await session.commit()
    await session.refresh(topic)

    logger.info("topic_created", topic_id=topic.id, campaign_id=campaign_id)

    return topic


@router.post("/personas", response_model=PersonaResponse, status_code=201)
async def create_persona(
    data: PersonaCreate,
    session: AsyncSession = Depends(get_authenticated_session),
):
    """Create a new persona."""
    import json
    
    persona = Persona(
        name=data.name,
        role=data.role,
        domain=data.domain,
        locale=data.locale,
        tone=data.tone,
        extra_json=json.dumps(data.extra_json) if data.extra_json else None,
    )
    session.add(persona)
    await session.commit()
    await session.refresh(persona)

    logger.info("persona_created", persona_id=persona.id, name=persona.name)

    return persona


@router.get("/personas", response_model=List[PersonaResponse])
async def list_personas(
    limit: int = 100,
    offset: int = 0,
    session: AsyncSession = Depends(get_authenticated_session),
):
    """List all personas."""
    stmt = select(Persona).limit(limit).offset(offset)
    result = await session.execute(stmt)
    personas = result.scalars().all()

    return personas


