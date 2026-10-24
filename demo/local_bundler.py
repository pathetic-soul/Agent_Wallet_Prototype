"""A tiny ERC-4337 bundler for local demos: JSON-RPC over HTTP, executes via handleOps on anvil.

It exists so the demo needs no paid bundler account. It simulates every operation with eth_call
before sending it, which gives readable policy-rejection reasons. It is NOT a production bundler.

Usage: .venv/bin/uvicorn local_bundler:app --app-dir demo --port 3000
"""

from __future__ import annotations

import json
import os

from eth_abi import decode
from eth_utils import keccak, to_checksum_address
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from chain import (
    ANVIL_KEYS, DEPLOYMENTS, USER_OP_TYPE, Client, Rpc, RpcError, address_of, artifact, calldata,
    describe_revert, error_selectors, op_from_json, op_tuple, user_op_hash,
)

deployment = json.loads(DEPLOYMENTS.read_text())
ENTRY_POINT = deployment["entryPoint"]
client = Client(Rpc(os.environ.get("CHAIN_RPC", deployment["rpc"])))
BUNDLER_KEY = ANVIL_KEYS["deployer"]
BENEFICIARY = address_of("deployer")
ERRORS = {**error_selectors(artifact("AgentWallet")["abi"]), **error_selectors(artifact("DevEntryPoint")["abi"])}
USER_OP_EVENT = "0x" + keccak(text="UserOperationEvent(bytes32,address,address,uint256,bool,uint256,uint256)").hex()

sent: dict[str, str] = {}  # userOpHash -> transaction hash

app = FastAPI(title="Local demo bundler")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def handle_ops_data(op: dict) -> bytes:
    return calldata(f"handleOps({USER_OP_TYPE}[],address)", [f"{USER_OP_TYPE}[]", "address"], [[op_tuple(op)], BENEFICIARY])


def simulate(op: dict) -> None:
    try:
        client.rpc.call("eth_call", [{"from": BENEFICIARY, "to": ENTRY_POINT, "data": "0x" + handle_ops_data(op).hex(), "gas": hex(5_000_000)}, "latest"])
    except RpcError as exc:
        data = exc.data if isinstance(exc.data, str) else (exc.data or {}).get("data") if isinstance(exc.data, dict) else None
        reason = describe_revert(bytes.fromhex(data[2:]), ERRORS) if isinstance(data, str) and data.startswith("0x") else str(exc)
        raise RpcError(-32500, f"Rejected by EntryPoint simulation: {reason}", data) from exc


def user_operation_receipt(op_hash: str):
    tx_hash = sent.get(op_hash)
    if not tx_hash:
        return None
    receipt = client.rpc.call("eth_getTransactionReceipt", [tx_hash])
    if not receipt:
        return None
    success = False
    for log in receipt["logs"]:
        if log["topics"][0] == USER_OP_EVENT and log["topics"][1] == op_hash:
            (_, success_flag, *_rest) = decode(["uint256", "bool", "uint256", "uint256"], bytes.fromhex(log["data"][2:]))
            success = success_flag
    return {
        "userOpHash": op_hash,
        "entryPoint": ENTRY_POINT,
        "success": success,
        "receipt": receipt,
        "logs": receipt["logs"],
    }


def dispatch(method: str, params: list):
    if method == "eth_chainId":
        return hex(client.chain_id)
    if method == "eth_supportedEntryPoints":
        return [ENTRY_POINT]
    if method == "eth_estimateUserOperationGas":
        op = op_from_json(params[0])
        simulate(op)
        return {"preVerificationGas": "0x186a0", "verificationGasLimit": "0x7a120", "callGasLimit": "0x7a120"}
    if method == "eth_sendUserOperation":
        op = op_from_json(params[0])
        op_hash = "0x" + user_op_hash(client, ENTRY_POINT, op).hex()
        simulate(op)
        receipt = client.send(BUNDLER_KEY, ENTRY_POINT, handle_ops_data(op))
        sent[op_hash] = receipt["transactionHash"]
        return op_hash
    if method == "eth_getUserOperationReceipt":
        return user_operation_receipt(params[0])
    raise RpcError(-32601, f"Method not found: {method}")


@app.post("/")
async def rpc(request: Request):
    body = await request.json()
    try:
        return {"jsonrpc": "2.0", "id": body.get("id"), "result": dispatch(body["method"], body.get("params", []))}
    except RpcError as exc:
        return {"jsonrpc": "2.0", "id": body.get("id"), "error": {"code": exc.code, "message": str(exc), "data": exc.data}}
