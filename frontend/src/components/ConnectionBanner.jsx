import { AlertTriangle, LoaderCircle, RefreshCw, WifiOff } from 'lucide-react';
import { useAppStatus } from '../context/AppStatusContext.jsx';

export function ConnectionBanner() {
  const { status, config, health, error, refresh } = useAppStatus();
  if (status === 'ready') return null;

  const content = {
    loading: { Icon: LoaderCircle, title: 'Connecting to Agent Wallet API', detail: 'Loading chain and bundler status.' },
    degraded: { Icon: AlertTriangle, title: 'Backend connected · provider setup incomplete', detail: health?.bundler?.detail ?? health?.chain?.detail ?? 'Add RPC and bundler settings to .env.' },
    offline: { Icon: WifiOff, title: 'Backend offline', detail: error ?? 'Start the API with pnpm dev.' },
  }[status];
  if (!content) return null;

  const { Icon, title, detail } = content;
  return <div className={`connection-banner connection-${status}`} role="status"><Icon className={status === 'loading' ? 'spin' : ''} size={16}/><div><strong>{title}</strong><span>{detail}{config?.chain_name ? ` · ${config.chain_name}` : ''}</span></div><button onClick={() => void refresh()} disabled={status === 'loading'}><RefreshCw size={13}/> Retry</button></div>;
}
