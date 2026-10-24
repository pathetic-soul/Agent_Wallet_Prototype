import { useCallback, useEffect, useState } from 'react';
import { walletApi } from '../services/api.js';

const POLL_MS = 3000;

/** Loads the wallet's on-chain pending queue and relays owner approve/reject actions. */
export function usePendingRequests({ poll = true, enabled = true } = {}) {
  const [state, setState] = useState({ requests: [], summary: null, loading: true, error: null });
  const [busyId, setBusyId] = useState(null);
  const [notice, setNotice] = useState(null);

  const refresh = useCallback(async () => {
    try {
      const [requests, summary] = await Promise.all([walletApi.getPendingRequests(), walletApi.getWalletSummary()]);
      setState({ requests, summary, loading: false, error: null });
    } catch (error) {
      setState((current) => ({ ...current, loading: false, error: error instanceof Error ? error.message : 'Request failed' }));
    }
  }, []);

  useEffect(() => {
    if (!enabled) return undefined;
    void refresh();
    if (!poll) return undefined;
    const timer = setInterval(() => void refresh(), POLL_MS);
    return () => clearInterval(timer);
  }, [refresh, poll, enabled]);

  const act = useCallback(async (id, action) => {
    setBusyId(id);
    setNotice(null);
    try {
      const call = action === 'approve' ? walletApi.approvePending : walletApi.rejectPending;
      const { transaction_hash: hash } = await call(id);
      setNotice({ tone: 'success', text: `Request #${id} ${action === 'approve' ? 'approved' : 'rejected'} on-chain · ${hash.slice(0, 12)}…` });
    } catch (error) {
      setNotice({ tone: 'error', text: error instanceof Error ? error.message : 'Action failed' });
    } finally {
      setBusyId(null);
      await refresh();
    }
  }, [refresh]);

  return { ...state, busyId, notice, refresh, approve: (id) => act(id, 'approve'), reject: (id) => act(id, 'reject') };
}
