from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, Field


def _validate_hex(value: object) -> str:
    if not isinstance(value, str) or not value.startswith("0x"):
        raise ValueError("must be a 0x-prefixed hexadecimal string")
    payload = value[2:]
    if len(payload) % 2:
        raise ValueError("hexadecimal data must contain complete bytes")
    int(payload or "0", 16)
    return value.lower()


HexData = Annotated[str, BeforeValidator(_validate_hex)]


def _validate_quantity(value: object) -> str:
    if not isinstance(value, str) or not value.startswith("0x"):
        raise ValueError("must be a 0x-prefixed hexadecimal quantity")
    payload = value[2:].lower()
    if not payload or (len(payload) > 1 and payload.startswith("0")):
        raise ValueError("quantity must use canonical Ethereum encoding")
    try:
        int(payload, 16)
    except ValueError as exc:
        raise ValueError("quantity must contain valid hexadecimal characters") from exc
    return f"0x{payload}"


def _validate_address(value: object) -> str:
    if not isinstance(value, str) or not value.startswith("0x") or len(value) != 42:
        raise ValueError("must be a 20-byte 0x-prefixed address")
    try:
        int(value[2:], 16)
    except ValueError as exc:
        raise ValueError("address must contain valid hexadecimal characters") from exc
    return value.lower()


def _validate_hash(value: object) -> str:
    normalized = _validate_hex(value)
    if len(normalized) != 66:
        raise ValueError("must be a 32-byte hash")
    return normalized


HexQuantity = Annotated[str, BeforeValidator(_validate_quantity)]
Address = Annotated[str, BeforeValidator(_validate_address)]
Hash32 = Annotated[str, BeforeValidator(_validate_hash)]


class PackedUserOperation(BaseModel):
    sender: Address
    nonce: HexQuantity
    init_code: HexData = Field(alias="initCode")
    call_data: HexData = Field(alias="callData")
    account_gas_limits: HexData = Field(alias="accountGasLimits")
    pre_verification_gas: HexQuantity = Field(alias="preVerificationGas")
    gas_fees: HexData = Field(alias="gasFees")
    paymaster_and_data: HexData = Field(alias="paymasterAndData")
    signature: HexData

    model_config = {"populate_by_name": True}


class SubmitUserOperationRequest(BaseModel):
    user_operation: PackedUserOperation


class SubmitUserOperationResponse(BaseModel):
    user_operation_hash: Hash32


class EstimateUserOperationRequest(BaseModel):
    user_operation: PackedUserOperation


class UserOperationGasEstimate(BaseModel):
    pre_verification_gas: HexQuantity = Field(alias="preVerificationGas")
    verification_gas_limit: HexQuantity = Field(alias="verificationGasLimit")
    call_gas_limit: HexQuantity = Field(alias="callGasLimit")
    paymaster_verification_gas_limit: HexQuantity | None = Field(
        default=None, alias="paymasterVerificationGasLimit"
    )
    paymaster_post_op_gas_limit: HexQuantity | None = Field(
        default=None, alias="paymasterPostOpGasLimit"
    )

    model_config = {"populate_by_name": True}


class UserOperationReceiptResponse(BaseModel):
    user_operation_hash: Hash32
    receipt: dict[str, Any] | None


class RpcHealth(BaseModel):
    status: Literal["ok", "unconfigured", "unreachable"]
    chain_id: int | None = None
    detail: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    environment: str
    chain: RpcHealth
    bundler: RpcHealth


class PublicConfig(BaseModel):
    chain_id: int
    chain_name: str
    entry_point_address: str | None
    wallet_factory_address: str | None
    backend_configured: bool
