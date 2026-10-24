# Agent Wallet Backend

The backend is an untrusted convenience layer. It exposes public chain configuration, checks RPC and bundler readiness, and forwards already-signed ERC-4337 v0.7 UserOperations. Wallet policy remains on-chain.

## Local setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e './backend[dev]'
cp .env.example .env
.venv/bin/uvicorn app.main:app --app-dir backend --reload
```

Open `http://127.0.0.1:8000/docs` for the generated API documentation.

## Initial endpoints

- `GET /api/v1/health` checks configured RPC and bundler connectivity.
- `GET /api/v1/config` returns non-secret frontend configuration.
- `POST /api/v1/user-operations` validates and relays a signed packed UserOperation.
- `POST /api/v1/user-operations/estimate` validates a bundler gas estimate.
- `GET /api/v1/user-operations/{hash}` returns a receipt or a pending result.

The API intentionally does not accept or store owner or agent private keys.

## Regression tests

```bash
.venv/bin/pytest backend
```

The suite enforces a 90% branch-aware coverage floor and performs no live network calls.
