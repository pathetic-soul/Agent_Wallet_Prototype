import { Radio } from 'lucide-react';
import { formatTokenAmount, formatUsd } from '../lib/format.js';

const TONES = { ETH: 'purple', dUSDC: 'blue', USDC: 'blue' };

export function TokenList({ tokens, compact = false }) {
  return <div className={`token-list ${compact ? 'token-list-compact' : ''}`}>{tokens.map((token) => <div className="token-item" key={token.address}><div className={`token-coin coin-${TONES[token.symbol] ?? 'amber'}`}>{token.symbol === 'ETH' ? '◆' : token.symbol.includes('USD') ? '$' : token.symbol[0]}</div><div className="token-info"><strong>{token.symbol}<span> · {token.price_source === 'chainlink' ? 'Chainlink feed' : token.price_source === 'fixed' ? 'Fixed testnet price' : 'No price'}</span></strong><small>{formatTokenAmount(token.balance, token.decimals)} {token.symbol}</small></div><div className="token-value"><strong>{token.usd_value === null ? '—' : formatUsd(token.usd_value)}</strong><small className={`feed-status ${token.freshness === 'Fresh' ? '' : 'feed-mock'}`}><Radio size={10}/>{token.freshness}</small></div></div>)}</div>;
}
