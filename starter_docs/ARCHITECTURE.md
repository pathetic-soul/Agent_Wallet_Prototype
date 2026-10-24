# Agent Wallet Architecture

## Purpose

This document defines the first implementation boundary for Agent Wallet. The design keeps structural security checks in ERC-4337 validation and applies price-dependent limits during execution, where external oracle reads are allowed. The wallet fails closed: a request that exceeds policy or cannot be priced is recorded for owner review and is not executed.

## Trust boundaries and flow

```text
Owner ── signs admin calls ───────────────────────────────────────┐
                                                                  v
Local agent ── tool call ──> FastAPI ── UserOperation ──> Bundler ──> EntryPoint v0.7
Attacker ───────────────────────── raw UserOperation ────────────────> EntryPoint v0.7
                                                                        |
                                                                        v
                                                               AgentWallet
                                                               | validation
                                                               | execution
                                                               | pending queue
                                                               +----> PriceOracle
                                                               +----> Demo targets
                                                                        |
                                                                        v
Backend event indexer <────────────── wallet events ───────── Dashboard and web push
```

The agent and attacker enter through the same bundler and EntryPoint boundary. The backend may prepare and submit operations, but it is not trusted to enforce wallet policy.

## Contract responsibilities

### AgentWallet

- Implements `IAccount.validateUserOp` for EntryPoint v0.7.
- Supports owner and session-key signatures.
- Exposes `execute` and `executeBatch` as the only agent execution paths.
- Applies target, selector, recipient, session, gas, and spend policies.
- Maintains the fixed daily spend window and per-transaction limit.
- Stores over-limit, unknown-token, and stale-price requests in a pending queue.
- Supports owner pause, revoke, policy updates, approval, and rejection.
- Implements EIP-1271 so only the owner can authorize arbitrary messages.

### AgentWalletFactory

- Deploys wallets deterministically with CREATE2.
- Makes the counterfactual address known before deployment.
- Supports replay testing with matching deployment conditions across Base Sepolia and Ethereum Sepolia.

### PriceOracle

- Converts native and ERC-20 amounts to USD with eight-decimal precision.
- Rejects stale or invalid feed data.
- Stores feed-specific heartbeat thresholds.
- Allows a clearly labeled owner-set mock feed for testnet assets without a supported Chainlink feed.

### Demo targets

- `TicketShop.sol` provides a simple on-chain purchase.
- The paywall merchant demonstrates an HTTP 402-style API purchase.

## Wallet state model

| State | Purpose |
|---|---|
| `owner`, `paused` | Root control and emergency stop |
| `sessions[agent]` | Validity interval, revocation, and pending-count state |
| `allowedCall[target][selector]` | Target and method allowlist |
| `allowedRecipient[address]` | Recipient and spender allowlist |
| `tokenConfig[token]` | Feed, decimals, enabled flag, and staleness policy |
| `perTxLimitUsd`, `dailyLimitUsd` | USD limits at eight-decimal precision |
| `windowStart`, `spentInWindowUsd` | Fixed 24-hour accounting window |
| `pending[id]` | Stored target, value, calldata, USD value, expiry, requester, and status |

## Validation path

`validateUserOp` must:

1. Accept calls only from the EntryPoint.
2. Recover the signer from `userOpHash`.
3. Give the owner full access after a valid signature.
4. Require an active, unrevoked session for an agent signature and reject when paused.
5. Permit only `execute` or `executeBatch` for agent operations.
6. Reject self-calls, admin methods, and delegatecall paths.
7. Check every inner target and function selector against policy.
8. Decode `transfer`, `transferFrom`, and `approve` calldata and enforce recipient or spender policy.
9. Cap agent gas fields and fee fields to protect the wallet deposit.
10. Return session validity through packed `validationData`.

## Execution path

`execute` and `executeBatch` must:

1. Accept calls only from the EntryPoint or owner.
2. Decode the complete batch before performing any external call.
3. Price native value and token amounts, counting `approve` amounts in full.
4. Sum the USD value of the entire batch.
5. Execute and update the daily counter only when all checks pass.
6. Record a pending request without executing when the request exceeds a limit or pricing fails.
7. Enforce a per-agent cap on open pending requests.

## Owner approval path

- `approvePending(id)` executes a non-expired stored request and marks it approved.
- `rejectPending(id)` marks a request rejected without executing it.
- Expired requests cannot execute.
- Owner-approved spend does not consume the agent's daily allowance.
- Reentrancy protection and checks-effects-interactions apply to pending execution.

## Events to define early

- `SessionAdded`, `SessionRevoked`
- `PolicyUpdated`, `TokenConfigUpdated`
- `WalletPaused`, `WalletUnpaused`
- `AgentCallExecuted`
- `ApprovalRequested`, `PendingApproved`, `PendingRejected`, `PendingExpired`
- `AgentCallBlocked` where the execution model permits a persistent record

## Decisions requiring implementation confirmation

- Exact EntryPoint v0.7 deployment address and bundler compatibility.
- Supported Base Sepolia Chainlink feeds and heartbeat thresholds.
- Whether blocked validation attempts are derived from bundler simulation logs or persisted by the application, because reverted validation cannot emit durable on-chain events.
- Exact gas and fee caps for agent operations.
- Pending request ID scheme and duplicate-request handling.
- Reentrancy and partial-failure behavior for owner-approved batches.

