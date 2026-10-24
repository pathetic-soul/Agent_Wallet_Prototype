import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { walletApi } from '../services/api.js';
import { useAppStatus } from './AppStatusContext.jsx';
import { usePendingRequests } from '../hooks/usePendingRequests.js';

const WalletDataContext = createContext(null);
const POLL_MS = 3000;

/** One shared poller for everything the dashboard reads from the wallet. */
export function WalletDataProvider({ children, poll = true }) {
  const { config } = useAppStatus();
  const configured = Boolean(config?.wallet_address);
  const pending = usePendingRequests({ poll, enabled: configured });
  const [data, setData] = useState({ overview: null, policy: null, activity: null, loading: true, error: null });
  const [busy, setBusy] = useState(null);
  const [notice, setNotice] = useState(null);

  const refresh = useCallback(async () => {
    try {
      const [overview, policy, activity] = await Promise.all([walletApi.getOverview(), walletApi.getPolicy(), walletApi.getActivity()]);
      setData({ overview, policy, activity, loading: false, error: null });
    } catch (error) {
      setData((current) => ({ ...current, loading: false, error: error instanceof Error ? error.message : 'Request failed' }));
    }
  }, []);

  useEffect(() => {
    if (!configured) return undefined;
    void refresh();
    if (!poll) return undefined;
    const timer = setInterval(() => void refresh(), POLL_MS);
    return () => clearInterval(timer);
  }, [configured, refresh, poll]);

  /** Run an owner transaction through the backend, then reload everything the dashboard shows. */
  const runOwner = useCallback(async (label, action) => {
    setBusy(label);
    setNotice(null);
    try {
      const { transaction_hash: hash } = await action();
      setNotice({ tone: 'success', text: `${label} confirmed on-chain · ${hash.slice(0, 12)}…` });
    } catch (error) {
      setNotice({ tone: 'error', text: error instanceof Error ? error.message : 'Action failed' });
    } finally {
      setBusy(null);
      await Promise.all([refresh(), pending.refresh()]);
    }
  }, [refresh, pending.refresh]);

  const value = {
    ...data,
    configured,
    canSign: Boolean(config?.owner_signer_enabled),
    attackConsoleEnabled: Boolean(config?.attack_console_enabled),
    pending,
    owner: { busy, notice, run: runOwner },
    refresh,
  };
  return <WalletDataContext.Provider value={value}>{children}</WalletDataContext.Provider>;
}

export function useWalletData() {
  const value = useContext(WalletDataContext);
  if (!value) throw new Error('useWalletData must be used inside WalletDataProvider');
  return value;
}
