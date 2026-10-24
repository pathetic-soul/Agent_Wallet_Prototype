# Agent Wallet

Agent Wallet is a testnet-only ERC-4337 v0.7 smart account designed for AI agents. Instead of trusting prompts or an off-chain service to prevent unsafe payments, the wallet enforces session, call, recipient, gas, and USD spending policy in the smart contract.

The project currently includes the Solidity wallet core, a deterministic factory, a price-oracle wrapper, a demo ticket contract, a FastAPI bundler relay, and production-oriented contract and backend regression suites.

> **Security notice:** This project is unaudited and under active development. Use it only on test networks with assets that have no real value.

## What the project demonstrates

- ERC-4337 v0.7 account validation with `PackedUserOperation`.
- Separate owner and constrained-agent execution paths.
- Time-bounded agent sessions that can be paused or revoked.
- Allowlisted targets and function selectors.
- Decoded ERC-20 recipient and spender checks for `transfer`, `transferFrom`, and `approve`.
- Per-transaction and fixed-window daily limits denominated in USD.
- Chainlink-style price feeds with heartbeat-based staleness rejection.
- Owner approval for over-limit or unpriceable operations.
- Gas and fee caps that limit deposit griefing by a compromised agent key.
- Owner-only EIP-1271 signatures, preventing an agent from signing arbitrary Permit messages.
- CREATE2 wallet deployment with a predictable address.
- A backend that relays signed UserOperations without storing private keys.

## Project status

| Area | Status |
|---|---|
| Wallet contract | Implemented and covered by unit and fuzz tests |
| CREATE2 factory | Implemented and tested |
| USD price oracle | Implemented with feed and fixed testnet price modes |
| Ticket demo target | Implemented and tested |
| Backend health and public configuration | Implemented |
| UserOperation relay | Implemented |
| Gas estimation and receipt polling | Implemented |
| React dashboard backend status and relay | Implemented and tested |
| Dashboard event and wallet read model | Demonstration data; indexer planned |
| Live Base Sepolia deployment | Not yet configured |
| Persistent event indexer | Planned |
| Local AI agent tools | Planned |
| React owner dashboard | Planned |

## Architecture

```text
Owner wallet ───────────────────────────────────────────────────────────┐
                                                                       │
Local agent ── tool request ──> Backend ── signed UserOperation ──> Bundler
                                                                       │
Attacker ───────────────────────── crafted UserOperation ──────────────┤
                                                                       v
                                                               EntryPoint v0.7
                                                                       │
                                                                       v
                                                                AgentWallet
                                                              validation │ execution
                                                                  │      │
                                                                  v      v
                                                            PriceOracle  Targets
                                                                         │
                                                                  TicketShop/ERC-20
```

The backend is not a policy or custody boundary. The agent signs its own UserOperation, and the contract independently decides whether the request is valid and whether it may execute immediately.

Structural checks run during ERC-4337 validation. Price-dependent checks run during execution because oracle storage cannot safely be treated as validation-only state. If pricing fails or a limit is exceeded, the wallet stores a pending request without executing the underlying calls.

## Repository structure

```text
.
├── backend/
│   ├── app/
│   │   ├── api/              FastAPI routes
│   │   ├── services/         JSON-RPC and bundler clients
│   │   ├── config.py         Environment configuration
│   │   ├── main.py           Application factory
│   │   └── models.py         Typed API and UserOperation models
│   └── tests/                Backend unit and API regression tests
├── contracts/
│   ├── src/                  Solidity contracts
│   ├── test/                 Foundry unit and fuzz tests
│   └── scripts/              Deterministic solc-js build scripts
├── frontend/
│   ├── src/components/       Shared dashboard components
│   ├── src/context/          Backend connection state
│   ├── src/pages/            Dashboard and UserOperation relay screens
│   ├── src/services/         Typed API boundary
│   └── tests/                Vitest integration regression tests
├── starter_docs/             Architecture, threat model, runbook, and build plan
├── .github/workflows/ci.yml  Continuous integration gates
├── .env.example              Safe environment template
├── foundry.toml              Foundry configuration
├── package.json              Unified workspace commands
└── TESTING.md                Detailed regression strategy
```

## Prerequisites

Install the following before setup:

- Git.
- Node.js 20 or newer. CI currently uses Node.js 22.
- pnpm 11 or newer.
- Python 3.11 or 3.12.
- A C/C++ compatible environment if one of Python's transitive packages needs a local build.

You do not need a machine-global Foundry installation. The repository installs a project-local Forge binary through pnpm.

For live testnet usage you will also need:

- A Base Sepolia RPC URL.
- An ERC-4337 v0.7 bundler endpoint for Base Sepolia.
- The matching EntryPoint v0.7 address supported by that bundler.
- Base Sepolia ETH for deployment and UserOperation gas.
- Test tokens and confirmed price-feed addresses for any ERC-20 demo assets.

Always verify network addresses against the provider's current official documentation before deploying.

## Quick start

### 1. Install JavaScript and contract dependencies

From the repository root:

```bash
pnpm install
```

This installs the React frontend, Solidity 0.8.28, OpenZeppelin Contracts, the ERC-4337 reference interfaces, the frontend test runner, and a local Forge executable.

### 2. Create the Python environment

Linux or macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e './backend[dev]'
```

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e './backend[dev]'
```

The editable installation makes the `backend/app` package immediately reflect local code changes.

### 3. Create local configuration

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

The backend starts without provider credentials in a degraded but usable development state. Configuration and OpenAPI endpoints remain available, while bundler-dependent endpoints return `503`.

### 4. Compile and test everything

```bash
pnpm contracts:compile
pnpm contracts:test
pnpm frontend:build
pnpm frontend:test
python -m pytest backend
```

Expected baseline:

- Five project Solidity sources compile with Solidity 0.8.28.
- The Foundry suite runs 28 tests, including 256 fuzz cases.
- The frontend API integration suite runs 12 tests with enforced coverage gates.
- The backend suite runs 57 tests and enforces at least 90% branch-aware coverage.

You can run all regression suites with one command. The workspace automatically detects `.venv/bin/python` or `.venv\\Scripts\\python.exe`:

```bash
pnpm test
```

### 5. Run the complete application

Activate the Python environment, then start the FastAPI backend and Vite frontend together:

```bash
pnpm dev
```

Open:

- Dashboard: `http://127.0.0.1:5173`
- API documentation: `http://127.0.0.1:8000/docs`
- Health check: `http://127.0.0.1:8000/api/v1/health`

Vite proxies `/api` requests to the backend during local development. The dashboard displays the real chain, EntryPoint, factory, RPC, and bundler readiness returned by the backend. Dashboard balances, events, policies, and sessions remain clearly scoped demonstration data until the event indexer is implemented.

To run the services separately:

With the virtual environment activated:

```bash
uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```

Without activating the environment:

```bash
.venv/bin/uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```

In another terminal:

```bash
pnpm dev:frontend
```

## Environment configuration

The `.env` file is read locally and ignored by Git.

| Variable | Required | Default | Description |
|---|---:|---|---|
| `APP_ENV` | No | `development` | Environment label returned by health checks |
| `APP_HOST` | No | `127.0.0.1` | Recommended API bind host |
| `APP_PORT` | No | `8000` | Recommended API port |
| `CORS_ORIGINS` | No | `http://localhost:5173` | Comma-separated browser origins |
| `CHAIN_ID` | No | `84532` | Expected EVM chain ID; 84532 is Base Sepolia |
| `CHAIN_NAME` | No | `Base Sepolia` | Display name returned to clients |
| `RPC_URL` | Live use | Empty | Standard Base Sepolia JSON-RPC endpoint |
| `BUNDLER_RPC_URL` | Live use | Empty | ERC-4337 bundler JSON-RPC endpoint |
| `ENTRY_POINT_ADDRESS` | Live use | Empty | EntryPoint address supported by the bundler |
| `WALLET_FACTORY_ADDRESS` | After deployment | Empty | Deployed `AgentWalletFactory` address |

Example configured development file:

```dotenv
APP_ENV=development
APP_HOST=127.0.0.1
APP_PORT=8000
CORS_ORIGINS=http://localhost:5173

CHAIN_ID=84532
CHAIN_NAME=Base Sepolia
RPC_URL=https://your-base-sepolia-rpc.example
BUNDLER_RPC_URL=https://your-base-sepolia-bundler.example
ENTRY_POINT_ADDRESS=0xYourVerifiedEntryPointAddress
WALLET_FACTORY_ADDRESS=0xYourDeployedFactoryAddress
```

Do not add deployer, owner, agent, or attacker private keys to this file. The current backend does not need or accept them.

## Contract development

### Compile

```bash
pnpm contracts:compile
```

The deterministic compiler writes ABI and bytecode artifacts under `out/<Contract>.sol/<Contract>.json`.

### Run tests

```bash
pnpm contracts:test
```

Run one contract or test by name:

```bash
pnpm exec forge test --match-contract AgentWalletTest -vv
pnpm exec forge test --match-test testApproveToUnapprovedSpenderIsRejected -vvvv
```

### Check formatting

```bash
pnpm exec forge fmt --check contracts/src contracts/test
```

Apply Foundry formatting:

```bash
pnpm exec forge fmt contracts/src contracts/test
```

### Generate coverage

```bash
pnpm exec forge coverage --report summary
```

The latest local baseline covers approximately 82% of project contract lines and 81% of contract functions. Branch coverage is lower and remains an active hardening target.

### Clean generated outputs

```bash
pnpm contracts:clean
```

## Contract behavior

### Owner path

The owner may:

- Execute arbitrary calls directly or through an owner-signed UserOperation.
- Add or revoke agent sessions.
- Pause or unpause agent activity.
- Configure allowed targets, selectors, recipients, and spend limits.
- Configure gas, pending-request, and expiry limits.
- Approve or reject pending requests.
- Withdraw the wallet's EntryPoint deposit.
- Produce valid EIP-1271 signatures.

### Agent path

An agent must call `executeAgent` or `executeAgentBatch`. Validation binds the recovered signer to the explicit agent address encoded in the wallet call. The wallet then enforces:

1. An active session and valid time range.
2. Wallet pause and session revocation state.
3. Verification gas, call gas, and maximum fee caps.
4. Allowed target and selector pairs.
5. Decoded ERC-20 recipient or spender policy.
6. Whole-batch USD pricing before any call executes.
7. Per-transaction and daily USD limits.
8. A cap on open pending requests per agent.

### Pending requests

When a request exceeds a limit or cannot be priced, its calls are encoded and stored without execution. The owner can approve the request, reject it, or allow anyone to mark it expired after its deadline.

Owner-approved pending spend does not consume the agent's daily allowance because it represents a new explicit owner decision.

### Price oracle

`PriceOracle` normalizes quotes to eight USD decimals. It supports:

- Chainlink-compatible feeds with token decimals and feed-specific maximum age.
- A fixed-price mode for clearly labeled testnet tokens without a supported feed.
- Disabled-token and stale-answer failure behavior.

Fixed prices are a testnet demonstration feature and are not suitable for production custody.

## Backend API

### Health

```http
GET /api/v1/health
```

Checks the standard RPC chain ID and confirms the configured EntryPoint appears in the bundler's supported entry-point list.

An unconfigured local response is intentionally degraded:

```json
{
  "status": "degraded",
  "environment": "development",
  "chain": {
    "status": "unconfigured",
    "chain_id": null,
    "detail": "RPC_URL is not set"
  },
  "bundler": {
    "status": "unconfigured",
    "chain_id": null,
    "detail": "BUNDLER_RPC_URL and ENTRY_POINT_ADDRESS are required"
  }
}
```

### Public configuration

```http
GET /api/v1/config
```

Returns the chain, EntryPoint, factory address, and readiness state. RPC URLs and other provider configuration are not returned.

### Submit a signed UserOperation

```http
POST /api/v1/user-operations
Content-Type: application/json
```

Example body:

```json
{
  "user_operation": {
    "sender": "0x1111111111111111111111111111111111111111",
    "nonce": "0x0",
    "initCode": "0x",
    "callData": "0x",
    "accountGasLimits": "0x0000000000000000000000000000000000000000000000000000000000000000",
    "preVerificationGas": "0x0",
    "gasFees": "0x0000000000000000000000000000000000000000000000000000000000000000",
    "paymasterAndData": "0x",
    "signature": "0x1111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111"
  }
}
```

The API validates canonical Ethereum quantities, byte strings, addresses, and response hashes before forwarding the operation to `eth_sendUserOperation`.

### Estimate UserOperation gas

```http
POST /api/v1/user-operations/estimate
```

The request uses the same body shape as submission and calls `eth_estimateUserOperationGas`.

### Poll for a receipt

```http
GET /api/v1/user-operations/{userOperationHash}
```

The response contains `receipt: null` while the operation is pending, or the bundler receipt object after inclusion.

## Backend testing

Run the complete backend suite:

```bash
python -m pytest backend
```

Run selected groups:

```bash
python -m pytest backend -m unit
python -m pytest backend -m api
python -m pytest backend/tests/test_json_rpc.py
```

The suite uses mocked JSON-RPC transports and makes no live network calls. It covers configuration, input validation, malformed responses, provider failures, bundler methods, API error mapping, and unconfigured development behavior.

See [TESTING.md](TESTING.md) for the complete regression matrix.

## Frontend integration

The React dashboard consumes these real backend endpoints:

- `GET /api/v1/config` for chain, EntryPoint, and factory configuration.
- `GET /api/v1/health` for RPC and bundler readiness.
- `POST /api/v1/user-operations/estimate` for bundler gas estimation.
- `POST /api/v1/user-operations` for signed UserOperation submission.
- `GET /api/v1/user-operations/{hash}` for receipt polling.

Use the **Relay** screen to paste a signed packed v0.7 UserOperation, estimate gas, submit it, and poll its receipt. The browser never receives RPC or bundler provider URLs and the backend never stores private keys.

For a separately hosted frontend, create `frontend/.env`:

```dotenv
VITE_API_BASE_URL=https://api.example.com
```

Add that frontend origin to `CORS_ORIGINS` in the root `.env`. Leave `VITE_API_BASE_URL` empty during local development to use the Vite proxy.

## Base Sepolia deployment checklist

Deployment automation is the next implementation milestone. Until it is added, treat the following as a required checklist rather than a ready-to-run deployment command:

1. Confirm the Base Sepolia chain ID, EntryPoint v0.7 address, bundler compatibility, and RPC endpoints.
2. Fund a dedicated testnet deployer.
3. Deploy `PriceOracle` with the intended configuration owner.
4. Configure the native-token and ERC-20 price feeds with verified decimals and heartbeat thresholds.
5. Deploy `AgentWalletFactory` with the confirmed EntryPoint and oracle addresses.
6. Predict and deploy an `AgentWallet` with CREATE2.
7. Configure sessions, call policies, recipients, gas limits, and USD limits from the wallet owner.
8. Deposit Base Sepolia ETH into EntryPoint for the wallet.
9. Verify all source code on Basescan.
10. Record addresses and transaction hashes in the project configuration.
11. Run one owner operation and every adversarial test before connecting a UI.

Never deploy from an account that holds mainnet funds or reuse test private keys anywhere else.

## Continuous integration

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs on pull requests and pushes to `main`.

The contract job:

- Installs locked pnpm dependencies.
- Checks Solidity formatting.
- Compiles deterministic artifacts.
- Runs the complete Foundry suite and fuzz cases.

The frontend job:

- Builds the production Vite bundle.
- Runs the Vitest regression suite.
- Enforces 90% line, statement, and function coverage plus 80% branch coverage on the backend integration boundary.

The backend matrix:

- Runs on Python 3.11 and 3.12.
- Installs the backend with development dependencies.
- Runs pytest with the 90% coverage gate.
- Uploads JUnit results even when a test fails.

## Troubleshooting

### `forge` is not found

Run commands through pnpm so the project-local binary is used:

```bash
pnpm exec forge --version
pnpm contracts:test
```

If dependencies are missing, rerun `pnpm install`.

### Backend imports fail

Install the backend in editable mode from the repository root:

```bash
python -m pip install -e './backend[dev]'
```

### Health remains degraded

Check that `.env` contains all three live-service values:

- `RPC_URL`
- `BUNDLER_RPC_URL`
- `ENTRY_POINT_ADDRESS`

Then confirm that `RPC_URL` returns chain ID `84532` and that the bundler's `eth_supportedEntryPoints` result includes the configured address.

### API rejects hexadecimal values

- Addresses must contain exactly 20 bytes.
- Hashes must contain exactly 32 bytes.
- Byte data must contain complete byte pairs, such as `0x` or `0x00`.
- Ethereum quantities must be canonical, such as `0x0`, `0x1`, or `0x5208`. Values such as `0x00` and `0x01` are rejected.

### Contract coverage prints many anchor warnings

Forge coverage disables optimizer settings for instrumentation and may print source-anchor warnings for imported or test helper code. Use the final summary table as the coverage result and keep normal compilation and tests as the authoritative correctness gates.

## Security model and limitations

- The owner key remains the root of trust.
- A compromised agent key may spend within its configured policy until it expires or is revoked.
- The fixed 24-hour window can allow up to twice the nominal daily limit around a reset boundary.
- Arbitrary allowlisted target methods are trusted to have understood economic behavior; direct native and supported ERC-20 values are what the wallet currently prices.
- The backend does not persist events yet and should not be treated as an audit log.
- Validation failures must be obtained from bundler simulation or backend telemetry because reverted validation does not create durable wallet events.
- Fixed oracle prices are for labeled testnet demonstrations only.
- There has been no independent audit.

Read [starter_docs/THREAT_MODEL.md](starter_docs/THREAT_MODEL.md) before changing wallet policy or adding a new execution path.

## Documentation

- [Testing strategy](TESTING.md)
- [Backend guide](backend/README.md)
- [Contract guide](contracts/README.md)
- [Architecture](starter_docs/ARCHITECTURE.md)
- [Threat model](starter_docs/THREAT_MODEL.md)
- [Build plan](starter_docs/BUILD_PLAN.md)
- [Demo runbook](starter_docs/DEMO_RUNBOOK.md)
- [Project brief](starter_docs/Agent_Wallet_Project_Brief.docx)

## Near-term roadmap

1. Add deterministic deployment and verification scripts.
2. Add live Base Sepolia integration tests behind an explicit marker.
3. Persist wallet and EntryPoint events in a database-backed indexer.
4. Build the local-agent UserOperation toolchain and scripted attacker.
5. Build the React owner dashboard and installable PWA.
6. Add invariant handlers for randomized multi-operation sequences.
7. Complete an external security review before considering any network with valuable assets.
