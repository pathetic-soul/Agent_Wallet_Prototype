import { Check, Clock3, Ticket, X } from 'lucide-react';
import { useAppStatus } from '../context/AppStatusContext.jsx';
import { useWalletData } from '../context/WalletDataContext.jsx';
import { formatCountdown, secondsLeft, shortAddress } from '../lib/format.js';

export function ApprovalCard() {
  const { config } = useAppStatus();
  const { pending: { requests, summary, busyId, notice, approve, reject } } = useWalletData();
  const open = requests.filter((r) => r.status === 'open');
  const current = open[open.length - 1];
  const canSign = config?.owner_signer_enabled;

  if (!current) {
    return <section className="panel approval-card approval-complete"><div className="approval-top"><span className="eyebrow-pill pill-green"><span/> NOTHING WAITING</span></div>{notice ? <p className="success-note"><Check size={14}/> {notice.text}</p> : <p className="fine-print">No requests are waiting for owner approval.</p>}</section>;
  }
  return <section className="panel approval-card"><div className="approval-top"><span className="eyebrow-pill pill-amber"><span/> APPROVAL NEEDED</span><span className="countdown"><Clock3 size={13}/> {formatCountdown(secondsLeft(current.expires_at))}</span></div><div className="approval-title"><span className="action-icon action-amber"><Ticket size={17}/></span><div><strong>Request #{current.id}</strong><small>{shortAddress(current.calls[0]?.target)} · {current.calls.length} call{current.calls.length > 1 ? 's' : ''}</small></div><b>${current.usd_value}</b></div><div className="approval-warning"><strong>{current.reason.replaceAll('_', ' ')}{summary ? ` · limit $${summary.per_transaction_limit_usd}` : ''}</strong><small>Held in the on-chain pending queue · request #{current.id}</small></div><div className="requested-by"><span>Requested by</span><strong>{shortAddress(current.agent)}</strong></div><div className="approval-actions"><button className="button button-primary" disabled={!canSign || busyId === current.id} onClick={() => void approve(current.id)}><Check size={14}/> {busyId === current.id ? 'Sending…' : 'Approve request'}</button><button className="button button-danger-ghost" disabled={!canSign || busyId === current.id} onClick={() => void reject(current.id)}><X size={14}/> Reject</button></div>{notice && <p className={notice.tone === 'success' ? 'success-note' : 'fine-print'}>{notice.text}</p>}{!canSign && <p className="fine-print">Owner signing is not enabled on this backend.</p>}<p className="fine-print">Owner-approved spend never consumes the agent’s daily budget.</p></section>;
}
