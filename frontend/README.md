# Agent Wallet frontend

React and Vite dashboard for the Agent Wallet project. It is part of the root pnpm workspace and connects directly to the FastAPI service.

## Local development

Complete the root project setup first, activate the root Python virtual environment, and run both services:

```bash
pnpm dev
```

- Dashboard: `http://127.0.0.1:5173`
- Backend: `http://127.0.0.1:8000`
- API documentation: `http://127.0.0.1:8000/docs`

To run only the frontend:

```bash
pnpm dev:frontend
```

The Vite development server proxies `/api` to `http://127.0.0.1:8000`.

## Backend integration

`src/services/api.js` calls the real `/api/v1` endpoints for:

- Public chain and contract configuration
- RPC and bundler health
- UserOperation gas estimation
- Signed UserOperation submission
- UserOperation receipt polling

Connection status is shared through `src/context/AppStatusContext.jsx`. The UI explicitly reports loading, degraded, and offline states instead of treating mock data as live backend data.

The balances, activity feed, policy editor, approvals, sessions, and attack demonstrations currently use design-fixture data. Those screens require a persistent event indexer and wallet read API before they can become live views. The **Relay** screen is connected to the implemented backend today.

## Environment

For local development, no frontend environment file is needed. For a separately deployed API, copy the example and set the public backend origin:

```bash
cp frontend/.env.example frontend/.env
```

```dotenv
VITE_API_BASE_URL=https://api.example.com
```

Do not place provider secrets or private keys in any `VITE_*` variable; Vite exposes those values to the browser bundle.

## Build and test

From the repository root:

```bash
pnpm frontend:build
pnpm frontend:test
```

The Vitest suite covers the API boundary and application connection state. Coverage gates require 90% for lines, statements, and functions and 80% for branches across those integration modules.

Preview the production build:

```bash
pnpm --filter al-wallet preview
```
