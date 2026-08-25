from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "crm-backend"
    api_prefix: str = "/api"
    database_url: str = "postgresql+psycopg://crm:crm@db:5432/crm"

    # Attachment storage. Paths are resolved relative to the backend working
    # directory; the tree is created lazily on first write.
    attachments_dir: str = "./var/attachments"
    max_upload_bytes: int = 10 * 1024 * 1024

    model_config = SettingsConfigDict(env_file=".env", env_prefix="CRM_", extra="ignore")


settings = Settings()
