"""Compatibility mode - minimal 2-table schema for restricted environments."""
import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy import Column, DateTime, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.logging import get_logger
from app.db.base import Base

logger = get_logger(__name__)


class Event(Base):
    """Generic event log for compat mode."""

    __tablename__ = "events"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    kind = Column(String(100), nullable=False)  # question_imported, run_created, etc.
    occurred_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    payload = Column(Text, nullable=False)  # JSON string

    __table_args__ = {"schema": settings.db_schema}


class Result(Base):
    """Generic result storage for compat mode."""

    __tablename__ = "results"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id = Column(String(100), nullable=False, index=True)
    item_id = Column(String(100), nullable=False, unique=True)  # Idempotency key
    status = Column(String(50), nullable=False)
    response = Column(Text, nullable=True)  # JSON response
    meta = Column(Text, nullable=True)  # JSON metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = {"schema": settings.db_schema}


class CompatRepository:
    """Repository for compat mode operations."""

    def __init__(self, session: AsyncSession):
        """Initialize repository.
        
        Args:
            session: Async SQLAlchemy session
        """
        self.session = session

    async def log_event(self, kind: str, payload: Dict[str, Any]) -> str:
        """Log an event.
        
        Args:
            kind: Event kind
            payload: Event payload
            
        Returns:
            Event ID
        """
        event = Event(
            kind=kind,
            payload=json.dumps(payload),
        )
        self.session.add(event)
        await self.session.commit()
        
        logger.debug("compat_event_logged", kind=kind, event_id=event.id)
        return event.id

    async def store_result(
        self,
        run_id: str,
        item_id: str,
        status: str,
        response: Optional[Dict[str, Any]] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Store a result.
        
        Args:
            run_id: Run ID
            item_id: Item ID (idempotency key)
            status: Status
            response: Response data
            meta: Metadata
            
        Returns:
            Result ID
        """
        result = Result(
            run_id=run_id,
            item_id=item_id,
            status=status,
            response=json.dumps(response) if response else None,
            meta=json.dumps(meta) if meta else None,
        )
        self.session.add(result)
        await self.session.commit()
        
        logger.debug("compat_result_stored", run_id=run_id, item_id=item_id[:16])
        return result.id

    async def get_result(self, item_id: str) -> Optional[Dict[str, Any]]:
        """Get a result by item ID.
        
        Args:
            item_id: Item ID
            
        Returns:
            Result data if found
        """
        stmt = select(Result).where(Result.item_id == item_id)
        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()
        
        if not row:
            return None
        
        return {
            "id": row.id,
            "run_id": row.run_id,
            "item_id": row.item_id,
            "status": row.status,
            "response": json.loads(row.response) if row.response else None,
            "meta": json.loads(row.meta) if row.meta else None,
            "created_at": row.created_at.isoformat(),
        }

    async def get_run_results(
        self,
        run_id: str,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get all results for a run.
        
        Args:
            run_id: Run ID
            limit: Result limit
            offset: Result offset
            
        Returns:
            List of result data
        """
        stmt = (
            select(Result)
            .where(Result.run_id == run_id)
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        rows = result.scalars().all()
        
        return [
            {
                "id": row.id,
                "run_id": row.run_id,
                "item_id": row.item_id,
                "status": row.status,
                "response": json.loads(row.response) if row.response else None,
                "meta": json.loads(row.meta) if row.meta else None,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]

    async def update_result_status(
        self,
        item_id: str,
        status: str,
        response: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        """Update result status.
        
        Args:
            item_id: Item ID
            status: New status
            response: Response data
            error: Error message
        """
        stmt = select(Result).where(Result.item_id == item_id)
        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()
        
        if row:
            row.status = status
            if response:
                row.response = json.dumps(response)
            if error:
                meta = json.loads(row.meta) if row.meta else {}
                meta["error"] = error
                row.meta = json.dumps(meta)
            
            await self.session.commit()
            logger.debug("compat_result_updated", item_id=item_id[:16], status=status)


