import { useState } from 'react';
import { Sidebar } from './components/Sidebar.jsx';
import { Topbar } from './components/Topbar.jsx';
import { Overview } from './pages/Overview.jsx';
import { Activity } from './pages/Activity.jsx';
import { Approvals } from './pages/Approvals.jsx';
import { Policy } from './pages/Policy.jsx';
import { Sessions } from './pages/Sessions.jsx';
import { AttackConsole } from './pages/AttackConsole.jsx';
import { Relay } from './pages/Relay.jsx';
import { ConnectionBanner } from './components/ConnectionBanner.jsx';
import { AppStatusProvider } from './context/AppStatusContext.jsx';
import { WalletDataProvider } from './context/WalletDataContext.jsx';

const pageMap = { Overview, Activity, Approvals, Policy, Sessions, Relay, 'Attack Console': AttackConsole };

export default function App() {
  const [page, setPage] = useState('Overview');
  const [menuOpen, setMenuOpen] = useState(false);
  const Page = pageMap[page];

  return <AppStatusProvider><WalletDataProvider><div className="app-shell">
    <Sidebar active={page} onNavigate={(next) => { setPage(next); setMenuOpen(false); }} open={menuOpen} />
    <main className="main-area">
      <Topbar onMenu={() => setMenuOpen(!menuOpen)} />
      <div className="page-content"><ConnectionBanner/><Page onNavigate={setPage} /></div>
    </main>
  </div></WalletDataProvider></AppStatusProvider>;
}
