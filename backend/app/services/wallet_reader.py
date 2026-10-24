"""Dashboard read model: balances, policy, sessions and an event-derived activity feed.

Everything is read from the wallet, its price oracle, and standard JSON-RPC log queries. There is no
database: the feed is rebuilt from `eth_getLogs` on each request, which is fine for a local chain or a
young testnet wallet. A production deployment needs a persistent indexer instead.
"""

import asyncio
from typing import Any

from eth_abi import decode
from eth_utils import keccak

from app.services.wallet_chain import PENDING_REASON, WalletChain, _usd

ZERO = "0x" + "00" * 20
EXPLORER_NOTE = "Derived from wallet events"

# name -> ordered (type, indexed, field) tuples, matching AgentWallet.sol
WALLET_EVENTS: dict[str, list[tuple[str, bool, str]]] = {
    "AgentCallExecuted": [("address", True, "agent"), ("uint256", False, "usd"), ("uint256", False, "calls")],
    "ApprovalRequested": [("uint256", True, "id"), ("address", True, "agent"), ("uint8", False, "reason"), ("uint256", False, "usd"), ("uint48", False, "expires_at")],
    "PendingApproved": [("uint256", True, "id")],
    "PendingRejected": [("uint256", True, "id")],
    "PendingMarkedExpired": [("uint256", True, "id")],
    "SessionAdded": [("address", True, "agent"), ("uint48", False, "valid_after"), ("uint48", False, "valid_until")],
    "SessionRevoked": [("address", True, "agent")],
    "WalletPauseChanged": [("bool", False, "paused")],
    "CallPolicyUpdated": [("address", True, "target"), ("bytes4", True, "selector"), ("bool", False, "allowed")],
    "RecipientPolicyUpdated": [("address", True, "recipient"), ("bool", False, "allowed")],
    "SpendPolicyUpdated": [("uint256", False, "per_tx"), ("uint256", False, "daily")],
    "GasPolicyUpdated": [("uint128", False, "verification"), ("uint128", False, "call"), ("uint256", False, "fee")],
    "OwnershipTransferred": [("address", True, "previous"), ("address", True, "new")],
}
ORACLE_EVENTS: dict[str, list[tuple[str, bool, str]]] = {
    "FeedConfigured": [("address", True, "token"), ("address", True, "feed"), ("uint8", False, "decimals"), ("uint48", False, "max_age")],
    "FixedPriceConfigured": [("address", True, "token"), ("uint8", False, "decimals"), ("uint256", False, "price")],
    "TokenDisabled": [("address", True, "token")],
}

KNOWN_SELECTORS = {
    "0xa5f8cdbb": "buyTicket(address)",
    "0xa9059cbb": "transfer(address,uint256)",
    "0x095ea7b3": "approve(address,uint256)",
    "0x23b872dd": "transferFrom(address,address,uint256)",
}


def _topic0(name: str, fields: list[tuple[str, bool, str]]) -> str:
    return "0x" + keccak(text=f"{name}({','.join(t for t, _, _ in fields)})").hex()


def decode_log(log: dict[str, Any], events: dict[str, list[tuple[str, bool, str]]]) -> dict[str, Any] | None:
    by_topic = {_topic0(name, fields): (name, fields) for name, fields in events.items()}
    match = by_topic.get(log["topics"][0])
    if match is None:
        return None
    name, fields = match
    indexed = [f for f in fields if f[1]]
    plain = [f for f in fields if not f[1]]
    values: dict[str, Any] = {}
    for (kind, _, field), topic in zip(indexed, log["topics"][1:], strict=True):
        (values[field],) = decode([kind], bytes.fromhex(topic[2:]))
    if plain:
        decoded = decode([t for t, _, _ in plain], bytes.fromhex(log["data"][2:]))
        values.update({field: v for (_, _, field), v in zip(plain, decoded, strict=True)})
    for key, value in list(values.items()):
        if isinstance(value, bytes):
            values[key] = "0x" + value.hex()
        elif isinstance(value, str) and value.startswith("0x"):
            values[key] = value.lower()
    return {
        "event": name,
        "values": values,
        "block": int(log["blockNumber"], 16),
        "log_index": int(log["logIndex"], 16),
        "tx_hash": log["transactionHash"],
    }


def _short(address: str) -> str:
    return f"{address[:6]}...{address[-4:]}"


def _activity_item(event: dict[str, Any], timestamp: int) -> dict[str, Any]:
    v, name = event["values"], event["event"]
    base = {"id": f"{event['block']}-{event['log_index']}", "timestamp": timestamp, "tx_hash": event["tx_hash"], "usd": None}
    if name == "AgentCallExecuted":
        return {**base, "icon": "ticket", "title": "Agent call executed", "detail": f"{v['calls']} call(s) · agent {_short(v['agent'])}", "usd": _usd(v["usd"]), "status": "Allowed", "result": "executed on-chain"}
    if name == "ApprovalRequested":
        reason = PENDING_REASON[v["reason"]].replace("_", " ")
        return {**base, "icon": "ticket", "title": f"Held for owner approval #{v['id']}", "detail": f"{reason} · agent {_short(v['agent'])}", "usd": _usd(v["usd"]), "status": "Pending", "result": f"awaiting owner #{v['id']}"}
    if name == "PendingApproved":
        return {**base, "icon": "ticket", "title": f"Owner approved request #{v['id']}", "detail": "Owner · approvePending", "status": "Allowed", "result": "executed on-chain"}
    if name == "PendingRejected":
        return {**base, "icon": "shield", "title": f"Owner rejected request #{v['id']}", "detail": "Owner · rejectPending", "status": "Blocked", "result": "rejected by owner"}
    if name == "PendingMarkedExpired":
        return {**base, "icon": "shield", "title": f"Request #{v['id']} expired", "detail": "Deadline passed without approval", "status": "Blocked", "result": "expired"}
    if name == "SessionAdded":
        return {**base, "icon": "users", "title": "Session added", "detail": f"agent {_short(v['agent'])} · until {v['valid_until']}", "status": "Allowed", "result": "owner action"}
    if name == "SessionRevoked":
        return {**base, "icon": "key", "title": "Session revoked", "detail": f"agent {_short(v['agent'])}", "status": "Allowed", "result": "owner action"}
    if name == "WalletPauseChanged":
        return {**base, "icon": "shield", "title": "Wallet paused" if v["paused"] else "Wallet resumed", "detail": "Owner emergency control", "status": "Allowed", "result": "owner action"}
    if name == "CallPolicyUpdated":
        sel = KNOWN_SELECTORS.get(v["selector"], v["selector"])
        return {**base, "icon": "code", "title": f"Call {'allowed' if v['allowed'] else 'disallowed'}: {sel}", "detail": f"target {_short(v['target'])}", "status": "Allowed", "result": "owner action"}
    if name == "RecipientPolicyUpdated":
        return {**base, "icon": "code", "title": f"Recipient {'allowed' if v['allowed'] else 'removed'}", "detail": _short(v["recipient"]), "status": "Allowed", "result": "owner action"}
    if name == "SpendPolicyUpdated":
        return {**base, "icon": "shield", "title": "Spend limits updated", "detail": f"${_usd(v['per_tx'])} per tx · ${_usd(v['daily'])} daily", "status": "Allowed", "result": "owner action"}
    if name == "GasPolicyUpdated":
        return {**base, "icon": "shield", "title": "Gas caps updated", "detail": f"call {v['call']:,} · verification {v['verification']:,}", "status": "Allowed", "result": "owner action"}
    return {**base, "icon": "key", "title": "Ownership transferred", "detail": f"{_short(v['previous'])} → {_short(v['new'])}", "status": "Allowed", "result": "owner action"}


class WalletReader(WalletChain):
    async def _logs(self, address: str, events: dict[str, list[tuple[str, bool, str]]]) -> list[dict[str, Any]]:
        raw = await self.rpc.call("eth_getLogs", [{"address": address, "fromBlock": "0x0", "toBlock": "latest"}])
        decoded = [d for d in (decode_log(log, events) for log in raw) if d]
        return sorted(decoded, key=lambda d: (d["block"], d["log_index"]))

    async def _block_time(self, block: int | str) -> int:
        number = block if isinstance(block, str) else hex(block)
        return int((await self.rpc.call("eth_getBlockByNumber", [number, False]))["timestamp"], 16)

    async def activity(self) -> list[dict[str, Any]]:
        events = await self._logs(self.wallet, WALLET_EVENTS)
        blocks = sorted({e["block"] for e in events})
        times = dict(zip(blocks, await asyncio.gather(*(self._block_time(b) for b in blocks)), strict=True))
        items = [_activity_item(e, times[e["block"]]) for e in events]
        return list(reversed(items))

    async def _tokens(self, oracle: str) -> list[dict[str, Any]]:
        oracle_events = await self._logs(oracle, ORACLE_EVENTS)
        addresses = [ZERO] + sorted({e["values"]["token"] for e in oracle_events if e["values"]["token"] != ZERO})
        return list(await asyncio.gather(*(self._token(oracle, a) for a in addresses)))

    async def _token(self, oracle: str, token: str) -> dict[str, Any]:
        feed, _max_age, decimals, enabled, fixed, _price = (
            await self._view("tokenConfig(address)", ["address"], [token], ["address", "uint48", "uint8", "bool", "bool", "uint256"], to=oracle)
        )
        if token == ZERO:
            symbol = "ETH"
            balance = int(await self.rpc.call("eth_getBalance", [self.wallet, "latest"]), 16)
        else:
            try:
                (symbol,) = await self._view("symbol()", [], [], ["string"], to=token)
            except Exception:  # noqa: BLE001 - tokens without symbol() are still shown
                symbol = _short(token)
            (balance,) = await self._view("balanceOf(address)", ["address"], [self.wallet], ["uint256"], to=token)
        usd: str | None = None
        try:
            (value,) = await self._view("quoteUsd(address,uint256)", ["address", "uint256"], [token, balance], ["uint256"], to=oracle)
            usd = _usd(value)
        except Exception:  # noqa: BLE001 - stale or unconfigured prices stay unpriced
            usd = None
        if not enabled:
            freshness = "Disabled"
        elif usd is None:
            freshness = "Unpriced"
        else:
            freshness = "Mock" if fixed else "Fresh"
        return {
            "address": token,
            "symbol": symbol,
            "decimals": decimals,
            "balance": str(balance),
            "usd_value": usd,
            "price_source": "fixed" if fixed else "chainlink" if feed != ZERO else "none",
            "freshness": freshness,
        }

    async def overview(self) -> dict[str, Any]:
        summary, oracle, deposit_args, latest = await asyncio.gather(
            self.summary(),
            self._view("priceOracle()", [], [], ["address"]),
            self._view("entryPoint()", [], [], ["address"]),
            self.rpc.call("eth_getBlockByNumber", ["latest", False]),
        )
        entry_point = deposit_args[0]
        now = int(latest["timestamp"], 16)
        wallet_events, (window_start,), (deposit,), (gas,), (pending_policy,) = await asyncio.gather(
            self._logs(self.wallet, WALLET_EVENTS),
            self._view("windowStart()", [], [], ["uint48"]),
            self._view("balanceOf(address)", ["address"], [self.wallet], ["uint256"], to=entry_point),
            self._view("maxCallGas()", [], [], ["uint128"]),
            self._view("maxOpenPendingPerAgent()", [], [], ["uint32"]),
        )
        tokens = await self._tokens(oracle[0])
        agents = sorted({e["values"]["agent"] for e in wallet_events if e["event"] == "SessionAdded"})
        sessions = []
        for agent in agents:
            valid_after, valid_until, open_pending, revoked = await self._view(
                "sessions(address)", ["address"], [agent], ["uint48", "uint48", "uint32", "bool"]
            )
            sessions.append(
                {
                    "agent": agent,
                    "valid_after": valid_after,
                    "valid_until": valid_until,
                    "open_pending": open_pending,
                    "revoked": revoked,
                    "active": (not revoked) and valid_after <= now <= valid_until and not summary["paused"],
                }
            )
        executed = [e for e in wallet_events if e["event"] == "AgentCallExecuted"]
        priced = [t for t in tokens if t["usd_value"] is not None]
        return {
            "wallet": {**summary, "window_start": window_start, "window_resets_at": window_start + 86400, "max_open_pending": pending_policy, "max_call_gas": gas},
            "chain_time": now,
            "deposit_wei": str(deposit),
            "total_usd": f"{sum(float(t['usd_value']) for t in priced):.2f}",
            "tokens": tokens,
            "sessions": sessions,
            "stats": {
                "executed_operations": len(executed),
                "open_pending": sum(s["open_pending"] for s in sessions),
                "spend_history_usd": [float(_usd(e["values"]["usd"])) for e in executed][-30:],
            },
        }

    async def policy(self) -> dict[str, Any]:
        summary, oracle, wallet_events, (verification,), (call_gas,), (fee,), (ttl,), (max_open,) = await asyncio.gather(
            self.summary(),
            self._view("priceOracle()", [], [], ["address"]),
            self._logs(self.wallet, WALLET_EVENTS),
            self._view("maxVerificationGas()", [], [], ["uint128"]),
            self._view("maxCallGas()", [], [], ["uint128"]),
            self._view("maxFeePerGas()", [], [], ["uint256"]),
            self._view("pendingTtl()", [], [], ["uint48"]),
            self._view("maxOpenPendingPerAgent()", [], [], ["uint32"]),
        )
        tokens = await self._tokens(oracle[0])
        symbols = {t["address"]: t["symbol"] for t in tokens}
        call_pairs = {(e["values"]["target"], e["values"]["selector"]) for e in wallet_events if e["event"] == "CallPolicyUpdated"}
        recipients = {e["values"]["recipient"] for e in wallet_events if e["event"] == "RecipientPolicyUpdated"}
        calls = []
        for target, selector in sorted(call_pairs):
            (allowed,) = await self._view("allowedCall(address,bytes4)", ["address", "bytes4"], [target, bytes.fromhex(selector[2:])], ["bool"])
            calls.append({"target": target, "label": symbols.get(target, "Contract"), "selector": selector, "signature": KNOWN_SELECTORS.get(selector, selector), "allowed": allowed})
        recipient_rows = []
        for recipient in sorted(recipients):
            (allowed,) = await self._view("allowedRecipient(address)", ["address"], [recipient], ["bool"])
            recipient_rows.append({"address": recipient, "allowed": allowed})
        return {
            "spend": {"per_transaction_usd": summary["per_transaction_limit_usd"], "daily_usd": summary["daily_limit_usd"]},
            "gas": {"max_verification_gas": verification, "max_call_gas": call_gas, "max_fee_per_gas_wei": str(fee)},
            "pending": {"ttl_seconds": ttl, "max_open_per_agent": max_open},
            "allowed_calls": calls,
            "allowed_recipients": recipient_rows,
            "tokens": tokens,
        }

    async def chain_time(self) -> int:
        return await self._block_time("latest")
