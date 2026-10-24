import { useState } from 'react';
import { ArrowDownToLine, Search } from 'lucide-react';
import { ActivityTable } from '../components/ActivityTable.jsx';
import { SectionHeading } from '../components/SectionHeading.jsx';
import { walletGate } from '../components/WalletGate.jsx';
import { useWalletData } from '../context/WalletDataContext.jsx';
import { toRow } from '../lib/format.js';

export function Activity() {
  const { configured, loading, error, activity } = useWalletData();
  const [filter, setFilter] = useState('All');
  const [query, setQuery] = useState('');
  const gate = walletGate({ configured, loading, error, ready: Boolean(activity) }, 'Activity', 'Every operation your smart account accepted, blocked, or queued.');
  if (gate) return gate;
  const filters = ['All', 'Allowed', 'Blocked', 'Pending'];
  const rows = activity.items.filter((item) => (filter === 'All' || item.status === filter) && `${item.title} ${item.detail} ${item.result}`.toLowerCase().includes(query.toLowerCase()));
  return <><SectionHeading title="Activity" subtitle="Every operation your smart account accepted, blocked, or queued." action={<button className="button button-secondary" onClick={() => window.print()}><ArrowDownToLine size={14}/> Export activity</button>}/><div className="panel page-panel"><div className="panel-heading page-panel-heading"><div><h2>Wallet events</h2><p>{activity.items.length} events · latest first</p></div><label className="search-box"><Search size={14}/><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search activity"/></label></div><div className="filter-tabs page-filter-tabs">{filters.map((tab) => <button key={tab} onClick={() => setFilter(tab)} className={filter === tab ? 'selected' : ''}>{tab}</button>)}</div><ActivityTable items={rows.map(toRow)}/><p className="fine-print">{activity.note}</p></div></>;
}
