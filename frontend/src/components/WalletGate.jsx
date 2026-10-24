import { AlertTriangle, LoaderCircle, ShieldCheck } from 'lucide-react';
import { SectionHeading } from './SectionHeading.jsx';

/** Returns a placeholder element while wallet data is unavailable, or null once it can render. */
export function walletGate({ configured, loading, error, ready }, title, subtitle) {
  if (ready) return null;
  const content = !configured
    ? { Icon: AlertTriangle, heading: 'No wallet connected', text: 'Set RPC_URL and WALLET_ADDRESS on the backend (see demo/README.md) to see live wallet data here.' }
    : error
      ? { Icon: AlertTriangle, heading: 'Could not read the wallet', text: error }
      : { Icon: LoaderCircle, heading: 'Loading wallet data', text: 'Reading balances, policy and events from the chain.' };
  const { Icon, heading, text } = content;
  return <><SectionHeading title={title} subtitle={subtitle}/><div className="panel"><div className="panel-heading"><div><h2><Icon size={16}/> {heading}</h2><p>{text}</p></div></div></div></>;
}

export function OwnerNotice({ owner }) {
  if (!owner.notice) return null;
  return <div className={owner.notice.tone === 'success' ? 'success-banner' : 'connection-banner connection-offline'} role="status"><ShieldCheck size={17}/> {owner.notice.text}</div>;
}
