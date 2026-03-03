from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "Email Reviewer"
    APP_VERSION: str = "0.1.0"
    DATABASE_URL: str = "sqlite+aiosqlite:///email_reviewer.db"
    AUTH_ENABLED: bool = False
    CURRENT_USER: str = "system"
    HUBSPOT_ACCESS_TOKEN: str = ""
    ANTHROPIC_API_KEY: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
