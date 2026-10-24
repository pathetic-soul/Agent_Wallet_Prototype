import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, walletApi } from '../src/services/api.js';

function response(payload, { ok = true, status = 200 } = {}) {
  return { ok, status, json: vi.fn().mockResolvedValue(payload) };
}

describe('walletApi', () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock);
  });

  it('loads backend configuration and health together', async () => {
    fetchMock
      .mockResolvedValueOnce(response({ chain_id: 84532, chain_name: 'Base Sepolia' }))
      .mockResolvedValueOnce(response({ status: 'ok' }));

    await expect(walletApi.getSystemStatus()).resolves.toEqual({
      config: { chain_id: 84532, chain_name: 'Base Sepolia' },
      health: { status: 'ok' },
    });
    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/v1/config', expect.objectContaining({ headers: { Accept: 'application/json' } }));
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/v1/health', expect.any(Object));
  });

  it('exposes individual configuration and health calls', async () => {
    fetchMock.mockResolvedValueOnce(response({ chain_id: 84532 })).mockResolvedValueOnce(response({ status: 'degraded' }));
    await expect(walletApi.getConfig()).resolves.toEqual({ chain_id: 84532 });
    await expect(walletApi.getHealth()).resolves.toEqual({ status: 'degraded' });
  });

  it('submits and estimates packed operations as JSON', async () => {
    const operation = { sender: '0x1111111111111111111111111111111111111111' };
    fetchMock
      .mockResolvedValueOnce(response({ user_operation_hash: `0x${'a'.repeat(64)}` }, { status: 202 }))
      .mockResolvedValueOnce(response({ callGasLimit: '0x1' }));

    await walletApi.submitUserOperation(operation);
    await walletApi.estimateUserOperation(operation);

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/v1/user-operations', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ user_operation: operation }),
      headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    }));
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/v1/user-operations/estimate', expect.objectContaining({ method: 'POST' }));
  });

  it('looks up a receipt with an encoded hash', async () => {
    fetchMock.mockResolvedValueOnce(response({ receipt: null }));
    await expect(walletApi.getUserOperationReceipt('0xabc/def')).resolves.toEqual({ receipt: null });
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/user-operations/0xabc%2Fdef', expect.any(Object));
  });

  it('normalizes structured backend errors', async () => {
    fetchMock.mockResolvedValueOnce(response({ detail: { message: 'AA23 rejected', code: -32500 } }, { ok: false, status: 422 }));
    await expect(walletApi.getHealth()).rejects.toMatchObject({
      name: 'ApiError',
      message: 'AA23 rejected',
      status: 422,
      detail: { message: 'AA23 rejected', code: -32500 },
    });
  });

  it('uses string and status fallback error messages', async () => {
    fetchMock
      .mockResolvedValueOnce(response({ detail: 'Bundler unavailable' }, { ok: false, status: 503 }))
      .mockResolvedValueOnce({ ok: false, status: 500, json: vi.fn().mockRejectedValue(new Error('not JSON')) });
    await expect(walletApi.getHealth()).rejects.toThrow('Bundler unavailable');
    await expect(walletApi.getHealth()).rejects.toThrow('API request failed (500)');
  });

  it('wraps network failures and preserves ApiError metadata', async () => {
    fetchMock.mockRejectedValueOnce(new Error('connection refused'));
    const error = await walletApi.getHealth().catch((caught) => caught);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ message: 'Backend is unreachable', status: 0, detail: 'connection refused' });
  });
});
