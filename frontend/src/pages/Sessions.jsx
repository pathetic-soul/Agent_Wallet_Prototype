import { useState } from 'react';
import { Clock3, KeyRound, Pause, Plus, ShieldCheck, Trash2, Zap } from 'lucide-react';
import { SectionHeading } from '../components/SectionHeading.jsx';
import { OwnerNotice, walletGate } from '../components/WalletGate.jsx';
import { useWalletData } from '../context/WalletDataContext.jsx';
import { walletApi } from '../services/api.js';
import { formatDuration, formatUsd, shortAddress } from '../lib/format.js';

const DURATIONS = [['1 hour', 3600], ['1 day', 86400], ['7 days', 7 * 86400]];

export function Sessions() {
  const { configured, loading, error, overview, canSign, owner } = useWalletData();
  const [adding, setAdding] = useState(false);
  const [agent, setAgent] = useState('');
  const [duration, setDuration] = useState(86400);
  const gate = walletGate({ configured, loading, error, ready: Boolean(overview) }, 'Sessions', 'Scoped agent keys with an expiry, a budget, and an owner-controlled kill switch.');
  if (gate) return gate;

  const { wallet, sessions, chain_time: now } = overview;
  const disabled = !canSign || Boolean(owner.busy);
  const validAgent = /^0x[0-9a-fA-F]{40}$/.test(agent);
  const add = async () => { await owner.run('Add session', () => walletApi.addSession(agent, duration)); setAdding(false); setAgent(''); };

  return <><SectionHeading title="Sessions" subtitle="Scoped agent keys with an expiry, a budget, and an owner-controlled kill switch." action={<button className="button button-primary" disabled={disabled} onClick={() => setAdding(!adding)}><Plus size={14}/> Add session</button>}/>
    <OwnerNotice owner={owner}/>
    {!canSign && <div className="info-note">Owner signing is not enabled on this backend, so session changes are read-only here.</div>}
    {adding && <div className="panel"><div className="panel-heading"><div><h2>New agent session</h2><p>The agent key can act only inside the wallet's on-chain policy until this expires.</p></div></div><div className="relay-actions"><label className="hash-field"><span>Agent address</span><input value={agent} onChange={(e) => setAgent(e.target.value.trim())} placeholder="0x…"/></label><label className="hash-field"><span>Valid for</span><select value={duration} onChange={(e) => setDuration(Number(e.target.value))}>{DURATIONS.map(([label, secs]) => <option key={secs} value={secs}>{label}</option>)}</select></label><button className="button button-primary" disabled={!validAgent || disabled} onClick={() => void add()}>Create session</button></div></div>}
    {sessions.length === 0 && <div className="panel"><div className="panel-heading"><div><h2>No sessions yet</h2><p>Add an agent key so it can submit operations within policy.</p></div></div></div>}
    {sessions.map((s) => { const state = s.revoked ? 'REVOKED' : wallet.paused ? 'PAUSED' : s.active ? 'ACTIVE SESSION' : 'EXPIRED'; return <div className="session-grid" key={s.agent}><section className="panel session-detail"><div className="session-hero"><div className="agent-avatar large"><Zap size={20}/></div><div><span className={`eyebrow-pill ${s.active ? 'pill-green' : 'pill-red'}`}><span/>{state}</span><h2>Agent session key</h2><p className="mono">{s.agent}</p></div></div><div className="session-stats"><div><span><Clock3 size={13}/> VALID UNTIL</span><strong>{new Date(s.valid_until * 1000).toLocaleString()}<small> · {formatDuration(s.valid_until - now)} left</small></strong></div><div><span><KeyRound size={13}/> OPEN PENDING</span><strong>{s.open_pending} / {wallet.max_open_pending}</strong></div><div><span><ShieldCheck size={13}/> WALLET SPEND</span><strong>{formatUsd(wallet.spent_in_window_usd)} / {formatUsd(wallet.daily_limit_usd)}</strong></div></div><h3>Session permissions</h3><div className="permission-pills"><span>Daily cap · {formatUsd(wallet.daily_limit_usd)}</span><span>Per-call · {formatUsd(wallet.per_transaction_limit_usd)}</span><span>Allowlisted calls only</span></div><div className="session-controls"><button className="button button-secondary" disabled={disabled} onClick={() => void owner.run(wallet.paused ? 'Resume wallet' : 'Pause wallet', () => walletApi.setPaused(!wallet.paused))}><Pause size={14}/>{wallet.paused ? 'Resume wallet' : 'Pause wallet'}</button><button className="button button-danger-ghost" disabled={disabled || s.revoked} onClick={() => void owner.run('Revoke session', () => walletApi.revokeSession(s.agent))}><Trash2 size={14}/> Revoke session</button></div></section><aside className="panel session-security"><div className="security-mark"><ShieldCheck size={20}/></div><h2>Keys don't get admin rights.</h2><p>Session keys can submit operations only within the policy scope. Policy edits, recipient changes, and session creation require the owner signature ({shortAddress(wallet.owner)}).</p><div className="security-rule"><span className="dot dot-green"/> On-chain expiry enforced</div><div className="security-rule"><span className="dot dot-green"/> Owner can pause or revoke</div><div className="security-rule"><span className="dot dot-green"/> Spending policy stays in contract</div></aside></div>; })}</>;
}
