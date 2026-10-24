import { Activity, Bell, ChevronRight, LayoutDashboard, KeyRound, RadioTower, SlidersHorizontal, Shield, ShieldAlert, X } from 'lucide-react';
import { useAppStatus } from '../context/AppStatusContext.jsx';
import { useWalletData } from '../context/WalletDataContext.jsx';

const navItems = [
  { label: 'Overview', icon: LayoutDashboard }, { label: 'Activity', icon: Activity },
  { label: 'Approvals', icon: Bell }, { label: 'Policy', icon: SlidersHorizontal },
  { label: 'Sessions', icon: KeyRound }, { label: 'Relay', icon: RadioTower }, { label: 'Attack Console', icon: ShieldAlert },
];

export function Sidebar({ active, onNavigate, open }) {
  const { status, config, health } = useAppStatus();
  const { pending } = useWalletData();
  const openCount = pending.requests.filter((r) => r.status === 'open').length;
  const chainName = config?.chain_name ?? 'Not connected';
  const backendLive = status === 'ready';
  return <>
    {open && <button className="mobile-backdrop" onClick={() => onNavigate(active)} aria-label="Close navigation" />}
    <aside className={`sidebar ${open ? 'sidebar-open' : ''}`}>
      <div className="brand-row"><div className="brand-mark"><Shield size={19} strokeWidth={2.4} /></div><div><div className="brand-name">Al-Wallet</div><div className="brand-sub">ERC-4337 · ON-CHAIN POLICY</div></div><button className="sidebar-close icon-button" onClick={() => onNavigate(active)} aria-label="Close navigation"><X size={17}/></button></div>
      <div className="nav-caption">WORKSPACE</div>
      <nav className="nav-list" aria-label="Main navigation">
        {navItems.map(({ label, icon: Icon }) => <button key={label} onClick={() => onNavigate(label)} className={`nav-item ${active === label ? 'active' : ''}`}><Icon size={16}/><span>{label}</span>{label === 'Approvals' && openCount > 0 && <b className="nav-badge badge-amber">{openCount}</b>}</button>)}
      </nav>
      <div className="sidebar-bottom">
        <div className="network-card"><div className="network-title"><span className="dot dot-blue"/>{chainName}<span className={`live-label ${backendLive ? '' : 'text-amber'}`}><span className={`dot ${backendLive ? 'dot-green' : 'dot-amber'}`}/>{backendLive ? ' READY' : status.toUpperCase()}</span></div><div className="network-line"><span>EntryPoint</span><span>{config?.entry_point_address ? 'set' : 'not set'}</span></div><div className="network-line"><span>Bundler</span><span>{health?.bundler?.status ?? 'unknown'}</span></div><div className="network-line"><span>Chain ID</span><span>{config?.chain_id ?? '—'}</span></div></div>
        <div className="audit-badge"><Shield size={12}/> TESTNET ONLY <span>·</span> UNAUDITED</div>
        <button className="collapse-link" onClick={() => onNavigate('Overview')}>Open wallet details <ChevronRight size={13}/></button>
      </div>
    </aside>
  </>;
}
