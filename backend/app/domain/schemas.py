"""Pydantic schemas for API validation."""
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


# ============================================================================
# Common/Base Schemas
# ============================================================================

class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    database: str
    redis: str
    timestamp: datetime


# ============================================================================
# Campaign, Topic, Persona Schemas
# ============================================================================

class CampaignCreate(BaseModel):
    """Create campaign request."""
    name: str = Field(..., min_length=1, max_length=255)
    product_name: Optional[str] = Field(None, max_length=255)


class CampaignResponse(BaseModel):
    """Campaign response."""
    id: str
    name: str
    product_name: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class TopicCreate(BaseModel):
    """Create topic request."""
    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = None


class TopicResponse(BaseModel):
    """Topic response."""
    id: str
    campaign_id: str
    title: str
    description: Optional[str]

    class Config:
        from_attributes = True


class PersonaCreate(BaseModel):
    """Create persona request."""
    name: str = Field(..., min_length=1, max_length=255)
    role: Optional[str] = Field(None, max_length=255)
    domain: Optional[str] = Field(None, max_length=255)
    locale: Optional[str] = Field(None, max_length=10)
    tone: Optional[str] = Field(None, max_length=100)
    extra_json: Optional[Dict[str, Any]] = None


class PersonaResponse(BaseModel):
    """Persona response."""
    id: str
    name: str
    role: Optional[str]
    domain: Optional[str]
    locale: Optional[str]
    tone: Optional[str]
    extra_json: Optional[Dict[str, Any]]

    class Config:
        from_attributes = True


# ============================================================================
# Question Import Schemas (TICKET 1)
# ============================================================================

class QuestionImportItem(BaseModel):
    """Single question import item from agent."""
    campaign: str = Field(..., description="Campaign name")
    topic: Dict[str, Any] = Field(..., description="Topic data (title, description)")
    persona: Dict[str, Any] = Field(..., description="Persona data")
    question: Dict[str, Any] = Field(..., description="Question data (id, text, metadata)")
    provider_overrides: Optional[Dict[str, Any]] = Field(
        None, description="Provider-specific overrides"
    )


class QuestionImportRequest(BaseModel):
    """Bulk question import request (TICKET 1)."""
    items: List[QuestionImportItem] = Field(..., min_length=1)


class QuestionImportResponse(BaseModel):
    """Question import response."""
    imported: int = Field(..., description="Number of successfully imported items")
    skipped: int = Field(..., description="Number of skipped items")
    errors: List[str] = Field(default_factory=list, description="Error messages")


# ============================================================================
# Run Schemas
# ============================================================================

class ProviderConfig(BaseModel):
    """Provider configuration for a run."""
    name: str = Field(..., description="Provider name (openai, gemini, perplexity)")
    model: str = Field(..., description="Model name")
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    top_p: Optional[float] = Field(None, ge=0.0, le=1.0)
    max_tokens: Optional[int] = Field(None, gt=0)
    allow_sampling: bool = Field(
        default=False, description="Allow non-deterministic sampling (TICKET 6)"
    )

    @field_validator("name")
    @classmethod
    def validate_provider_name(cls, v: str) -> str:
        """Validate provider name is lowercase."""
        return v.lower()


class RunCreate(BaseModel):
    """Create run request."""
    campaign_id: str
    label: Optional[str] = Field(None, max_length=255)
    providers: List[ProviderConfig] = Field(..., min_length=1)
    prompt_version: str = Field(default="v1", description="Prompt template version")
    concurrency: int = Field(default=10, gt=0, le=100, description="Worker concurrency")
    rate_limits: Optional[Dict[str, Dict[str, int]]] = Field(
        None, description="Provider rate limits (qps, burst)"
    )


class RunItemSummary(BaseModel):
    """Run item summary for status endpoint."""
    id: str
    question_id: str
    status: str
    attempt_count: int
    last_error: Optional[str]


class RunStatusCounts(BaseModel):
    """Run status counts."""
    total: int
    pending: int
    running: int
    succeeded: int
    failed: int
    skipped: int


class RunResponse(BaseModel):
    """Run response with status and cost."""
    id: str
    campaign_id: str
    label: Optional[str]
    status: str
    cost_cents: Optional[float] = Field(None, description="Total cost in cents (TICKET 3)")
    counts: RunStatusCounts
    created_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    errors: List[Dict[str, str]] = Field(default_factory=list)

    class Config:
        from_attributes = True


class RunItemResponse(BaseModel):
    """Individual run item response."""
    id: str
    run_id: str
    question_id: str
    status: str
    attempt_count: int
    last_error: Optional[str]
    created_at: datetime
    updated_at: datetime
    response: Optional[Dict[str, Any]] = None  # Include response data if available

    class Config:
        from_attributes = True


# ============================================================================
# Response Schemas (TICKET 2 - JSON validated)
# ============================================================================

class ResponseSchema(BaseModel):
    """Expected JSON schema from providers (TICKET 2)."""
    answer: str = Field(..., description="Main answer text")
    citations: List[str] = Field(default_factory=list, description="Citation URLs")
    meta: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


# ============================================================================
# Export Schemas (TICKET 7 - Mapper versioning)
# ============================================================================

class ExportCreate(BaseModel):
    """Create export request."""
    run_id: str
    format: str = Field(..., pattern="^(csv|xlsx|jsonl)$")
    mapper_name: Optional[str] = Field(None, description="Partner API mapper name")
    mapper_version: str = Field(default="v1", description="Mapper version (TICKET 7)")
    config: Optional[Dict[str, Any]] = Field(None, description="Mapper configuration")


class ExportResponse(BaseModel):
    """Export response."""
    id: str
    run_id: str
    format: str
    mapper_name: Optional[str]
    mapper_version: str
    status: str
    file_url: Optional[str]
    created_at: datetime
    deliveries_created: Optional[int] = Field(
        None, description="Number of deliveries created (TICKET 5)"
    )
    delivery_stats: Optional[Dict[str, int]] = Field(
        None, description="Delivery counts by status (TICKET 5)"
    )
    sample_failures: Optional[List[Dict[str, Any]]] = Field(
        None, description="Sample of failed deliveries (up to 5)"
    )

    class Config:
        from_attributes = True


# ============================================================================
# Delivery Schemas (TICKET 5)
# ============================================================================

class DeliveryResponse(BaseModel):
    """Delivery response."""
    id: str
    export_id: str
    run_id: str
    mapper_name: str
    mapper_version: str
    status: str
    attempts: int
    last_error: Optional[str]
    response_body: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# File Upload Schemas
# ============================================================================

class FileUploadResponse(BaseModel):
    """File upload response."""
    id: str
    type: str
    uploaded_at: datetime
    parsed_summary: Optional[Dict[str, Any]]


# ============================================================================
# Pagination
# ============================================================================

class PaginatedResponse(BaseModel):
    """Generic paginated response."""
    items: List[Any]
    total: int
    limit: int
    offset: int
    has_more: bool


class RunItemsResponse(PaginatedResponse):
    """Paginated run items response."""
    items: List[RunItemResponse]


# ============================================================================
# Error Response
# ============================================================================

class ErrorResponse(BaseModel):
    """Error response."""
    detail: str
    error_code: Optional[str] = None


