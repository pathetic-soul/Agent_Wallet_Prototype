# Local zero-cost demo

Runs the whole stack on your machine with no accounts, API keys, or faucets:
anvil (local chain) -> reference EntryPoint -> AgentWallet -> a tiny local bundler -> FastAPI relay -> dashboard.

- `deploy_local.py` deploys EntryPoint, oracle (fixed prices: ETH $2000, dUSDC $1), mock USDC, two ticket shops ($10 and $35), the factory, and a configured wallet ($20 per-tx, $50 daily).
- `local_bundler.py` implements `eth_sendUserOperation`, `eth_estimateUserOperationGas`, `eth_getUserOperationReceipt`, `eth_supportedEntryPoints`. It simulates `handleOps` first, so policy rejections come back with readable reasons. Not a production bundler.
- `run_demo.py` signs operations as the agent and an attacker and relays them through the backend.
- `start.sh` does everything in order.

One-time setup: download Foundry v1.7.1 and place `anvil` in `.tools/bin/` (git-ignored). Keys in `chain.py` are anvil's public default accounts and are worthless.

Note: the installed `@account-abstraction/contracts` is 0.8.0, so the local EntryPoint is v0.8 (EIP-712 userOp hash), not v0.7.

Tests (stack must be running): `.venv/bin/python -m pytest demo/tests -o addopts="" -q` - 30 integration tests, each isolated by an anvil snapshot.

## Dashboard wiring

With the backend started by `start.sh` (or the same env vars), every dashboard page reads the local chain: balances and token prices, spend budget, sessions, policy, the activity feed (rebuilt from wallet events), and the approvals queue. Owner actions (approve/reject, pause, revoke, add session, limits, allowlists) are sent by the backend using `DEMO_OWNER_PRIVATE_KEY`; the Attack Console signs real hostile operations with `DEMO_AGENT_PRIVATE_KEY` and `DEMO_ATTACKER_PRIVATE_KEY`. All three are anvil's public test keys. Leave them unset anywhere else and those features switch off.

Blocked attempts are not on-chain events. They come from the API's in-memory relay log and reset when the API restarts.
Run the integration tests on a freshly deployed chain: the Attack Console's replay attack really executes one ticket purchase.
