"""Test JSON response validation (TICKET 2)."""
import json
import pytest
from app.domain.providers.openai_client import OpenAIClient, RESPONSE_JSON_SCHEMA
from jsonschema import validate, ValidationError


@pytest.mark.unit
@pytest.mark.ticket2
class TestJSONValidation:
    """Test strict JSON response validation (TICKET 2)."""

    def test_valid_json_response(self):
        """Test that valid JSON passes validation."""
        valid_response = {
            "answer": "The battery lasts 12 hours.",
            "citations": ["https://example.com/review"],
            "meta": {"confidence": 0.95}
        }
        
        # Should not raise
        validate(instance=valid_response, schema=RESPONSE_JSON_SCHEMA)

    def test_valid_json_minimal(self):
        """Test that minimal valid JSON (only answer) passes."""
        minimal_response = {
            "answer": "The battery lasts 12 hours."
        }
        
        # Should not raise (citations is optional)
        validate(instance=minimal_response, schema=RESPONSE_JSON_SCHEMA)

    def test_invalid_json_missing_answer(self):
        """Test that JSON without 'answer' fails validation."""
        invalid_response = {
            "citations": ["https://example.com"]
        }
        
        with pytest.raises(ValidationError):
            validate(instance=invalid_response, schema=RESPONSE_JSON_SCHEMA)

    def test_invalid_json_wrong_type(self):
        """Test that wrong type for answer fails validation."""
        invalid_response = {
            "answer": 123  # Should be string
        }
        
        with pytest.raises(ValidationError):
            validate(instance=invalid_response, schema=RESPONSE_JSON_SCHEMA)

    def test_invalid_citations_not_array(self):
        """Test that non-array citations fail validation."""
        invalid_response = {
            "answer": "Test",
            "citations": "not an array"
        }
        
        with pytest.raises(ValidationError):
            validate(instance=invalid_response, schema=RESPONSE_JSON_SCHEMA)

    def test_valid_empty_citations(self):
        """Test that empty citations array is valid."""
        response = {
            "answer": "Test answer",
            "citations": []
        }
        
        # Should not raise
        validate(instance=response, schema=RESPONSE_JSON_SCHEMA)

    @pytest.mark.asyncio
    async def test_parse_json_from_markdown(self):
        """Test parsing JSON wrapped in markdown code blocks."""
        client = OpenAIClient()
        
        # JSON wrapped in markdown
        content = '''```json
{
  "answer": "Test answer",
  "citations": []
}
```'''
        
        parsed, citations = await client._parse_and_validate_json(content)
        
        assert parsed["answer"] == "Test answer"
        assert citations == []

    @pytest.mark.asyncio
    async def test_parse_json_fallback_on_invalid(self):
        """Test fallback to text when JSON is invalid."""
        client = OpenAIClient()
        
        # Invalid JSON
        content = "This is just plain text, not JSON"
        
        parsed, citations = await client._parse_and_validate_json(content)
        
        # Should fallback
        assert parsed["answer"] == content
        assert citations == []
        assert "validation_error" in parsed.get("meta", {})

