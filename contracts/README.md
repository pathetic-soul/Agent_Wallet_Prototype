# Agent Wallet Contracts

The contract core uses ERC-4337 EntryPoint v0.7 and separates owner execution from agent execution. Agent calls must use `executeAgent` or `executeAgentBatch`, which lets validation bind the recovered session signer to the policy-enforced execution context.

## Contracts

- `AgentWallet.sol` implements account validation, session keys, call and recipient allowlists, gas caps, USD limits, pending approvals, owner controls, and owner-only EIP-1271 signatures.
- `AgentWalletFactory.sol` deploys deterministic CREATE2 wallets.
- `PriceOracle.sol` normalizes Chainlink-style feeds to 8-decimal USD values and includes a clearly labeled fixed-price testnet path.
- `TicketShop.sol` is the initial native-token demo target.

## Compile

```bash
pnpm install
pnpm contracts:compile
pnpm contracts:test
```

The repository installs a project-local Forge binary. The current suite covers a valid agent purchase, selector rejection, over-limit pending creation, and expired-request cleanup. Fuzz and invariant coverage are the next contract milestone.

## Signature convention

Owner and agent UserOperations currently use an ERC-191 `personal_sign` signature over the EntryPoint-provided `userOpHash`. Arbitrary EIP-1271 messages are accepted only from the owner.

## Security status

This code is an unaudited testnet prototype. It is not ready to hold real assets.
