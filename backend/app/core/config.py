from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "crm-backend"
    api_prefix: str = "/api"
    database_url: str = "postgresql+psycopg://crm:crm@db:5432/crm"

    model_config = SettingsConfigDict(env_file=".env", env_prefix="CRM_", extra="ignore")


settings = Settings()
