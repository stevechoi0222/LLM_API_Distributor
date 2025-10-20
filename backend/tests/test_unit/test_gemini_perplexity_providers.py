"""Unit tests for Gemini and Perplexity providers (TKT-002)."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
from app.domain.providers.gemini_client import GeminiClient
from app.domain.providers.perplexity_client import PerplexityClient


@pytest.mark.unit
@pytest.mark.tkt002
class TestGeminiClient:
    """Test Gemini provider client."""

    @pytest.mark.asyncio
    async def test_prepare_prompt(self):
        """Test Gemini prompt preparation."""
        client = GeminiClient()
        
        request = await client.prepare_prompt(
            question="What is AI?",
            persona={"name": "Developer", "role": "Engineer", "tone": "technical"},
            topic={"title": "Artificial Intelligence"}
        )
        
        assert "contents" in request
        assert isinstance(request["contents"], list)
        assert len(request["contents"]) == 1
        assert request["contents"][0]["role"] == "user"
        assert "parts" in request["contents"][0]
        # Should include both system and user templates
        text = request["contents"][0]["parts"][0]["text"]
        assert "JSON" in text
        assert "What is AI?" in text
        assert "Artificial Intelligence" in text

    @pytest.mark.asyncio
    async def test_invoke_success_with_valid_json(self):
        """Test successful Gemini invocation with valid JSON response."""
        client = GeminiClient()
        
        # Mock successful response with valid JSON
        mock_response = httpx.Response(
            status_code=200,
            json={
                "candidates": [{
                    "content": {
                        "parts": [{
                            "text": '{"answer": "AI is artificial intelligence", "citations": ["https://example.com"], "meta": {}}'
                        }]
                    }
                }],
                "usageMetadata": {
                    "promptTokenCount": 100,
                    "candidatesTokenCount": 50,
                    "totalTokenCount": 150
                }
            }
        )
        
        with patch.object(client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            
            request = {"contents": [{"role": "user", "parts": [{"text": "test"}]}]}
            result = await client.invoke(request, model="gemini-pro")
        
        assert result.text == "AI is artificial intelligence"
        assert result.citations == ["https://example.com"]
        assert result.usage["prompt_tokens"] == 100
        assert result.usage["completion_tokens"] == 50
        assert result.validated_json is not None
        assert result.validated_json["answer"] == "AI is artificial intelligence"
        assert result.cost_cents > 0

    @pytest.mark.asyncio
    async def test_invoke_with_grounding_citations(self):
        """Test Gemini citations extraction from grounding metadata."""
        client = GeminiClient()
        
        # Mock response with grounding metadata (Gemini-specific)
        mock_response = httpx.Response(
            status_code=200,
            json={
                "candidates": [{
                    "content": {
                        "parts": [{
                            "text": '{"answer": "Test answer", "citations": [], "meta": {}}'
                        }]
                    },
                    "groundingMetadata": {
                        "groundingSupports": [
                            {
                                "segment": {"uri": "https://source1.com"},
                                "groundingChunkIndices": []
                            }
                        ],
                        "groundingChunks": [
                            {"web": {"uri": "https://source2.com"}}
                        ]
                    }
                }],
                "usageMetadata": {
                    "promptTokenCount": 100,
                    "candidatesTokenCount": 50,
                    "totalTokenCount": 150
                }
            }
        )
        
        with patch.object(client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            
            request = {"contents": [{"role": "user", "parts": [{"text": "test"}]}]}
            result = await client.invoke(request, model="gemini-pro")
        
        # Should extract grounding citations
        assert len(result.citations) >= 1
        assert "https://source1.com" in result.citations

    @pytest.mark.asyncio
    async def test_invoke_invalid_json_fallback(self):
        """Test Gemini fallback when JSON is invalid."""
        client = GeminiClient()
        
        # Mock response with invalid JSON
        mock_response = httpx.Response(
            status_code=200,
            json={
                "candidates": [{
                    "content": {
                        "parts": [{
                            "text": "This is plain text, not JSON"
                        }]
                    }
                }],
                "usageMetadata": {
                    "promptTokenCount": 100,
                    "candidatesTokenCount": 50,
                    "totalTokenCount": 150
                }
            }
        )
        
        with patch.object(client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            
            request = {"contents": [{"role": "user", "parts": [{"text": "test"}]}]}
            result = await client.invoke(request, model="gemini-pro")
        
        # Should fallback to plain text
        assert result.text == "This is plain text, not JSON"
        assert result.citations == []
        assert result.validated_json["meta"].get("validation_error") is not None

    @pytest.mark.asyncio
    async def test_invoke_rate_limited_429(self):
        """Test Gemini handles 429 rate limiting."""
        client = GeminiClient()
        
        # Mock 429 response
        mock_response = httpx.Response(
            status_code=429,
            json={"error": "Rate limit exceeded"}
        )
        
        with patch.object(client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            
            request = {"contents": [{"role": "user", "parts": [{"text": "test"}]}]}
            
            with pytest.raises(httpx.HTTPStatusError):
                await client.invoke(request, model="gemini-pro")

    def test_validate_urls(self):
        """Test URL validation."""
        client = GeminiClient()
        
        urls = [
            "https://example.com",
            "http://test.org/path",
            "not-a-url",
            "ftp://invalid.com",  # Not http/https
            "",
            "https://valid.co.uk/page?param=value"
        ]
        
        valid = client._validate_urls(urls)
        
        assert "https://example.com" in valid
        assert "http://test.org/path" in valid
        assert "https://valid.co.uk/page?param=value" in valid
        assert "not-a-url" not in valid
        assert "ftp://invalid.com" not in valid
        assert len(valid) == 3

    def test_compute_cost(self):
        """Test Gemini cost computation."""
        client = GeminiClient()
        
        usage = {
            "prompt_tokens": 1000,
            "completion_tokens": 500,
            "total_tokens": 1500
        }
        
        cost = client.compute_cost("gemini-pro", usage)
        
        # Should use Gemini pricing
        expected_input_cost = (1000 / 1000) * 0.125  # $0.125 per 1K
        expected_output_cost = (500 / 1000) * 0.375  # $0.375 per 1K
        expected_total = (expected_input_cost + expected_output_cost) * 100  # cents
        
        assert cost == pytest.approx(expected_total, rel=0.01)


@pytest.mark.unit
@pytest.mark.tkt002
class TestPerplexityClient:
    """Test Perplexity provider client."""

    @pytest.mark.asyncio
    async def test_prepare_prompt(self):
        """Test Perplexity prompt preparation."""
        client = PerplexityClient()
        
        request = await client.prepare_prompt(
            question="What is ML?",
            persona={"name": "Student", "role": "Learner", "tone": "simple"},
            topic={"title": "Machine Learning"}
        )
        
        assert "messages" in request
        assert isinstance(request["messages"], list)
        assert len(request["messages"]) == 2  # System + user
        assert request["messages"][0]["role"] == "system"
        assert request["messages"][1]["role"] == "user"
        assert "What is ML?" in request["messages"][1]["content"]

    @pytest.mark.asyncio
    async def test_invoke_success_with_citations(self):
        """Test successful Perplexity invocation with citations."""
        client = PerplexityClient()
        
        # Mock successful response with Perplexity citations
        mock_response = httpx.Response(
            status_code=200,
            json={
                "choices": [{
                    "message": {
                        "content": '{"answer": "ML is machine learning", "citations": ["https://ml.com"], "meta": {}}',
                        "citations": ["https://perplexity-source.com"]  # Perplexity-specific
                    }
                }],
                "usage": {
                    "prompt_tokens": 80,
                    "completion_tokens": 40,
                    "total_tokens": 120
                },
                "citations": ["https://root-citation.com"]  # Also at root level
            }
        )
        
        with patch.object(client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            
            request = {"messages": [{"role": "user", "content": "test"}]}
            result = await client.invoke(request, model="llama-3.1-sonar-small-128k-online")
        
        assert result.text == "ML is machine learning"
        # Should merge JSON citations + Perplexity-specific citations
        assert len(result.citations) >= 2
        assert "https://ml.com" in result.citations or "https://perplexity-source.com" in result.citations
        assert result.usage["prompt_tokens"] == 80
        assert result.cost_cents > 0

    @pytest.mark.asyncio
    async def test_invoke_invalid_json_fallback(self):
        """Test Perplexity fallback when JSON is invalid."""
        client = PerplexityClient()
        
        # Mock response with invalid JSON
        mock_response = httpx.Response(
            status_code=200,
            json={
                "choices": [{
                    "message": {
                        "content": "Plain text answer without JSON formatting"
                    }
                }],
                "usage": {
                    "prompt_tokens": 80,
                    "completion_tokens": 40,
                    "total_tokens": 120
                }
            }
        )
        
        with patch.object(client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            
            request = {"messages": [{"role": "user", "content": "test"}]}
            result = await client.invoke(request, model="llama-3.1-sonar-small-128k-online")
        
        # Should fallback to plain text
        assert result.text == "Plain text answer without JSON formatting"
        assert result.citations == []
        assert "validation_error" in result.validated_json.get("meta", {})

    @pytest.mark.asyncio
    async def test_invoke_rate_limited_429(self):
        """Test Perplexity handles 429 rate limiting."""
        client = PerplexityClient()
        
        # Mock 429 response
        mock_response = httpx.Response(
            status_code=429,
            json={"error": "Too many requests"}
        )
        
        with patch.object(client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            
            request = {"messages": [{"role": "user", "content": "test"}]}
            
            with pytest.raises(httpx.HTTPStatusError):
                await client.invoke(request, model="llama-3.1-sonar-small-128k-online")

    def test_compute_cost(self):
        """Test Perplexity cost computation."""
        client = PerplexityClient()
        
        usage = {
            "prompt_tokens": 2000,
            "completion_tokens": 1000,
            "total_tokens": 3000
        }
        
        cost = client.compute_cost("llama-3.1-sonar-small-128k-online", usage)
        
        # Should use Perplexity pricing (same for input/output)
        expected_cost = ((2000 + 1000) / 1000) * 0.20 * 100  # $0.20 per 1K, convert to cents
        
        assert cost == pytest.approx(expected_cost, rel=0.01)


@pytest.mark.unit
@pytest.mark.tkt002
class TestCitationsNormalization:
    """Test citations normalization across providers."""

    def test_gemini_citations_deduplication(self):
        """Test Gemini deduplicates citations."""
        client = GeminiClient()
        
        urls = [
            "https://example.com",
            "https://example.com",  # Duplicate
            "https://test.org",
            "https://example.com"   # Another duplicate
        ]
        
        # Deduplicate using set (as done in invoke)
        unique = list(set(urls))
        valid = client._validate_urls(unique)
        
        assert len(valid) == 2
        assert "https://example.com" in valid
        assert "https://test.org" in valid

    def test_perplexity_multiple_citation_sources(self):
        """Test Perplexity extracts citations from multiple locations."""
        client = PerplexityClient()
        
        # Mock response with citations in multiple places
        data = {
            "citations": ["https://root.com"],
            "choices": [{
                "message": {
                    "citations": ["https://message.com"]
                }
            }]
        }
        
        citations = client._extract_perplexity_citations(data)
        
        assert len(citations) == 2
        assert "https://root.com" in citations
        assert "https://message.com" in citations


@pytest.mark.unit
@pytest.mark.tkt002
class TestDeterminism:
    """Test deterministic behavior (temperature=0)."""

    @pytest.mark.asyncio
    async def test_gemini_deterministic_by_default(self):
        """Test Gemini uses temperature=0 by default."""
        client = GeminiClient()
        
        mock_response = httpx.Response(
            status_code=200,
            json={
                "candidates": [{
                    "content": {
                        "parts": [{
                            "text": '{"answer": "test", "citations": [], "meta": {}}'
                        }]
                    }
                }],
                "usageMetadata": {
                    "promptTokenCount": 10,
                    "candidatesTokenCount": 5,
                    "totalTokenCount": 15
                }
            }
        )
        
        with patch.object(client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            
            request = {"contents": [{"role": "user", "parts": [{"text": "test"}]}]}
            await client.invoke(request, model="gemini-pro")
            
            # Check API request had temperature=0
            call_args = mock_post.call_args
            api_request = call_args.kwargs['json']
            assert api_request['generationConfig']['temperature'] == 0.0
            assert api_request['generationConfig']['topP'] == 1.0

    @pytest.mark.asyncio
    async def test_perplexity_deterministic_by_default(self):
        """Test Perplexity uses temperature=0 by default."""
        client = PerplexityClient()
        
        mock_response = httpx.Response(
            status_code=200,
            json={
                "choices": [{
                    "message": {
                        "content": '{"answer": "test", "citations": [], "meta": {}}'
                    }
                }],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15
                }
            }
        )
        
        with patch.object(client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            
            request = {"messages": [{"role": "user", "content": "test"}]}
            await client.invoke(request, model="llama-3.1-sonar-small-128k-online")
            
            # Check API request had temperature=0
            call_args = mock_post.call_args
            api_request = call_args.kwargs['json']
            assert api_request['temperature'] == 0.0
            assert api_request['top_p'] == 1.0

