/** Sparkline of recent executed spend. Renders nothing until there are at least two real points. */
export function MiniChart({ points = [] }) {
  if (points.length < 2) return <div className="mini-chart-empty fine-print">Spend history appears after the agent's first executed operations.</div>;
  const max = Math.max(...points, 1);
  const step = 440 / (points.length - 1);
  const coords = points.map((p, i) => `${(i * step).toFixed(1)} ${(74 - (p / max) * 64).toFixed(1)}`);
  return <svg className="mini-chart" viewBox="0 0 440 82" preserveAspectRatio="none" role="img" aria-label="Recent executed spend"><defs><linearGradient id="chartFill" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="#c5ff4c" stopOpacity=".22"/><stop offset="100%" stopColor="#c5ff4c" stopOpacity="0"/></linearGradient></defs><path d={`M${coords.join(' L')} V82 H0Z`} fill="url(#chartFill)"/><path d={`M${coords.join(' L')}`} fill="none" stroke="#c5ff4c" strokeWidth="2.2" vectorEffect="non-scaling-stroke"/></svg>;
}
