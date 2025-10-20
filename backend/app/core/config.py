"""Application configuration using Pydantic Settings."""
from typing import Dict, List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    # Database
    database_url: str = Field(
        default="postgresql+psycopg://geo:geo@localhost:5432/geo",
        description="Database connection URL"
    )
    local_database_url: str = Field(
        default="postgresql+psycopg://geo:geo@postgres:5432/geo",
        description="Local dev database URL"
    )
    db_schema: str = Field(default="geo_app", description="PostgreSQL schema name")
    db_apply_migrations: bool = Field(
        default=False, description="Auto-apply migrations on startup (dev only)"
    )
    db_compat_mode: bool = Field(
        default=False, description="Use minimal 2-table schema for restricted environments"
    )
    use_jsonb: bool = Field(default=True, description="Use JSONB columns (else TEXT JSON)")

    # Database pool settings
    db_pool_size: int = Field(default=10, description="Database connection pool size")
    db_max_overflow: int = Field(default=20, description="Max overflow connections")
    db_pool_recycle: int = Field(default=1800, description="Pool recycle time in seconds")

    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0", description="Redis connection URL")

    # Celery
    celery_broker_url: str = Field(
        default="redis://localhost:6379/0", description="Celery broker URL"
    )
    celery_result_backend: str = Field(
        default="redis://localhost:6379/0", description="Celery result backend URL"
    )

    # Security
    api_keys: str = Field(
        default="dev-key-123", description="Comma-separated API keys for authentication"
    )

    # Provider API Keys
    openai_api_key: str = Field(default="", description="OpenAI API key")
    google_api_key: str = Field(default="", description="Google/Gemini API key")
    perplexity_api_key: str = Field(default="", description="Perplexity API key")

    # Provider Feature Flags (TICKET 4)
    enable_openai: bool = Field(default=True, description="Enable OpenAI provider")
    enable_gemini: bool = Field(default=False, description="Enable Gemini provider")
    enable_perplexity: bool = Field(default=False, description="Enable Perplexity provider")

    # Logging
    log_level: str = Field(default="INFO", description="Logging level")

    # Rate Limiting
    openai_rate_limit_qps: int = Field(default=5, description="OpenAI QPS limit")
    openai_rate_limit_burst: int = Field(default=10, description="OpenAI burst limit")
    gemini_rate_limit_qps: int = Field(default=3, description="Gemini QPS limit")
    gemini_rate_limit_burst: int = Field(default=5, description="Gemini burst limit")
    perplexity_rate_limit_qps: int = Field(default=3, description="Perplexity QPS limit")
    perplexity_rate_limit_burst: int = Field(default=5, description="Perplexity burst limit")

    # Provider Settings (TICKET 6 - Determinism first)
    default_temperature: float = Field(default=0.0, description="Default temperature")
    default_top_p: float = Field(default=1.0, description="Default top_p")
    default_max_tokens: int = Field(default=1000, description="Default max tokens")

    # Cost Tracking (TICKET 3) - Prices in USD per 1K tokens
    openai_gpt4o_mini_input_per_1k: float = Field(default=0.15)
    openai_gpt4o_mini_output_per_1k: float = Field(default=0.60)
    openai_gpt4o_input_per_1k: float = Field(default=2.50)
    openai_gpt4o_output_per_1k: float = Field(default=10.00)

    # Delivery Queue (TICKET 5)
    max_delivery_attempts: int = Field(default=5, description="Max delivery retry attempts")
    delivery_retry_backoff_base: int = Field(
        default=2, description="Exponential backoff base for delivery retries"
    )

    # Application
    app_name: str = Field(default="GSE Visibility Engine", description="Application name")
    app_version: str = Field(default="0.1.0", description="Application version")

    def get_api_keys_list(self) -> List[str]:
        """Parse comma-separated API keys."""
        return [k.strip() for k in self.api_keys.split(",") if k.strip()]

    def get_enabled_providers(self) -> List[str]:
        """Get list of enabled provider names."""
        providers = []
        if self.enable_openai:
            providers.append("openai")
        if self.enable_gemini:
            providers.append("gemini")
        if self.enable_perplexity:
            providers.append("perplexity")
        return providers

    def get_provider_rate_limits(self, provider: str) -> Dict[str, int]:
        """Get rate limit configuration for a provider."""
        limits = {
            "openai": {"qps": self.openai_rate_limit_qps, "burst": self.openai_rate_limit_burst},
            "gemini": {"qps": self.gemini_rate_limit_qps, "burst": self.gemini_rate_limit_burst},
            "perplexity": {
                "qps": self.perplexity_rate_limit_qps,
                "burst": self.perplexity_rate_limit_burst,
            },
        }
        return limits.get(provider, {"qps": 1, "burst": 1})

    def get_model_pricing(self, provider: str, model: str) -> Dict[str, float]:
        """Get pricing for a specific model (TICKET 3)."""
        # Format: provider:model → pricing
        pricing_map = {
            "openai:gpt-4o-mini": {
                "input_per_1k": self.openai_gpt4o_mini_input_per_1k,
                "output_per_1k": self.openai_gpt4o_mini_output_per_1k,
            },
            "openai:gpt-4o": {
                "input_per_1k": self.openai_gpt4o_input_per_1k,
                "output_per_1k": self.openai_gpt4o_output_per_1k,
            },
            # GPT-5 placeholder (use gpt-4o pricing until known)
            "openai:gpt-5-large": {
                "input_per_1k": self.openai_gpt4o_input_per_1k,
                "output_per_1k": self.openai_gpt4o_output_per_1k,
            },
        }
        key = f"{provider}:{model}"
        return pricing_map.get(key, {"input_per_1k": 0.0, "output_per_1k": 0.0})


# Global settings instance
settings = Settings()


