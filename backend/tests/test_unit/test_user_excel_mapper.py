"""Unit tests for user_excel_v0_1 mapper (TKT-013)."""
import pytest
from app.exporters.mappers.user_excel_v0_1 import UserExcelV01Mapper, get_mapper


@pytest.mark.unit
@pytest.mark.tkt013
class TestUserExcelV01Mapper:
    """Test user_excel_v0_1 mapper."""

    def test_mapper_has_exact_columns(self):
        """Test mapper has exact column specifications."""
        mapper = UserExcelV01Mapper()
        
        # Check QUERY columns
        assert mapper.QUERY_COLUMNS == [
            "campaign",
            "run_id",
            "question_id",
            "persona_name",
            "question_text",
            "provider",
            "model",
            "response_text",
            "latency_ms",
            "prompt_tokens",
            "completion_tokens",
            "cost_cents",
            "status"
        ]
        
        # Check CITATION columns
        assert mapper.CITATION_COLUMNS == [
            "run_id",
            "question_id",
            "provider",
            "citation_index",
            "citation_url"
        ]

    def test_map_single_openai_response_with_citations(self):
        """Test mapping single OpenAI response with 2 citations."""
        mapper = UserExcelV01Mapper()
        
        result = {
            "run_id": "run_123",
            "question_id": "q_001",
            "campaign_name": "Test Campaign",
            "persona_name": "Developer",
            "question_text": "What is AI?",
            "provider": "openai",
            "model": "gpt-4o-mini",
            "response": {
                "answer": "AI is artificial intelligence",
                "citations": ["https://example.com/ai", "https://test.org/ml"]
            },
            "latency_ms": 1500,
            "token_usage": {
                "prompt_tokens": 100,
                "completion_tokens": 50
            },
            "cost_cents": 5.5,
            "status": "succeeded",
            "citations": ["https://example.com/ai", "https://test.org/ml"]
        }
        
        mapped = mapper.map_batch([result])
        
        # Check query rows
        assert len(mapped["query_rows"]) == 1
        query_row = mapped["query_rows"][0]
        assert query_row["campaign"] == "Test Campaign"
        assert query_row["run_id"] == "run_123"
        assert query_row["question_id"] == "q_001"
        assert query_row["persona_name"] == "Developer"
        assert query_row["provider"] == "openai"
        assert query_row["model"] == "gpt-4o-mini"
        assert query_row["response_text"] == "AI is artificial intelligence"
        assert query_row["latency_ms"] == 1500
        assert query_row["prompt_tokens"] == 100
        assert query_row["completion_tokens"] == 50
        assert query_row["cost_cents"] == 5.5
        assert query_row["status"] == "succeeded"
        
        # Check citation rows (2 expected)
        assert len(mapped["citation_rows"]) == 2
        
        citation_1 = mapped["citation_rows"][0]
        assert citation_1["run_id"] == "run_123"
        assert citation_1["question_id"] == "q_001"
        assert citation_1["provider"] == "openai"
        assert citation_1["citation_index"] == 0
        assert citation_1["citation_url"] == "https://example.com/ai"
        
        citation_2 = mapped["citation_rows"][1]
        assert citation_2["citation_index"] == 1
        assert citation_2["citation_url"] == "https://test.org/ml"

    def test_map_gemini_response_with_zero_citations(self):
        """Test mapping Gemini response with no citations."""
        mapper = UserExcelV01Mapper()
        
        result = {
            "run_id": "run_456",
            "question_id": "q_002",
            "campaign_name": "Gemini Test",
            "persona_name": "Student",
            "question_text": "Explain ML",
            "provider": "gemini",
            "model": "gemini-pro",
            "response": {
                "answer": "ML is machine learning"
            },
            "latency_ms": 2000,
            "token_usage": {
                "prompt_tokens": 80,
                "completion_tokens": 40
            },
            "cost_cents": 3.2,
            "status": "succeeded",
            "citations": []  # No citations
        }
        
        mapped = mapper.map_batch([result])
        
        # Check query row exists
        assert len(mapped["query_rows"]) == 1
        query_row = mapped["query_rows"][0]
        assert query_row["provider"] == "gemini"
        assert query_row["model"] == "gemini-pro"
        assert query_row["response_text"] == "ML is machine learning"
        
        # Check no citation rows
        assert len(mapped["citation_rows"]) == 0

    def test_map_multi_provider_responses(self):
        """Test mapping mixed providers (OpenAI + Perplexity)."""
        mapper = UserExcelV01Mapper()
        
        results = [
            {
                "run_id": "run_789",
                "question_id": "q_003",
                "campaign_name": "Multi Provider",
                "persona_name": "Researcher",
                "question_text": "What is deep learning?",
                "provider": "openai",
                "model": "gpt-4o-mini",
                "response": {"answer": "OpenAI answer"},
                "latency_ms": 1200,
                "token_usage": {"prompt_tokens": 90, "completion_tokens": 45},
                "cost_cents": 4.0,
                "status": "succeeded",
                "citations": ["https://openai.com/research"]
            },
            {
                "run_id": "run_789",
                "question_id": "q_003",
                "campaign_name": "Multi Provider",
                "persona_name": "Researcher",
                "question_text": "What is deep learning?",
                "provider": "perplexity",
                "model": "llama-3.1-sonar-small-128k-online",
                "response": {"answer": "Perplexity answer"},
                "latency_ms": 1800,
                "token_usage": {"prompt_tokens": 85, "completion_tokens": 50},
                "cost_cents": 5.0,
                "status": "succeeded",
                "citations": ["https://perplexity.ai/docs", "https://llama.meta.com"]
            }
        ]
        
        mapped = mapper.map_batch(results)
        
        # Should have 2 query rows (one per provider)
        assert len(mapped["query_rows"]) == 2
        
        query_openai = mapped["query_rows"][0]
        assert query_openai["provider"] == "openai"
        assert query_openai["model"] == "gpt-4o-mini"
        assert query_openai["response_text"] == "OpenAI answer"
        
        query_perplexity = mapped["query_rows"][1]
        assert query_perplexity["provider"] == "perplexity"
        assert query_perplexity["model"] == "llama-3.1-sonar-small-128k-online"
        assert query_perplexity["response_text"] == "Perplexity answer"
        
        # Should have 3 total citations (1 from OpenAI + 2 from Perplexity)
        assert len(mapped["citation_rows"]) == 3

    def test_url_validation(self):
        """Test URL validation filters invalid URLs."""
        mapper = UserExcelV01Mapper()
        
        result = {
            "run_id": "run_123",
            "question_id": "q_004",
            "campaign_name": "URL Test",
            "persona_name": "Tester",
            "question_text": "Test",
            "provider": "openai",
            "model": "gpt-4o-mini",
            "response": {"answer": "Test"},
            "latency_ms": 1000,
            "token_usage": {"prompt_tokens": 50, "completion_tokens": 25},
            "cost_cents": 2.0,
            "status": "succeeded",
            "citations": [
                "https://valid.com",
                "http://also-valid.org",
                "not-a-url",
                "ftp://invalid-protocol.com",
                "",
                "https://another-valid.co.uk/path"
            ]
        }
        
        mapped = mapper.map_batch([result])
        
        # Should only have 3 valid citations (https://valid.com, http://also-valid.org, https://another-valid.co.uk/path)
        assert len(mapped["citation_rows"]) == 3
        
        urls = [c["citation_url"] for c in mapped["citation_rows"]]
        assert "https://valid.com" in urls
        assert "http://also-valid.org" in urls
        assert "https://another-valid.co.uk/path" in urls
        assert "not-a-url" not in urls
        assert "ftp://invalid-protocol.com" not in urls

    def test_truncate_long_text(self):
        """Test truncation of very long cells."""
        mapper = UserExcelV01Mapper()
        
        # Create very long text (15k chars)
        long_text = "A" * 15000
        
        result = {
            "run_id": "run_999",
            "question_id": "q_long",
            "campaign_name": "Long Text Test",
            "persona_name": "Tester",
            "question_text": "Short question",
            "provider": "openai",
            "model": "gpt-4o-mini",
            "response": {"answer": long_text},
            "latency_ms": 2000,
            "token_usage": {"prompt_tokens": 100, "completion_tokens": 5000},
            "cost_cents": 50.0,
            "status": "succeeded",
            "citations": []
        }
        
        mapped = mapper.map_batch([result])
        
        query_row = mapped["query_rows"][0]
        # Should be truncated to MAX_CELL_LENGTH (10000) + "..."
        assert len(query_row["response_text"]) == 10003  # 10000 + "..."
        assert query_row["response_text"].endswith("...")

    def test_fallback_to_raw_text_when_json_invalid(self):
        """Test fallback to raw text when JSON response is missing/invalid."""
        mapper = UserExcelV01Mapper()
        
        result = {
            "run_id": "run_fallback",
            "question_id": "q_005",
            "campaign_name": "Fallback Test",
            "persona_name": "User",
            "question_text": "Test?",
            "provider": "openai",
            "model": "gpt-4o-mini",
            "response": {},  # Empty response dict
            "answer": "Fallback raw text answer",  # Should use this
            "latency_ms": 1500,
            "token_usage": {"prompt_tokens": 60, "completion_tokens": 30},
            "cost_cents": 3.0,
            "status": "succeeded",
            "citations": []
        }
        
        mapped = mapper.map_batch([result])
        
        query_row = mapped["query_rows"][0]
        assert query_row["response_text"] == "Fallback raw text answer"

    def test_get_mapper_from_registry(self):
        """Test getting mapper from registry."""
        mapper = get_mapper("user_excel_v0_1", "v1")
        
        assert mapper is not None
        assert isinstance(mapper, UserExcelV01Mapper)
        assert mapper.version == "v1"

    def test_get_mapper_unknown_name_raises(self):
        """Test unknown mapper name raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            get_mapper("unknown_mapper")
        
        assert "not found" in str(exc_info.value).lower()

    def test_get_mapper_unknown_version_raises(self):
        """Test unknown version raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            get_mapper("user_excel_v0_1", "v99")
        
        assert "version" in str(exc_info.value).lower()

    def test_column_order_preserved(self):
        """Test that column order matches specification exactly."""
        mapper = UserExcelV01Mapper()
        
        result = {
            "run_id": "run_order",
            "question_id": "q_order",
            "campaign_name": "Order Test",
            "persona_name": "Tester",
            "question_text": "Test",
            "provider": "openai",
            "model": "gpt-4o-mini",
            "response": {"answer": "Test"},
            "latency_ms": 1000,
            "token_usage": {"prompt_tokens": 50, "completion_tokens": 25},
            "cost_cents": 2.0,
            "status": "succeeded",
            "citations": ["https://example.com"]
        }
        
        mapped = mapper.map_batch([result])
        
        # Check query row keys match exact order
        query_row = mapped["query_rows"][0]
        assert list(query_row.keys()) == mapper.QUERY_COLUMNS
        
        # Check citation row keys match exact order
        citation_row = mapped["citation_rows"][0]
        assert list(citation_row.keys()) == mapper.CITATION_COLUMNS

    def test_zero_based_citation_index(self):
        """Test citation_index is 0-based."""
        mapper = UserExcelV01Mapper()
        
        result = {
            "run_id": "run_idx",
            "question_id": "q_idx",
            "campaign_name": "Index Test",
            "persona_name": "Tester",
            "question_text": "Test",
            "provider": "openai",
            "model": "gpt-4o-mini",
            "response": {"answer": "Test"},
            "latency_ms": 1000,
            "token_usage": {"prompt_tokens": 50, "completion_tokens": 25},
            "cost_cents": 2.0,
            "status": "succeeded",
            "citations": ["https://first.com", "https://second.com", "https://third.com"]
        }
        
        mapped = mapper.map_batch([result])
        
        assert len(mapped["citation_rows"]) == 3
        assert mapped["citation_rows"][0]["citation_index"] == 0
        assert mapped["citation_rows"][1]["citation_index"] == 1
        assert mapped["citation_rows"][2]["citation_index"] == 2

