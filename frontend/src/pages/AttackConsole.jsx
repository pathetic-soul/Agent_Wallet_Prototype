import { useEffect, useState } from 'react';
import { ArrowUpRight, CheckCircle2, Code2, KeyRound, Repeat2, Shield, ShieldAlert, Terminal, Ticket, Zap } from 'lucide-react';
import { ATTACK_CATALOG } from '../data/attackCatalog.js';
import { SectionHeading } from '../components/SectionHeading.jsx';
import { useWalletData } from '../context/WalletDataContext.jsx';
import { walletApi } from '../services/api.js';

const icons = { shield: Shield, key: KeyRound, code: Code2, repeat: Repeat2, ticket: Ticket };
const clean = (reason) => (reason ?? '').replace('Rejected by EntryPoint simulation: ', '');

export function AttackConsole() {
  const { configured, attackConsoleEnabled } = useWalletData();
  const [history, setHistory] = useState({ history: [], attempts: 0, blocked: 0, executed: 0 });
  const [running, setRunning] = useState(null);
  const [lastResults, setLastResults] = useState({});
  const [error, setError] = useState(null);

  const load = async () => { try { setHistory(await walletApi.getAttackHistory()); } catch (e) { setError(e instanceof Error ? e.message : 'Request failed'); } };
  useEffect(() => { if (configured && attackConsoleEnabled) void load(); }, [configured, attackConsoleEnabled]);

  const fire = async (attack) => {
    setRunning(attack.id); setError(null);
    try { const result = await walletApi.runAttack(attack.id); setLastResults((prev) => ({ ...prev, [attack.id]: result })); }
    catch (e) { setError(e instanceof Error ? e.message : 'Attack failed to run'); }
    finally { setRunning(null); await load(); }
  };

  if (!configured || !attackConsoleEnabled) return <><SectionHeading title="Attack Console" subtitle="Run real hostile UserOperations against the wallet."/><div className="panel"><div className="panel-heading"><div><h2>Attack console is off</h2><p>It is a local-demo feature: the backend needs a wallet plus DEMO_AGENT_PRIVATE_KEY and DEMO_ATTACKER_PRIVATE_KEY (see demo/README.md). It never runs against a real network.</p></div></div></div></>;

  return <>
    <SectionHeading title="Attack Console" subtitle="Run real hostile UserOperations against the wallet."/>
    <section className="attack-hero">
      <div><span className="eyebrow-pill pill-red"><span/> LIVE SUBMISSION · LOCAL CHAIN</span><h2>Six attacks. <em>Zero get through.</em></h2><p>Each button signs a real operation and sends it through the same bundler and EntryPoint an agent uses. The result below is whatever the chain says, not a script.</p></div>
      <div className="attack-summary"><div><span>ATTEMPTS</span><strong>{history.attempts}</strong></div><div><span>REJECTED</span><strong className="text-red">{history.blocked}</strong></div><div><span>EXECUTED</span><strong className={history.executed ? 'text-red' : 'text-green'}>{history.executed}</strong></div></div>
    </section>
    {error && <div className="connection-banner connection-offline" role="alert"><div><strong>Attack console error</strong><span>{error}</span></div></div>}
    <div className="attack-layout">
      <div className="attack-cards">{ATTACK_CATALOG.map((attack) => {
        const Icon = icons[attack.icon] || Shield;
        const result = lastResults[attack.id];
        return <article className="panel attack-card" key={attack.id}><div className="attack-card-title"><span className="attack-icon"><Icon size={18}/></span><div><small>ATTACK {attack.number}</small><h2>{attack.title}</h2></div></div><p>{attack.text}</p><pre className="attack-code">{attack.code}</pre><div className="attack-result">{result ? <strong className={result.outcome === 'blocked' ? '' : 'text-red'}>{result.outcome === 'blocked' ? `× ${clean(result.reason)}` : 'ACCEPTED - the wallet did not stop this'}</strong> : <strong className="muted">Expected: {attack.expect}</strong>}<small><CheckCircle2 size={13}/> Defence: {attack.caught}</small></div><div className="attack-actions"><button className="button button-danger" disabled={running !== null} onClick={() => void fire(attack)}><Zap size={13}/> {running === attack.id ? 'Submitting…' : 'Run attack'}</button>{result?.user_operation_hash && <span className="muted">{result.user_operation_hash.slice(0, 12)}… <ArrowUpRight size={12}/></span>}</div></article>;
      })}</div>
      <section className="panel terminal-panel"><div className="terminal-head"><div className="traffic-lights"><i/><i/><i/></div><span>attack.log · this API process</span></div><div className="terminal-body"><div className="terminal-command"><Terminal size={13}/> $ attacks --history</div>{history.history.length === 0 && <div className="terminal-line">No attacks run yet.</div>}{[...history.history].reverse().map((entry, index) => <div key={`${entry.timestamp}-${index}`}><div className="terminal-line">{new Date(entry.timestamp * 1000).toLocaleTimeString()}  {entry.outcome === 'blocked' ? '×' : '!'} {entry.title}</div><div className={`terminal-line ${entry.outcome === 'blocked' ? 'terminal-error' : ''}`}>{'             '}{entry.outcome === 'blocked' ? `× ${clean(entry.reason)}` : 'ACCEPTED'}</div></div>)}<div className="terminal-total">{history.blocked} rejected <span>·</span> {history.executed} executed</div><div className="terminal-prompt">$ <i/></div></div><div className="terminal-foot"><span>›</span> Live results; history resets when the API restarts</div></section>
    </div>
    <section className="panel attack-steps"><div className="panel-heading"><div><h2><ShieldAlert size={16}/> Where each attack dies</h2><p>validateUserOp runs before execution, so a bad operation is refused and costs the wallet nothing.</p></div></div><div className="step-track">{[['Signature + session','× leaked key'],['Agent field = signer','× impersonation'],['Gas caps','× gas grief'],['Target + selector','× unlisted call'],['Decoded recipient / spender','× injection, approve'],['Every call in a batch','× smuggling'],['EntryPoint nonce','× replay']].map(([title, result], index) => <div className="step-item step-fail" key={title}><span>{index + 1}</span><strong>{title}</strong><small>{result}</small></div>)}</div></section>
  </>;
}
