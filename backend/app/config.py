from secrets import token_urlsafe
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Staywell Hotel"
    app_env: str = "development"
    database_url: str = "sqlite:///./hotel.db"
    jwt_secret: str = Field(default_factory=lambda: token_urlsafe(48))
    seed_user_password: str | None = None
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 14
    cookie_secure: bool = False
    cors_origins: list[str] = []
    trusted_hosts: list[str] = ["localhost", "127.0.0.1", "testserver"]

    @model_validator(mode="after")
    def validate_production_security(self):
        if self.app_env.lower() == "production":
            if "jwt_secret" not in self.model_fields_set or len(self.jwt_secret) < 32 or self.jwt_secret.startswith("replace-with-"):
                raise ValueError("Production requires a unique JWT_SECRET of at least 32 characters")
            if "trusted_hosts" not in self.model_fields_set:
                raise ValueError("Production requires TRUSTED_HOSTS to be configured explicitly")
            password = self.seed_user_password or ""
            if len(password) < 16 or password.startswith("replace-with-"):
                raise ValueError("Production requires a unique SEED_USER_PASSWORD of at least 16 characters")
            if not any(char.islower() for char in password) or not any(char.isupper() for char in password):
                raise ValueError("Production SEED_USER_PASSWORD must include upper- and lower-case letters")
            if not any(char.isdigit() for char in password) or not any(not char.isalnum() for char in password):
                raise ValueError("Production SEED_USER_PASSWORD must include a number and a symbol")
            if "*" in self.trusted_hosts:
                raise ValueError("Production TRUSTED_HOSTS cannot contain a wildcard")
            self.cookie_secure = True
        return self


settings = Settings()