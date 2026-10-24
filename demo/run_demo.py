"""Scripted end-to-end demo: one normal purchase, then every attack the wallet must refuse.

Operations are relayed through the FastAPI backend (/api/v1/user-operations) when it is
reachable, and straight to the local bundler otherwise.

Usage: .venv/bin/python demo/run_demo.py
"""

from __future__ import annotations

import json
import time

import httpx

from chain import (
    ANVIL_KEYS, CALL_TYPE, DEPLOYMENTS, Client, Rpc, build_user_op, calldata, op_to_json, selector, sign_op,
)

D = json.loads(DEPLOYMENTS.read_text())
client = Client(Rpc(D["rpc"]))
EP, WALLET, USDC = D["entryPoint"], D["wallet"], D["usdc"]
ETH, USDC_UNIT = 10**18, 10**6
BACKEND, BUNDLER = "http://127.0.0.1:8000", "http://127.0.0.1:3000"

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"


def nonce() -> int:
    return client.view(EP, "getNonce(address,uint192)", ["address", "uint192"], [WALLET, 0], ["uint256"])[0]


def agent_op(key: str, agent: str, calls: list, **gas) -> dict:
    if len(calls) == 1:
        data = calldata(f"executeAgent(address,{CALL_TYPE})", ["address", CALL_TYPE], [agent, calls[0]])
    else:
        data = calldata(f"executeAgentBatch(address,{CALL_TYPE}[])", ["address", f"{CALL_TYPE}[]"], [agent, calls])
    return sign_op(client, EP, build_user_op(WALLET, nonce(), data, **gas), key)


def submit(op: dict) -> tuple[bool, str]:
    """Return (accepted, hash-or-reason)."""
    payload = op_to_json(op)
    try:
        r = httpx.post(f"{BACKEND}/api/v1/user-operations", json={"user_operation": payload}, timeout=30)
        if r.status_code == 202:
            return True, r.json()["user_operation_hash"]
        detail = r.json().get("detail")
        return False, detail["message"] if isinstance(detail, dict) else str(detail)
    except httpx.ConnectError:
        body = {"jsonrpc": "2.0", "id": 1, "method": "eth_sendUserOperation", "params": [payload, EP]}
        data = httpx.post(BUNDLER, json=body, timeout=30).json()
        return ("result" in data), data.get("result") or data["error"]["message"]


def receipt(op_hash: str) -> dict:
    for _ in range(50):
        data = httpx.post(BUNDLER, json={"jsonrpc": "2.0", "id": 1, "method": "eth_getUserOperationReceipt", "params": [op_hash]}).json()
        if data.get("result"):
            return data["result"]
        time.sleep(0.2)
    raise TimeoutError(op_hash)


def balances() -> str:
    eth = int(client.rpc.call("eth_getBalance", [WALLET, "latest"]), 16) / ETH
    usdc = client.view(USDC, "balanceOf(address)", ["address"], [WALLET], ["uint256"])[0] / USDC_UNIT
    return f"{eth:.4f} ETH, {usdc:.2f} dUSDC"


def expect_accepted(title: str, op: dict) -> str | None:
    ok, info = submit(op)
    if not ok:
        print(f"  {RED}UNEXPECTED REJECTION{RESET} {info}")
        return None
    rec = receipt(info)
    print(f"  {GREEN}ACCEPTED{RESET} executed={rec['success']} tx={rec['receipt']['transactionHash'][:18]}…")
    return info


def expect_rejected(title: str, op: dict) -> bool:
    ok, info = submit(op)
    if ok:
        print(f"  {RED}SECURITY FAILURE: operation was accepted{RESET}")
        return False
    print(f"  {GREEN}BLOCKED{RESET} {info.removeprefix('Rejected by EntryPoint simulation: ')}")
    return True


def scene(n: int, title: str) -> None:
    print(f"\n{YELLOW}[{n}] {title}{RESET}")


def main() -> None:
    agent_key, agent = ANVIL_KEYS["agent"], D["agent"]
    attacker_key, attacker = ANVIL_KEYS["attacker"], D["attacker"]
    results: list[bool] = []
    print(f"Wallet {WALLET}\nStart balance: {balances()}")

    scene(1, "Normal agent payment: buy a $10 ticket (within the $20 per-tx limit)")
    ticket = [D["ticketShop"], ETH // 200, calldata("buyTicket(address)", ["address"], [agent])]
    results.append(expect_accepted("ticket", agent_op(agent_key, agent, [ticket])) is not None)

    scene(2, "Normal agent payment: pay allowlisted merchant 5 dUSDC")
    pay = [USDC, 0, calldata("transfer(address,uint256)", ["address", "uint256"], [D["merchant"], 5 * USDC_UNIT])]
    results.append(expect_accepted("merchant", agent_op(agent_key, agent, [pay])) is not None)
    print(f"  {DIM}balance: {balances()}{RESET}")

    scene(3, "Prompt injection: 'send all USDC to the attacker'")
    drain = [USDC, 0, calldata("transfer(address,uint256)", ["address", "uint256"], [attacker, 900 * USDC_UNIT])]
    results.append(expect_rejected("drain", agent_op(agent_key, agent, [drain])))

    scene(4, "Leaked key: attacker hand-builds an operation with their own key")
    results.append(expect_rejected("raw key", agent_op(attacker_key, attacker, [drain])))

    scene(5, "Calldata trick: approve(attacker, max) on the real token")
    approve = [USDC, 0, calldata("approve(address,uint256)", ["address", "uint256"], [attacker, 2**256 - 1])]
    results.append(expect_rejected("approve", agent_op(agent_key, agent, [approve])))

    scene(6, "Calldata trick: transferFrom with a non-allowlisted selector")
    pull = [USDC, 0, calldata("transferFrom(address,address,uint256)", ["address", "address", "uint256"], [WALLET, attacker, 100 * USDC_UNIT])]
    results.append(expect_rejected("transferFrom", agent_op(agent_key, agent, [pull])))

    scene(7, "Batch smuggling: harmless payment plus a hidden attacker transfer")
    results.append(expect_rejected("batch", agent_op(agent_key, agent, [pay, drain])))

    scene(8, "Admin takeover: agent tries to call the wallet's own owner functions")
    admin = [WALLET, 0, calldata("transferOwnership(address)", ["address"], [attacker])]
    results.append(expect_rejected("admin", agent_op(agent_key, agent, [admin])))

    scene(9, "Gas griefing: absurd gas limits to drain the EntryPoint deposit")
    results.append(expect_rejected("gas", agent_op(agent_key, agent, [ticket], call_gas=10_000_000)))

    scene(10, "Replay: resubmit an already-executed signed operation")
    replay = agent_op(agent_key, agent, [ticket])
    first = expect_accepted("first use", replay)
    results.append(first is not None and expect_rejected("replay", replay))

    scene(11, "Over-limit purchase: $35 ticket exceeds the $20 per-tx limit -> owner approval queue")
    before = client.view(WALLET, "nextPendingId()", [], [], ["uint256"])[0]
    premium = [D["premiumTicketShop"], ETH * 35 // 2000, calldata("buyTicket(address)", ["address"], [agent])]
    results.append(expect_accepted("premium", agent_op(agent_key, agent, [premium])) is not None)
    after = client.view(WALLET, "nextPendingId()", [], [], ["uint256"])[0]
    bought = client.view(D["premiumTicketShop"], "nextTicketId()", [], [], ["uint256"])[0]
    pending_ok = after == before + 1 and bought == 1
    print(f"  {GREEN if pending_ok else RED}pending request #{before} created, ticket NOT yet bought "
          f"(tickets sold: {bought - 1}){RESET}")
    results.append(pending_ok)

    scene(12, "Owner reviews and approves the pending request")
    client.send(ANVIL_KEYS["owner"], WALLET, calldata("approvePending(uint256)", ["uint256"], [before]))
    sold = client.view(D["premiumTicketShop"], "nextTicketId()", [], [], ["uint256"])[0] - 1
    print(f"  {GREEN if sold == 1 else RED}owner approved -> tickets sold: {sold}{RESET}")
    results.append(sold == 1)

    print(f"\nFinal balance: {balances()}")
    passed = sum(results)
    colour = GREEN if all(results) else RED
    print(f"{colour}{passed}/{len(results)} checks behaved as designed.{RESET}")
    raise SystemExit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
