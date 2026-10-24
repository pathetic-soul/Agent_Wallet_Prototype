import { Check, Clock3, ShieldCheck, Ticket, X } from 'lucide-react';
import { SectionHeading } from '../components/SectionHeading.jsx';
import { useAppStatus } from '../context/AppStatusContext.jsx';
import { useWalletData } from '../context/WalletDataContext.jsx';
import { REASON_TEXT, describeCall, formatCountdown, secondsLeft, shortAddress, weiToEth } from '../lib/format.js';

export function Approvals() {
  const { config } = useAppStatus();
  const { pending: { requests, summary, loading, error, busyId, notice, approve, reject } } = useWalletData();
  const open = requests.filter((r) => r.status === 'open');
  const current = open[open.length - 1];
  const history = requests.filter((r) => r.status !== 'open').slice(0, 5);
  const canSign = config?.owner_signer_enabled;

  return <><SectionHeading title="Approvals" subtitle="Review owner-gated operations before they are sent on-chain."/>
    {error && <div className="connection-banner connection-offline" role="alert"><div><strong>Could not load pending requests</strong><span>{error}</span></div></div>}
    {notice && <div className={notice.tone === 'success' ? 'success-banner' : 'connection-banner connection-offline'} role="status"><ShieldCheck size={17}/> {notice.text}</div>}
    {!current && !loading && !error && <div className="panel"><div className="panel-heading"><div><h2>No requests waiting</h2><p>When the agent exceeds a limit, the request appears here from the wallet's on-chain pending queue.</p></div></div></div>}
    {current && <div className="approval-page-grid"><div className="panel approval-detail">
      <div className="panel-heading"><div><h2>Pending request <span className="request-id">#{current.id}</span></h2><p>Expires in {formatCountdown(secondsLeft(current.expires_at))}</p></div><span className="eyebrow-pill pill-amber"><span/> NEEDS REVIEW</span></div>
      <div className="ticket-hero"><div className="ticket-icon"><Ticket size={23}/></div><span>{current.calls.length} CALL{current.calls.length > 1 ? 'S' : ''} · QUEUED ON-CHAIN</span><strong>${current.usd_value}</strong><small>{shortAddress(current.calls[0]?.target)} · {describeCall(current.calls[0] ?? {})}</small></div>
      <div className="checks-block"><h3>Policy checks</h3>{current.calls.map((call, i) => <div className="check-row" key={i}><span className="check-mark"><Check size={12}/></span><span>Call {i + 1} allowlisted</span><strong>{shortAddress(call.target)}{call.value !== '0' ? ` · ${weiToEth(call.value)} ETH` : ''}</strong></div>)}<div className="check-row"><span className="check-mark check-warn"><Clock3 size={12}/></span><span>Per-tx limit</span><strong className="text-amber">${current.usd_value}{summary ? ` > $${summary.per_transaction_limit_usd}` : ''}</strong></div></div>
      <div className="request-meta"><div><span>Requested by</span><strong>agent {shortAddress(current.agent)}</strong></div><div><span>Reason</span><strong>{current.reason.replaceAll('_', ' ')}</strong></div><div><span>Daily budget after</span><strong className="text-green">unchanged</strong></div></div>
      <div className="approval-page-actions"><button className="button button-primary" disabled={!canSign || busyId === current.id} onClick={() => void approve(current.id)}><Check size={15}/> {busyId === current.id ? 'Sending…' : canSign ? 'Approve request' : 'Approve with MetaMask'}</button><button className="button button-danger-ghost" disabled={!canSign || busyId === current.id} onClick={() => void reject(current.id)}><X size={15}/> Reject request</button></div>
      {!canSign && <p className="fine-print">Owner signing is not enabled on this backend. Set DEMO_OWNER_PRIVATE_KEY for a local demo, or approve from the owner wallet.</p>}
    </div><aside className="panel approval-policy"><div className="policy-icon"><ShieldCheck size={18}/></div><h2>Why is this waiting?</h2><p>{REASON_TEXT[current.reason]} The target and function selector are allowlisted, so an owner can approve the exact request.</p>{summary && <><div className="policy-fact"><span>Per-tx limit</span><strong>${summary.per_transaction_limit_usd}</strong></div><div className="policy-fact"><span>Requested amount</span><strong className="text-amber">${current.usd_value}</strong></div><div className="policy-fact"><span>Spent in window</span><strong>${summary.spent_in_window_usd} / ${summary.daily_limit_usd}</strong></div></>}<div className="info-note">Approval executes only this queued operation. It does not change policy or raise spending limits.</div></aside></div>}
    {history.length > 0 && <div className="panel"><div className="panel-heading"><div><h2>Recently resolved</h2><p>Latest decisions read from the wallet</p></div></div>{history.map((r) => <div className="check-row" key={r.id}><span>#{r.id} · ${r.usd_value} · {shortAddress(r.agent)}</span><strong>{r.status}</strong></div>)}</div>}
  </>;
}
