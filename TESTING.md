# Testing Strategy

The regression suite treats the wallet contract as the security boundary and the backend as an untrusted relay. All tests run without live RPC credentials.

## Required local checks

```bash
pnpm contracts:compile
pnpm frontend:build
pnpm test
```

## Contract coverage

The Foundry suite currently covers:

- Owner and agent execution boundaries.
- ERC-4337 session signature validation.
- Pause, revoke, expiry, and gas-field limits.
- Target, selector, ERC-20 recipient, spender, and `transferFrom` checks.
- Per-transaction and daily USD limits.
- Whole-batch aggregation before execution.
- Pending creation, approval, rejection, expiry, and queue caps.
- Unknown-price failure behavior.
- Owner-only EIP-1271 signatures.
- Deterministic factory deployment.
- Fixed and feed-based oracle prices, decimal normalization, and staleness.
- Ticket purchase behavior.
- Fuzzed native-token spend accounting with 256 cases per run.

Run the optional coverage report with:

```bash
pnpm exec forge coverage --report summary
```

## Backend coverage

The pytest suite uses isolated environment fixtures, ASGI requests, mocked JSON-RPC transports, typed failure assertions, and parameterized boundary cases. It enforces at least 90% branch-aware coverage and currently covers:

- Safe configuration defaults and environment parsing.
- Ethereum address, byte-data, quantity, and hash validation.
- JSON-RPC request shape, IDs, errors, HTTP failures, and malformed responses.
- Bundler entry-point discovery, operation submission, gas estimation, and receipt lookup.
- API health, public configuration, successful relay behavior, and upstream error mapping.
- Unconfigured service behavior and invalid request rejection.

## Frontend coverage

The Vitest and React Testing Library suite uses mocked browser requests and covers:

- Public configuration and health requests.
- Signed UserOperation estimation and submission payloads.
- Receipt URL encoding and polling responses.
- Structured backend errors, malformed responses, and network failures.
- Loading, ready, degraded, offline, and retry connection states.
- Context misuse protection.

Coverage gates require at least 90% of lines, statements, and functions and 80% of branches in the frontend API and connection-state modules.

## Live integration tests

Live Base Sepolia tests are intentionally separate because they need funded accounts and provider credentials. Add them under `backend/tests/integration/` with the `integration` marker and keep them excluded from pull-request CI until ephemeral test funding and secret management are configured.
