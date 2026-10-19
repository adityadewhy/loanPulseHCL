from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Database
    database_url: str

    # AI Underwriting — Free providers
    gemini_api_key: str = ""
    groq_api_key: str = ""

    # JWT Auth
    secret_key: str = "dev-insecure-secret-change-in-production"
    access_token_expire_hours: int = 24

    # Email (Gmail SMTP — free)
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""

    # Legacy (kept for backward compat, not primary)
    openai_api_key: str = "placeholder"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()