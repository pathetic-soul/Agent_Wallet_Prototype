import asyncio

import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from app.config import Settings, get_settings
from app.models import (
    EstimateUserOperationRequest,
    Hash32,
    HealthResponse,
    PublicConfig,
    RpcHealth,
    SubmitUserOperationRequest,
    SubmitUserOperationResponse,
    UserOperationGasEstimate,
    UserOperationReceiptResponse,
)
from app.services.bundler import BundlerClient
from app.services.json_rpc import JsonRpcClient, JsonRpcError


router = APIRouter(prefix="/api/v1")


def _bundler_from_settings(settings: Settings) -> BundlerClient:
    if settings.bundler_rpc_url is None or settings.entry_point_address is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Bundler is not configured",
        )
    return BundlerClient(str(settings.bundler_rpc_url), settings.entry_point_address)


def _raise_bundler_error(exc: Exception) -> None:
    if isinstance(exc, JsonRpcError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": exc.code, "message": str(exc), "data": exc.data},
        ) from exc
    if isinstance(exc, httpx.HTTPError):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Bundler request failed",
        ) from exc
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="Bundler returned an invalid response",
    ) from exc


async def _chain_health(settings: Settings) -> RpcHealth:
    if settings.rpc_url is None:
        return RpcHealth(status="unconfigured", detail="RPC_URL is not set")
    try:
        result = await JsonRpcClient(str(settings.rpc_url)).call("eth_chainId")
        chain_id = int(result, 16)
        if chain_id != settings.chain_id:
            return RpcHealth(
                status="unreachable",
                chain_id=chain_id,
                detail=f"Expected chain {settings.chain_id}, received {chain_id}",
            )
        return RpcHealth(status="ok", chain_id=chain_id)
    except (httpx.HTTPError, JsonRpcError, RuntimeError, ValueError) as exc:
        return RpcHealth(status="unreachable", detail=str(exc))


async def _bundler_health(settings: Settings) -> RpcHealth:
    if settings.bundler_rpc_url is None or settings.entry_point_address is None:
        return RpcHealth(
            status="unconfigured",
            detail="BUNDLER_RPC_URL and ENTRY_POINT_ADDRESS are required",
        )
    try:
        supported = await BundlerClient(
            str(settings.bundler_rpc_url), settings.entry_point_address
        ).supported_entry_points()
        if settings.entry_point_address.lower() not in supported:
            return RpcHealth(
                status="unreachable",
                detail="Configured EntryPoint is not supported by the bundler",
            )
        return RpcHealth(status="ok", chain_id=settings.chain_id)
    except (httpx.HTTPError, JsonRpcError, RuntimeError, ValueError) as exc:
        return RpcHealth(status="unreachable", detail=str(exc))


@router.get("/health", response_model=HealthResponse)
async def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    chain, bundler = await asyncio.gather(
        _chain_health(settings), _bundler_health(settings)
    )
    overall = "ok" if chain.status == bundler.status == "ok" else "degraded"
    return HealthResponse(
        status=overall,
        environment=settings.app_env,
        chain=chain,
        bundler=bundler,
    )


@router.get("/config", response_model=PublicConfig)
async def public_config(settings: Settings = Depends(get_settings)) -> PublicConfig:
    return PublicConfig(
        chain_id=settings.chain_id,
        chain_name=settings.chain_name,
        entry_point_address=settings.entry_point_address,
        wallet_factory_address=settings.wallet_factory_address,
        backend_configured=settings.configured,
    )


@router.post(
    "/user-operations",
    response_model=SubmitUserOperationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_user_operation(
    request: SubmitUserOperationRequest,
    settings: Settings = Depends(get_settings),
) -> SubmitUserOperationResponse:
    bundler = _bundler_from_settings(settings)
    try:
        operation_hash = await bundler.send_user_operation(request.user_operation)
    except (JsonRpcError, httpx.HTTPError, RuntimeError) as exc:
        _raise_bundler_error(exc)
    return SubmitUserOperationResponse(user_operation_hash=operation_hash)


@router.post(
    "/user-operations/estimate",
    response_model=UserOperationGasEstimate,
)
async def estimate_user_operation(
    request: EstimateUserOperationRequest,
    settings: Settings = Depends(get_settings),
) -> UserOperationGasEstimate:
    bundler = _bundler_from_settings(settings)
    try:
        return await bundler.estimate_user_operation_gas(request.user_operation)
    except (JsonRpcError, httpx.HTTPError, RuntimeError, ValueError) as exc:
        _raise_bundler_error(exc)


@router.get(
    "/user-operations/{user_operation_hash}",
    response_model=UserOperationReceiptResponse,
)
async def get_user_operation_receipt(
    user_operation_hash: Hash32,
    settings: Settings = Depends(get_settings),
) -> UserOperationReceiptResponse:
    bundler = _bundler_from_settings(settings)
    try:
        receipt = await bundler.get_user_operation_receipt(user_operation_hash)
    except (JsonRpcError, httpx.HTTPError, RuntimeError) as exc:
        _raise_bundler_error(exc)
    return UserOperationReceiptResponse(
        user_operation_hash=user_operation_hash,
        receipt=receipt,
    )
