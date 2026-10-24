import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { usePendingRequests } from '../src/hooks/usePendingRequests.js';
import { walletApi } from '../src/services/api.js';
import { describeCall, formatCountdown, secondsLeft, shortAddress, weiToEth } from '../src/lib/format.js';

const open = { id: 1, status: 'open', usd_value: '35.00', calls: [], expires_at: 0 };
const summary = { per_transaction_limit_usd: '20.00' };

beforeEach(() => {
  vi.spyOn(walletApi, 'getPendingRequests').mockResolvedValue([open]);
  vi.spyOn(walletApi, 'getWalletSummary').mockResolvedValue(summary);
});

afterEach(() => vi.restoreAllMocks());

describe('usePendingRequests', () => {
  it('loads the queue and summary', async () => {
    const { result } = renderHook(() => usePendingRequests({ poll: false }));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.requests).toEqual([open]);
    expect(result.current.summary).toEqual(summary);
  });

  it('surfaces load failures', async () => {
    walletApi.getPendingRequests.mockRejectedValue(new Error('chain down'));
    const { result } = renderHook(() => usePendingRequests({ poll: false }));
    await waitFor(() => expect(result.current.error).toBe('chain down'));
  });

  it('uses a generic message for non-Error failures', async () => {
    walletApi.getPendingRequests.mockRejectedValue('boom');
    const { result } = renderHook(() => usePendingRequests({ poll: false }));
    await waitFor(() => expect(result.current.error).toBe('Request failed'));
  });

  it('approves, refreshes, and reports the transaction', async () => {
    vi.spyOn(walletApi, 'approvePending').mockResolvedValue({ transaction_hash: '0x' + 'ab'.repeat(32) });
    const { result } = renderHook(() => usePendingRequests({ poll: false }));
    await waitFor(() => expect(result.current.loading).toBe(false));
    walletApi.getPendingRequests.mockResolvedValue([{ ...open, status: 'approved' }]);
    await act(() => result.current.approve(1));
    expect(walletApi.approvePending).toHaveBeenCalledWith(1);
    expect(result.current.notice.tone).toBe('success');
    expect(result.current.notice.text).toContain('approved');
    expect(result.current.requests[0].status).toBe('approved');
    expect(result.current.busyId).toBeNull();
  });

  it('rejects and reports errors from the backend', async () => {
    vi.spyOn(walletApi, 'rejectPending').mockRejectedValueOnce(new Error('Owner transaction reverted'));
    const { result } = renderHook(() => usePendingRequests({ poll: false }));
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(() => result.current.reject(1));
    expect(result.current.notice).toEqual({ tone: 'error', text: 'Owner transaction reverted' });
    walletApi.rejectPending.mockResolvedValueOnce({ transaction_hash: '0x' + 'cd'.repeat(32) });
    await act(() => result.current.reject(1));
    expect(result.current.notice.text).toContain('rejected');
  });

  it('falls back to a generic action error', async () => {
    vi.spyOn(walletApi, 'approvePending').mockRejectedValueOnce('nope');
    const { result } = renderHook(() => usePendingRequests({ poll: false }));
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(() => result.current.approve(1));
    expect(result.current.notice.text).toBe('Action failed');
  });

  it('polls on an interval and stops on unmount', async () => {
    vi.useFakeTimers();
    const { unmount } = renderHook(() => usePendingRequests());
    await act(async () => { await vi.advanceTimersByTimeAsync(6100); });
    expect(walletApi.getPendingRequests.mock.calls.length).toBeGreaterThanOrEqual(3);
    unmount();
    const calls = walletApi.getPendingRequests.mock.calls.length;
    await act(async () => { await vi.advanceTimersByTimeAsync(6000); });
    expect(walletApi.getPendingRequests.mock.calls.length).toBe(calls);
    vi.useRealTimers();
  });
});

describe('format helpers', () => {
  it('shortens addresses and handles missing ones', () => {
    expect(shortAddress('0x1234567890abcdef1234567890abcdef12345678')).toBe('0x1234...5678');
    expect(shortAddress(undefined)).toBe('—');
  });
  it('names known selectors and falls back to the raw selector', () => {
    expect(describeCall({ selector: '0xa5f8cdbb' })).toBe('buyTicket(address)');
    expect(describeCall({ selector: '0xdeadbeef' })).toBe('0xdeadbeef');
  });
  it('computes countdowns that never go negative', () => {
    expect(secondsLeft(1100, 1_000_000)).toBe(100);
    expect(secondsLeft(10, 1_000_000)).toBe(0);
    expect(formatCountdown(3599)).toBe('59:59');
  });
  it('converts wei to ETH', () => {
    expect(weiToEth('17500000000000000')).toBe('0.0175');
  });
});

describe('walletApi wallet endpoints', () => {
  it('posts approve and reject to the encoded request path', async () => {
    vi.restoreAllMocks();
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ transaction_hash: '0x1' }) });
    vi.stubGlobal('fetch', fetchMock);
    await walletApi.approvePending(7);
    await walletApi.rejectPending(8);
    await walletApi.getWalletSummary();
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/wallet/pending/7/approve');
    expect(fetchMock.mock.calls[0][1].method).toBe('POST');
    expect(fetchMock.mock.calls[1][0]).toBe('/api/v1/wallet/pending/8/reject');
    expect(fetchMock.mock.calls[2][0]).toBe('/api/v1/wallet/summary');
  });
});

describe('walletApi dashboard endpoints', () => {
  it('calls every read and owner endpoint with the right path, method and body', async () => {
    vi.restoreAllMocks();
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
    vi.stubGlobal('fetch', fetchMock);
    await walletApi.getOverview();
    await walletApi.getPolicy();
    await walletApi.getActivity();
    await walletApi.getPendingRequests();
    await walletApi.setPaused(true);
    await walletApi.addSession('0xa', 3600);
    await walletApi.revokeSession('0xa');
    await walletApi.setSpendPolicy('10', '20');
    await walletApi.setCallPolicy('0xa', '0x12345678', true);
    await walletApi.setRecipientPolicy('0xb', false);
    await walletApi.getAttackHistory();
    await walletApi.runAttack('replay');
    const seen = fetchMock.mock.calls.map(([url, init]) => [url.replace('/api/v1', ''), init.method ?? 'GET', init.body ? JSON.parse(init.body) : null]);
    expect(seen).toEqual([
      ['/wallet/overview', 'GET', null],
      ['/wallet/policy', 'GET', null],
      ['/wallet/activity', 'GET', null],
      ['/wallet/pending', 'GET', null],
      ['/wallet/owner/pause', 'POST', { paused: true }],
      ['/wallet/owner/sessions', 'POST', { agent: '0xa', valid_for_seconds: 3600 }],
      ['/wallet/owner/sessions/revoke', 'POST', { agent: '0xa' }],
      ['/wallet/owner/spend-policy', 'POST', { per_transaction_usd: '10', daily_usd: '20' }],
      ['/wallet/owner/call-policy', 'POST', { target: '0xa', selector: '0x12345678', allowed: true }],
      ['/wallet/owner/recipient-policy', 'POST', { recipient: '0xb', allowed: false }],
      ['/demo/attacks', 'GET', null],
      ['/demo/attacks/replay', 'POST', null],
    ]);
  });
});
