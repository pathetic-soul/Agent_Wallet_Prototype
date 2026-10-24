export function StatusBadge({ status }) {
  return <span className={`status-badge status-${status.toLowerCase()}`}><span/>{status}</span>;
}
