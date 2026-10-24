from unittest.mock import AsyncMock

import httpx
import pytest

from app.api import routes
from app.config import Settings, get_settings
from app.main import create_app
from app.models import UserOperationGasEstimate
from app.services.json_rpc import JsonRpcError


OPERATION_HASH = "0x" + "ab" * 32


@pytest.mark.api
@pytest.mark.asyncio
async def test_config_exposes_only_public_values(api_client):
    response = await api_client.get("/api/v1/config")
    assert response.status_code == 200
    assert response.json() == {
        "chain_id": 84532,
        "chain_name": "Base Sepolia",
        "entry_point_address": "0x0000000071727de22e5e9d8baf0edac6f37da032",
        "wallet_factory_address": "0x1111111111111111111111111111111111111111",
        "backend_configured": True,
    }
    assert "rpc_url" not in response.json()


@pytest.mark.api
@pytest.mark.asyncio
async def test_health_reports_healthy_dependencies(api_client, monkeypatch):
    monkeypatch.setattr(routes.JsonRpcClient, "call", AsyncMock(return_value="0x14a34"))
    monkeypatch.setattr(
        routes.BundlerClient,
        "supported_entry_points",
        AsyncMock(return_value=["0x0000000071727de22e5e9d8baf0edac6f37da032"]),
    )
    response = await api_client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["chain"] == {
        "status": "ok",
        "chain_id": 84532,
        "detail": None,
    }


@pytest.mark.api
@pytest.mark.asyncio
async def test_health_reports_wrong_chain_and_unsupported_entrypoint(api_client, monkeypatch):
    monkeypatch.setattr(routes.JsonRpcClient, "call", AsyncMock(return_value="0x1"))
    monkeypatch.setattr(
        routes.BundlerClient,
        "supported_entry_points",
        AsyncMock(return_value=["0x2222222222222222222222222222222222222222"]),
    )
    body = (await api_client.get("/api/v1/health")).json()
    assert body["status"] == "degraded"
    assert body["chain"]["chain_id"] == 1
    assert "Expected chain" in body["chain"]["detail"]
    assert "not supported" in body["bundler"]["detail"]


@pytest.mark.api
@pytest.mark.asyncio
async def test_health_reports_provider_errors(api_client, monkeypatch):
    monkeypatch.setattr(
        routes.JsonRpcClient,
        "call",
        AsyncMock(side_effect=RuntimeError("bad chain response")),
    )
    monkeypatch.setattr(
        routes.BundlerClient,
        "supported_entry_points",
        AsyncMock(side_effect=JsonRpcError(-32000, "bundler offline")),
    )
    body = (await api_client.get("/api/v1/health")).json()
    assert body["chain"]["status"] == "unreachable"
    assert body["bundler"]["status"] == "unreachable"


@pytest.mark.api
@pytest.mark.asyncio
async def test_health_is_degraded_when_unconfigured():
    settings = Settings(_env_file=None)
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/health")
    assert response.json()["chain"]["status"] == "unconfigured"
    assert response.json()["bundler"]["status"] == "unconfigured"


@pytest.mark.api
@pytest.mark.asyncio
async def test_submit_user_operation_success(api_client, operation_payload, monkeypatch):
    send = AsyncMock(return_value=OPERATION_HASH)
    monkeypatch.setattr(routes.BundlerClient, "send_user_operation", send)
    response = await api_client.post(
        "/api/v1/user-operations", json={"user_operation": operation_payload}
    )
    assert response.status_code == 202
    assert response.json() == {"user_operation_hash": OPERATION_HASH}
    send.assert_awaited_once()


@pytest.mark.api
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error,status_code,detail",
    [
        (JsonRpcError(-32500, "AA23 reverted", "0xbeef"), 422, "AA23 reverted"),
        (httpx.ConnectError("offline"), 502, "Bundler request failed"),
        (RuntimeError("bad response"), 502, "Bundler returned an invalid response"),
    ],
)
async def test_submit_user_operation_maps_failures(
    api_client, operation_payload, monkeypatch, error, status_code, detail
):
    monkeypatch.setattr(
        routes.BundlerClient, "send_user_operation", AsyncMock(side_effect=error)
    )
    response = await api_client.post(
        "/api/v1/user-operations", json={"user_operation": operation_payload}
    )
    assert response.status_code == status_code
    assert detail in str(response.json()["detail"])


@pytest.mark.api
@pytest.mark.asyncio
async def test_estimate_and_receipt_endpoints(api_client, operation_payload, monkeypatch):
    monkeypatch.setattr(
        routes.BundlerClient,
        "estimate_user_operation_gas",
        AsyncMock(
            return_value=UserOperationGasEstimate(
                preVerificationGas="0x5208",
                verificationGasLimit="0x186a0",
                callGasLimit="0x30d40",
            )
        ),
    )
    monkeypatch.setattr(
        routes.BundlerClient,
        "get_user_operation_receipt",
        AsyncMock(return_value={"success": True}),
    )
    estimate = await api_client.post(
        "/api/v1/user-operations/estimate",
        json={"user_operation": operation_payload},
    )
    receipt = await api_client.get(f"/api/v1/user-operations/{OPERATION_HASH}")
    assert estimate.status_code == 200
    assert estimate.json()["callGasLimit"] == "0x30d40"
    assert receipt.json() == {
        "user_operation_hash": OPERATION_HASH,
        "receipt": {"success": True},
    }


@pytest.mark.api
@pytest.mark.asyncio
async def test_invalid_operation_and_hash_return_422(api_client, operation_payload):
    operation_payload["nonce"] = "0x00"
    operation_response = await api_client.post(
        "/api/v1/user-operations", json={"user_operation": operation_payload}
    )
    hash_response = await api_client.get("/api/v1/user-operations/0x1234")
    assert operation_response.status_code == 422
    assert hash_response.status_code == 422


@pytest.mark.api
@pytest.mark.asyncio
async def test_bundler_endpoints_return_503_when_unconfigured(operation_payload):
    settings = Settings(_env_file=None)
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/user-operations", json={"user_operation": operation_payload}
        )
    assert response.status_code == 503
