import { act, cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import AppAvailabilityGuard from '../AppAvailabilityGuard';

vi.mock('@capacitor/core', () => ({
  Capacitor: { isNativePlatform: () => false },
}));

describe('A+ availability fallback', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it('keeps the application visible when the health endpoint is healthy', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true, json: async () => ({ status: 'ok' }),
    });
    vi.stubGlobal('fetch', fetchMock);
    render(<AppAvailabilityGuard />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(12000);
    });
    expect(screen.queryByTestId('aplus-availability')).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('shows a friendly fallback only after two failed checks and self-recovers', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: false, status: 503 })
      .mockResolvedValueOnce({ ok: false, status: 503 })
      .mockResolvedValue({
        ok: true, json: async () => ({ status: 'ok' }),
      });
    vi.stubGlobal('fetch', fetchMock);
    const resume = vi.fn();
    window.addEventListener('aplus-app-resume', resume);
    try {
      render(<AppAvailabilityGuard />);
      await act(async () => {
        window.dispatchEvent(new Event('aplus-backend-possibly-unavailable'));
        await vi.advanceTimersByTimeAsync(6000);
      });
      expect(screen.getByTestId('aplus-availability')).toBeInTheDocument();
      expect(screen.getByText(/keine verbindliche Rückkehrzeit/)).toBeInTheDocument();

      await act(async () => {
        window.dispatchEvent(new Event('aplus-backend-possibly-unavailable'));
        await vi.advanceTimersByTimeAsync(6000);
      });
      expect(screen.queryByTestId('aplus-availability')).toBeNull();
      expect(resume).toHaveBeenCalledTimes(1);
    } finally {
      window.removeEventListener('aplus-app-resume', resume);
    }
  });

  it('does not show maintenance for a single brief connection error', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: false, status: 503 })
      .mockResolvedValue({ ok: true, json: async () => ({ status: 'ok' }) });
    vi.stubGlobal('fetch', fetchMock);
    render(<AppAvailabilityGuard />);
    await act(async () => {
      window.dispatchEvent(new Event('aplus-backend-possibly-unavailable'));
      await vi.advanceTimersByTimeAsync(6000);
    });
    expect(screen.queryByTestId('aplus-availability')).toBeNull();
  });
});
