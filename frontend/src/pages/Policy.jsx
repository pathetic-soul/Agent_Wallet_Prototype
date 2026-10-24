import { useEffect, useState } from 'react';
import { AlertTriangle, Info, LockKeyhole, Plus, ShieldCheck, SlidersHorizontal } from 'lucide-react';
import { SectionHeading } from '../components/SectionHeading.jsx';
import { OwnerNotice, walletGate } from '../components/WalletGate.jsx';
import { useWalletData } from '../context/WalletDataContext.jsx';
import { walletApi } from '../services/api.js';
import { formatTokenAmount, shortAddress } from '../lib/format.js';

const ADDRESS = /^0x[0-9a-fA-F]{40}$/;
const SELECTOR = /^0x[0-9a-fA-F]{8}$/;
const FAIL_CLOSED = ['Over limit → pending queue, never reverts', 'Unknown token / stale price → pending', 'Open pending per agent capped', 'Pending requests expire', 'isValidSignature (EIP-1271) owner-only', 'approve() amount counts toward limit'];

export function Policy() {
  const { configured, loading, error, policy, canSign, owner } = useWalletData();
  const [perTx, setPerTx] = useState('');
  const [daily, setDaily] = useState('');
  const [form, setForm] = useState(null); // 'call' | 'recipient' | null
  const [target, setTarget] = useState('');
  const [selector, setSelector] = useState('');

  useEffect(() => {
    if (policy && perTx === '' && daily === '') { setPerTx(policy.spend.per_transaction_usd); setDaily(policy.spend.daily_usd); }
  }, [policy, perTx, daily]);

  const gate = walletGate({ configured, loading, error, ready: Boolean(policy) }, 'Policy', 'Every rule here lives in AgentWallet.sol. The agent can read it, never change it.');
  if (gate) return gate;

  const disabled = !canSign || Boolean(owner.busy);
  const dirty = perTx !== policy.spend.per_transaction_usd || daily !== policy.spend.daily_usd;
  const limitsValid = Number(perTx) > 0 && Number(daily) >= Number(perTx);
  const gasCap = (wei) => `${Number(BigInt(wei) / 10n ** 7n) / 100} gwei`;

  return <><SectionHeading title="Policy" subtitle="Every rule here lives in AgentWallet.sol. The agent can read it, never change it." action={<button className="button button-primary" disabled={disabled || !dirty || !limitsValid} onClick={() => void owner.run('Update spend limits', () => walletApi.setSpendPolicy(perTx, daily))}><ShieldCheck size={14}/> {canSign ? 'Save limits on-chain' : 'Sign with owner wallet'}</button>}/>
    <OwnerNotice owner={owner}/>
    <div className="pending-change"><div className="pending-lock"><LockKeyhole size={16}/></div><div><strong>{dirty ? 'Unsaved changes' : 'Matches the on-chain policy'}</strong><p>{canSign ? 'Saving sends a setSpendPolicy() transaction signed by the demo owner key.' : 'Owner signing is not enabled on this backend; values are read-only.'}</p></div><button className="button button-secondary" disabled={!dirty} onClick={() => { setPerTx(policy.spend.per_transaction_usd); setDaily(policy.spend.daily_usd); }}>Discard</button></div>
    <div className="policy-layout"><div className="policy-main">
      <section className="panel spending-panel"><div className="panel-heading"><div><h2><SlidersHorizontal size={16}/> Spending limits</h2><p>Priced in USD by the oracle at execution time (8 decimals).</p></div><span className="eyebrow-pill pill-blue"><span/> ENFORCED IN EXECUTE</span></div><div className="limit-grid"><label className="limit-control"><span>Per transaction</span><div className="money-input"><span>$</span><input type="number" min="0.01" step="0.01" disabled={!canSign} value={perTx} onChange={(e) => setPerTx(e.target.value)}/><small>USD</small></div><small className="muted">Over this → approval queue</small></label><label className="limit-control"><span>Daily window {dirty && <em>EDITED</em>}</span><div className={`money-input ${dirty ? 'money-input-edit' : ''}`}><span>$</span><input type="number" min="0.01" step="0.01" disabled={!canSign} value={daily} onChange={(e) => setDaily(e.target.value)}/><small>USD</small></div><small className="muted">Fixed 24h from window start</small></label></div>{!limitsValid && <p className="form-error">Per-transaction must be above zero and not exceed the daily limit.</p>}<div className="info-note"><Info size={14}/> Trade-off, stated plainly: a fixed window allows up to 2× the daily limit around a reset. Rolling buckets are the upgrade path.</div></section>
      <section className="panel targets-panel"><div className="panel-heading"><div><h2>Allowed calls</h2><p>allowedCall(target, selector), checked for every inner call.</p></div><button className="button button-secondary" disabled={disabled} onClick={() => setForm(form === 'call' ? null : 'call')}><Plus size={14}/> Add target</button></div>
        {form === 'call' && <div className="relay-actions"><label className="hash-field"><span>Target address</span><input value={target} onChange={(e) => setTarget(e.target.value.trim())} placeholder="0x…"/></label><label className="hash-field"><span>Selector (4 bytes)</span><input value={selector} onChange={(e) => setSelector(e.target.value.trim())} placeholder="0xa5f8cdbb"/></label><button className="button button-primary" disabled={!ADDRESS.test(target) || !SELECTOR.test(selector) || disabled} onClick={() => { void owner.run('Allow call', () => walletApi.setCallPolicy(target, selector, true)); setForm(null); setTarget(''); setSelector(''); }}>Allow</button></div>}
        <div className="table-wrap"><table className="targets-table"><thead><tr><th>TARGET</th><th>SELECTOR</th><th>ENABLED</th></tr></thead><tbody>{policy.allowed_calls.length === 0 && <tr><td colSpan={3} className="muted">No calls allowed yet. The agent cannot do anything.</td></tr>}{policy.allowed_calls.map((call, index) => <tr key={`${call.target}-${call.selector}`}><td><div className="target-name"><span className={`target-icon target-${index % 4}`}><ShieldCheck size={14}/></span><div><strong>{call.label}</strong><small>{shortAddress(call.target)}</small></div></div></td><td><code>{call.signature}</code></td><td><button aria-label={`Toggle ${call.label} ${call.signature}`} disabled={disabled} className={`toggle ${call.allowed ? 'toggle-on' : ''}`} onClick={() => void owner.run(call.allowed ? 'Disallow call' : 'Allow call', () => walletApi.setCallPolicy(call.target, call.selector, !call.allowed))}><span/></button></td></tr>)}</tbody></table></div></section>
      <section className="panel recipients-panel"><div className="panel-heading"><div><h2>Allowed recipients</h2><p>For transfer / transferFrom / approve the recipient or spender is decoded from calldata and must be here.</p></div></div><div className="recipient-pills">{policy.allowed_recipients.map((r) => <span key={r.address} style={r.allowed ? undefined : { opacity: 0.5 }}>{r.allowed ? '●' : '○'} {shortAddress(r.address)} <button aria-label={`${r.allowed ? 'Remove' : 'Restore'} recipient ${r.address}`} disabled={disabled} onClick={() => void owner.run(r.allowed ? 'Remove recipient' : 'Allow recipient', () => walletApi.setRecipientPolicy(r.address, !r.allowed))}>{r.allowed ? 'remove' : 'restore'}</button></span>)}<button disabled={disabled} onClick={() => setForm(form === 'recipient' ? null : 'recipient')}><Plus size={13}/> Add recipient</button></div>{form === 'recipient' && <div className="relay-actions"><label className="hash-field"><span>Recipient address</span><input value={target} onChange={(e) => setTarget(e.target.value.trim())} placeholder="0x…"/></label><button className="button button-primary" disabled={!ADDRESS.test(target) || disabled} onClick={() => { void owner.run('Allow recipient', () => walletApi.setRecipientPolicy(target, true)); setForm(null); setTarget(''); }}>Allow</button></div>}</section>
    </div><aside className="policy-aside">
      <section className="panel tokens-panel"><h2>Tokens & oracles</h2><p>Stale price never auto-approves.</p><div className="oracle-list">{policy.tokens.map((token) => <div className="oracle-row" key={token.address}><span className={`token-coin coin-${token.symbol === 'ETH' ? 'purple' : 'blue'}`}>{token.symbol === 'ETH' ? '◆' : '$'}</span><strong>{token.symbol} · {token.price_source === 'chainlink' ? 'Chainlink feed' : token.price_source === 'fixed' ? 'Fixed testnet price' : 'No price'}<small>{formatTokenAmount(token.balance, token.decimals, 2)} held</small></strong><span className={`eyebrow-pill ${token.freshness === 'Fresh' ? 'pill-green' : 'pill-amber'}`}><span/>{token.freshness.toUpperCase()}</span></div>)}</div></section>
      <section className="panel rules-panel"><h2>Fail-closed rules</h2><p>Hard-coded in the contract. Not editable from the dashboard.</p>{FAIL_CLOSED.map((rule) => <div className="fail-rule" key={rule}><LockKeyhole size={12}/><span>{rule}</span></div>)}</section>
      <section className="panel gas-panel"><div className="panel-heading"><div><h2>Agent gas caps</h2><p>So a leaked key can't burn the deposit.</p></div><span className="gas-icon"><AlertTriangle size={15}/></span></div>{[['callGasLimit', policy.gas.max_call_gas.toLocaleString()], ['verificationGasLimit', policy.gas.max_verification_gas.toLocaleString()], ['maxFeePerGas', gasCap(policy.gas.max_fee_per_gas_wei)], ['pending TTL', `${policy.pending.ttl_seconds / 60} min`], ['max open pending', policy.pending.max_open_per_agent]].map(([label, value]) => <div className="gas-row" key={label}><span>{label}</span><strong>{value}</strong></div>)}</section>
    </aside></div></>;
}
