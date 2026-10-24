# Agent Wallet Threat Model

## Scope and conclusion

The first release protects a testnet wallet when the agent is malicious, manipulated, or using a leaked session key. Security relies on the EntryPoint hash domain, wallet validation logic, execution-time policy checks, trusted owner keys, and fresh oracle data. The system is unaudited and must not custody real funds.

## Assets

- Native ETH and configured ERC-20 balances held by the wallet.
- EntryPoint deposit used to pay UserOperation gas.
- Owner control over policies, sessions, approvals, and emergency pause.
- Integrity of spend counters, pending requests, allowlists, and token configuration.
- Availability of the demo, backend, dashboard, bundler, RPC, and oracle feeds.

## Trust assumptions

- The owner EOA and MetaMask session are not compromised.
- EntryPoint v0.7 and the selected cryptographic libraries behave as specified.
- Chainlink feed addresses and heartbeat thresholds are configured correctly.
- The bundler may reject or censor requests, but it cannot bypass wallet validation.
- The backend and local model are untrusted for policy enforcement.
- Demo target contracts behave as documented.

## Security invariants

1. Agent-executed USD spend in a window never exceeds `dailyLimitUsd`.
2. No agent operation executes against a non-allowlisted target, selector, recipient, or spender.
3. No agent operation executes after session expiry, after revocation, or while paused.
4. An agent operation cannot change owner or policy storage.
5. Open pending requests per agent never exceed the configured cap.
6. A batch is evaluated against its total value before any member executes.
7. Unknown or stale prices never result in automatic execution.
8. Only the owner can authorize arbitrary EIP-1271 messages.

## Threat matrix

| Threat | Control | Required evidence | Residual risk |
|---|---|---|---|
| Prompt injection instructs a transfer to an attacker | On-chain target, selector, and decoded-recipient allowlists | Unit test and live rejected UserOperation | Allowed recipients may still be malicious or compromised |
| Agent session key leaks | Same policy applies to hand-built UserOperations; session expiry, revoke, pause, and gas caps | Attack script using the raw key | Attacker can spend within the granted policy until revoked |
| ERC-20 calldata hides the true recipient | Decode `transfer`, `transferFrom`, and `approve`; enforce recipient or spender allowlist | Tests for malformed and adversarial calldata | Token contracts with unusual semantics need explicit support |
| Approve then transferFrom bypasses spend limits | Count the full approved amount toward USD limits; agent cannot sign Permit messages | Tests for approve and EIP-1271 Permit attempts | Existing allowances created by the owner remain a governance concern |
| Batch splits value into many small calls | Sum the complete batch before any execution | Unit, fuzz, and invariant tests | Complex target-side effects require careful atomicity review |
| Agent calls wallet admin functions | Permit only `execute` or `executeBatch`, reject self-calls and admin selectors | Tests for every owner-only method | Future methods must be included in regression testing |
| Cross-chain or cross-wallet replay | Verify the EntryPoint `userOpHash`, which binds chain, EntryPoint, and sender | Replay script on Ethereum Sepolia and a second wallet | Misconfigured or nonstandard EntryPoint integrations could weaken assumptions |
| Expired or revoked session executes | Check session state and pack validity into `validationData` | Boundary tests around `validAfter` and `validUntil` | Timestamp granularity and reorg behavior remain normal chain risks |
| Stale, missing, or invalid price feed | Fail closed to pending; validate answer, timestamp, decimals, and heartbeat | Tests using stale and invalid mock answers | Oracle compromise or incorrect configuration remains possible |
| Pending queue flooding | Per-agent open-request cap and expiry | Fuzz test and live flood script | A compromised key may fill its own cap and deny further requests |
| Gas deposit griefing | Cap call gas, verification gas, and fee fields during validation | Tests with oversized values | Repeated valid requests within caps can still consume gas |
| Owner approval reentrancy | Checks-effects-interactions, reentrancy guard, single-use status transition | Malicious target contract test | Owner can deliberately approve dangerous calls |
| Backend or dashboard compromise | Policy enforced in the wallet; owner verifies transaction details in MetaMask | Integration test with malicious backend payload | Phishing can still trick the owner into changing policy |

## Out of scope for the first build

- Mainnet custody or production deployment.
- A compromised owner key or malicious owner.
- Bugs in EntryPoint, the EVM, OpenZeppelin cryptography, or the selected oracle network.
- General support for fee-on-transfer, rebasing, callback-heavy, or otherwise nonstandard tokens.
- Full rolling-window rate limits; the fixed window can permit up to twice the nominal daily limit around a boundary.
- Full x402 compatibility when it requires agent-authorized off-chain token signatures.
- Privacy of balances, policies, requests, and transaction history.
- Guaranteed availability of RPC, bundler, web-push, hosting, or the local model.

## Test strategy

### Unit tests

- Owner and agent signature paths.
- Every allowlist dimension and every supported ERC-20 selector.
- Session time boundaries, pause, revoke, and admin access.
- USD conversion, decimals, batch aggregation, daily reset, stale prices, and unknown tokens.
- Pending creation, cap, expiry, approval, rejection, duplicate execution, and reentrancy.
- EIP-1271 owner acceptance and agent rejection.

### Fuzz and invariant tests

- Random agent call sequences preserve all eight security invariants.
- Random token decimals, prices, and amounts do not undercount spend through rounding.
- Random batches cannot partially execute before a failing policy decision.
- Pending counts and status transitions remain consistent.

### Static and integration checks

- Run Slither on every contract and document non-informational findings.
- Run `forge test` in CI on each push.
- Record `forge snapshot` costs for the policy path.
- Exercise every live attack on Base Sepolia with explorer evidence.

## Known limitations and decisions to revisit

- The fixed 24-hour window has a boundary effect; rolling buckets are the upgrade path.
- Execution-time oracle checks mean an over-limit operation consumes some gas before becoming pending.
- A persistent dashboard record for validation failures must come from bundler simulation or backend telemetry, because rejected validation is not a durable on-chain event.
- Mock price feeds are acceptable only for labeled testnet demonstrations.
- Contract freeze at hour 16 limits late fixes; any later change requires redeployment and a full regression run.

