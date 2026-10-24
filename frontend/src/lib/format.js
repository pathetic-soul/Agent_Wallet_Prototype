const SELECTORS = {
  '0x': 'native transfer',
  '0xa5f8cdbb': 'buyTicket(address)',
  '0xa9059cbb': 'transfer(address,uint256)',
  '0x095ea7b3': 'approve(address,uint256)',
};

export const shortAddress = (address) => (address ? `${address.slice(0, 6)}...${address.slice(-4)}` : '—');

export function describeCall(call) {
  return SELECTORS[call.selector] ?? call.selector;
}

export const REASON_TEXT = {
  over_per_transaction_limit: 'This call exceeds your configured per-transaction limit.',
  over_daily_limit: 'This call would push the agent past its daily budget.',
  pricing_failed: 'A token price was unavailable or stale, so the wallet failed closed.',
};

export function secondsLeft(expiresAt, now = Date.now()) {
  return Math.max(0, Math.floor(expiresAt - now / 1000));
}

export function formatCountdown(seconds) {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

export const weiToEth = (wei) => (Number(BigInt(wei)) / 1e18).toString();

export const formatDuration = (seconds) => {
  if (seconds <= 0) return 'expired';
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
};

export const formatUsd = (value) => `$${Number(value ?? 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export function formatTokenAmount(balance, decimals, places = 4) {
  const divisor = 10n ** BigInt(decimals);
  const whole = BigInt(balance) / divisor;
  const fraction = (BigInt(balance) % divisor).toString().padStart(decimals, '0').slice(0, places);
  return `${whole.toLocaleString('en-US')}${places > 0 && decimals > 0 ? `.${fraction.padEnd(places, '0')}` : ''}`;
}

const timeOfDay = (timestamp) => new Date(timestamp * 1000).toLocaleTimeString('en-GB');

/** Map a backend activity item into the shape ActivityTable renders. */
export function toRow(item) {
  const hash = item.tx_hash ? ` ${item.tx_hash.slice(0, 10)}… ↗` : '';
  return {
    key: item.id,
    time: timeOfDay(item.timestamp),
    icon: item.icon,
    title: item.title,
    detail: item.detail,
    amount: item.usd ? `$${item.usd}` : '—',
    status: item.status,
    result: `${item.result}${item.status === 'Allowed' ? hash : ''}`,
  };
}

export const ATTACK_ICONS = { 'prompt-injection': 'shield', 'leaked-key': 'key', 'approve-max': 'code', 'batch-smuggling': 'code', 'gas-grief': 'shield', replay: 'repeat' };
