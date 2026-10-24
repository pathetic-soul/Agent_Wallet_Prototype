from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio

from app.config import Settings, get_settings
from app.main import create_app


ENV_KEYS = (
    "APP_ENV",
    "APP_HOST",
    "APP_PORT",
    "CORS_ORIGINS",
    "CHAIN_ID",
    "CHAIN_NAME",
    "RPC_URL",
    "BUNDLER_RPC_URL",
    "ENTRY_POINT_ADDRESS",
    "WALLET_FACTORY_ADDRESS",
    "WALLET_ADDRESS",
    "DEMO_OWNER_PRIVATE_KEY",
)


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch):
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def configured_settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        rpc_url="https://rpc.example.test",
        bundler_rpc_url="https://bundler.example.test",
        entry_point_address="0x0000000071727de22e5e9d8baf0edac6f37da032",
        wallet_factory_address="0x1111111111111111111111111111111111111111",
    )


@pytest_asyncio.fixture
async def api_client(configured_settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: configured_settings
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client


@pytest.fixture
def operation_payload() -> dict[str, str]:
    return {
        "sender": "0x1111111111111111111111111111111111111111",
        "nonce": "0x0",
        "initCode": "0x",
        "callData": "0x",
        "accountGasLimits": "0x" + "00" * 32,
        "preVerificationGas": "0x0",
        "gasFees": "0x" + "00" * 32,
        "paymasterAndData": "0x",
        "signature": "0x" + "11" * 65,
    }
