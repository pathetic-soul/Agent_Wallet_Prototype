import { useState } from 'react';
import { Activity as ActivityIcon, Bell, Clock3, Shield, ShieldAlert, Zap } from 'lucide-react';
import { SectionHeading } from '../components/SectionHeading.jsx';
import { TokenList } from '../components/TokenList.jsx';
import { MiniChart } from '../components/MiniChart.jsx';
import { ActivityTable } from '../components/ActivityTable.jsx';
import { ApprovalCard } from '../components/ApprovalCard.jsx';
import { OwnerNotice, walletGate } from '../components/WalletGate.jsx';
import { useWalletData } from '../context/WalletDataContext.jsx';
import { walletApi } from '../services/api.js';
import { formatDuration, formatUsd, shortAddress, toRow } from '../lib/format.js';

function StatCard({ icon: Icon, label, value, caption, tone = 'blue' }) { return <div className="panel stat-card"><div className={`stat-icon tone-${tone}`}><Icon size={15}/></div><span>{label}</span><strong>{value}</strong><small>{caption}</small></div>; }

export function Overview() {
  const { configured, loading, error, overview, activity, canSign, owner, pending } = useWalletData();
  const [filter, setFilter] = useState('All');
  const gate = walletGate({ configured, loading, error, ready: Boolean(overview && activity) }, 'Overview', "Your agent can spend. It can't be tricked into draining you.");
  if (gate) return gate;

  const { wallet, tokens, sessions, stats, chain_time: now, total_usd: totalUsd } = overview;
  const filters = ['All', 'Executed', 'Blocked', 'Pending'];
  const items = activity.items.filter((a) => filter === 'All' || (filter === 'Executed' ? a.status === 'Allowed' : a.status === filter));
  const spent = Number(wallet.spent_in_window_usd);
  const daily = Number(wallet.daily_limit_usd);
  const percent = daily > 0 ? Math.min(100, Math.round((spent / daily) * 100)) : 0;
  const session = sessions[sessions.length - 1];
  const openPending = pending.requests.filter((r) => r.status === 'open').length;

  return <>
    <SectionHeading title="Overview" subtitle="Your agent can spend. It can't be tricked into draining you." />
    <OwnerNotice owner={owner}/>
    <section className="overview-top-grid">
      <div className="panel balance-card"><div className="panel-label-row"><span>Smart account balance</span><span className="eyebrow-pill pill-blue"><span/> ERC-4337</span></div><div className="balance-amount">{formatUsd(totalUsd)}<small>{tokens.length} tokens · oracle-priced</small></div><MiniChart points={stats.spend_history_usd}/><TokenList tokens={tokens} compact/></div>
      <div className="panel budget-card"><div className="panel-label-row"><span>Daily budget</span><span className="tiny-mono">USD · ORACLE</span></div><div className="budget-amount">{formatUsd(spent)} <span>/ {formatUsd(daily)}</span></div><div className="progress-track"><span style={{ width: `${percent}%` }}/></div><div className="budget-usage"><span>{percent}% used</span><span>{formatUsd(Math.max(0, daily - spent))} left</span></div><div className="budget-details"><div><span>Per-tx limit</span><strong>{formatUsd(wallet.per_transaction_limit_usd)}</strong></div><div><span>Window resets in</span><strong>{formatDuration(wallet.window_resets_at - now)}</strong></div><div><span>Price feeds</span><strong className={tokens.every((t) => t.usd_value !== null) ? 'text-green' : 'text-amber'}>● {tokens.every((t) => t.usd_value !== null) ? 'priced' : 'unpriced token'}</strong></div></div></div>
      <div className="panel attacks-card"><div className="stat-icon tone-green"><Shield size={15}/></div><span>Attempts blocked</span><strong>{activity.blocked_attempts}</strong><span className="lost-pill">{wallet.paused ? 'WALLET PAUSED' : 'WALLET ACTIVE'}</span><p>Rejected before execution, so the wallet paid no gas. Counted by this API's relay log since it started.</p></div>
    </section>
    <section className="stats-grid"><StatCard icon={Zap} label="Agent operations executed" value={stats.executed_operations} caption="AgentCallExecuted events"/><StatCard icon={ShieldAlert} label="Rejected in validation" value={activity.blocked_attempts} caption="relay log · $0 gas" tone="red"/><StatCard icon={Bell} label="Pending approvals" value={openPending} caption={openPending ? 'waiting for the owner' : 'queue is empty'} tone="amber"/><StatCard icon={Clock3} label="Session expires in" value={session ? formatDuration(session.valid_until - now) : '—'} caption={session ? `agent ${shortAddress(session.agent)}` : 'no session'} tone="green"/></section>
    <section className="overview-bottom-grid"><div className="panel activity-panel"><div className="panel-heading"><div><h2><ActivityIcon size={16}/> Live activity</h2><p>Read from wallet events · refreshes every 3 seconds</p></div><div className="filter-tabs">{filters.map((tab) => <button key={tab} onClick={() => setFilter(tab)} className={filter === tab ? 'selected' : ''}>{tab}</button>)}</div></div><ActivityTable items={items.slice(0, 12).map(toRow)} compact/></div><div className="overview-side"><ApprovalCard/>{session && <div className="panel session-panel"><div className="panel-heading"><div><h2><Clock3 size={16}/> Agent session</h2></div><span className={`eyebrow-pill ${session.active ? 'pill-green' : 'pill-red'}`}><span/> {session.revoked ? 'REVOKED' : wallet.paused ? 'PAUSED' : session.active ? 'ACTIVE' : 'EXPIRED'}</span></div><div className="agent-box"><span className="agent-avatar"><Zap size={14}/></span><div><strong>Agent session key</strong><small>{shortAddress(session.agent)}</small></div></div><div className="session-row"><span>Valid until</span><strong>{new Date(session.valid_until * 1000).toLocaleString()}</strong></div><div className="session-row"><span>Open pending</span><strong>{session.open_pending} / {wallet.max_open_pending}</strong></div><div className="session-buttons"><button className="button button-secondary" disabled={!canSign || Boolean(owner.busy)} onClick={() => void owner.run(wallet.paused ? 'Resume wallet' : 'Pause wallet', () => walletApi.setPaused(!wallet.paused))}>{wallet.paused ? 'Resume wallet' : 'Pause wallet'}</button><button className="button button-danger-ghost" disabled={!canSign || session.revoked || Boolean(owner.busy)} onClick={() => void owner.run('Revoke session', () => walletApi.revokeSession(session.agent))}>Revoke</button></div></div>}</div></section>
  </>;
}
