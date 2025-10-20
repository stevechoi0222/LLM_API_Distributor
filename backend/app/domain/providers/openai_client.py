"""OpenAI provider client with JSON validation and cost tracking."""
import json
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


# JSON Schema for provider response (TICKET 2)
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


# Prompt templates with JSON schema instruction (TICKET 2)
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


class OpenAIClient(ProviderClient):
    """OpenAI API client with retries, circuit breaker, and JSON validation."""

    name = "openai"

    def __init__(self):
        """Initialize OpenAI client."""
        self.api_key = settings.openai_api_key
        self.base_url = "https://api.openai.com/v1"
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
        """Prepare prompt with JSON schema instruction (TICKET 2).
        
        Args:
            question: Question text
            persona: Persona data
            topic: Topic data
            prompt_version: Prompt version
            
        Returns:
            Messages for OpenAI API
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
        """Invoke OpenAI API with retries and JSON validation.
        
        Args:
            request: Prepared request
            **settings: Model, temperature, etc.
            
        Returns:
            Provider result with validated JSON
        """
        start_time = time.time()
        
        # Extract settings with deterministic defaults (TICKET 6)
        model = settings.get("model", "gpt-4o-mini")
        allow_sampling = settings.get("allow_sampling", False)
        
        # Determinism first (TICKET 6)
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
        }
        
        # Add seed if supported (for determinism)
        if not allow_sampling:
            api_request["seed"] = 42

        logger.debug(
            "openai_request",
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
        response.raise_for_status()
        
        latency_ms = int((time.time() - start_time) * 1000)
        data = response.json()

        # Extract response
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        
        # Parse and validate JSON (TICKET 2)
        validated_json, citations = await self._parse_and_validate_json(content)
        
        # Compute cost (TICKET 3)
        cost_cents = self.compute_cost(model, usage)

        result = ProviderResult(
            text=validated_json.get("answer", content),
            citations=citations,
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
            "openai_response",
            model=model,
            latency_ms=latency_ms,
            tokens=usage.get("total_tokens", 0),
            cost_cents=cost_cents,
        )

        return result

    async def _parse_and_validate_json(
        self,
        content: str,
    ) -> tuple[Dict[str, Any], List[str]]:
        """Parse and validate JSON response (TICKET 2).
        
        Args:
            content: Response content
            
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
                content_preview=content[:200]
            )
            
            # Fallback: return content as answer with empty citations
            return {
                "answer": content,
                "citations": [],
                "meta": {"validation_error": str(e)}
            }, []

    def compute_cost(
        self,
        model: str,
        usage: Dict[str, int],
    ) -> float:
        """Compute cost from token usage (TICKET 3).
        
        Args:
            model: Model name
            usage: Token usage
            
        Returns:
            Cost in cents (USD)
        """
        pricing = settings.get_model_pricing("openai", model)
        
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


