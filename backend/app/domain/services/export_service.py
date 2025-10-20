"""Export service for results and deliveries (TICKET 5)."""
import json
import os
from typing import Any, Dict, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.logging import get_logger
from app.db.models import Export, Run, RunItem, Response, Delivery
from app.exporters.csv_exporter import CSVExporter
from app.exporters.xlsx_exporter import XLSXExporter
from app.exporters.jsonl_exporter import JSONLExporter

logger = get_logger(__name__)


class ExportService:
    """Service for exporting run results."""

    def __init__(self, session: AsyncSession):
        """Initialize export service.
        
        Args:
            session: Database session
        """
        self.session = session
        self.exporters = {
            "csv": CSVExporter(),
            "xlsx": XLSXExporter(),
            "jsonl": JSONLExporter(),
        }

    async def create_export(
        self,
        run_id: str,
        format: str,
        mapper_name: str | None = None,
        mapper_version: str = "v1",
        config: Dict[str, Any] | None = None,
    ) -> Export:
        """Create export job.
        
        Args:
            run_id: Run ID
            format: Export format (csv, xlsx, jsonl)
            mapper_name: Optional mapper for partner API
            mapper_version: Mapper version (TICKET 7)
            config: Mapper configuration
            
        Returns:
            Created export
        """
        export = Export(
            run_id=run_id,
            format=format,
            mapper_name=mapper_name,
            mapper_version=mapper_version,
            config_json=json.dumps(config or {}),
            status="pending",
        )
        self.session.add(export)
        await self.session.commit()

        logger.info(
            "export_created",
            export_id=export.id,
            run_id=run_id,
            format=format,
            mapper=mapper_name
        )

        return export

    async def get_run_results_for_export(
        self,
        run_id: str,
    ) -> List[Dict[str, Any]]:
        """Get all run results for export.
        
        Args:
            run_id: Run ID
            
        Returns:
            List of result dictionaries
        """
        # Get run items with responses
        stmt = (
            select(RunItem, Response)
            .join(Response, RunItem.id == Response.run_item_id, isouter=True)
            .where(RunItem.run_id == run_id)
            .order_by(RunItem.created_at)
        )
        result = await self.session.execute(stmt)
        rows = result.all()

        # Format results
        results = []
        for run_item, response in rows:
            # Parse metadata
            metadata = {}
            try:
                if run_item.question.metadata_json:
                    metadata = json.loads(run_item.question.metadata_json)
            except json.JSONDecodeError:
                pass

            # Parse response data
            response_data = {}
            if response and response.response_json:
                try:
                    response_data = json.loads(response.response_json)
                except json.JSONDecodeError:
                    response_data = {"answer": response.text or ""}

            result_dict = {
                "run_id": run_id,
                "run_item_id": run_item.id,
                "question_id": run_item.question_id,
                "question_text": run_item.question.text,
                "persona_name": run_item.question.persona.name,
                "persona_role": run_item.question.persona.role,
                "persona_locale": run_item.question.persona.locale,
                "topic_title": run_item.question.topic.title,
                "status": run_item.status,
                "attempt_count": run_item.attempt_count,
                "last_error": run_item.last_error,
            }

            if response:
                result_dict.update({
                    "provider": response.provider,
                    "model": response.model,
                    "prompt_version": response.prompt_version,
                    "response": response_data,
                    "answer": response_data.get("answer", response.text or ""),
                    "citations": response_data.get("citations", []),
                    "token_usage": json.loads(response.token_usage_json) if response.token_usage_json else {},
                    "latency_ms": response.latency_ms,
                    "cost_cents": float(response.cost_cents) if response.cost_cents else 0.0,
                })

            results.append(result_dict)

        return results

    async def export_to_file(
        self,
        export_id: str,
        output_dir: str = "artefacts",
    ) -> str:
        """Execute export to file.
        
        Args:
            export_id: Export ID
            output_dir: Output directory
            
        Returns:
            File path
        """
        # Get export
        stmt = select(Export).where(Export.id == export_id)
        result = await self.session.execute(stmt)
        export = result.scalar_one_or_none()

        if not export:
            raise ValueError(f"Export {export_id} not found")

        # Update status
        export.status = "processing"
        await self.session.commit()

        try:
            # Get results
            results = await self.get_run_results_for_export(export.run_id)

            # Get exporter
            exporter = self.exporters.get(export.format)
            if not exporter:
                raise ValueError(f"Unknown export format: {export.format}")

            # Generate filename
            os.makedirs(output_dir, exist_ok=True)
            filename = f"run_{export.run_id}_{export.id}.{export.format}"
            output_path = os.path.join(output_dir, filename)

            # Export
            file_path = await exporter.export(results, output_path)

            # Update export
            export.file_url = file_path
            export.status = "completed"
            await self.session.commit()

            logger.info(
                "export_completed",
                export_id=export_id,
                file_path=file_path,
                result_count=len(results)
            )

            return file_path

        except Exception as e:
            export.status = "failed"
            await self.session.commit()
            logger.error("export_failed", export_id=export_id, error=str(e))
            raise

    async def create_delivery(
        self,
        export_id: str,
        run_id: str,
        mapper_name: str,
        payload: Dict[str, Any],
    ) -> Delivery:
        """Create delivery for partner API (TICKET 5).
        
        Args:
            export_id: Export ID
            run_id: Run ID
            mapper_name: Mapper name
            payload: Mapped payload
            
        Returns:
            Created delivery
        """
        delivery = Delivery(
            export_id=export_id,
            run_id=run_id,
            mapper_name=mapper_name,
            payload_json=json.dumps(payload),
            status="pending",
        )
        self.session.add(delivery)
        await self.session.commit()

        logger.info(
            "delivery_created",
            delivery_id=delivery.id,
            export_id=export_id,
            mapper=mapper_name
        )

        return delivery


