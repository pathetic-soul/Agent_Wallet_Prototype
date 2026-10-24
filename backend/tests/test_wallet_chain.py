import json
from unittest.mock import AsyncMock

import httpx
import pytest
from eth_abi import decode, encode
from eth_account import Account
from eth_utils import function_signature_to_4byte_selector

from app.api import routes
from app.config import Settings, get_settings
from app.main import create_app
from app.services.json_rpc import JsonRpcClient, JsonRpcError
from app.services.wallet_chain import (
    OwnerTransactionError,
    WalletChain,
    _selector,
    _usd,
)

WALLET = "0x" + "11" * 20
AGENT = "0x" + "22" * 20
TARGET = "0x" + "33" * 20
OWNER_KEY = "0x" + "ab" * 32
OWNER = Account.from_key(OWNER_KEY).address
CALLS_TYPE = "(address,uint256,bytes)[]"


def sel(signature: str) -> bytes:
    return function_signature_to_4byte_selector(signature)


def pending_entry(status: int, reason: int, usd: int, data: bytes):
    calls = encode([CALLS_TYPE], [[(TARGET, 5, data)]])
    return (AGENT, 100, 3700, status, reason, usd, calls)


class FakeChain:
    """Answers the JSON-RPC calls WalletChain makes, keyed by 4-byte selector."""

    def __init__(self, receipt_status: str | None = "0x1", base_fee: str = "0x3b9aca00"):
        self.sent: list[str] = []
        self.receipt_status = receipt_status
        self.base_fee = base_fee
        self.pending = {
            1: pending_entry(1, 0, 3_500_000_000, sel("buyTicket(address)") + b"\x00" * 32),
            2: pending_entry(3, 2, 0, b""),
        }

    def eth_call(self, params):
        data = bytes.fromhex(params[0]["data"][2:])
        head, body = data[:4], data[4:]
        table = {
            sel("owner()"): lambda: encode(["address"], [OWNER]),
            sel("paused()"): lambda: encode(["bool"], [False]),
            sel("perTransactionLimitUsd()"): lambda: encode(["uint256"], [20 * 10**8]),
            sel("dailyLimitUsd()"): lambda: encode(["uint256"], [50 * 10**8]),
            sel("spentInWindowUsd()"): lambda: encode(["uint256"], [1_050_000_000]),
            sel("nextPendingId()"): lambda: encode(["uint256"], [len(self.pending) + 1]),
        }
        if head == sel("getPending(uint256)"):
            (pid,) = decode(["uint256"], body)
            return "0x" + encode(["(address,uint48,uint48,uint8,uint8,uint256,bytes)"], [self.pending[pid]]).hex()
        return "0x" + table[head]().hex()

    def __call__(self, request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        method, params = payload["method"], payload["params"]
        results = {
            "eth_call": lambda: self.eth_call(params),
            "eth_getTransactionCount": lambda: "0x5",
            "eth_getBlockByNumber": lambda: {"baseFeePerGas": self.base_fee},
            "eth_estimateGas": lambda: "0x5208",
            "eth_chainId": lambda: "0x7a69",
            "eth_sendRawTransaction": lambda: self.sent.append(params[0]) or "0x" + "cd" * 32,
            "eth_getTransactionReceipt": lambda: (
                {"status": self.receipt_status} if self.receipt_status else None
            ),
        }
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": payload["id"], "result": results[method]()})


def chain_for(fake: FakeChain) -> WalletChain:
    rpc = JsonRpcClient("https://rpc.test", transport=httpx.MockTransport(fake))
    return WalletChain("https://rpc.test", WALLET, rpc=rpc)


@pytest.mark.unit
def test_helpers_format_usd_and_selectors():
    assert _usd(3_500_000_000) == "35.00"
    assert _usd(1_050_000_000) == "10.50"
    assert _usd(0) == "0.00"
    assert _selector("approvePending(uint256)") == "0x" + sel("approvePending(uint256)").hex()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_summary_decodes_wallet_state():
    summary = await chain_for(FakeChain()).summary()
    assert summary == {
        "address": WALLET,
        "owner": OWNER.lower(),
        "paused": False,
        "per_transaction_limit_usd": "20.00",
        "daily_limit_usd": "50.00",
        "spent_in_window_usd": "10.50",
        "next_pending_id": 3,
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_pending_requests_are_decoded_newest_first():
    requests = await chain_for(FakeChain()).pending_requests()
    assert [r["id"] for r in requests] == [2, 1]
    open_request = requests[1]
    assert open_request["status"] == "open"
    assert open_request["reason"] == "over_per_transaction_limit"
    assert open_request["usd_value"] == "35.00"
    assert open_request["agent"] == AGENT
    assert open_request["calls"][0]["target"] == TARGET
    assert open_request["calls"][0]["value"] == "5"
    assert open_request["calls"][0]["selector"] == "0x" + sel("buyTicket(address)").hex()
    assert requests[0]["status"] == "rejected" and requests[0]["reason"] == "pricing_failed"
    assert requests[0]["calls"][0]["selector"] == "0x"  # call without calldata


@pytest.mark.unit
@pytest.mark.asyncio
async def test_pending_requests_empty_when_none_created():
    fake = FakeChain()
    fake.pending = {}
    assert await chain_for(fake).pending_requests() == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_owner_transaction_signs_and_returns_hash():
    fake = FakeChain()
    tx_hash = await chain_for(fake).owner_transaction(OWNER_KEY, "approvePending(uint256)", ["uint256"], [1])
    assert tx_hash == "0x" + "cd" * 32
    assert len(fake.sent) == 1 and fake.sent[0].startswith("0x")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_owner_transaction_reports_revert():
    with pytest.raises(OwnerTransactionError, match="reverted"):
        await chain_for(FakeChain(receipt_status="0x0")).owner_transaction(
            OWNER_KEY, "approvePending(uint256)", ["uint256"], [1]
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_owner_transaction_times_out_without_receipt(monkeypatch):
    monkeypatch.setattr("app.services.wallet_chain.asyncio.sleep", AsyncMock())
    with pytest.raises(OwnerTransactionError, match="Timed out"):
        await chain_for(FakeChain(receipt_status=None)).owner_transaction(
            OWNER_KEY, "rejectPending(uint256)", ["uint256"], [1]
        )


@pytest.fixture
def wallet_settings() -> Settings:
    return Settings(
        _env_file=None,
        rpc_url="https://rpc.example.test",
        wallet_address=WALLET,
        demo_owner_private_key=OWNER_KEY,
    )


async def client_for(settings: Settings):
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")


@pytest.mark.api
@pytest.mark.asyncio
async def test_wallet_endpoints_require_configuration(api_client):
    for path in ("/api/v1/wallet/summary", "/api/v1/wallet/pending"):
        assert (await api_client.get(path)).status_code == 503
    assert (await api_client.post("/api/v1/wallet/pending/1/approve")).status_code == 503


@pytest.mark.api
@pytest.mark.asyncio
async def test_summary_and_pending_endpoints(wallet_settings, monkeypatch):
    fake = FakeChain()
    monkeypatch.setattr(
        routes, "WalletReader", lambda url, wallet: chain_for(fake)
    )
    async with await client_for(wallet_settings) as client:
        summary = await client.get("/api/v1/wallet/summary")
        pending = await client.get("/api/v1/wallet/pending")
    assert summary.json()["daily_limit_usd"] == "50.00"
    assert [item["id"] for item in pending.json()] == [2, 1]


@pytest.mark.api
@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["approve", "reject"])
async def test_owner_actions_relay_with_demo_signer(wallet_settings, monkeypatch, action):
    fake = FakeChain()
    monkeypatch.setattr(routes, "WalletReader", lambda url, wallet: chain_for(fake))
    async with await client_for(wallet_settings) as client:
        response = await client.post(f"/api/v1/wallet/pending/1/{action}")
    assert response.status_code == 200
    assert response.json() == {"transaction_hash": "0x" + "cd" * 32}


@pytest.mark.api
@pytest.mark.asyncio
async def test_owner_actions_are_forbidden_without_demo_signer():
    settings = Settings(_env_file=None, rpc_url="https://rpc.example.test", wallet_address=WALLET)
    async with await client_for(settings) as client:
        response = await client.post("/api/v1/wallet/pending/1/approve")
    assert response.status_code == 403
    assert "owner" in response.json()["detail"]


@pytest.mark.api
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "status"),
    [
        (JsonRpcError(3, "execution reverted", "0x"), 422),
        (OwnerTransactionError("Owner transaction reverted"), 409),
        (httpx.ConnectError("down"), 502),
    ],
)
async def test_chain_errors_map_to_http_statuses(wallet_settings, monkeypatch, error, status):
    fake = FakeChain()
    chain = chain_for(fake)
    chain.owner_transaction = AsyncMock(side_effect=error)
    chain.summary = AsyncMock(side_effect=error)
    monkeypatch.setattr(routes, "WalletReader", lambda url, wallet: chain)
    async with await client_for(wallet_settings) as client:
        approve = await client.post("/api/v1/wallet/pending/1/approve")
        summary = await client.get("/api/v1/wallet/summary")
    assert approve.status_code == status
    assert summary.status_code == status


@pytest.mark.api
@pytest.mark.asyncio
async def test_pending_endpoint_maps_chain_failure(wallet_settings, monkeypatch):
    chain = chain_for(FakeChain())
    chain.pending_requests = AsyncMock(side_effect=httpx.ConnectError("down"))
    monkeypatch.setattr(routes, "WalletReader", lambda url, wallet: chain)
    async with await client_for(wallet_settings) as client:
        response = await client.get("/api/v1/wallet/pending")
    assert response.status_code == 502


@pytest.mark.api
@pytest.mark.asyncio
async def test_public_config_flags_demo_signer_without_leaking_key(wallet_settings):
    async with await client_for(wallet_settings) as client:
        body = (await client.get("/api/v1/config")).json()
    assert body["owner_signer_enabled"] is True
    assert body["wallet_address"] == WALLET
    assert OWNER_KEY not in json.dumps(body)
