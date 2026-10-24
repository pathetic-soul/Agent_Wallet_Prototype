const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim() ?? '';
const API_BASE_URL = configuredBaseUrl.replace(/\/$/, '');

export class ApiError extends Error {
  constructor(message, status, detail) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(`${API_BASE_URL}/api/v1${path}`, {
      ...options,
      headers: {
        Accept: 'application/json',
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...options.headers,
      },
    });
  } catch (error) {
    throw new ApiError('Backend is unreachable', 0, error instanceof Error ? error.message : null);
  }

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = payload?.detail ?? payload;
    const message = typeof detail === 'string'
      ? detail
      : detail?.message ?? `API request failed (${response.status})`;
    throw new ApiError(message, response.status, detail);
  }
  return payload;
}

const post = (path, body) => request(path, { method: 'POST', body: JSON.stringify(body) });

export const walletApi = {
  getConfig: () => request('/config'),
  getHealth: () => request('/health'),
  getSystemStatus: async () => {
    const [config, health] = await Promise.all([request('/config'), request('/health')]);
    return { config, health };
  },
  submitUserOperation: (userOperation) => request('/user-operations', {
    method: 'POST',
    body: JSON.stringify({ user_operation: userOperation }),
  }),
  estimateUserOperation: (userOperation) => request('/user-operations/estimate', {
    method: 'POST',
    body: JSON.stringify({ user_operation: userOperation }),
  }),
  getUserOperationReceipt: (userOperationHash) => request(`/user-operations/${encodeURIComponent(userOperationHash)}`),
  getWalletSummary: () => request('/wallet/summary'),
  getPendingRequests: () => request('/wallet/pending'),
  approvePending: (id) => request(`/wallet/pending/${encodeURIComponent(id)}/approve`, { method: 'POST' }),
  rejectPending: (id) => request(`/wallet/pending/${encodeURIComponent(id)}/reject`, { method: 'POST' }),
  getOverview: () => request('/wallet/overview'),
  getPolicy: () => request('/wallet/policy'),
  getActivity: () => request('/wallet/activity'),
  setPaused: (paused) => post('/wallet/owner/pause', { paused }),
  addSession: (agent, validForSeconds) => post('/wallet/owner/sessions', { agent, valid_for_seconds: validForSeconds }),
  revokeSession: (agent) => post('/wallet/owner/sessions/revoke', { agent }),
  setSpendPolicy: (perTransactionUsd, dailyUsd) => post('/wallet/owner/spend-policy', { per_transaction_usd: perTransactionUsd, daily_usd: dailyUsd }),
  setCallPolicy: (target, selector, allowed) => post('/wallet/owner/call-policy', { target, selector, allowed }),
  setRecipientPolicy: (recipient, allowed) => post('/wallet/owner/recipient-policy', { recipient, allowed }),
  getAttackHistory: () => request('/demo/attacks'),
  runAttack: (attack) => request(`/demo/attacks/${encodeURIComponent(attack)}`, { method: 'POST' }),
};
