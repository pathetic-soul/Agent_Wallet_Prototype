import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../src/services/api.js', () => ({
  walletApi: { getSystemStatus: vi.fn() },
}));

import { walletApi } from '../src/services/api.js';
import { AppStatusProvider, useAppStatus } from '../src/context/AppStatusContext.jsx';

function Probe() {
  const { status, config, error, refresh } = useAppStatus();
  return <><span>{status}</span><span>{config?.chain_name}</span><span>{error}</span><button onClick={() => void refresh()}>refresh</button></>;
}

describe('AppStatusProvider', () => {
  it('moves from loading to ready', async () => {
    walletApi.getSystemStatus.mockResolvedValue({ config: { chain_name: 'Base Sepolia' }, health: { status: 'ok' } });
    render(<AppStatusProvider><Probe/></AppStatusProvider>);
    expect(screen.getByText('loading')).toBeInTheDocument();
    expect(await screen.findByText('ready')).toBeInTheDocument();
    expect(screen.getByText('Base Sepolia')).toBeInTheDocument();
  });

  it('reports degraded provider health', async () => {
    walletApi.getSystemStatus.mockResolvedValue({ config: {}, health: { status: 'degraded' } });
    render(<AppStatusProvider><Probe/></AppStatusProvider>);
    expect(await screen.findByText('degraded')).toBeInTheDocument();
  });

  it('reports backend connection failures and can retry', async () => {
    walletApi.getSystemStatus.mockRejectedValueOnce(new Error('API unavailable')).mockResolvedValueOnce({ config: {}, health: { status: 'ok' } });
    render(<AppStatusProvider><Probe/></AppStatusProvider>);
    expect(await screen.findByText('offline')).toBeInTheDocument();
    expect(screen.getByText('API unavailable')).toBeInTheDocument();
    screen.getByRole('button', { name: 'refresh' }).click();
    await waitFor(() => expect(screen.getByText('ready')).toBeInTheDocument());
    expect(walletApi.getSystemStatus).toHaveBeenCalledTimes(2);
  });

  it('uses a safe fallback for non-Error failures', async () => {
    walletApi.getSystemStatus.mockRejectedValue('offline');
    render(<AppStatusProvider><Probe/></AppStatusProvider>);
    expect(await screen.findByText('Backend is unreachable')).toBeInTheDocument();
  });

  it('rejects context access outside the provider', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => render(<Probe/>)).toThrow('useAppStatus must be used inside AppStatusProvider');
    consoleError.mockRestore();
  });
});
