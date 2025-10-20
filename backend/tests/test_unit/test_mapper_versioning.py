"""Test mapper versioning (TICKET 7)."""
import pytest
from app.exporters.mappers.example_webhook import (
    ExampleWebhookMapperV1,
    get_mapper,
    MAPPER_REGISTRY,
)


@pytest.mark.unit
@pytest.mark.ticket7
class TestMapperVersioning:
    """Test mapper versioning and registry (TICKET 7)."""

    def test_mapper_has_version(self):
        """Test that mapper has version attribute."""
        mapper = ExampleWebhookMapperV1()
        
        assert hasattr(mapper, "version")
        assert mapper.version == "v1"

    def test_get_mapper_v1(self):
        """Test getting mapper by name and version."""
        mapper = get_mapper("example_partner", version="v1")
        
        assert mapper is not None
        assert mapper.version == "v1"
        assert isinstance(mapper, ExampleWebhookMapperV1)

    def test_get_mapper_default_version(self):
        """Test getting mapper with default version."""
        mapper = get_mapper("example_partner")
        
        assert mapper is not None
        assert mapper.version == "v1"

    def test_get_mapper_unknown_name_raises(self):
        """Test that unknown mapper name raises ValueError."""
        with pytest.raises(ValueError) as exc:
            get_mapper("unknown_partner")
        
        assert "not found" in str(exc.value).lower()

    def test_get_mapper_unknown_version_raises(self):
        """Test that unknown version raises ValueError."""
        with pytest.raises(ValueError) as exc:
            get_mapper("example_partner", version="v99")
        
        assert "version" in str(exc.value).lower()
        assert "not found" in str(exc.value).lower()

    def test_mapper_registry_structure(self):
        """Test that mapper registry has correct structure."""
        assert "example_partner" in MAPPER_REGISTRY
        assert "v1" in MAPPER_REGISTRY["example_partner"]
        assert isinstance(MAPPER_REGISTRY["example_partner"]["v1"], ExampleWebhookMapperV1)

    def test_mapper_transformation(self):
        """Test that mapper transforms data correctly."""
        mapper = ExampleWebhookMapperV1()
        
        result = {
            "run_item_id": "item_123",
            "question_text": "Test question?",
            "response": {
                "answer": "Test answer",
                "citations": ["https://example.com"]
            },
            "provider": "openai",
            "model": "gpt-4o-mini",
            "cost_cents": 5.0,
            "latency_ms": 1500,
        }
        
        payload = mapper.map(result)
        
        assert payload["query_id"] == "item_123"
        assert payload["question"] == "Test question?"
        assert payload["answer"] == "Test answer"
        assert payload["sources"] == ["https://example.com"]
        assert payload["metadata"]["provider"] == "openai"
        assert payload["metadata"]["cost_usd"] == 0.05  # 5 cents

