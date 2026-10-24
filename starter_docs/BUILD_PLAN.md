# Agent Wallet 24 Hour Build Plan

## Objective

Deliver a testnet-only ERC-4337 wallet whose on-chain controls stop four live attack categories: prompt injection, leaked-key abuse, calldata tricks, and cross-chain replay. A working UserOperation is the critical path; if it is not live by hour 8, all available engineering effort moves to that milestone.

## Team ownership

| Role | Primary ownership | Handoff |
|---|---|---|
| A Contract lead | Wallet, factory, validation, execution, and both testnet deployments | B for tests; C for ABIs |
| B Security and tests | Unit, fuzz, invariant, Slither, threat model, attack scripts, rehearsal lead | A for fixes; D for attack console |
| C Agent and backend | Local agent, tools, UserOperation builder, event indexer, paywall, and web push | D for APIs; B for attacker bot |
| D Frontend, UX, and pitch | Dashboard, MetaMask owner flow, PWA push, attack console, README, deck, and demo | Entire team for rehearsal |

## Pre-build readiness

- [ ] Confirm competition rules on pre-event setup.
- [ ] Create primary and backup Base Sepolia RPC and bundler accounts.
- [ ] Fund deployer, owner, agent, and attacker accounts with test ETH and USDC.
- [ ] Fund the replay-test deployer on Ethereum Sepolia.
- [ ] Confirm Chainlink feed addresses and heartbeat thresholds.
- [ ] Install Foundry, Node 20, Python 3.11, and Slither.
- [ ] Test one local 7-8B model tool call end to end.
- [ ] Generate VAPID keys and test Android and iOS web push.
- [ ] Obtain a Basescan API key.
- [ ] Create repository folders and `.env.example` without secrets.
- [ ] Review EntryPoint v0.7 `IAccount`, `PackedUserOperation`, and `validationData`.

## Gates

| Gate | Target | Pass condition |
|---|---:|---|
| First UserOperation | Hour 6 | Owner-signed operation executes on Base Sepolia through the selected bundler |
| Policy complete | Hour 12 | Sessions, allowlists, recipient decoding, USD limits, pending queue, pause, and revoke work on testnet |
| Contract freeze | Hour 16 | Contracts deployed and verified; unit, fuzz, invariant, and static checks are acceptable |
| Demo freeze | Hour 20 | Happy path, four attack sequences, approval push, explorer links, and backup video are ready |
| Submission | Hour 24 | Public URLs, README, threat model, scripts, deck, and final demo assets are complete |

## Workstream plan

### Hours 0 to 6

- A: scaffold Foundry, interfaces, wallet validation, owner path, factory, and deployment script.
- B: write interface-first tests for EntryPoint-only access, owner signatures, and forbidden agent calls.
- C: establish bundler integration and submit a minimal owner UserOperation.
- D: scaffold the dashboard, wallet connection, navigation, and activity data contracts.
- Team: land the first Base Sepolia UserOperation and capture its explorer link.

### Hours 6 to 12

- A: add sessions, execute paths, allowlists, calldata decoding, and gas caps.
- B: add fuzz tests and attack tests for target, selector, recipient, session, and gas bypasses.
- C: add event indexing, tool schemas, paywall endpoint, and agent happy path.
- D: build policy editing, activity feed, pause/revoke, and pending approval surfaces.
- Team: demonstrate each structural policy on testnet.

### Hours 12 to 16

- A: implement USD pricing, daily limits, batch aggregation, and pending approvals.
- B: complete invariants, stale-oracle tests, reentrancy tests, Slither, and gas snapshot.
- C: wire web push, owner approval status, and scripted fallback agent.
- D: finish the PWA, attack console, error states, and testnet/unaudited labeling.
- Team: freeze contracts, deploy and verify on Base Sepolia and Ethereum Sepolia.

### Hours 16 to 20

- A and B: fix only evidence-backed release blockers; redeploy and rerun the full suite after any change.
- C: harden provider fallbacks and pre-warm the model.
- D: finish README, deployment data, architecture visual, deck, and demo narration.
- Team: run the complete demo three times and record a three-minute backup video.

### Hours 20 to 24

- Run final CI and inspect every link, address, environment variable, and one-command script.
- Capture final explorer evidence and gas numbers.
- Rehearse judge questions and assign the speaker for each answer.
- Buffer for submission upload, network issues, and a final rest rotation.

## Break-glass plan

| Risk | Early warning | Response |
|---|---|---|
| Bundler rejects the first UserOperation | Not working by hour 6 | Read `simulateValidation`, switch to the backup provider, and compare the provider's expected v0.7 fields |
| Python encoding mismatch | Hash or signature mismatch | Retrieve the EntryPoint's `getUserOpHash` instead of duplicating hashing logic |
| Missing Chainlink testnet feed | Discovered during setup | Use the labeled owner-set mock feed for that demo token |
| Oracle rejects every purchase | All requests become pending | Configure the threshold from the feed's documented heartbeat |
| Web push fails | Hour-12 phone test fails | Use Android Chrome on stage and keep an in-dashboard notification fallback |
| CREATE2 addresses differ | Replay setup produces different senders | Reproduce deployer, nonce, salt, factory bytecode, and deterministic-deployer conditions |
| Local model produces bad arguments | Rehearsal tool-call errors | Restrict the tool schema and switch to the scripted agent |
| Late contract defect | Invariant fails after freeze | Fix, redeploy, update one environment address, and rerun the complete suite |
| Stage network failure | RPC or Wi-Fi stalls | Use a hotspot and play the hour-20 backup video |

## Release checklist

- [ ] Basescan-verified contract addresses are recorded.
- [ ] Public dashboard and backend URLs work outside the development laptop.
- [ ] CI is green and the README badge resolves.
- [ ] Attack scripts run with one command each.
- [ ] The threat model includes defended threats, out-of-scope threats, and known limitations.
- [ ] The backup demo video is available offline.
- [ ] The deck contains six to eight slides and one gas snapshot slide.
- [ ] The UI displays `Testnet only - unaudited`.

