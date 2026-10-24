# Agent Wallet Demo Runbook

## Demo goal

Show one successful agent purchase, then prove that policy survives a malicious prompt, a raw leaked key, crafted token calldata, and a cross-chain replay. End with an over-limit request that reaches the owner and executes only after explicit approval.

## Preflight checklist

- [ ] Base Sepolia and Ethereum Sepolia deployments match the recorded addresses.
- [ ] Owner, agent, attacker, and deployer accounts are loaded and funded.
- [ ] Wallet holds enough test ETH and tokens for the full run.
- [ ] Bundler, both RPC providers, backend, dashboard, and web push are healthy.
- [ ] The local model is loaded and has completed one warm-up tool call.
- [ ] The scripted fallback agent is one action away.
- [ ] Browser tabs are ordered: dashboard, Basescan wallet, UserOperation explorer, attack console.
- [ ] Phone is unlocked, charged, and subscribed to notifications.
- [ ] Every attack command has been reset to a known state.
- [ ] The backup video is stored locally and can play without network access.

## Three minute sequence

| Time | Action | Evidence | Spoken point |
|---|---|---|---|
| 0:00-0:15 | State the risk | Wallet balance and policy screen | Agent wallets fail when prompt safety is the only control; this wallet enforces policy in the contract |
| 0:15-0:50 | Set a 20 USD per-transaction and 50 USD daily policy; buy API credits and a ticket | Two successful UserOperations and activity entries | Normal agent payments still work |
| 0:50-1:25 | Run the malicious prompt asking for all USDC to be sent to the attacker | Rejected simulation or UserOperation with decoded policy reason | Prompt injection cannot override the contract |
| 1:25-1:50 | Submit a hand-built operation with the raw agent key | Rejected validation and attack-console output | The same controls apply even when the model is removed from the loop |
| 1:50-2:15 | Fire `approve(attacker, max)` and a token transfer with the attacker hidden in calldata | Both rejected with spender or recipient reason | The wallet parses the real token recipient, not just the outer target |
| 2:15-2:30 | Resubmit the signed operation on Ethereum Sepolia | Hash mismatch or signature failure | Chain ID, EntryPoint, and sender are bound into the operation hash |
| 2:30-2:50 | Request a 35 USD ticket, receive push, and approve with MetaMask | Pending event, phone notification, owner transaction, ticket event | Exceptions require explicit owner consent |
| 2:50-3:00 | Show green invariants and verified contracts | CI badge, test summary, and Basescan tabs | Four attack categories, no unauthorized spend; testnet only and unaudited |

## Evidence contract

For each scene, capture:

- The command or UI action that triggered it.
- The UserOperation hash or simulation identifier.
- The wallet event or explicit validation reason.
- The wallet balance before and after.
- The exact automated test that covers the same claim.

## Failure recovery

- Bundler trouble: switch to the backup provider and keep the same signed payload only when provider schemas are compatible.
- RPC trouble: switch the dashboard and backend together so displayed state does not diverge.
- Push trouble: show the pending item in the dashboard and explain the tested phone path.
- Model trouble: trigger the scripted agent, using the same public tools and wallet key.
- Explorer delay: show the local event indexer first, then refresh the explorer once.
- Network outage: play the local backup video and answer questions from the test output and verified source.

## Judge questions

### Why build the account from scratch

The first build prioritizes learning and direct control over the ERC-4337 validation boundary. A production evolution would move the design into an ERC-7579 validator and hook after the policy and threat model are proven.

### Why price limits run in execution

ERC-4337 validation must stay compatible with validation rules that restrict external state access. Structural checks remain in validation, while oracle-dependent pricing occurs in execution. A price failure does not execute the call; it creates a pending owner decision.

### Can a leaked key drain the EntryPoint deposit

Agent operations have gas and fee caps, sessions expire and can be revoked, and open pending requests are capped. A compromised key can still create bounded cost within the granted policy, which is a documented residual risk.

### What happens when an oracle is stale

The wallet fails closed. It does not execute the agent call and creates a pending request for the owner. Feed-specific staleness thresholds come from the feed heartbeat, not a single global guess.

### Is the daily window rolling

The first build uses a fixed 24-hour window. It can permit up to twice the limit around a reset boundary. Rolling buckets are the planned upgrade.

### Is it audited or suitable for real money

No. It is a testnet-only prototype with automated tests and a written threat model, not an audit.

### How does this relate to x402

The demo reproduces an HTTP 402-style flow. Full x402 support may depend on signature-based token transfers, while the first policy intentionally refuses arbitrary agent EIP-1271 signatures. That tension is an explicit design question for the next version.

## Post-demo capture

- [ ] Save final explorer URLs and screenshots.
- [ ] Record the exact contract commit and deployment parameters.
- [ ] Export test and gas reports.
- [ ] Note every deviation from the rehearsed sequence.
- [ ] Rotate or discard demo keys after the event.

