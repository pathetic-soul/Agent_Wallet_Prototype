import { Copy, Menu, Wallet } from 'lucide-react';
import { useAppStatus } from '../context/AppStatusContext.jsx';
import { useWalletData } from '../context/WalletDataContext.jsx';
import { shortAddress } from '../lib/format.js';

export function Topbar({ onMenu }) {
  const { config } = useAppStatus();
  const { overview } = useWalletData();
  const walletAddress = config?.wallet_address;
  const owner = overview?.wallet?.owner;
  return <header className="topbar"><button className="menu-button icon-button" onClick={onMenu} aria-label="Open navigation"><Menu size={19}/></button><div className="topbar-spacer"/><div className="topbar-chip network-chip"><span className="dot dot-blue"/>{config?.chain_name ?? 'Not connected'}</div><button className="topbar-chip address-chip" disabled={!walletAddress} title={walletAddress ? 'Copy wallet address' : 'No wallet configured'} onClick={() => walletAddress && navigator.clipboard?.writeText(walletAddress)}><Wallet size={14}/><span>{walletAddress ? shortAddress(walletAddress) : 'no wallet'}</span><Copy size={12}/></button><div className="topbar-chip owner-chip"><div className="avatar">O</div><div><small>Owner</small><strong>{owner ? shortAddress(owner) : '—'}</strong></div></div></header>;
}
