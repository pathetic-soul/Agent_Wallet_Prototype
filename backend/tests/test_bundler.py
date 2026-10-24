from unittest.mock import AsyncMock

import pytest

from app.models import PackedUserOperation
from app.services.bundler import BundlerClient


ENTRY_POINT = "0x0000000071727de22e5e9d8baf0edac6f37da032"


@pytest.fixture
def operation(operation_payload) -> PackedUserOperation:
    return PackedUserOperation.model_validate(operation_payload)


@pytest.fixture
def rpc() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def bundler(rpc) -> BundlerClient:
    return BundlerClient("https://bundler.test", ENTRY_POINT, rpc=rpc)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_supported_entry_points_normalizes_addresses(bundler, rpc):
    rpc.call.return_value = [ENTRY_POINT.upper().replace("0X", "0x")]
    assert await bundler.supported_entry_points() == [ENTRY_POINT]
    rpc.call.assert_awaited_once_with("eth_supportedEntryPoints")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_supported_entry_points_rejects_wrong_shape(bundler, rpc):
    rpc.call.return_value = {"entryPoint": ENTRY_POINT}
    with pytest.raises(RuntimeError, match="entry-point list"):
        await bundler.supported_entry_points()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_user_operation_forwards_alias_payload(bundler, rpc, operation):
    expected_hash = "0x" + "ab" * 32
    rpc.call.return_value = expected_hash.upper().replace("0X", "0x")
    assert await bundler.send_user_operation(operation) == expected_hash
    rpc.call.assert_awaited_once_with(
        "eth_sendUserOperation",
        [operation.model_dump(by_alias=True), ENTRY_POINT],
    )


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("value", [None, 12, "0x1234"])
async def test_send_user_operation_rejects_invalid_hash(bundler, rpc, operation, value):
    rpc.call.return_value = value
    with pytest.raises(RuntimeError, match="invalid UserOperation hash"):
        await bundler.send_user_operation(operation)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_estimate_user_operation_gas_validates_result(bundler, rpc, operation):
    rpc.call.return_value = {
        "preVerificationGas": "0x5208",
        "verificationGasLimit": "0x186a0",
        "callGasLimit": "0x30d40",
    }
    estimate = await bundler.estimate_user_operation_gas(operation)
    assert estimate.call_gas_limit == "0x30d40"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_estimate_rejects_non_object(bundler, rpc, operation):
    rpc.call.return_value = []
    with pytest.raises(RuntimeError, match="invalid gas estimate"):
        await bundler.estimate_user_operation_gas(operation)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_receipt_accepts_pending_and_complete_states(bundler, rpc):
    operation_hash = "0x" + "ab" * 32
    rpc.call.side_effect = [None, {"success": True, "userOpHash": operation_hash}]
    assert await bundler.get_user_operation_receipt(operation_hash) is None
    assert (await bundler.get_user_operation_receipt(operation_hash))["success"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_receipt_rejects_invalid_shape(bundler, rpc):
    rpc.call.return_value = []
    with pytest.raises(RuntimeError, match="invalid UserOperation receipt"):
        await bundler.get_user_operation_receipt("0x" + "ab" * 32)
