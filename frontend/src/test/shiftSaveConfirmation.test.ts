import { describe, expect, it } from 'vitest';
import { confirmShiftWrite } from '../shiftSaveConfirmation';

describe('mobile shift save confirmation', () => {
  it('returns the normal write response without requiring a second write', async () => {
    let writes = 0;
    let reads = 0;
    const result = await confirmShiftWrite(
      async () => { writes += 1; return { id: 'created-shift' }; },
      async () => { reads += 1; return undefined; },
      { verifyDelayMs: 30, timeoutMs: 100 },
    );
    expect(result.id).toBe('created-shift');
    expect(writes).toBe(1);
    expect(reads).toBe(0);
  });

  it('closes a hanging write only after a fresh readback confirms it', async () => {
    let writes = 0;
    let reads = 0;
    let writeSignal: AbortSignal | undefined;
    const result = await confirmShiftWrite(
      async (signal) => {
        writes += 1;
        writeSignal = signal;
        return new Promise<{ id: string }>(() => {});
      },
      async () => {
        reads += 1;
        return reads >= 2 ? { id: 'committed-shift' } : undefined;
      },
      { verifyDelayMs: 1, pollIntervalMs: 1, timeoutMs: 100 },
    );
    expect(result.id).toBe('committed-shift');
    expect(writes).toBe(1);
    expect(reads).toBeGreaterThanOrEqual(2);
    expect(writeSignal?.aborted).toBe(true);
  });

  it('does not retry an unconfirmed mutation or claim success', async () => {
    let writes = 0;
    await expect(confirmShiftWrite(
      async () => {
        writes += 1;
        return new Promise<{ id: string }>(() => {});
      },
      async () => undefined,
      { verifyDelayMs: 1, pollIntervalMs: 1, timeoutMs: 12 },
    )).rejects.toThrow('Speichern noch nicht bestätigt');
    expect(writes).toBe(1);
  });

  it('propagates a real API error instead of treating it as success', async () => {
    await expect(confirmShiftWrite(
      async () => { throw new Error('Keine Berechtigung'); },
      async () => undefined,
      { verifyDelayMs: 1, timeoutMs: 50 },
    )).rejects.toThrow('Keine Berechtigung');
  });
});
