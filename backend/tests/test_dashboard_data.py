import json
from unittest.mock import AsyncMock

import httpx
import pytest
from eth_abi import decode, encode
from eth_account import Account
from eth_utils import function_signature_to_4byte_selector, keccak

from app.api import routes
from app.config import Settings, get_settings
from app.main import create_app
from app.services.bundler import BundlerClient
from app.services.demo_attacks import ATTACKS, AttackSetupError, DemoAttacks
from app.services.json_rpc import JsonRpcClient, JsonRpcError
from app.services.telemetry import TelemetryLog
from app.services.wallet_reader import (
    ORACLE_EVENTS,
    WALLET_EVENTS,
    WalletReader,
    _activity_item,
    decode_log,
)

WALLET = "0x" + "11" * 20
ORACLE = "0x" + "44" * 20
ENTRY = "0x" + "55" * 20
TOKEN = "0x" + "66" * 20
SHOP = "0x" + "77" * 20
AGENT_KEY = "0x" + "a1" * 32
ATTACKER_KEY = "0x" + "b2" * 32
AGENT = Account.from_key(AGENT_KEY).address
ZERO = "0x" + "00" * 20
BUY = "0xa5f8cdbb"


def sel(sig: str) -> bytes:
    return function_signature_to_4byte_selector(sig)


def make_log(address, events, name, **values):
    fields = events[name]
    topic0 = "0x" + keccak(text=f"{name}({','.join(t for t, _, _ in fields)})").hex()
    topics, plain_types, plain_values = [topic0], [], []
    for kind, indexed, field in fields:
        if indexed:
            topics.append("0x" + encode([kind], [values[field]]).hex())
        else:
            plain_types.append(kind)
            plain_values.append(values[field])
    return {
        "address": address, "topics": topics, "data": "0x" + encode(plain_types, plain_values).hex(),
        "blockNumber": hex(values.get("_block", 1)), "logIndex": hex(values.get("_idx", 0)), "transactionHash": "0x" + "ee" * 32,
    }


def wallet_logs():
    w = WALLET_EVENTS
    return [
        make_log(WALLET, w, "SessionAdded", agent=AGENT, valid_after=0, valid_until=2_000_000_000, _block=1),
        make_log(WALLET, w, "CallPolicyUpdated", target=SHOP, selector=bytes.fromhex(BUY[2:]), allowed=True, _block=2),
        make_log(WALLET, w, "CallPolicyUpdated", target=TOKEN, selector=sel("transfer(address,uint256)"), allowed=True, _block=2, _idx=1),
        make_log(WALLET, w, "RecipientPolicyUpdated", recipient="0x" + "88" * 20, allowed=True, _block=3),
        make_log(WALLET, w, "AgentCallExecuted", agent=AGENT, usd=1_000_000_000, calls=1, _block=4),
        make_log(WALLET, w, "ApprovalRequested", id=1, agent=AGENT, reason=0, usd=3_500_000_000, expires_at=99, _block=5),
    ]


class FakeNode:
    def __init__(self):
        self.responses = {
            (WALLET, "owner()"): ("address", AGENT),
            (WALLET, "paused()"): ("bool", False),
            (WALLET, "perTransactionLimitUsd()"): ("uint256", 20 * 10**8),
            (WALLET, "dailyLimitUsd()"): ("uint256", 50 * 10**8),
            (WALLET, "spentInWindowUsd()"): ("uint256", 10 * 10**8),
            (WALLET, "nextPendingId()"): ("uint256", 2),
            (WALLET, "priceOracle()"): ("address", ORACLE),
            (WALLET, "entryPoint()"): ("address", ENTRY),
            (WALLET, "windowStart()"): ("uint48", 1000),
            (WALLET, "maxCallGas()"): ("uint128", 2_000_000),
            (WALLET, "maxVerificationGas()"): ("uint128", 1_000_000),
            (WALLET, "maxFeePerGas()"): ("uint256", 100 * 10**9),
            (WALLET, "pendingTtl()"): ("uint48", 3600),
            (WALLET, "maxOpenPendingPerAgent()"): ("uint32", 5),
            (ENTRY, "balanceOf(address)"): ("uint256", 10**18),
            (TOKEN, "balanceOf(address)"): ("uint256", 500 * 10**6),
            (TOKEN, "symbol()"): ("string", "dUSDC"),
        }
        self.token_config = {
            ZERO: ("address,uint48,uint8,bool,bool,uint256", (ZERO, 0, 18, True, True, 2000 * 10**8)),
            TOKEN: ("address,uint48,uint8,bool,bool,uint256", ("0x" + "99" * 20, 100, 6, True, False, 0)),
        }
        self.quote_fails = set()
        self.logs = {WALLET: wallet_logs(), ORACLE: [
            make_log(ORACLE, ORACLE_EVENTS, "FixedPriceConfigured", token=ZERO, decimals=18, price=2000 * 10**8),
            make_log(ORACLE, ORACLE_EVENTS, "FeedConfigured", token=TOKEN, feed="0x" + "99" * 20, decimals=6, max_age=100),
        ]}

    def eth_call(self, params):
        to = params[0]["to"].lower()
        data = bytes.fromhex(params[0]["data"][2:])
        head, body = data[:4], data[4:]
        to_key = {a.lower(): a for a in (WALLET, ORACLE, ENTRY, TOKEN, SHOP)}.get(to, to)
        for (addr, sig), (kind, value) in self.responses.items():
            if addr == to_key and sel(sig) == head:
                return "0x" + encode([kind], [value]).hex()
        if to_key == ORACLE and head == sel("tokenConfig(address)"):
            (token,) = decode(["address"], body)
            types, values = self.token_config[token.lower()]
            return "0x" + encode(types.split(","), list(values)).hex()
        if to_key == ORACLE and head == sel("quoteUsd(address,uint256)"):
            token, amount = decode(["address", "uint256"], body)
            if token.lower() in self.quote_fails:
                raise JsonRpcError(3, "execution reverted")
            price = 2000 * 10**8 if token == ZERO else 10**8
            decimals = 18 if token == ZERO else 6
            return "0x" + encode(["uint256"], [amount * price // 10**decimals]).hex()
        if to_key == WALLET and head == sel("sessions(address)"):
            return "0x" + encode(["uint48", "uint48", "uint32", "bool"], [0, 2_000_000_000, 1, False]).hex()
        if to_key == WALLET and head == sel("allowedCall(address,bytes4)"):
            return "0x" + encode(["bool"], [True]).hex()
        if to_key == WALLET and head == sel("allowedRecipient(address)"):
            return "0x" + encode(["bool"], [False]).hex()
        raise AssertionError(f"unexpected call to {to} {head.hex()}")

    def __call__(self, request):
        payload = json.loads(request.content)
        method, params = payload["method"], payload["params"]
        try:
            if method == "eth_call":
                result = self.eth_call(params)
            elif method == "eth_getLogs":
                result = self.logs[params[0]["address"]]
            elif method == "eth_getBalance":
                result = hex(2 * 10**18)
            elif method == "eth_getBlockByNumber":
                number = params[0]
                ts = 1_500_000_000 if number == "latest" else 1_000_000 + int(number, 16)
                result = {"timestamp": hex(ts), "baseFeePerGas": "0x1"}
            else:
                raise AssertionError(method)
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": payload["id"], "result": result})
        except JsonRpcError as exc:
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": payload["id"], "error": {"code": exc.code, "message": str(exc)}})


def reader_for(node=None):
    node = node or FakeNode()
    # Node answers eth_call with the lowercase address, so normalise like a real node would.
    rpc = JsonRpcClient("https://rpc.test", transport=httpx.MockTransport(node))
    return WalletReader("https://rpc.test", WALLET, rpc=rpc), node


@pytest.mark.unit
@pytest.mark.parametrize(
    ("name", "values", "status", "needle"),
    [
        ("AgentCallExecuted", {"agent": AGENT, "usd": 500, "calls": 2}, "Allowed", "Agent call executed"),
        ("ApprovalRequested", {"id": 3, "agent": AGENT, "reason": 1, "usd": 0, "expires_at": 1}, "Pending", "Held for owner approval #3"),
        ("PendingApproved", {"id": 3}, "Allowed", "approved request #3"),
        ("PendingRejected", {"id": 3}, "Blocked", "rejected request #3"),
        ("PendingMarkedExpired", {"id": 3}, "Blocked", "Request #3 expired"),
        ("SessionAdded", {"agent": AGENT, "valid_after": 0, "valid_until": 9}, "Allowed", "Session added"),
        ("SessionRevoked", {"agent": AGENT}, "Allowed", "Session revoked"),
        ("WalletPauseChanged", {"paused": True}, "Allowed", "Wallet paused"),
        ("WalletPauseChanged", {"paused": False}, "Allowed", "Wallet resumed"),
        ("CallPolicyUpdated", {"target": SHOP, "selector": bytes.fromhex(BUY[2:]), "allowed": False}, "Allowed", "Call disallowed: buyTicket"),
        ("RecipientPolicyUpdated", {"recipient": SHOP, "allowed": True}, "Allowed", "Recipient allowed"),
        ("RecipientPolicyUpdated", {"recipient": SHOP, "allowed": False}, "Allowed", "Recipient removed"),
        ("SpendPolicyUpdated", {"per_tx": 10**8, "daily": 5 * 10**8}, "Allowed", "Spend limits updated"),
        ("GasPolicyUpdated", {"verification": 1, "call": 2, "fee": 3}, "Allowed", "Gas caps updated"),
        ("OwnershipTransferred", {"previous": AGENT, "new": SHOP}, "Allowed", "Ownership transferred"),
    ],
)
def test_every_wallet_event_becomes_an_activity_item(name, values, status, needle):
    event = decode_log(make_log(WALLET, WALLET_EVENTS, name, **values), WALLET_EVENTS)
    item = _activity_item(event, 123)
    assert item["status"] == status and needle in item["title"] and item["timestamp"] == 123


@pytest.mark.unit
def test_decode_log_ignores_unknown_events():
    log = make_log(WALLET, WALLET_EVENTS, "PendingApproved", id=1)
    log["topics"][0] = "0x" + "00" * 32
    assert decode_log(log, WALLET_EVENTS) is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_activity_is_newest_first_with_block_timestamps():
    reader, _ = reader_for()
    items = await reader.activity()
    assert [i["status"] for i in items][0] == "Pending"
    assert items[0]["timestamp"] > items[-1]["timestamp"]
    assert items[-1]["title"] == "Session added"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_overview_combines_balances_tokens_sessions_and_stats():
    reader, _ = reader_for()
    overview = await reader.overview()
    assert overview["wallet"]["window_resets_at"] == 1000 + 86400
    assert overview["deposit_wei"] == str(10**18)
    assert [t["symbol"] for t in overview["tokens"]] == ["ETH", "dUSDC"]
    eth, usdc = overview["tokens"]
    assert eth["usd_value"] == "4000.00" and eth["freshness"] == "Mock"
    assert usdc["usd_value"] == "500.00" and usdc["freshness"] == "Fresh" and usdc["price_source"] == "chainlink"
    assert overview["total_usd"] == "4500.00"
    assert overview["sessions"][0]["active"] is True
    assert overview["stats"] == {"executed_operations": 1, "open_pending": 1, "spend_history_usd": [10.0]}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_overview_marks_unpriced_disabled_and_symbolless_tokens():
    reader, node = reader_for()
    node.quote_fails.add(TOKEN)
    del node.responses[(TOKEN, "symbol()")]
    node.token_config[TOKEN] = ("address,uint48,uint8,bool,bool,uint256", (ZERO, 0, 6, False, False, 0))
    tokens = (await reader.overview())["tokens"]
    assert tokens[1]["freshness"] == "Disabled" and tokens[1]["usd_value"] is None
    assert tokens[1]["symbol"] == "0x6666...6666" and tokens[1]["price_source"] == "none"
    node.token_config[TOKEN] = ("address,uint48,uint8,bool,bool,uint256", ("0x" + "99" * 20, 5, 6, True, False, 0))
    assert (await reader.overview())["tokens"][1]["freshness"] == "Unpriced"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_policy_reads_current_allowlists_and_caps():
    reader, _ = reader_for()
    policy = await reader.policy()
    assert policy["spend"] == {"per_transaction_usd": "20.00", "daily_usd": "50.00"}
    assert policy["gas"]["max_call_gas"] == 2_000_000
    assert policy["pending"] == {"ttl_seconds": 3600, "max_open_per_agent": 5}
    labels = {(c["label"], c["signature"]) for c in policy["allowed_calls"]}
    assert ("dUSDC", "transfer(address,uint256)") in labels and ("Contract", "buyTicket(address)") in labels
    assert policy["allowed_recipients"] == [{"address": "0x" + "88" * 20, "allowed": False}]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_chain_time_reads_latest_block():
    reader, _ = reader_for()
    assert await reader.chain_time() == 1_500_000_000


def test_telemetry_ring_buffer_filters_and_caps():
    log = TelemetryLog(capacity=2)
    log.record("attack", "a", "d", "r")
    log.record("blocked_operation", "b", "d", "r")
    log.record("attack", "c", "d", "r", "executed")
    assert [e["title"] for e in log.list()] == ["c", "b"]
    assert [e["title"] for e in log.list("attack")] == ["c"]


# ---------- attack runner ----------
class StubReader:
    wallet = WALLET

    def __init__(self, allowed=True):
        self.allowed = allowed

    async def policy(self):
        calls = [
            {"target": SHOP, "signature": "buyTicket(address)", "allowed": self.allowed},
            {"target": TOKEN, "signature": "transfer(address,uint256)", "allowed": self.allowed},
        ]
        return {"allowed_calls": calls}

    async def _view(self, signature, types, values, out, to=None):
        if signature.startswith("ticketPrice"):
            return (5 * 10**15,)
        if signature.startswith("getNonce"):
            self.nonce = getattr(self, "nonce", 0)
            return (self.nonce,)
        if signature.startswith("getUserOpHash"):
            return (b"\x42" * 32,)
        raise AssertionError(signature)


def attacks_with(reader, send):
    bundler = BundlerClient("https://bundler.test", ENTRY, rpc=JsonRpcClient("https://bundler.test"))
    bundler.send_user_operation = send
    return DemoAttacks(reader, bundler, ENTRY, AGENT_KEY, ATTACKER_KEY)


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("attack", [a for a in ATTACKS if a != "replay"])
async def test_attacks_report_blocked_reason(attack):
    send = AsyncMock(side_effect=JsonRpcError(-32500, "AA23 reverted: RecipientNotAllowed"))
    result = await attacks_with(StubReader(), send).run(attack)
    assert result["outcome"] == "blocked" and "AA23" in result["reason"]
    assert send.await_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_attack_that_gets_through_is_reported_as_executed():
    result = await attacks_with(StubReader(), AsyncMock(return_value="0x" + "ab" * 32)).run("prompt-injection")
    assert result["outcome"] == "executed" and result["user_operation_hash"] == "0x" + "ab" * 32


@pytest.mark.unit
@pytest.mark.asyncio
async def test_replay_submits_twice_and_second_is_blocked(monkeypatch):
    reader = StubReader()
    send = AsyncMock(side_effect=["0x" + "cd" * 32, JsonRpcError(-32500, "AA25 invalid account nonce")])
    runner = attacks_with(reader, send)
    monkeypatch.setattr(runner, "_wait_for_nonce", AsyncMock())
    result = await runner.run("replay")
    assert send.await_count == 2 and result["reason"].startswith("AA25")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_replay_requires_the_first_operation_to_succeed():
    send = AsyncMock(side_effect=JsonRpcError(-32500, "AA23 nope"))
    with pytest.raises(AttackSetupError, match="nothing to replay"):
        await attacks_with(StubReader(), send).run("replay")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_wait_for_nonce_polls_until_nonce_advances(monkeypatch):
    reader = StubReader()
    runner = attacks_with(reader, AsyncMock())
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)
        reader.nonce = 1

    monkeypatch.setattr("asyncio.sleep", fake_sleep)
    await runner._wait_for_nonce("0x0")
    assert sleeps == [0.1]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_attacks_need_allowed_targets_and_known_names():
    with pytest.raises(AttackSetupError, match="allowed buyTicket"):
        await attacks_with(StubReader(allowed=False), AsyncMock()).run("leaked-key")
    with pytest.raises(KeyError):
        await attacks_with(StubReader(), AsyncMock()).run("nope")


# ---------- routes ----------
def demo_settings(**overrides) -> Settings:
    base = dict(
        _env_file=None, rpc_url="https://rpc.test", bundler_rpc_url="https://bundler.test",
        entry_point_address=ENTRY, wallet_address=WALLET,
        demo_owner_private_key="0x" + "ab" * 32, demo_agent_private_key=AGENT_KEY, demo_attacker_private_key=ATTACKER_KEY,
    )
    return Settings(**{**base, **overrides})


def client_for(settings):
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    return app, httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")


@pytest.mark.api
@pytest.mark.asyncio
async def test_read_endpoints_return_chain_data(monkeypatch):
    reader, _ = reader_for()
    monkeypatch.setattr(routes, "WalletReader", lambda url, wallet: reader)
    app, client = client_for(demo_settings())
    app.state.telemetry.record("blocked_operation", "Rejected UserOperation", "sender 0x1", "Rejected by EntryPoint simulation: AA24 signature error")
    app.state.telemetry.record("attack", "x", "d", "r", "executed")
    async with client:
        overview = await client.get("/api/v1/wallet/overview")
        policy = await client.get("/api/v1/wallet/policy")
        activity = (await client.get("/api/v1/wallet/activity")).json()
    assert overview.json()["total_usd"] == "4500.00" and len(policy.json()["allowed_calls"]) == 2
    results = {i["result"] for i in activity["items"] if i.get("source") == "relay"}
    assert "AA24 signature error" in results and "ACCEPTED - unexpected" in results
    assert activity["blocked_attempts"] == 1


@pytest.mark.api
@pytest.mark.asyncio
async def test_read_endpoints_require_configuration_and_map_errors(api_client, monkeypatch):
    for path in ("overview", "policy", "activity"):
        assert (await api_client.get(f"/api/v1/wallet/{path}")).status_code == 503
    reader, _ = reader_for()
    for method in ("overview", "policy", "activity"):
        setattr(reader, method, AsyncMock(side_effect=httpx.ConnectError("down")))
    monkeypatch.setattr(routes, "WalletReader", lambda url, wallet: reader)
    _, client = client_for(demo_settings())
    async with client:
        for path in ("overview", "policy", "activity"):
            assert (await client.get(f"/api/v1/wallet/{path}")).status_code == 502


@pytest.mark.api
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "body", "signature"),
    [
        ("pause", {"paused": True}, "setPaused(bool)"),
        ("sessions/revoke", {"agent": AGENT}, "revokeSession(address)"),
        ("spend-policy", {"per_transaction_usd": "12.5", "daily_usd": "40"}, "setSpendPolicy(uint256,uint256)"),
        ("call-policy", {"target": SHOP, "selector": BUY, "allowed": True}, "setCallPolicy(address,bytes4,bool)"),
        ("recipient-policy", {"recipient": SHOP, "allowed": False}, "setRecipientPolicy(address,bool)"),
        ("sessions", {"agent": AGENT, "valid_for_seconds": 3600}, "addSession(address,uint48,uint48)"),
    ],
)
async def test_owner_policy_endpoints_encode_the_right_call(monkeypatch, path, body, signature):
    reader, _ = reader_for()
    reader.owner_transaction = AsyncMock(return_value="0x" + "cd" * 32)
    monkeypatch.setattr(routes, "WalletReader", lambda url, wallet: reader)
    _, client = client_for(demo_settings())
    async with client:
        response = await client.post(f"/api/v1/wallet/owner/{path}", json=body)
    assert response.status_code == 200
    args = reader.owner_transaction.await_args.args
    assert args[1] == signature
    if path == "spend-policy":
        assert args[3] == [1_250_000_000, 4_000_000_000]
    if path == "sessions":
        assert args[3][2] == 1_500_000_000 + 3600  # chain time + duration


@pytest.mark.api
@pytest.mark.asyncio
async def test_owner_policy_endpoints_validate_input_and_signer(monkeypatch):
    reader, _ = reader_for()
    reader.owner_transaction = AsyncMock(return_value="0x1")
    monkeypatch.setattr(routes, "WalletReader", lambda url, wallet: reader)
    _, client = client_for(demo_settings())
    async with client:
        bad_limits = await client.post("/api/v1/wallet/owner/spend-policy", json={"per_transaction_usd": "50", "daily_usd": "10"})
        bad_format = await client.post("/api/v1/wallet/owner/spend-policy", json={"per_transaction_usd": "ten", "daily_usd": "10"})
        bad_selector = await client.post("/api/v1/wallet/owner/call-policy", json={"target": SHOP, "selector": "0x12", "allowed": True})
        bad_session = await client.post("/api/v1/wallet/owner/sessions", json={"agent": AGENT, "valid_for_seconds": 5})
    assert [r.status_code for r in (bad_limits, bad_format, bad_selector, bad_session)] == [422] * 4
    reader.owner_transaction.assert_not_awaited()
    _, no_signer = client_for(demo_settings(demo_owner_private_key=None))
    async with no_signer:
        assert (await no_signer.post("/api/v1/wallet/owner/pause", json={"paused": True})).status_code == 403


@pytest.mark.api
@pytest.mark.asyncio
async def test_add_session_maps_chain_time_failure(monkeypatch):
    reader, _ = reader_for()
    reader.chain_time = AsyncMock(side_effect=httpx.ConnectError("down"))
    monkeypatch.setattr(routes, "WalletReader", lambda url, wallet: reader)
    _, client = client_for(demo_settings())
    async with client:
        response = await client.post("/api/v1/wallet/owner/sessions", json={"agent": AGENT, "valid_for_seconds": 3600})
    assert response.status_code == 502


@pytest.mark.api
@pytest.mark.asyncio
async def test_attack_endpoints_are_disabled_without_demo_keys(api_client):
    assert (await api_client.get("/api/v1/demo/attacks")).status_code == 403
    assert (await api_client.post("/api/v1/demo/attacks/replay")).status_code == 403


@pytest.mark.api
@pytest.mark.asyncio
async def test_attack_endpoint_runs_records_and_summarises(monkeypatch):
    async def fake_run(self, attack):
        if attack == "replay":
            raise AttackSetupError("no targets")
        outcome = "executed" if attack == "gas-grief" else "blocked"
        return {"attack": attack, "outcome": outcome, "reason": "AA23" if outcome == "blocked" else None,
                "user_operation_hash": "0x" + "ab" * 32 if outcome == "executed" else None}

    monkeypatch.setattr(DemoAttacks, "run", fake_run)
    _, client = client_for(demo_settings())
    async with client:
        blocked = await client.post("/api/v1/demo/attacks/prompt-injection")
        executed = await client.post("/api/v1/demo/attacks/gas-grief")
        unknown = await client.post("/api/v1/demo/attacks/nope")
        setup = await client.post("/api/v1/demo/attacks/replay")
        history = (await client.get("/api/v1/demo/attacks")).json()
    assert blocked.json()["outcome"] == "blocked" and executed.json()["outcome"] == "executed"
    assert unknown.status_code == 404 and setup.status_code == 409
    assert (history["attempts"], history["blocked"], history["executed"]) == (2, 1, 1)


@pytest.mark.api
@pytest.mark.asyncio
async def test_attack_endpoint_maps_chain_errors(monkeypatch):
    monkeypatch.setattr(DemoAttacks, "run", AsyncMock(side_effect=httpx.ConnectError("down")))
    _, client = client_for(demo_settings())
    async with client:
        assert (await client.post("/api/v1/demo/attacks/leaked-key")).status_code == 502


@pytest.mark.api
@pytest.mark.asyncio
async def test_relayed_rejections_are_recorded_for_the_activity_feed(operation_payload, monkeypatch):
    monkeypatch.setattr(
        routes.BundlerClient, "send_user_operation",
        AsyncMock(side_effect=JsonRpcError(-32500, "AA24 signature error")),
    )
    app, client = client_for(demo_settings())
    async with client:
        response = await client.post("/api/v1/user-operations", json={"user_operation": operation_payload})
    assert response.status_code == 422
    recorded = app.state.telemetry.list("blocked_operation")
    assert recorded[0]["reason"] == "AA24 signature error"
