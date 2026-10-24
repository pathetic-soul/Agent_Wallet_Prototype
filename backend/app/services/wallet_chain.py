"""Read wallet state and (optionally) send owner transactions over standard JSON-RPC.

The wallet contract stays the only policy authority. This module only reads its public state and,
when a local demo owner key is explicitly configured, relays owner calls such as approvePending.
"""

import asyncio
from typing import Any

from eth_abi import decode, encode
from eth_account import Account
from eth_utils import function_signature_to_4byte_selector

from app.services.json_rpc import JsonRpcClient

PENDING_STATUS = ("none", "open", "approved", "rejected", "expired")
PENDING_REASON = ("over_per_transaction_limit", "over_daily_limit", "pricing_failed")
PENDING_TYPE = "(address,uint48,uint48,uint8,uint8,uint256,bytes)"
CALLS_TYPE = "(address,uint256,bytes)[]"
USD_DECIMALS = 10**8


class OwnerTransactionError(RuntimeError):
    pass


def _selector(signature: str) -> str:
    return "0x" + function_signature_to_4byte_selector(signature).hex()


def _usd(value: int) -> str:
    return f"{value // USD_DECIMALS}.{value % USD_DECIMALS * 100 // USD_DECIMALS:02d}"


class WalletChain:
    def __init__(self, rpc_url: str, wallet: str, rpc: JsonRpcClient | None = None) -> None:
        self.rpc = rpc or JsonRpcClient(rpc_url)
        self.wallet = wallet

    async def _view(
        self,
        signature: str,
        types: list[str],
        values: list[Any],
        out: list[str],
        to: str | None = None,
    ) -> tuple:
        data = bytes.fromhex(_selector(signature)[2:]) + encode(types, values)
        result = await self.rpc.call(
            "eth_call", [{"to": to or self.wallet, "data": "0x" + data.hex()}, "latest"]
        )
        return decode(out, bytes.fromhex(result[2:]))

    async def summary(self) -> dict[str, Any]:
        owner, paused, per_tx, daily, spent, next_id = await asyncio.gather(
            self._view("owner()", [], [], ["address"]),
            self._view("paused()", [], [], ["bool"]),
            self._view("perTransactionLimitUsd()", [], [], ["uint256"]),
            self._view("dailyLimitUsd()", [], [], ["uint256"]),
            self._view("spentInWindowUsd()", [], [], ["uint256"]),
            self._view("nextPendingId()", [], [], ["uint256"]),
        )
        return {
            "address": self.wallet,
            "owner": owner[0].lower(),
            "paused": paused[0],
            "per_transaction_limit_usd": _usd(per_tx[0]),
            "daily_limit_usd": _usd(daily[0]),
            "spent_in_window_usd": _usd(spent[0]),
            "next_pending_id": next_id[0],
        }

    async def pending_requests(self) -> list[dict[str, Any]]:
        (next_id,) = await self._view("nextPendingId()", [], [], ["uint256"])
        ids = range(1, next_id)
        raw = await asyncio.gather(
            *(self._view("getPending(uint256)", ["uint256"], [i], [PENDING_TYPE]) for i in ids)
        )
        requests = []
        for pending_id, (entry,) in zip(ids, raw, strict=True):
            agent, created_at, expires_at, status, reason, usd_value, encoded = entry
            (calls,) = decode([CALLS_TYPE], encoded)
            requests.append(
                {
                    "id": pending_id,
                    "agent": agent.lower(),
                    "status": PENDING_STATUS[status],
                    "reason": PENDING_REASON[reason],
                    "usd_value": _usd(usd_value),
                    "created_at": created_at,
                    "expires_at": expires_at,
                    "calls": [
                        {
                            "target": target.lower(),
                            "value": str(value),
                            "data": "0x" + data.hex(),
                            "selector": "0x" + data[:4].hex() if len(data) >= 4 else "0x",
                        }
                        for target, value, data in calls
                    ],
                }
            )
        return list(reversed(requests))

    async def owner_transaction(self, private_key: str, signature: str, types: list[str], values: list[Any]) -> str:
        account = Account.from_key(private_key)
        data = "0x" + (bytes.fromhex(_selector(signature)[2:]) + encode(types, values)).hex()
        call = {"from": account.address, "to": self.wallet, "data": data}
        nonce, block, gas = await asyncio.gather(
            self.rpc.call("eth_getTransactionCount", [account.address, "pending"]),
            self.rpc.call("eth_getBlockByNumber", ["latest", False]),
            self.rpc.call("eth_estimateGas", [call]),
        )
        base_fee = int(block.get("baseFeePerGas", "0x0"), 16)
        chain_id = int(await self.rpc.call("eth_chainId"), 16)
        signed = account.sign_transaction(
            {
                "nonce": int(nonce, 16),
                "gasPrice": base_fee * 2 + 10**9,
                "gas": int(gas, 16) * 12 // 10 + 20_000,
                "to": self.wallet,
                "value": 0,
                "data": data,
                "chainId": chain_id,
            }
        )
        tx_hash = await self.rpc.call("eth_sendRawTransaction", ["0x" + signed.raw_transaction.hex()])
        for _ in range(100):
            receipt = await self.rpc.call("eth_getTransactionReceipt", [tx_hash])
            if receipt:
                if receipt.get("status") != "0x1":
                    raise OwnerTransactionError("Owner transaction reverted")
                return tx_hash
            await asyncio.sleep(0.1)
        raise OwnerTransactionError("Timed out waiting for the owner transaction")
