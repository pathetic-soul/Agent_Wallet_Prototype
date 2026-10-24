"""Local-demo attack runner: hand-builds and signs hostile UserOperations and submits them for real.

Every attack goes through the same bundler and EntryPoint as a legitimate agent. The keys come from
`DEMO_*` settings and exist only so a local demo can show the wallet refusing them. Never configure
them against a network that holds assets with value.
"""

from typing import Any

from eth_abi import encode
from eth_account import Account
from eth_account.messages import encode_defunct
from eth_utils import function_signature_to_4byte_selector

from app.models import PackedUserOperation
from app.services.bundler import BundlerClient
from app.services.json_rpc import JsonRpcError
from app.services.wallet_reader import WalletReader

CALL = "(address,uint256,bytes)"
USER_OP = "(address,uint256,bytes,bytes,bytes32,uint256,bytes32,bytes,bytes)"
MAX_UINT = 2**256 - 1
ATTACKS = ("prompt-injection", "leaked-key", "approve-max", "batch-smuggling", "gas-grief", "replay")


class AttackSetupError(RuntimeError):
    """The wallet is not configured with the targets the attack needs."""


def _sel(signature: str) -> bytes:
    return function_signature_to_4byte_selector(signature)


def _pack(high: int, low: int) -> bytes:
    return high.to_bytes(16, "big") + low.to_bytes(16, "big")


class DemoAttacks:
    def __init__(self, reader: WalletReader, bundler: BundlerClient, entry_point: str, agent_key: str, attacker_key: str) -> None:
        self.reader, self.bundler, self.entry_point = reader, bundler, entry_point
        self.agent_key, self.attacker_key = agent_key, attacker_key
        self.agent = Account.from_key(agent_key).address
        self.attacker = Account.from_key(attacker_key).address

    async def _targets(self) -> tuple[str, str, int]:
        policy = await self.reader.policy()
        allowed = [c for c in policy["allowed_calls"] if c["allowed"]]
        shop = next((c["target"] for c in allowed if c["signature"] == "buyTicket(address)"), None)
        token = next((c["target"] for c in allowed if c["signature"] == "transfer(address,uint256)"), None)
        if shop is None or token is None:
            raise AttackSetupError("The wallet needs an allowed buyTicket target and an allowed token transfer")
        (price,) = await self.reader._view("ticketPrice()", [], [], ["uint256"], to=shop)
        return shop, token, price

    async def _operation(self, calls: list[tuple[str, int, bytes]], key: str, agent: str, call_gas: int = 500_000) -> PackedUserOperation:
        if len(calls) == 1:
            data = _sel(f"executeAgent(address,{CALL})") + encode(["address", CALL], [agent, calls[0]])
        else:
            data = _sel(f"executeAgentBatch(address,{CALL}[])") + encode(["address", f"{CALL}[]"], [agent, calls])
        (nonce,) = await self.reader._view("getNonce(address,uint192)", ["address", "uint192"], [self.reader.wallet, 0], ["uint256"], to=self.entry_point)
        fields = [self.reader.wallet, nonce, b"", data, _pack(500_000, call_gas), 100_000, _pack(1_000_000_000, 3_000_000_000), b"", b""]
        (digest,) = await self.reader._view(f"getUserOpHash({USER_OP})", [USER_OP], [fields], ["bytes32"], to=self.entry_point)
        signature = Account.sign_message(encode_defunct(primitive=digest), private_key=key).signature
        hx = lambda b: "0x" + bytes(b).hex()  # noqa: E731
        return PackedUserOperation(
            sender=self.reader.wallet, nonce=hex(nonce), initCode="0x", callData=hx(data),
            accountGasLimits=hx(fields[4]), preVerificationGas=hex(100_000), gasFees=hx(fields[6]),
            paymasterAndData="0x", signature=hx(signature),
        )

    async def _submit(self, operation: PackedUserOperation) -> tuple[str, str | None]:
        try:
            return "executed", await self.bundler.send_user_operation(operation)
        except JsonRpcError as exc:
            return "blocked", str(exc)

    async def run(self, attack: str) -> dict[str, Any]:
        shop, token, price = await self._targets()
        wallet = self.reader.wallet
        buy = (shop, price, _sel("buyTicket(address)") + encode(["address"], [self.agent]))
        drain = (token, 0, _sel("transfer(address,uint256)") + encode(["address", "uint256"], [self.attacker, 100_000_000]))
        reason: str | None
        if attack == "prompt-injection":
            outcome, reason = await self._submit(await self._operation([drain], self.agent_key, self.agent))
        elif attack == "leaked-key":
            outcome, reason = await self._submit(await self._operation([buy], self.attacker_key, self.attacker))
        elif attack == "approve-max":
            approve = (token, 0, _sel("approve(address,uint256)") + encode(["address", "uint256"], [self.attacker, MAX_UINT]))
            outcome, reason = await self._submit(await self._operation([approve], self.agent_key, self.agent))
        elif attack == "batch-smuggling":
            outcome, reason = await self._submit(await self._operation([buy, drain], self.agent_key, self.agent))
        elif attack == "gas-grief":
            outcome, reason = await self._submit(await self._operation([buy], self.agent_key, self.agent, call_gas=10_000_000))
        elif attack == "replay":
            operation = await self._operation([buy], self.agent_key, self.agent)
            first, _ = await self._submit(operation)
            if first != "executed":
                raise AttackSetupError("The legitimate operation was refused, so there is nothing to replay")
            await self._wait_for_nonce(operation.nonce)
            outcome, reason = await self._submit(operation)
        else:
            raise KeyError(attack)
        return {"attack": attack, "outcome": outcome, "reason": reason if outcome == "blocked" else None, "user_operation_hash": reason if outcome == "executed" else None, "wallet": wallet}

    async def _wait_for_nonce(self, used_nonce: str) -> None:
        import asyncio

        for _ in range(50):
            (nonce,) = await self.reader._view("getNonce(address,uint192)", ["address", "uint192"], [self.reader.wallet, 0], ["uint256"], to=self.entry_point)
            if nonce > int(used_nonce, 16):
                return
            await asyncio.sleep(0.1)
