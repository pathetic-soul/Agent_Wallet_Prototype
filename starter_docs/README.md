# Agent Wallet

Agent Wallet is a testnet-only ERC-4337 smart account for AI agents. It places spending and call policies on-chain so that a compromised model or leaked agent key cannot bypass them. The first build targets Base Sepolia, EntryPoint v0.7, a MetaMask owner, and a local open-weight agent model.

## What the first version must prove

- A valid agent operation can buy API credits and a ticket through a bundler.
- Target, function selector, recipient, session, gas, and USD spending limits are enforced by the wallet contract.
- Over-limit or unpriceable requests become owner-visible pending requests instead of executing.
- Prompt injection, a leaked agent key, calldata tricks, expired or revoked sessions, Permit signing, and cross-chain replay all fail on-chain.
- The owner can pause the wallet, revoke a session, change policy, approve a pending request, and reject a pending request.

## System components

| Component | Responsibility |
|---|---|
| `AgentWallet.sol` | ERC-4337 account, validation, execution, policy enforcement, pending approvals, EIP-1271 behavior |
| `AgentWalletFactory.sol` | Deterministic CREATE2 deployment |
| `PriceOracle.sol` | Chainlink-based USD valuation with staleness checks and a clearly labeled mock-feed path for unsupported testnet assets |
| `TicketShop.sol` | On-chain purchase target used in the demo |
| Local agent | Generates constrained tool calls and submits UserOperations |
| FastAPI backend | Builds/submits UserOperations, indexes wallet events, serves the paywall, and sends web-push notifications |
| React dashboard | Owner policy controls, activity feed, approvals, pause/revoke controls, and attack console |
| Bundler and EntryPoint | Simulate, validate, and execute UserOperations |

## Locked technical decisions

- Chain: Base Sepolia, with Ethereum Sepolia used only for replay testing.
- Account abstraction: EntryPoint v0.7 and `PackedUserOperation`.
- Contracts: built from scratch around `IAccount`; OpenZeppelin only for proven cryptographic utilities.
- Owner authentication: MetaMask EOA.
- Agent: local 7-8B model with a scripted fallback for the demo.
- Contract tooling: Foundry, Slither, and GitHub Actions.
- Application stack: Python 3.11 with FastAPI, React with Vite and wagmi, and web push.
- Security posture: testnet only and unaudited.

## Repository layout

```text
contracts/   Solidity contracts, Foundry tests, scripts, and deployment records
agent/       Local model runner, tools, and scripted fallback agent
backend/     FastAPI service, UserOperation sender, event indexer, paywall, and push sender
web/         React dashboard and installable PWA
starter_docs/  Architecture, threat model, build plan, and demo runbook
```

## Milestones

1. A signed owner UserOperation executes on Base Sepolia by hour 6.
2. All on-chain policy checks work on testnet by hour 12.
3. Contracts freeze and deployments verify by hour 16.
4. The full demo, attack suite, backup video, and submission materials freeze by hour 20-24.

## Definition of done

- Contracts are deployed and verified on Basescan, with addresses recorded here.
- `forge test`, fuzz tests, invariants, and Slither checks pass in CI.
- The dashboard and backend are reachable from a public URL.
- Every stage claim maps to a passing automated test.
- Each attack script runs with one command and produces an auditable on-chain result.
- The README contains a ten-minute setup path, architecture diagram, deployment addresses, and demo walkthrough.
- The UI clearly says `Testnet only - unaudited`.

## Working document index

- [Architecture](ARCHITECTURE.md)
- [Threat model](THREAT_MODEL.md)
- [Build plan](BUILD_PLAN.md)
- [Demo runbook](DEMO_RUNBOOK.md)
- `Agent_Wallet_Project_Brief.docx` for stakeholder review and sharing

## Open fields to complete

- Base Sepolia EntryPoint address: `TBD`
- Factory address: `TBD`
- Wallet address: `TBD`
- Price feed addresses and heartbeat thresholds: `TBD`
- Bundler provider and endpoint: `TBD`
- Dashboard URL: `TBD`
- Backend URL: `TBD`
- Demo transaction and UserOperation links: `TBD`

