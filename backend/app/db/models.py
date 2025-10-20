"""SQLAlchemy database models."""
import uuid
from datetime import datetime
from typing import Any, Dict
from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from app.core.config import settings
from app.db.base import Base


def get_json_type():
    """Get JSON column type based on USE_JSONB setting."""
    return JSONB if settings.use_jsonb else Text


def generate_uuid() -> str:
    """Generate UUID as string (app-side, no DB extension needed)."""
    return str(uuid.uuid4())


class Campaign(Base):
    """Campaign - top level entity for a product/topic set."""

    __tablename__ = "campaigns"

    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    product_name = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    topics = relationship("Topic", back_populates="campaign", cascade="all, delete-orphan")
    runs = relationship("Run", back_populates="campaign", cascade="all, delete-orphan")


class Topic(Base):
    """Topic within a campaign."""

    __tablename__ = "topics"

    id = Column(String, primary_key=True, default=generate_uuid)
    campaign_id = Column(String, ForeignKey(f"{settings.db_schema}.campaigns.id"), nullable=False)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)

    # Relationships
    campaign = relationship("Campaign", back_populates="topics")
    questions = relationship("Question", back_populates="topic", cascade="all, delete-orphan")


class Persona(Base):
    """Persona - user profile for questions."""

    __tablename__ = "personas"

    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    role = Column(String(255), nullable=True)
    domain = Column(String(255), nullable=True)
    locale = Column(String(10), nullable=True)
    tone = Column(String(100), nullable=True)
    extra_json = Column(get_json_type(), nullable=True)  # Additional persona fields

    # Relationships
    questions = relationship("Question", back_populates="persona", cascade="all, delete-orphan")


class Question(Base):
    """Question paired with a persona and topic."""

    __tablename__ = "questions"

    id = Column(String, primary_key=True, default=generate_uuid)
    topic_id = Column(String, ForeignKey(f"{settings.db_schema}.topics.id"), nullable=False)
    persona_id = Column(String, ForeignKey(f"{settings.db_schema}.personas.id"), nullable=False)
    text = Column(Text, nullable=False)
    metadata_json = Column(get_json_type(), nullable=True)  # Tags, variant, etc.

    # Relationships
    topic = relationship("Topic", back_populates="questions")
    persona = relationship("Persona", back_populates="questions")
    run_items = relationship("RunItem", back_populates="question", cascade="all, delete-orphan")

    # Indexes
    __table_args__ = (
        Index("ix_questions_topic_id", "topic_id"),
        Index("ix_questions_persona_id", "persona_id"),
        {"schema": settings.db_schema},
    )


class Run(Base):
    """Execution run for a campaign against providers."""

    __tablename__ = "runs"

    id = Column(String, primary_key=True, default=generate_uuid)
    campaign_id = Column(String, ForeignKey(f"{settings.db_schema}.campaigns.id"), nullable=False)
    label = Column(String(255), nullable=True)
    provider_settings_json = Column(get_json_type(), nullable=False)  # Providers, models, params
    status = Column(
        String(50),
        nullable=False,
        default="pending"
    )  # pending, running, completed, failed
    cost_cents = Column(Numeric(12, 2), nullable=True, default=0)  # TICKET 3 - rollup
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)

    # Relationships
    campaign = relationship("Campaign", back_populates="runs")
    run_items = relationship("RunItem", back_populates="run", cascade="all, delete-orphan")
    exports = relationship("Export", back_populates="run", cascade="all, delete-orphan")

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'cancelled')",
            name="check_run_status"
        ),
        Index("ix_runs_campaign_id", "campaign_id"),
        Index("ix_runs_status", "status"),
        {"schema": settings.db_schema},
    )


class RunItem(Base):
    """Individual question execution within a run."""

    __tablename__ = "run_items"

    id = Column(String, primary_key=True, default=generate_uuid)
    run_id = Column(String, ForeignKey(f"{settings.db_schema}.runs.id"), nullable=False)
    question_id = Column(String, ForeignKey(f"{settings.db_schema}.questions.id"), nullable=False)
    idempotency_key = Column(String(64), nullable=False, unique=True)
    status = Column(
        String(50),
        nullable=False,
        default="pending"
    )  # pending, running, succeeded, failed
    attempt_count = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    run = relationship("Run", back_populates="run_items")
    question = relationship("Question", back_populates="run_items")
    responses = relationship("Response", back_populates="run_item", cascade="all, delete-orphan")

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed', 'skipped')",
            name="check_run_item_status"
        ),
        UniqueConstraint("idempotency_key", name="uq_run_items_idempotency_key"),
        Index("ix_run_items_run_id", "run_id"),
        Index("ix_run_items_status", "status"),
        Index("ix_run_items_question_id", "question_id"),
        {"schema": settings.db_schema},
    )


class Response(Base):
    """Provider response for a run item."""

    __tablename__ = "responses"

    id = Column(String, primary_key=True, default=generate_uuid)
    run_item_id = Column(String, ForeignKey(f"{settings.db_schema}.run_items.id"), nullable=False)
    provider = Column(String(50), nullable=False)
    model = Column(String(100), nullable=False)
    prompt_version = Column(String(50), nullable=False)
    request_json = Column(get_json_type(), nullable=False)  # Full request for reproducibility
    response_json = Column(get_json_type(), nullable=False)  # Validated JSON response (TICKET 2)
    text = Column(Text, nullable=True)  # Response text (convenience field)
    citations_json = Column(get_json_type(), nullable=True)  # Array of citation URLs
    token_usage_json = Column(get_json_type(), nullable=True)  # prompt_tokens, completion_tokens
    latency_ms = Column(Integer, nullable=True)
    cost_cents = Column(Numeric(10, 4), nullable=True)  # TICKET 3 - computed from token usage
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    run_item = relationship("RunItem", back_populates="responses")

    # Indexes
    __table_args__ = (
        Index("ix_responses_run_item_id", "run_item_id"),
        Index("ix_responses_provider", "provider"),
        {"schema": settings.db_schema},
    )


class Export(Base):
    """Export job for run results."""

    __tablename__ = "exports"

    id = Column(String, primary_key=True, default=generate_uuid)
    run_id = Column(String, ForeignKey(f"{settings.db_schema}.runs.id"), nullable=False)
    format = Column(String(50), nullable=False)  # csv, xlsx, jsonl
    mapper_name = Column(String(100), nullable=True)  # For partner API exports
    mapper_version = Column(String(50), nullable=False, default="v1")  # TICKET 7
    config_json = Column(get_json_type(), nullable=True)  # Mapper configuration
    status = Column(
        String(50),
        nullable=False,
        default="pending"
    )  # pending, processing, completed, failed
    file_url = Column(String(500), nullable=True)  # S3 URL or local path
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    run = relationship("Run", back_populates="exports")
    deliveries = relationship("Delivery", back_populates="export", cascade="all, delete-orphan")

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed')",
            name="check_export_status"
        ),
        Index("ix_exports_run_id", "run_id"),
        {"schema": settings.db_schema},
    )


class Delivery(Base):
    """Outbound delivery to partner APIs (TICKET 5)."""

    __tablename__ = "deliveries"

    id = Column(String, primary_key=True, default=generate_uuid)
    export_id = Column(String, ForeignKey(f"{settings.db_schema}.exports.id"), nullable=False)
    run_id = Column(String, nullable=False)  # Denormalized for queries
    mapper_name = Column(String(100), nullable=False)
    payload_json = Column(get_json_type(), nullable=False)  # Mapped payload for partner
    status = Column(
        String(50),
        nullable=False,
        default="pending"
    )  # pending, succeeded, failed
    attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    response_body = Column(Text, nullable=True)  # Partner API response
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    export = relationship("Export", back_populates="deliveries")

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'succeeded', 'failed')",
            name="check_delivery_status"
        ),
        Index("ix_deliveries_export_id", "export_id"),
        Index("ix_deliveries_status", "status"),
        Index("ix_deliveries_run_id", "run_id"),
        {"schema": settings.db_schema},
    )


class File(Base):
    """Uploaded file metadata."""

    __tablename__ = "files"

    id = Column(String, primary_key=True, default=generate_uuid)
    type = Column(String(50), nullable=False)  # excel, csv, jsonl
    url_or_path = Column(String(500), nullable=False)
    parsed_summary_json = Column(get_json_type(), nullable=True)  # Import summary
    uploaded_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Constraints
    __table_args__ = (
        {"schema": settings.db_schema},
    )


