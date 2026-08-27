from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App
    app_env: str = Field(default="development", alias="APP_ENV")
    app_name: str = Field(default="chevstyle-backend", alias="APP_NAME")
    app_debug: bool = Field(default=False, alias="APP_DEBUG")

    # Clerk (authentication)
    clerk_secret_key: str | None = Field(
        default=None, alias="CLERK_SECRET_KEY")
    clerk_publishable_key: str | None = Field(
        default=None, alias="CLERK_PUBLISHABLE_KEY")
    clerk_jwks_url: str | None = Field(default=None, alias="CLERK_JWKS_URL")

    # Convex (database / storage)
    convex_url: str | None = Field(default=None, alias="CONVEX_URL")
    convex_deploy_key: str | None = Field(
        default=None, alias="CONVEX_DEPLOY_KEY")

    # Gemini / AI
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")

    # OpenAI
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")

    # Moondream
    moondream_api_key: str | None = Field(default=None, alias="MOONDREAM_API_KEY")

    # Clerk JWT validation
    clerk_issuer: str | None = Field(default=None, alias="CLERK_ISSUER")
    clerk_audience: str | None = Field(default=None, alias="CLERK_AUDIENCE")

    # Image limits
    allowed_origins: list[str] = Field(default_factory=lambda: ["*"])
    max_image_size_mb: int = Field(default=10)
    min_image_dimension: int = Field(default=256)

    # AI Generation
    ai_provider: str = Field(default="gemini")
    ai_generation_timeout_seconds: int = Field(default=120)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
