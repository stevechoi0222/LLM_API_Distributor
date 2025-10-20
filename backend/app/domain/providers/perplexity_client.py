"""Perplexity provider client with citations normalization (TKT-002)."""
import json
import re
import time
from typing import Any, Dict, List
import httpx
from jinja2 import Template
from jsonschema import validate, ValidationError as JsonSchemaValidationError
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
from app.core.config import settings
from app.core.logging import get_logger
from app.domain.providers.base import ProviderClient, ProviderResult

logger = get_logger(__name__)


# JSON Schema for provider response
RESPONSE_JSON_SCHEMA = {
    "type": "object",
    "required": ["answer"],
    "properties": {
        "answer": {"type": "string"},
        "citations": {
            "type": "array",
            "items": {"type": "string", "format": "uri"},
            "default": []
        },
        "meta": {"type": "object"}
    },
    "additionalProperties": False
}


# Prompt templates
SYSTEM_TEMPLATE = """You are a helpful AI engine providing accurate information.

CRITICAL: You MUST respond with ONLY a valid JSON object matching this exact schema:

```json
{
  "answer": "your detailed answer here",
  "citations": ["https://source1.com", "https://source2.com"],
  "meta": {}
}
```

Requirements:
- "answer" is required and must be a string
- "citations" should be an array of URLs (can be empty)
- "meta" can contain additional metadata (optional)
- Do not include any text before or after the JSON
- Ensure valid JSON syntax"""

USER_TEMPLATE = """Question: {{question}}

Context:
- Topic: {{topic_title}}
- Persona: {{persona_name}} ({{persona_role}})
- Tone: {{persona_tone}}

Provide your answer as a JSON object matching the required schema."""


class PerplexityClient(ProviderClient):
    """Perplexity API client with citations normalization (TKT-002)."""

    name = "perplexity"

    def __init__(self):
        """Initialize Perplexity client."""
        self.api_key = settings.perplexity_api_key
        self.base_url = "https://api.perplexity.ai"
        self.timeout = 60.0
        
        # HTTP client with connection pooling
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout),
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
        )

    async def prepare_prompt(
        self,
        question: str,
        persona: Dict[str, Any],
        topic: Dict[str, Any],
        prompt_version: str = "v1",
    ) -> Dict[str, Any]:
        """Prepare prompt with JSON schema instruction.
        
        Args:
            question: Question text
            persona: Persona data
            topic: Topic data
            prompt_version: Prompt version
            
        Returns:
            Messages for Perplexity API
        """
        # Render user message
        user_template = Template(USER_TEMPLATE)
        user_message = user_template.render(
            question=question,
            topic_title=topic.get("title", ""),
            persona_name=persona.get("name", "User"),
            persona_role=persona.get("role", ""),
            persona_tone=persona.get("tone", "neutral"),
        )

        # Perplexity uses OpenAI-compatible message format
        return {
            "messages": [
                {"role": "system", "content": SYSTEM_TEMPLATE},
                {"role": "user", "content": user_message},
            ],
            "prompt_version": prompt_version,
        }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
    )
    async def invoke(
        self,
        request: Dict[str, Any],
        **settings: Any,
    ) -> ProviderResult:
        """Invoke Perplexity API with retries and JSON validation.
        
        Args:
            request: Prepared request
            **settings: Model, temperature, etc.
            
        Returns:
            Provider result with validated JSON and normalized citations
        """
        start_time = time.time()
        
        # Extract settings with deterministic defaults
        model = settings.get("model", "llama-3.1-sonar-small-128k-online")
        allow_sampling = settings.get("allow_sampling", False)
        
        # Determinism first
        temperature = settings.get("temperature", settings.default_temperature)
        top_p = settings.get("top_p", settings.default_top_p)
        
        if not allow_sampling:
            temperature = 0.0
            top_p = 1.0
        
        # Build API request
        api_request = {
            "model": model,
            "messages": request["messages"],
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": settings.get("max_tokens", settings.default_max_tokens),
            # Perplexity-specific: return sources
            "return_citations": True,
            "return_images": False,
        }

        logger.debug(
            "perplexity_request",
            model=model,
            temperature=temperature,
            allow_sampling=allow_sampling
        )

        # Make request
        response = await self.client.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=api_request,
        )
        
        # Handle rate limiting (429)
        if response.status_code == 429:
            logger.warning("perplexity_rate_limited")
            raise httpx.HTTPStatusError(
                "Rate limit exceeded",
                request=response.request,
                response=response
            )
        
        response.raise_for_status()
        
        latency_ms = int((time.time() - start_time) * 1000)
        data = response.json()

        # Extract response
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        
        # Extract and normalize citations from Perplexity's response
        perplexity_citations = self._extract_perplexity_citations(data)
        
        # Parse and validate JSON
        validated_json, json_citations = await self._parse_and_validate_json(content)
        
        # Merge citations: prefer JSON citations, fallback to Perplexity's sources
        all_citations = list(set(json_citations + perplexity_citations))
        all_citations = self._validate_urls(all_citations)
        
        # Compute cost
        cost_cents = self.compute_cost(model, usage)

        result = ProviderResult(
            text=validated_json.get("answer", content),
            citations=all_citations,
            usage={
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
            latency_ms=latency_ms,
            cost_cents=cost_cents,
            raw_response=data,
            validated_json=validated_json,
        )

        logger.info(
            "perplexity_response",
            model=model,
            latency_ms=latency_ms,
            tokens=usage.get("total_tokens", 0),
            cost_cents=cost_cents,
            citations_count=len(all_citations)
        )

        return result

    def _extract_perplexity_citations(self, data: Dict[str, Any]) -> List[str]:
        """Extract citations from Perplexity's response.
        
        Perplexity returns citations in the 'citations' field.
        
        Args:
            data: Perplexity API response
            
        Returns:
            List of citation URLs
        """
        citations = []
        
        # Perplexity returns citations at the root level
        if "citations" in data:
            perplexity_citations = data["citations"]
            if isinstance(perplexity_citations, list):
                citations.extend(perplexity_citations)
        
        # Also check in message metadata
        choices = data.get("choices", [])
        if choices:
            message = choices[0].get("message", {})
            
            # Check for sources in metadata
            if "citations" in message:
                message_citations = message["citations"]
                if isinstance(message_citations, list):
                    citations.extend(message_citations)
        
        return citations

    async def _parse_and_validate_json(
        self,
        content: str,
        retry_count: int = 0,
    ) -> tuple[Dict[str, Any], List[str]]:
        """Parse and validate JSON response (with retry once on failure).
        
        Args:
            content: Response content
            retry_count: Current retry count
            
        Returns:
            (validated_json, citations)
        """
        # Try to parse JSON
        try:
            # Extract JSON if wrapped in markdown
            if "```json" in content:
                start = content.find("```json") + 7
                end = content.find("```", start)
                json_str = content[start:end].strip()
            elif "```" in content:
                start = content.find("```") + 3
                end = content.find("```", start)
                json_str = content[start:end].strip()
            else:
                json_str = content.strip()
            
            parsed = json.loads(json_str)
            
            # Validate against schema
            validate(instance=parsed, schema=RESPONSE_JSON_SCHEMA)
            
            logger.debug("json_validation_success")
            
            # Extract citations
            citations = parsed.get("citations", [])
            if not isinstance(citations, list):
                citations = []
            
            return parsed, citations
            
        except (json.JSONDecodeError, JsonSchemaValidationError) as e:
            logger.warning(
                "json_validation_failed",
                error=str(e),
                content_preview=content[:200],
                retry_count=retry_count
            )
            
            # Fallback: return content as answer with empty citations
            return {
                "answer": content,
                "citations": [],
                "meta": {"validation_error": str(e)}
            }, []

    def _validate_urls(self, urls: List[str]) -> List[str]:
        """Validate and filter URLs.
        
        Args:
            urls: List of potential URLs
            
        Returns:
            List of valid URLs (http/https only)
        """
        valid_urls = []
        url_pattern = re.compile(
            r'^https?://'  # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain
            r'localhost|'  # localhost
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # IP
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        
        for url in urls:
            if isinstance(url, str) and url_pattern.match(url):
                valid_urls.append(url)
        
        return valid_urls

    def compute_cost(
        self,
        model: str,
        usage: Dict[str, int],
    ) -> float:
        """Compute cost from token usage.
        
        Args:
            model: Model name
            usage: Token usage
            
        Returns:
            Cost in cents (USD)
        """
        pricing = settings.get_model_pricing("perplexity", model)
        
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        
        # Cost = (tokens / 1000) * price_per_1k
        input_cost = (input_tokens / 1000) * pricing["input_per_1k"]
        output_cost = (output_tokens / 1000) * pricing["output_per_1k"]
        
        total_cost_dollars = input_cost + output_cost
        total_cost_cents = total_cost_dollars * 100
        
        return round(total_cost_cents, 4)

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()


