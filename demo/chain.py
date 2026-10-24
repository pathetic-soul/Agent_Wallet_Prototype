"""Minimal JSON-RPC, deployment, and UserOperation helpers for the local demo.

Everything here targets a throwaway anvil chain. The keys below are anvil's
publicly documented default accounts and must never hold real value.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
from eth_abi import decode, encode
from eth_account import Account
from eth_account.messages import encode_defunct
from eth_utils import function_signature_to_4byte_selector, keccak, to_checksum_address

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"
DEPLOYMENTS = ROOT / "demo" / "deployments.local.json"

# anvil/Hardhat's documented default mnemonic. Deriving the keys at runtime keeps raw private-key
# strings out of the repository, so secret scanners have nothing to flag.
ANVIL_MNEMONIC = "test test test test test test test test test test test junk"
Account.enable_unaudited_hdwallet_features()


def _anvil_key(index: int) -> str:
    return "0x" + Account.from_mnemonic(ANVIL_MNEMONIC, account_path=f"m/44'/60'/0'/0/{index}").key.hex().removeprefix("0x")


ANVIL_KEYS = {role: _anvil_key(i) for i, role in enumerate(("deployer", "owner", "agent", "attacker", "merchant"))}

CALL_TYPE = "(address,uint256,bytes)"
USER_OP_TYPE = "(address,uint256,bytes,bytes,bytes32,uint256,bytes32,bytes,bytes)"


class RpcError(RuntimeError):
    def __init__(self, code: int, message: str, data: object | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.data = data


class Rpc:
    def __init__(self, url: str = "http://127.0.0.1:8545") -> None:
        self.url = url
        self._client = httpx.Client(timeout=30)
        self._id = 0

    def call(self, method: str, params: list | None = None):
        self._id += 1
        body = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params or []}
        data = self._client.post(self.url, json=body).json()
        if "error" in data:
            err = data["error"]
            raise RpcError(err.get("code", -32000), err.get("message", "error"), err.get("data"))
        return data["result"]


def selector(signature: str) -> bytes:
    return function_signature_to_4byte_selector(signature)


def calldata(signature: str, types: list[str], values: list) -> bytes:
    return selector(signature) + encode(types, values)


def artifact(name: str, source: str | None = None) -> dict:
    return json.loads((OUT / f"{source or name}.sol" / f"{name}.json").read_text())


class Client:
    def __init__(self, rpc: Rpc) -> None:
        self.rpc = rpc
        self.chain_id = int(rpc.call("eth_chainId"), 16)

    def send(self, key: str, to: str | None, data: bytes = b"", value: int = 0) -> dict:
        acct = Account.from_key(key)
        nonce = int(self.rpc.call("eth_getTransactionCount", [acct.address, "pending"]), 16)
        base_fee = int(self.rpc.call("eth_getBlockByNumber", ["latest", False])["baseFeePerGas"], 16)
        gas_price = base_fee * 2 + 1_000_000_000  # eth_gasPrice on anvil can drift to absurd values
        tx = {"from": acct.address, "value": hex(value), "data": "0x" + data.hex()}
        if to:
            tx["to"] = to
        gas = int(self.rpc.call("eth_estimateGas", [tx]), 16)
        built = {
            "nonce": nonce,
            "gasPrice": gas_price,
            "gas": gas * 12 // 10 + 20_000,
            "value": value,
            "data": data,
            "chainId": self.chain_id,
        }
        if to:
            built["to"] = to
        raw = acct.sign_transaction(built).raw_transaction
        tx_hash = self.rpc.call("eth_sendRawTransaction", ["0x" + raw.hex()])
        return self.wait(tx_hash)

    def wait(self, tx_hash: str) -> dict:
        for _ in range(100):
            receipt = self.rpc.call("eth_getTransactionReceipt", [tx_hash])
            if receipt:
                if receipt["status"] != "0x1":
                    raise RuntimeError(f"transaction {tx_hash} reverted")
                return receipt
            time.sleep(0.1)
        raise TimeoutError(tx_hash)

    def deploy(self, key: str, name: str, types: list[str] | None = None, args: list | None = None, source: str | None = None) -> str:
        code = bytes.fromhex(artifact(name, source)["bytecode"]["object"][2:])
        if types:
            code += encode(types, args or [])
        receipt = self.send(key, None, code)
        return to_checksum_address(receipt["contractAddress"])

    def view(self, to: str, signature: str, types: list[str], values: list, out: list[str]):
        result = self.rpc.call("eth_call", [{"to": to, "data": "0x" + calldata(signature, types, values).hex()}, "latest"])
        return decode(out, bytes.fromhex(result[2:]))

    def timestamp(self) -> int:
        return int(self.rpc.call("eth_getBlockByNumber", ["latest", False])["timestamp"], 16)


def address_of(role: str) -> str:
    return Account.from_key(ANVIL_KEYS[role]).address


def pack_pair(high: int, low: int) -> bytes:
    return high.to_bytes(16, "big") + low.to_bytes(16, "big")


def build_user_op(sender: str, nonce: int, call_data: bytes, *, verification_gas: int = 500_000, call_gas: int = 500_000, pre_verification_gas: int = 100_000, max_fee: int = 3_000_000_000, priority_fee: int = 1_000_000_000) -> dict:
    return {
        "sender": sender,
        "nonce": nonce,
        "initCode": b"",
        "callData": call_data,
        "accountGasLimits": pack_pair(verification_gas, call_gas),
        "preVerificationGas": pre_verification_gas,
        "gasFees": pack_pair(priority_fee, max_fee),
        "paymasterAndData": b"",
        "signature": b"",
    }


def op_tuple(op: dict) -> list:
    return [op["sender"], op["nonce"], op["initCode"], op["callData"], op["accountGasLimits"], op["preVerificationGas"], op["gasFees"], op["paymasterAndData"], op["signature"]]


def user_op_hash(client: Client, entry_point: str, op: dict) -> bytes:
    (digest,) = client.view(entry_point, f"getUserOpHash({USER_OP_TYPE})", [USER_OP_TYPE], [op_tuple(op)], ["bytes32"])
    return digest


def sign_op(client: Client, entry_point: str, op: dict, key: str) -> dict:
    digest = user_op_hash(client, entry_point, op)
    signed = Account.sign_message(encode_defunct(primitive=digest), private_key=key)
    return {**op, "signature": bytes(signed.signature)}


def op_to_json(op: dict) -> dict:
    """Serialize into the packed JSON shape the backend and bundlers exchange."""
    hexbytes = lambda value: "0x" + value.hex()
    return {
        "sender": op["sender"].lower(),
        "nonce": hex(op["nonce"]),
        "initCode": hexbytes(op["initCode"]),
        "callData": hexbytes(op["callData"]),
        "accountGasLimits": hexbytes(op["accountGasLimits"]),
        "preVerificationGas": hex(op["preVerificationGas"]),
        "gasFees": hexbytes(op["gasFees"]),
        "paymasterAndData": hexbytes(op["paymasterAndData"]),
        "signature": hexbytes(op["signature"]),
    }


def op_from_json(data: dict) -> dict:
    raw = lambda value: bytes.fromhex(value[2:])
    return {
        "sender": to_checksum_address(data["sender"]),
        "nonce": int(data["nonce"], 16),
        "initCode": raw(data["initCode"]),
        "callData": raw(data["callData"]),
        "accountGasLimits": raw(data["accountGasLimits"]),
        "preVerificationGas": int(data["preVerificationGas"], 16),
        "gasFees": raw(data["gasFees"]),
        "paymasterAndData": raw(data["paymasterAndData"]),
        "signature": raw(data["signature"]),
    }


def encode_call(target: str, value: int, data: bytes) -> list:
    return [target, value, data]


def error_selectors(abi: list[dict]) -> dict[bytes, dict]:
    table = {}
    for item in abi:
        if item["type"] == "error":
            types = [i["type"] for i in item["inputs"]]
            sig = f"{item['name']}({','.join(types)})"
            table[keccak(text=sig)[:4]] = {"name": item["name"], "types": types}
    return table


def describe_revert(data: bytes, table: dict[bytes, dict]) -> str:
    """Turn raw revert bytes into a readable reason, unwrapping EntryPoint FailedOp errors."""
    if len(data) < 4:
        return "reverted without data"
    head, body = data[:4], data[4:]
    if head == selector("FailedOp(uint256,string)"):
        _, reason = decode(["uint256", "string"], body)
        return reason
    if head == selector("FailedOpWithRevert(uint256,string,bytes)"):
        _, reason, inner = decode(["uint256", "string", "bytes"], body)
        return f"{reason}: {describe_revert(inner, table)}"
    if head == selector("Error(string)"):
        return decode(["string"], body)[0]
    known = table.get(head)
    if known:
        values = decode(known["types"], body) if known["types"] else ()
        rendered = ", ".join(str(v) for v in values)
        return f"{known['name']}({rendered})"
    return "0x" + data.hex()
