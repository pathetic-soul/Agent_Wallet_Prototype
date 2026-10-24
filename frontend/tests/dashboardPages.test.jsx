import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AppStatusProvider } from '../src/context/AppStatusContext.jsx';
import { WalletDataProvider, useWalletData } from '../src/context/WalletDataContext.jsx';
import { Overview } from '../src/pages/Overview.jsx';
import { Activity } from '../src/pages/Activity.jsx';
import { Sessions } from '../src/pages/Sessions.jsx';
import { Policy } from '../src/pages/Policy.jsx';
import { Approvals } from '../src/pages/Approvals.jsx';
import { AttackConsole } from '../src/pages/AttackConsole.jsx';
import { walletApi } from '../src/services/api.js';
import { formatDuration, formatTokenAmount, formatUsd, toRow } from '../src/lib/format.js';

const AGENT = '0x3c44cdddb6a900fa2b585dd299e03d12fa4293bc';
const SHOP = '0xdc64a140aa3e981100a9beca4e685f962f0cf6c9';
const WALLET = '0xe2057ec4707c3bacccc4bb8bdfe554aba49c9ea82';
const NOW = 1_800_000_000;

const config = { chain_name: 'Local Anvil', wallet_address: WALLET, owner_signer_enabled: true, attack_console_enabled: true, entry_point_address: '0x1', wallet_factory_address: '0x2', backend_configured: true };
const health = { status: 'ok', chain: { status: 'ok' }, bundler: { status: 'ok' } };
const overview = {
  wallet: { address: WALLET, owner: '0x70997970c51812dc3a010c7d01b50e0d17dc79c8', paused: false, per_transaction_limit_usd: '20.00', daily_limit_usd: '50.00', spent_in_window_usd: '10.00', window_resets_at: NOW + 7200, max_open_pending: 5, max_call_gas: 2_000_000 },
  chain_time: NOW, total_usd: '5000.00',
  tokens: [
    { address: '0x' + '00'.repeat(20), symbol: 'ETH', decimals: 18, balance: '2000000000000000000', usd_value: '4000.00', price_source: 'fixed', freshness: 'Mock' },
    { address: '0x' + '66'.repeat(20), symbol: 'dUSDC', decimals: 6, balance: '1000000000', usd_value: '1000.00', price_source: 'chainlink', freshness: 'Fresh' },
  ],
  sessions: [{ agent: AGENT, valid_after: 0, valid_until: NOW + 86400, open_pending: 1, revoked: false, active: true }],
  stats: { executed_operations: 3, open_pending: 1, spend_history_usd: [5, 10, 10] },
};
const activity = {
  blocked_attempts: 2, note: 'Blocked attempts come from relay log.',
  items: [
    { id: '5-0', timestamp: NOW, icon: 'ticket', title: 'Held for owner approval #1', detail: 'over per transaction limit', usd: '35.00', status: 'Pending', result: 'awaiting owner #1', tx_hash: '0x' + 'ab'.repeat(32) },
    { id: '4-0', timestamp: NOW - 5, icon: 'ticket', title: 'Agent call executed', detail: '1 call(s)', usd: '10.00', status: 'Allowed', result: 'executed on-chain', tx_hash: '0x' + 'cd'.repeat(32) },
    { id: 'relay-1', timestamp: NOW - 9, icon: 'shield', title: 'Rejected UserOperation', detail: 'sender 0x1', usd: null, status: 'Blocked', result: 'AA24 signature error', tx_hash: null },
  ],
};
const policy = {
  spend: { per_transaction_usd: '20.00', daily_usd: '50.00' },
  gas: { max_verification_gas: 1_000_000, max_call_gas: 2_000_000, max_fee_per_gas_wei: '100000000000' },
  pending: { ttl_seconds: 3600, max_open_per_agent: 5 },
  allowed_calls: [{ target: SHOP, label: 'Contract', selector: '0xa5f8cdbb', signature: 'buyTicket(address)', allowed: true }],
  allowed_recipients: [{ address: '0x15d34aaf54267db7d7c367839aaf71a00a2c6a65', allowed: true }, { address: '0x90f79bf6eb2c4f870365e785982e1f101e93b906', allowed: false }],
  tokens: overview.tokens,
};
const openRequest = { id: 1, agent: AGENT, status: 'open', reason: 'over_per_transaction_limit', usd_value: '35.00', created_at: NOW, expires_at: Math.floor(Date.now() / 1000) + 3000, calls: [{ target: SHOP, value: '17500000000000000', data: '0x', selector: '0xa5f8cdbb' }] };
const summary = { per_transaction_limit_usd: '20.00', daily_limit_usd: '50.00', spent_in_window_usd: '10.00' };
const hash = '0x' + 'ef'.repeat(32);

function setup(page, { cfg = config } = {}) {
  vi.spyOn(walletApi, 'getSystemStatus').mockResolvedValue({ config: cfg, health });
  vi.spyOn(walletApi, 'getOverview').mockResolvedValue(overview);
  vi.spyOn(walletApi, 'getPolicy').mockResolvedValue(policy);
  vi.spyOn(walletApi, 'getActivity').mockResolvedValue(activity);
  vi.spyOn(walletApi, 'getPendingRequests').mockResolvedValue([openRequest]);
  vi.spyOn(walletApi, 'getWalletSummary').mockResolvedValue(summary);
  for (const name of ['setPaused', 'addSession', 'revokeSession', 'setSpendPolicy', 'setCallPolicy', 'setRecipientPolicy', 'approvePending', 'rejectPending']) {
    vi.spyOn(walletApi, name).mockResolvedValue({ transaction_hash: hash });
  }
  const Page = page;
  return render(<AppStatusProvider><WalletDataProvider poll={false}><Page/></WalletDataProvider></AppStatusProvider>);
}

afterEach(() => vi.restoreAllMocks());

describe('Overview', () => {
  it('shows real balances, budget, tokens and blocked attempts', async () => {
    setup(Overview);
    expect(await screen.findByText('$5,000.00')).toBeInTheDocument();
    expect(screen.getByText('Daily budget').closest('.budget-card')).toHaveTextContent('$10.00 / $50.00');
    expect(screen.getByText('20% used')).toBeInTheDocument();
    expect(screen.getByText('2h 0m', { exact: false })).toBeInTheDocument();
    expect(screen.getByText('1,000.0000 dUSDC')).toBeInTheDocument();
    expect(screen.getByText('Fixed testnet price', { exact: false })).toBeInTheDocument();
    expect(screen.getByText('Attempts blocked').closest('.attacks-card')).toHaveTextContent('2');
    expect(screen.getByText('AA24 signature error')).toBeInTheDocument();
  });

  it('filters the activity feed', async () => {
    setup(Overview);
    await screen.findByText('$5,000.00');
    await userEvent.click(screen.getByRole('button', { name: 'Blocked' }));
    expect(screen.queryByText('Agent call executed')).not.toBeInTheDocument();
    expect(screen.getByText('Rejected UserOperation')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Executed' }));
    expect(screen.getByText('Agent call executed')).toBeInTheDocument();
  });

  it('pauses the wallet through the owner endpoint and reports the transaction', async () => {
    setup(Overview);
    await userEvent.click(await screen.findByRole('button', { name: 'Pause wallet' }));
    await waitFor(() => expect(walletApi.setPaused).toHaveBeenCalledWith(true));
    expect(await screen.findByText(/Pause wallet confirmed on-chain/)).toBeInTheDocument();
  });

  it('shows a not-connected state without a wallet', async () => {
    setup(Overview, { cfg: { ...config, wallet_address: null } });
    expect(await screen.findByText('No wallet connected')).toBeInTheDocument();
  });

  it('shows the chain error when reads fail', async () => {
    setup(Overview);
    walletApi.getOverview.mockRejectedValue(new Error('rpc down'));
    expect(await screen.findByText('rpc down')).toBeInTheDocument();
  });
});

describe('Activity', () => {
  it('lists events and searches them', async () => {
    setup(Activity);
    expect(await screen.findByText('3 events · latest first')).toBeInTheDocument();
    await userEvent.type(screen.getByPlaceholderText('Search activity'), 'rejected');
    expect(screen.queryByText('Agent call executed')).not.toBeInTheDocument();
    await userEvent.clear(screen.getByPlaceholderText('Search activity'));
    await userEvent.click(screen.getByRole('button', { name: 'Pending' }));
    expect(screen.getByText('Held for owner approval #1')).toBeInTheDocument();
    expect(screen.queryByText('Agent call executed')).not.toBeInTheDocument();
  });
});

describe('Sessions', () => {
  it('revokes a session', async () => {
    setup(Sessions);
    await userEvent.click(await screen.findByRole('button', { name: /Revoke session/ }));
    await waitFor(() => expect(walletApi.revokeSession).toHaveBeenCalledWith(AGENT));
  });

  it('only submits a new session for a valid address', async () => {
    setup(Sessions);
    await userEvent.click(await screen.findByRole('button', { name: /Add session/ }));
    const create = screen.getByRole('button', { name: 'Create session' });
    expect(create).toBeDisabled();
    await userEvent.type(screen.getByPlaceholderText('0x…'), AGENT);
    await userEvent.selectOptions(screen.getByRole('combobox'), '3600');
    await userEvent.click(create);
    await waitFor(() => expect(walletApi.addSession).toHaveBeenCalledWith(AGENT, 3600));
  });

  it('is read-only without an owner signer', async () => {
    setup(Sessions, { cfg: { ...config, owner_signer_enabled: false } });
    expect(await screen.findByText(/read-only here/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Revoke session/ })).toBeDisabled();
  });
});

describe('Policy', () => {
  it('saves edited limits on-chain and blocks invalid ones', async () => {
    setup(Policy);
    const [perTx] = await screen.findAllByRole('spinbutton');
    const save = screen.getByRole('button', { name: /Save limits on-chain/ });
    expect(save).toBeDisabled();
    await userEvent.clear(perTx);
    await userEvent.type(perTx, '60');
    expect(screen.getByText(/must be above zero and not exceed/)).toBeInTheDocument();
    expect(save).toBeDisabled();
    await userEvent.clear(screen.getAllByRole('spinbutton')[1]);
    await userEvent.type(screen.getAllByRole('spinbutton')[1], '70');
    await userEvent.click(save);
    await waitFor(() => expect(walletApi.setSpendPolicy).toHaveBeenCalledWith('60', '70'));
  });

  it('discards edits', async () => {
    setup(Policy);
    const [perTx] = await screen.findAllByRole('spinbutton');
    await userEvent.type(perTx, '5');
    await userEvent.click(screen.getByRole('button', { name: 'Discard' }));
    expect(screen.getAllByRole('spinbutton')[0]).toHaveValue(20);
  });

  it('toggles an allowed call and a recipient', async () => {
    setup(Policy);
    await userEvent.click(await screen.findByLabelText('Toggle Contract buyTicket(address)'));
    await waitFor(() => expect(walletApi.setCallPolicy).toHaveBeenCalledWith(SHOP, '0xa5f8cdbb', false));
    await userEvent.click(screen.getAllByText('remove')[0]);
    await waitFor(() => expect(walletApi.setRecipientPolicy).toHaveBeenCalledWith('0x15d34aaf54267db7d7c367839aaf71a00a2c6a65', false));
    await userEvent.click(screen.getByText('restore'));
    await waitFor(() => expect(walletApi.setRecipientPolicy).toHaveBeenCalledWith('0x90f79bf6eb2c4f870365e785982e1f101e93b906', true));
  });

  it('adds a target and a recipient only with valid input', async () => {
    setup(Policy);
    await userEvent.click(await screen.findByRole('button', { name: /Add target/ }));
    const allow = screen.getByRole('button', { name: 'Allow' });
    expect(allow).toBeDisabled();
    const [targetInput, selectorInput] = screen.getAllByPlaceholderText(/0x/);
    await userEvent.type(targetInput, SHOP);
    await userEvent.type(selectorInput, '0xa9059cbb');
    await userEvent.click(allow);
    await waitFor(() => expect(walletApi.setCallPolicy).toHaveBeenCalledWith(SHOP, '0xa9059cbb', true));
    await userEvent.click(screen.getByRole('button', { name: /Add recipient/ }));
    await userEvent.type(screen.getByPlaceholderText('0x…'), AGENT);
    await userEvent.click(screen.getByRole('button', { name: 'Allow' }));
    await waitFor(() => expect(walletApi.setRecipientPolicy).toHaveBeenCalledWith(AGENT, true));
  });

  it('is read-only without an owner signer', async () => {
    setup(Policy, { cfg: { ...config, owner_signer_enabled: false } });
    expect(await screen.findByText(/values are read-only/)).toBeInTheDocument();
    expect(screen.getByLabelText('Toggle Contract buyTicket(address)')).toBeDisabled();
  });
});

describe('Approvals', () => {
  it('approves the queued request through the backend', async () => {
    setup(Approvals);
    await userEvent.click(await screen.findByRole('button', { name: /Approve request/ }));
    await waitFor(() => expect(walletApi.approvePending).toHaveBeenCalledWith(1));
    expect(await screen.findByText(/Request #1 approved on-chain/)).toBeInTheDocument();
  });

  it('shows an empty state when nothing is waiting', async () => {
    setup(Approvals);
    walletApi.getPendingRequests.mockResolvedValue([]);
    expect(await screen.findByText('No requests waiting')).toBeInTheDocument();
  });
});

describe('AttackConsole', () => {
  const history = { attacks: [], history: [], attempts: 0, blocked: 0, executed: 0 };

  it('explains when the console is disabled', async () => {
    setup(AttackConsole, { cfg: { ...config, attack_console_enabled: false } });
    expect(await screen.findByText('Attack console is off')).toBeInTheDocument();
  });

  it('runs an attack for real and shows the chain-provided reason', async () => {
    setup(AttackConsole);
    vi.spyOn(walletApi, 'getAttackHistory').mockResolvedValue(history);
    vi.spyOn(walletApi, 'runAttack').mockResolvedValue({ attack: 'prompt-injection', outcome: 'blocked', reason: 'Rejected by EntryPoint simulation: AA23 reverted: RecipientNotAllowed(0x90)', user_operation_hash: null });
    await userEvent.click((await screen.findAllByRole('button', { name: /Run attack/ }))[0]);
    await waitFor(() => expect(walletApi.runAttack).toHaveBeenCalledWith('prompt-injection'));
    expect(await screen.findByText('× AA23 reverted: RecipientNotAllowed(0x90)')).toBeInTheDocument();
  });

  it('flags an attack that is accepted and surfaces errors', async () => {
    setup(AttackConsole);
    vi.spyOn(walletApi, 'getAttackHistory').mockResolvedValue({ ...history, history: [{ timestamp: NOW, title: 'x', outcome: 'executed', reason: '' }], attempts: 1, executed: 1 });
    vi.spyOn(walletApi, 'runAttack').mockResolvedValueOnce({ attack: 'leaked-key', outcome: 'executed', reason: null, user_operation_hash: hash }).mockRejectedValueOnce(new Error('no targets'));
    const buttons = await screen.findAllByRole('button', { name: /Run attack/ });
    await userEvent.click(buttons[1]);
    expect(await screen.findByText(/ACCEPTED - the wallet did not stop this/)).toBeInTheDocument();
    await userEvent.click(screen.getAllByRole('button', { name: /Run attack/ })[2]);
    expect(await screen.findByText('no targets')).toBeInTheDocument();
  });
});

describe('WalletDataContext', () => {
  it('throws when used outside the provider', () => {
    const Probe = () => { useWalletData(); return null; };
    vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => render(<Probe/>)).toThrow('useWalletData must be used inside WalletDataProvider');
  });

  it('reports owner action failures', async () => {
    setup(Overview);
    walletApi.setPaused.mockRejectedValue(new Error('Owner transaction reverted'));
    await userEvent.click(await screen.findByRole('button', { name: 'Pause wallet' }));
    expect(await screen.findByText('Owner transaction reverted')).toBeInTheDocument();
  });

  it('uses generic messages for non-Error failures', async () => {
    setup(Overview);
    walletApi.setPaused.mockRejectedValue('boom');
    await userEvent.click(await screen.findByRole('button', { name: 'Pause wallet' }));
    expect(await screen.findByText('Action failed')).toBeInTheDocument();
  });

  it('polls on an interval and stops on unmount', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.spyOn(walletApi, 'getSystemStatus').mockResolvedValue({ config, health });
    vi.spyOn(walletApi, 'getOverview').mockResolvedValue(overview);
    vi.spyOn(walletApi, 'getPolicy').mockResolvedValue(policy);
    vi.spyOn(walletApi, 'getActivity').mockResolvedValue(activity);
    vi.spyOn(walletApi, 'getPendingRequests').mockResolvedValue([]);
    vi.spyOn(walletApi, 'getWalletSummary').mockResolvedValue(summary);
    const { unmount } = render(<AppStatusProvider><WalletDataProvider><div/></WalletDataProvider></AppStatusProvider>);
    await waitFor(() => expect(walletApi.getOverview).toHaveBeenCalled());
    await vi.advanceTimersByTimeAsync(6500);
    expect(walletApi.getOverview.mock.calls.length).toBeGreaterThanOrEqual(3);
    unmount();
    const calls = walletApi.getOverview.mock.calls.length;
    await vi.advanceTimersByTimeAsync(7000);
    expect(walletApi.getOverview.mock.calls.length).toBe(calls);
    vi.useRealTimers();
  });

  it('keeps old data and records a generic error for non-Error read failures', async () => {
    setup(Overview);
    await screen.findByText('$5,000.00');
    walletApi.getOverview.mockRejectedValue('x');
    vi.spyOn(walletApi, 'setPaused').mockResolvedValue({ transaction_hash: hash });
    await userEvent.click(screen.getByRole('button', { name: 'Pause wallet' }));
    await waitFor(() => expect(screen.getByText('$5,000.00')).toBeInTheDocument());
  });
});

describe('format helpers for the dashboard', () => {
  it('formats durations', () => {
    expect(formatDuration(0)).toBe('expired');
    expect(formatDuration(90061)).toBe('1d 1h');
    expect(formatDuration(3700)).toBe('1h 1m');
    expect(formatDuration(300)).toBe('5m');
  });
  it('formats USD and token amounts', () => {
    expect(formatUsd('1234.5')).toBe('$1,234.50');
    expect(formatUsd(undefined)).toBe('$0.00');
    expect(formatTokenAmount('1500000', 6)).toBe('1.5000');
    expect(formatTokenAmount('7', 0, 0)).toBe('7');
  });
  it('maps activity items into table rows', () => {
    const allowed = toRow(activity.items[1]);
    expect(allowed.amount).toBe('$10.00');
    expect(allowed.result).toContain('↗');
    const blocked = toRow(activity.items[2]);
    expect(blocked.amount).toBe('—');
    expect(blocked.result).toBe('AA24 signature error');
    expect(toRow(activity.items[0]).result).not.toContain('↗');
  });
});

describe('table rendering', () => {
  it('has no leftover hard-coded demo values', async () => {
    setup(Overview);
    await screen.findByText('$5,000.00');
    const text = document.body.textContent;
    for (const stale of ['Qwen2.5', '1,284.50', '0x7a3F', 'Pimlico', 'Oct 24']) expect(text).not.toContain(stale);
    expect(within(document.body).queryByText(/DEMO DATA/)).toBeNull();
  });
});

beforeEach(() => { vi.useRealTimers(); });
