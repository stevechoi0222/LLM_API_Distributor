"""SQLAlchemy declarative base."""
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings


class Base(DeclarativeBase):
    """Base class for all database models."""
    
    # Schema will be set via metadata
    __table_args__ = {"schema": settings.db_schema}


