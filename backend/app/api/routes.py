import asyncio
from decimal import Decimal
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.config import Settings, get_settings
from app.models import (
    AgentRequest,
    AttackResult,
    CallPolicyRequest,
    EstimateUserOperationRequest,
    Hash32,
    HealthResponse,
    OwnerActionResponse,
    PauseRequest,
    PendingRequestView,
    RecipientPolicyRequest,
    SessionRequest,
    SpendPolicyRequest,
    PublicConfig,
    RpcHealth,
    SubmitUserOperationRequest,
    SubmitUserOperationResponse,
    UserOperationGasEstimate,
    UserOperationReceiptResponse,
    WalletSummary,
)
from app.services.bundler import BundlerClient
from app.services.json_rpc import JsonRpcClient, JsonRpcError
from app.services.demo_attacks import ATTACKS, AttackSetupError, DemoAttacks
from app.services.telemetry import TelemetryLog
from app.services.wallet_chain import OwnerTransactionError
from app.services.wallet_reader import WalletReader


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
        wallet_address=settings.wallet_address,
        owner_signer_enabled=settings.demo_owner_private_key is not None,
        attack_console_enabled=settings.attack_console_enabled,
        backend_configured=settings.configured,
    )


@router.post(
    "/user-operations",
    response_model=SubmitUserOperationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_user_operation(
    request: SubmitUserOperationRequest,
    http_request: Request,
    settings: Settings = Depends(get_settings),
) -> SubmitUserOperationResponse:
    bundler = _bundler_from_settings(settings)
    try:
        operation_hash = await bundler.send_user_operation(request.user_operation)
    except (JsonRpcError, httpx.HTTPError, RuntimeError) as exc:
        if isinstance(exc, JsonRpcError):
            http_request.app.state.telemetry.record(
                "blocked_operation",
                "Rejected UserOperation",
                f"sender {request.user_operation.sender}",
                str(exc),
            )
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


def _wallet_from_settings(settings: Settings) -> WalletReader:
    if settings.rpc_url is None or settings.wallet_address is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RPC_URL and WALLET_ADDRESS are required",
        )
    return WalletReader(str(settings.rpc_url), settings.wallet_address)


def _raise_chain_error(exc: Exception) -> None:
    if isinstance(exc, JsonRpcError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": exc.code, "message": str(exc), "data": exc.data},
        ) from exc
    if isinstance(exc, OwnerTransactionError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY, detail="Chain request failed"
    ) from exc


CHAIN_ERRORS = (JsonRpcError, OwnerTransactionError, httpx.HTTPError, RuntimeError, ValueError)


@router.get("/wallet/summary", response_model=WalletSummary)
async def wallet_summary(settings: Settings = Depends(get_settings)) -> WalletSummary:
    wallet = _wallet_from_settings(settings)
    try:
        return WalletSummary(**await wallet.summary())
    except CHAIN_ERRORS as exc:
        _raise_chain_error(exc)


@router.get("/wallet/pending", response_model=list[PendingRequestView])
async def wallet_pending(
    settings: Settings = Depends(get_settings),
) -> list[PendingRequestView]:
    wallet = _wallet_from_settings(settings)
    try:
        return [PendingRequestView(**item) for item in await wallet.pending_requests()]
    except CHAIN_ERRORS as exc:
        _raise_chain_error(exc)


async def _owner_call(
    settings: Settings, signature: str, types: list[str], values: list[Any]
) -> OwnerActionResponse:
    wallet = _wallet_from_settings(settings)
    if settings.demo_owner_private_key is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owner actions must be signed in the owner's wallet; no demo signer is configured",
        )
    try:
        tx_hash = await wallet.owner_transaction(
            settings.demo_owner_private_key.get_secret_value(), signature, types, values
        )
    except CHAIN_ERRORS as exc:
        _raise_chain_error(exc)
    return OwnerActionResponse(transaction_hash=tx_hash)


async def _owner_action(
    settings: Settings, signature: str, request_id: int
) -> OwnerActionResponse:
    return await _owner_call(settings, signature, ["uint256"], [request_id])


@router.post("/wallet/pending/{request_id}/approve", response_model=OwnerActionResponse)
async def approve_pending(
    request_id: int, settings: Settings = Depends(get_settings)
) -> OwnerActionResponse:
    return await _owner_action(settings, "approvePending(uint256)", request_id)


@router.post("/wallet/pending/{request_id}/reject", response_model=OwnerActionResponse)
async def reject_pending(
    request_id: int, settings: Settings = Depends(get_settings)
) -> OwnerActionResponse:
    return await _owner_action(settings, "rejectPending(uint256)", request_id)


def _usd_e8(amount: str) -> int:
    return int(Decimal(amount) * 10**8)


@router.get("/wallet/overview")
async def wallet_overview(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    wallet = _wallet_from_settings(settings)
    try:
        return await wallet.overview()
    except CHAIN_ERRORS as exc:
        _raise_chain_error(exc)


@router.get("/wallet/policy")
async def wallet_policy(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    wallet = _wallet_from_settings(settings)
    try:
        return await wallet.policy()
    except CHAIN_ERRORS as exc:
        _raise_chain_error(exc)


def _telemetry_item(index: int, event: dict[str, Any]) -> dict[str, Any]:
    prefix = "Rejected by EntryPoint simulation: "
    reason = event["reason"].removeprefix(prefix)
    executed = event["outcome"] == "executed"
    return {
        "id": f"relay-{event['timestamp']}-{index}",
        "timestamp": event["timestamp"],
        "icon": "shield",
        "title": event["title"],
        "detail": event["detail"],
        "usd": None,
        "status": "Allowed" if executed else "Blocked",
        "result": "ACCEPTED - unexpected" if executed else reason,
        "tx_hash": None,
        "source": "relay",
    }


@router.get("/wallet/activity")
async def wallet_activity(
    http_request: Request, settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    wallet = _wallet_from_settings(settings)
    telemetry: TelemetryLog = http_request.app.state.telemetry
    try:
        chain_items = await wallet.activity()
    except CHAIN_ERRORS as exc:
        _raise_chain_error(exc)
    relay_items = [_telemetry_item(i, e) for i, e in enumerate(telemetry.list())]
    merged = sorted(chain_items + relay_items, key=lambda item: item["timestamp"], reverse=True)
    return {
        "items": merged,
        "blocked_attempts": sum(1 for item in relay_items if item["status"] == "Blocked"),
        "note": "Blocked attempts come from this API's in-memory relay log; they are not on-chain events.",
    }


@router.post("/wallet/owner/pause", response_model=OwnerActionResponse)
async def owner_pause(body: PauseRequest, settings: Settings = Depends(get_settings)) -> OwnerActionResponse:
    return await _owner_call(settings, "setPaused(bool)", ["bool"], [body.paused])


@router.post("/wallet/owner/sessions/revoke", response_model=OwnerActionResponse)
async def owner_revoke_session(body: AgentRequest, settings: Settings = Depends(get_settings)) -> OwnerActionResponse:
    return await _owner_call(settings, "revokeSession(address)", ["address"], [body.agent])


@router.post("/wallet/owner/sessions", response_model=OwnerActionResponse)
async def owner_add_session(body: SessionRequest, settings: Settings = Depends(get_settings)) -> OwnerActionResponse:
    wallet = _wallet_from_settings(settings)
    try:
        now = await wallet.chain_time()
    except CHAIN_ERRORS as exc:
        _raise_chain_error(exc)
    return await _owner_call(
        settings, "addSession(address,uint48,uint48)", ["address", "uint48", "uint48"],
        [body.agent, 0, now + body.valid_for_seconds],
    )


@router.post("/wallet/owner/spend-policy", response_model=OwnerActionResponse)
async def owner_spend_policy(body: SpendPolicyRequest, settings: Settings = Depends(get_settings)) -> OwnerActionResponse:
    per_tx, daily = _usd_e8(body.per_transaction_usd), _usd_e8(body.daily_usd)
    if per_tx == 0 or daily < per_tx:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Per-transaction limit must be above zero and not exceed the daily limit",
        )
    return await _owner_call(settings, "setSpendPolicy(uint256,uint256)", ["uint256", "uint256"], [per_tx, daily])


@router.post("/wallet/owner/call-policy", response_model=OwnerActionResponse)
async def owner_call_policy(body: CallPolicyRequest, settings: Settings = Depends(get_settings)) -> OwnerActionResponse:
    return await _owner_call(
        settings, "setCallPolicy(address,bytes4,bool)", ["address", "bytes4", "bool"],
        [body.target, bytes.fromhex(body.selector[2:]), body.allowed],
    )


@router.post("/wallet/owner/recipient-policy", response_model=OwnerActionResponse)
async def owner_recipient_policy(body: RecipientPolicyRequest, settings: Settings = Depends(get_settings)) -> OwnerActionResponse:
    return await _owner_call(settings, "setRecipientPolicy(address,bool)", ["address", "bool"], [body.recipient, body.allowed])


def _attacks_from_settings(settings: Settings) -> DemoAttacks:
    if not settings.attack_console_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Attack console is a local-demo feature and is not enabled",
        )
    return DemoAttacks(
        _wallet_from_settings(settings),
        _bundler_from_settings(settings),
        settings.entry_point_address,
        settings.demo_agent_private_key.get_secret_value(),
        settings.demo_attacker_private_key.get_secret_value(),
    )


@router.get("/demo/attacks")
async def attack_history(http_request: Request, settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    _attacks_from_settings(settings)
    history = http_request.app.state.telemetry.list("attack")
    return {
        "attacks": list(ATTACKS),
        "history": history,
        "attempts": len(history),
        "blocked": sum(1 for h in history if h["outcome"] == "blocked"),
        "executed": sum(1 for h in history if h["outcome"] == "executed"),
    }


@router.post("/demo/attacks/{attack}", response_model=AttackResult)
async def run_attack(
    attack: str, http_request: Request, settings: Settings = Depends(get_settings)
) -> AttackResult:
    runner = _attacks_from_settings(settings)
    if attack not in ATTACKS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown attack")
    try:
        result = await runner.run(attack)
    except AttackSetupError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except CHAIN_ERRORS as exc:
        _raise_chain_error(exc)
    http_request.app.state.telemetry.record(
        "attack", attack, f"agent {runner.agent}", result["reason"] or result["user_operation_hash"] or "", result["outcome"]
    )
    return AttackResult(**result)
