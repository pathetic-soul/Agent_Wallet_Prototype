"""Deploy the full Agent Wallet stack to a local anvil chain and configure demo policy.

Usage: .venv/bin/python demo/deploy_local.py [--rpc http://127.0.0.1:8545]
"""

from __future__ import annotations

import argparse
import json

from eth_utils import to_checksum_address

from chain import ANVIL_KEYS, DEPLOYMENTS, Client, Rpc, address_of, calldata, selector

USD = 10**8  # oracle precision
ETH_PRICE = 2_000 * USD
ETH = 10**18
USDC = 10**6


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rpc", default="http://127.0.0.1:8545")
    args = parser.parse_args()

    client = Client(Rpc(args.rpc))
    deployer, owner = ANVIL_KEYS["deployer"], ANVIL_KEYS["owner"]
    owner_addr, agent_addr = address_of("owner"), address_of("agent")
    merchant_addr = address_of("merchant")

    entry_point = client.deploy(deployer, "DevEntryPoint", source="DevEntryPoint")
    oracle = client.deploy(deployer, "PriceOracle", ["address"], [address_of("deployer")])
    usdc = client.deploy(deployer, "DevMockUSDC")
    shop = client.deploy(deployer, "TicketShop", ["uint256"], [ETH // 200])  # 0.005 ETH = $10
    premium_shop = client.deploy(deployer, "TicketShop", ["uint256"], [ETH * 35 // 2000])  # $35
    factory = client.deploy(deployer, "AgentWalletFactory", ["address", "address"], [entry_point, oracle])

    zero = "0x0000000000000000000000000000000000000000"
    client.send(deployer, oracle, calldata("setFixedPrice(address,uint8,uint256)", ["address", "uint8", "uint256"], [zero, 18, ETH_PRICE]))
    client.send(deployer, oracle, calldata("setFixedPrice(address,uint8,uint256)", ["address", "uint8", "uint256"], [usdc, 6, USD]))

    salt = b"\x00" * 32
    per_tx, daily = 20 * USD, 50 * USD
    client.send(deployer, factory, calldata("createWallet(address,bytes32,uint256,uint256)", ["address", "bytes32", "uint256", "uint256"], [owner_addr, salt, per_tx, daily]))
    (wallet,) = client.view(factory, "getAddress(address,bytes32,uint256,uint256)", ["address", "bytes32", "uint256", "uint256"], [owner_addr, salt, per_tx, daily], ["address"])
    wallet = to_checksum_address(wallet)

    def owner_tx(signature: str, types: list[str], values: list) -> None:
        client.send(owner, wallet, calldata(signature, types, values))

    buy = selector("buyTicket(address)")
    for target in (shop, premium_shop):
        owner_tx("setCallPolicy(address,bytes4,bool)", ["address", "bytes4", "bool"], [target, buy, True])
    for sig in ("transfer(address,uint256)", "approve(address,uint256)"):
        owner_tx("setCallPolicy(address,bytes4,bool)", ["address", "bytes4", "bool"], [usdc, selector(sig), True])
    owner_tx("setRecipientPolicy(address,bool)", ["address", "bool"], [merchant_addr, True])

    now = client.timestamp()
    owner_tx("addSession(address,uint48,uint48)", ["address", "uint48", "uint48"], [agent_addr, 0, now + 7 * 24 * 3600])

    # Fund the wallet with ETH, test USDC, and an EntryPoint deposit for gas.
    client.send(deployer, wallet, b"", value=2 * ETH)
    client.send(deployer, usdc, calldata("mint(address,uint256)", ["address", "uint256"], [wallet, 1_000 * USDC]))
    client.send(deployer, wallet, calldata("addDeposit()", [], []), value=1 * ETH)

    DEPLOYMENTS.write_text(json.dumps({
        "rpc": args.rpc,
        "chainId": client.chain_id,
        "entryPoint": entry_point,
        "oracle": oracle,
        "usdc": usdc,
        "ticketShop": shop,
        "premiumTicketShop": premium_shop,
        "factory": factory,
        "wallet": wallet,
        "owner": owner_addr,
        "agent": agent_addr,
        "attacker": address_of("attacker"),
        "merchant": merchant_addr,
    }, indent=2) + "\n")
    print(f"Deployed. Wallet {wallet}\nEntryPoint {entry_point}\nSaved {DEPLOYMENTS}")


if __name__ == "__main__":
    main()
