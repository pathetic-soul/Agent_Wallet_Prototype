#!/usr/bin/env bash
# One-command local demo: anvil + deploy + local bundler + backend + dashboard, then the scripted attacks.
# Requires: pnpm install done, `forge build` artifacts in out/, .tools/bin/anvil (see demo/README.md).
set -euo pipefail
cd "$(dirname "$0")/.."
LOGS="${TMPDIR:-/tmp}/agent-wallet-demo"; mkdir -p "$LOGS"
PY=.venv/bin/python
demo_key() { (cd demo && ../$PY -c "from chain import ANVIL_KEYS; print(ANVIL_KEYS['$1'])"); }

node_modules/.bin/forge build >/dev/null
.tools/bin/anvil --host 127.0.0.1 --port 8545 --code-size-limit 100000 --block-base-fee-per-gas 1000000000 >"$LOGS/anvil.log" 2>&1 &
sleep 2
(cd demo && ../$PY deploy_local.py)
(cd demo && ../.venv/bin/uvicorn local_bundler:app --port 3000 >"$LOGS/bundler.log" 2>&1 &)
FACTORY=$($PY -c "import json;print(json.load(open('demo/deployments.local.json'))['factory'])")
ENTRY_POINT_ADDRESS=$($PY -c "import json;print(json.load(open('demo/deployments.local.json'))['entryPoint'])") \
RPC_URL=http://127.0.0.1:8545 BUNDLER_RPC_URL=http://127.0.0.1:3000 CHAIN_ID=31337 CHAIN_NAME="Local Anvil" \
WALLET_FACTORY_ADDRESS=$FACTORY \
WALLET_ADDRESS=$($PY -c "import json;print(json.load(open('demo/deployments.local.json'))['wallet'])") \
DEMO_OWNER_PRIVATE_KEY=$(demo_key owner) \
DEMO_AGENT_PRIVATE_KEY=$(demo_key agent) \
DEMO_ATTACKER_PRIVATE_KEY=$(demo_key attacker) \
.venv/bin/uvicorn app.main:app --app-dir backend --port 8000 >"$LOGS/backend.log" 2>&1 &
(cd frontend && node_modules/.bin/vite --host 127.0.0.1 >"$LOGS/frontend.log" 2>&1 &)
sleep 4
(cd demo && ../$PY run_demo.py)
echo "Dashboard http://127.0.0.1:5173  API docs http://127.0.0.1:8000/docs  logs $LOGS"
echo "Stop everything with: pkill -f 'anvil|local_bundler|app.main|vite'"
