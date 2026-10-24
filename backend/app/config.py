from functools import lru_cache
from typing import Annotated

from pydantic import BeforeValidator, Field, HttpUrl, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def _empty_to_none(value: object) -> object:
    return None if value == "" else value


OptionalUrl = Annotated[HttpUrl | None, BeforeValidator(_empty_to_none)]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = Field(default=8000, ge=1, le=65535)
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]

    chain_id: int = Field(default=84532, gt=0)
    chain_name: str = "Base Sepolia"
    rpc_url: OptionalUrl = None
    bundler_rpc_url: OptionalUrl = None
    entry_point_address: str | None = None
    wallet_factory_address: str | None = None
    wallet_address: str | None = None
    # Local demos only: lets the API relay owner approve/reject calls. Leave empty everywhere else.
    demo_owner_private_key: Annotated[SecretStr | None, BeforeValidator(_empty_to_none)] = None
    # Local demos only: let the attack console sign as the agent and as an unauthorised attacker.
    demo_agent_private_key: Annotated[SecretStr | None, BeforeValidator(_empty_to_none)] = None
    demo_attacker_private_key: Annotated[SecretStr | None, BeforeValidator(_empty_to_none)] = None

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("entry_point_address", "wallet_factory_address", "wallet_address", mode="before")
    @classmethod
    def normalize_optional_address(cls, value: object) -> object:
        if value == "":
            return None
        if value is None:
            return value
        text = str(value)
        if not text.startswith("0x") or len(text) != 42:
            raise ValueError("must be a 20-byte 0x-prefixed address")
        try:
            int(text[2:], 16)
        except ValueError as exc:
            raise ValueError("must contain valid hexadecimal characters") from exc
        return text

    @property
    def attack_console_enabled(self) -> bool:
        return all((self.demo_agent_private_key, self.demo_attacker_private_key, self.wallet_address, self.rpc_url, self.bundler_rpc_url, self.entry_point_address))

    @property
    def configured(self) -> bool:
        return all((self.rpc_url, self.bundler_rpc_url, self.entry_point_address))


@lru_cache
def get_settings() -> Settings:
    return Settings()
