import { afterEach, describe, expect, it, vi } from 'vitest';
import { confirmShiftWrite, ShiftWriteUnconfirmedError } from '../shiftSaveConfirmation';

afterEach(() => {
  vi.useRealTimers();
});

describe('atomic mobile shift save confirmation', () => {
  it('closes on the first successful write without waiting for a separate GET', async () => {
    const verify = vi.fn().mockResolvedValue(undefined);
    const write = vi.fn().mockResolvedValue({ id: 'saved' });
    await expect(confirmShiftWrite(write, verify)).resolves.toEqual({ id: 'saved' });
    expect(write).toHaveBeenCalledTimes(1);
    expect(verify).not.toHaveBeenCalled();
  });

  it('uses persisted readback when the write response is lost after commit', async () => {
    vi.useFakeTimers();
    const write = vi.fn().mockRejectedValue(new TypeError('Load failed'));
    const verify = vi.fn().mockResolvedValue({ id: 'saved-on-server' });
    const result = confirmShiftWrite(write, verify, { verifyDelayMs: 100, pollIntervalMs: 50, timeoutMs: 1000 });
    await vi.advanceTimersByTimeAsync(105);
    await expect(result).resolves.toEqual({ id: 'saved-on-server' });
    expect(write).toHaveBeenCalledTimes(1);
    expect(verify).toHaveBeenCalledTimes(1);
  });

  it('keeps checking if a readback fails transiently before confirming', async () => {
    vi.useFakeTimers();
    const write = vi.fn().mockRejectedValue(new Error('Network unreachable'));
    const verify = vi.fn()
      .mockRejectedValueOnce(new Error('GET interrupted'))
      .mockResolvedValueOnce(undefined)
      .mockResolvedValueOnce({ id: 'committed' });
    const result = confirmShiftWrite(write, verify, { verifyDelayMs: 50, pollIntervalMs: 50, timeoutMs: 1000 });
    await vi.advanceTimersByTimeAsync(165);
    await expect(result).resolves.toEqual({ id: 'committed' });
    expect(write).toHaveBeenCalledTimes(1);
    expect(verify).toHaveBeenCalledTimes(3);
  });

  it('returns a definitive validation error promptly and never retries the mutation', async () => {
    const error = Object.assign(new Error('Doppelte Schicht'), { status: 400 });
    const write = vi.fn().mockRejectedValue(error);
    const verify = vi.fn().mockResolvedValue(undefined);
    await expect(confirmShiftWrite(write, verify)).rejects.toBe(error);
    expect(write).toHaveBeenCalledTimes(1);
    expect(verify).not.toHaveBeenCalled();
  });

  it('blocks uncertain re-submission after a bounded readback deadline', async () => {
    vi.useFakeTimers();
    const write = vi.fn().mockImplementation(() => new Promise(() => {}));
    const verify = vi.fn().mockResolvedValue(undefined);
    const result = confirmShiftWrite(write, verify, { verifyDelayMs: 50, pollIntervalMs: 50, timeoutMs: 250 });
    const expectation = expect(result).rejects.toBeInstanceOf(ShiftWriteUnconfirmedError);
    await vi.advanceTimersByTimeAsync(260);
    await expectation;
    expect(write).toHaveBeenCalledTimes(1);
    expect(verify).toHaveBeenCalled();
  });
});
