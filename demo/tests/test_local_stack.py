"""Integration tests against the live local stack (anvil + deployed contracts + local bundler).

Start the stack first (see demo/README.md). Each test runs inside an anvil snapshot that is
reverted afterwards, so tests are independent and order does not matter.

Run: .venv/bin/python -m pytest demo/tests -o addopts="" -q
"""

from __future__ import annotations

import json
import time

import httpx
import pytest

from chain import (
    ANVIL_KEYS, CALL_TYPE, DEPLOYMENTS, Client, Rpc, RpcError, build_user_op, calldata, op_to_json,
    sign_op, user_op_hash,
)
from eth_account import Account
from eth_account.messages import encode_defunct

BUNDLER = "http://127.0.0.1:3000"
ETH, USDC_UNIT, USD = 10**18, 10**6, 10**8
PENDING_TYPE = "(address,uint48,uint48,uint8,uint8,uint256,bytes)"
HOUR, DAY = 3600, 24 * 3600

if not DEPLOYMENTS.exists():
    pytest.skip("run demo/deploy_local.py first", allow_module_level=True)
D = json.loads(DEPLOYMENTS.read_text())
EP, WALLET, USDC = D["entryPoint"], D["wallet"], D["usdc"]
SHOP, PREMIUM = D["ticketShop"], D["premiumTicketShop"]
AGENT, ATTACKER, MERCHANT = D["agent"], D["attacker"], D["merchant"]
AGENT_KEY, ATTACKER_KEY, OWNER_KEY = ANVIL_KEYS["agent"], ANVIL_KEYS["attacker"], ANVIL_KEYS["owner"]
client = Client(Rpc(D["rpc"]))


@pytest.fixture(autouse=True)
def isolated_chain():
    snapshot = client.rpc.call("evm_snapshot")
    yield
    client.rpc.call("evm_revert", [snapshot])


# ---------- helpers ----------
def view(to, sig, types, values, out):
    return client.view(to, sig, types, values, out)


def nonce():
    return view(EP, "getNonce(address,uint192)", ["address", "uint192"], [WALLET, 0], ["uint256"])[0]


def call(target, value, data):
    return [target, value, data]


def buy(shop=SHOP, value=ETH // 200):
    return call(shop, value, calldata("buyTicket(address)", ["address"], [AGENT]))


def transfer(token, to, amount):
    return call(token, 0, calldata("transfer(address,uint256)", ["address", "uint256"], [to, amount]))


def op_for(calls, key=AGENT_KEY, agent=AGENT, **gas):
    if len(calls) == 1:
        data = calldata(f"executeAgent(address,{CALL_TYPE})", ["address", CALL_TYPE], [agent, calls[0]])
    else:
        data = calldata(f"executeAgentBatch(address,{CALL_TYPE}[])", ["address", f"{CALL_TYPE}[]"], [agent, calls])
    return sign_op(client, EP, build_user_op(WALLET, nonce(), data, **gas), key)


def rpc_send(op):
    body = {"jsonrpc": "2.0", "id": 1, "method": "eth_sendUserOperation", "params": [op_to_json(op), EP]}
    return httpx.post(BUNDLER, json=body, timeout=30).json()


def run(op):
    """Submit an operation that must be accepted; return its receipt."""
    data = rpc_send(op)
    assert "result" in data, data.get("error")
    for _ in range(50):
        body = {"jsonrpc": "2.0", "id": 1, "method": "eth_getUserOperationReceipt", "params": [data["result"]]}
        receipt = httpx.post(BUNDLER, json=body).json()["result"]
        if receipt:
            return receipt
        time.sleep(0.1)
    raise TimeoutError


def rejected(op, fragment):
    data = rpc_send(op)
    assert "error" in data, "operation was accepted but should have been rejected"
    assert fragment in data["error"]["message"], data["error"]["message"]


def owner_tx(sig, types, values):
    return client.send(OWNER_KEY, WALLET, calldata(sig, types, values))


def tickets_sold(shop=SHOP):
    return view(shop, "nextTicketId()", [], [], ["uint256"])[0] - 1


def spent():
    return view(WALLET, "spentInWindowUsd()", [], [], ["uint256"])[0]


def usdc_balance(who):
    return view(USDC, "balanceOf(address)", ["address"], [who], ["uint256"])[0]


def pending(pid):
    return view(WALLET, f"getPending(uint256)", ["uint256"], [pid], [PENDING_TYPE])[0]


def open_pending():
    return view(WALLET, "sessions(address)", ["address"], [AGENT], ["uint48", "uint48", "uint32", "bool"])[2]


def make_pending():
    """Create one open pending request ($35 > $20 per-tx limit); return its id."""
    first = view(WALLET, "nextPendingId()", [], [], ["uint256"])[0]
    assert run(op_for([buy(PREMIUM, ETH * 35 // 2000)]))["success"]
    return first


# ---------- happy paths and spend limits ----------
def test_01_agent_buys_ticket_within_limits():
    assert run(op_for([buy()]))["success"]
    assert tickets_sold() == 1
    assert spent() == 10 * USD


def test_02_daily_limit_diverts_to_pending_with_daily_reason():
    for _ in range(2):  # two $20 batches fill $40 of the $50 daily budget
        run(op_for([buy(), buy()]))
    assert spent() == 40 * USD and tickets_sold() == 4
    run(op_for([buy(), buy()]))  # would reach $60
    assert tickets_sold() == 4 and spent() == 40 * USD
    assert pending(1)[4] == 1  # PendingReason.OverDailyLimit


def test_03_merchant_transfer_allowed_and_moves_funds():
    before = usdc_balance(MERCHANT)
    assert run(op_for([transfer(USDC, MERCHANT, 5 * USDC_UNIT)]))["success"]
    assert usdc_balance(MERCHANT) == before + 5 * USDC_UNIT


# ---------- calldata and target policy ----------
def test_04_transfer_to_attacker_blocked():
    rejected(op_for([transfer(USDC, ATTACKER, 900 * USDC_UNIT)]), "RecipientNotAllowed")


def test_05_transfer_from_blocked_as_unlisted_selector():
    pull = call(USDC, 0, calldata("transferFrom(address,address,uint256)", ["address", "address", "uint256"], [WALLET, ATTACKER, 1]))
    rejected(op_for([pull]), "CallNotAllowed")


def test_06_approve_attacker_blocked():
    approve = call(USDC, 0, calldata("approve(address,uint256)", ["address", "uint256"], [ATTACKER, 2**256 - 1]))
    rejected(op_for([approve]), "RecipientNotAllowed")


def test_07_unlisted_target_blocked():
    rejected(op_for([call(ATTACKER, 1, b"")]), "CallNotAllowed")


def test_08_wallet_self_call_blocked():
    admin = call(WALLET, 0, calldata("transferOwnership(address)", ["address"], [ATTACKER]))
    rejected(op_for([admin]), "InvalidAgentCall")


def test_09_batch_with_one_bad_call_blocked_entirely():
    rejected(op_for([buy(), transfer(USDC, ATTACKER, 1)]), "RecipientNotAllowed")
    assert tickets_sold() == 0


def test_10_empty_batch_blocked():
    rejected(op_for([]), "InvalidAgentCall")


def test_11_two_call_batch_executes_both():
    assert run(op_for([buy(), buy()]))["success"]
    assert tickets_sold() == 2 and spent() == 20 * USD


def test_12_batch_over_per_tx_limit_executes_nothing():
    run(op_for([buy(), buy(), buy()]))  # $30 > $20
    assert tickets_sold() == 0 and spent() == 0
    assert pending(1)[4] == 0  # PendingReason.OverPerTransactionLimit


# ---------- signature, identity, replay, gas ----------
def test_13_attacker_own_key_rejected():
    rejected(op_for([buy()], key=ATTACKER_KEY, agent=ATTACKER), "AA24")


def test_14_agent_field_must_match_signer():
    rejected(op_for([buy()], key=AGENT_KEY, agent=ATTACKER), "InvalidAgentCall")


def test_15_call_gas_cap_enforced():
    rejected(op_for([buy()], call_gas=10_000_000), "GasLimitExceeded")


def test_16_verification_gas_cap_enforced():
    rejected(op_for([buy()], verification_gas=5_000_000), "GasLimitExceeded")


def test_17_max_fee_cap_enforced():
    rejected(op_for([buy()], max_fee=10**12), "GasLimitExceeded")


def test_18_replay_of_executed_operation_blocked():
    op = op_for([buy()])
    assert run(op)["success"]
    rejected(op, "AA25")


def test_19_tampered_signature_rejected():
    op = op_for([buy()])
    sig = bytearray(op["signature"])
    sig[10] ^= 0xFF
    rejected({**op, "signature": bytes(sig)}, "AA24")


# ---------- owner controls ----------
def test_20_revoked_session_rejected():
    owner_tx("revokeSession(address)", ["address"], [AGENT])
    rejected(op_for([buy()]), "AA24")


def test_21_paused_wallet_rejects_agent_and_resumes():
    owner_tx("setPaused(bool)", ["bool"], [True])
    rejected(op_for([buy()]), "AA24")
    owner_tx("setPaused(bool)", ["bool"], [False])
    assert run(op_for([buy()]))["success"]


def test_22_expired_session_rejected():
    op = op_for([buy()])
    client.rpc.call("evm_increaseTime", [8 * DAY])
    client.rpc.call("evm_mine")
    rejected(op, "AA22")


def test_23_non_owner_cannot_change_policy():
    with pytest.raises(RpcError):
        client.send(ATTACKER_KEY, WALLET, calldata("setPaused(bool)", ["bool"], [True]))


def test_24_owner_can_execute_directly():
    before = int(client.rpc.call("eth_getBalance", [MERCHANT, "latest"]), 16)
    client.send(OWNER_KEY, WALLET, calldata(f"execute({CALL_TYPE})", [CALL_TYPE], [call(MERCHANT, ETH // 10, b"")]))
    assert int(client.rpc.call("eth_getBalance", [MERCHANT, "latest"]), 16) == before + ETH // 10


# ---------- pending approvals ----------
def test_25_over_limit_creates_pending_without_executing():
    pid = make_pending()
    assert tickets_sold(PREMIUM) == 0
    assert pending(pid)[3] == 1  # PendingStatus.Open
    assert pending(pid)[5] == 35 * USD
    assert open_pending() == 1


def test_26_owner_reject_never_executes_and_frees_slot():
    pid = make_pending()
    owner_tx("rejectPending(uint256)", ["uint256"], [pid])
    assert tickets_sold(PREMIUM) == 0 and pending(pid)[3] == 3 and open_pending() == 0  # status Rejected


def test_27_owner_approve_executes_without_using_daily_budget():
    pid = make_pending()
    owner_tx("approvePending(uint256)", ["uint256"], [pid])
    assert tickets_sold(PREMIUM) == 1 and pending(pid)[3] == 2  # status Approved
    assert spent() == 0
    with pytest.raises(RpcError):  # cannot be approved twice
        owner_tx("approvePending(uint256)", ["uint256"], [pid])


def test_28_expired_pending_cannot_be_approved_but_anyone_can_expire_it():
    pid = make_pending()
    client.rpc.call("evm_increaseTime", [2 * HOUR])
    client.rpc.call("evm_mine")
    with pytest.raises(RpcError):
        owner_tx("approvePending(uint256)", ["uint256"], [pid])
    client.send(ATTACKER_KEY, WALLET, calldata("expirePending(uint256)", ["uint256"], [pid]))
    assert pending(pid)[3] == 4 and open_pending() == 0


def test_29_pending_queue_capped_at_five():
    for _ in range(5):
        make_pending()
    assert open_pending() == 5
    receipt = run(op_for([buy(PREMIUM, ETH * 35 // 2000)]))
    assert receipt["success"] is False  # sixth request reverts inside execution
    assert open_pending() == 5


def test_30_eip1271_accepts_owner_and_rejects_agent():
    digest = b"\x42" * 32

    def check(key):
        sig = bytes(Account.sign_message(encode_defunct(primitive=digest), private_key=key).signature)
        return view(WALLET, "isValidSignature(bytes32,bytes)", ["bytes32", "bytes"], [digest, sig], ["bytes4"])[0]

    assert check(OWNER_KEY) == bytes.fromhex("1626ba7e")
    assert check(AGENT_KEY) == bytes.fromhex("ffffffff")
