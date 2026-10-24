import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { walletApi } from '../services/api.js';

const AppStatusContext = createContext(null);

export function AppStatusProvider({ children }) {
  const [state, setState] = useState({ status: 'loading', config: null, health: null, error: null });

  const refresh = useCallback(async () => {
    setState((current) => ({ ...current, status: 'loading', error: null }));
    try {
      const { config, health } = await walletApi.getSystemStatus();
      setState({
        status: health.status === 'ok' ? 'ready' : 'degraded',
        config,
        health,
        error: null,
      });
    } catch (error) {
      setState({
        status: 'offline',
        config: null,
        health: null,
        error: error instanceof Error ? error.message : 'Backend is unreachable',
      });
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return <AppStatusContext.Provider value={{ ...state, refresh }}>{children}</AppStatusContext.Provider>;
}

export function useAppStatus() {
  const value = useContext(AppStatusContext);
  if (!value) throw new Error('useAppStatus must be used inside AppStatusProvider');
  return value;
}
