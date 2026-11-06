/**
 * A shift can already be committed when a mobile connection loses its response.
 * Send exactly ONE mutation, accept the successful response immediately, and
 * independently read back persisted state when the response is delayed/lost.
 * Never mistake an ambiguous transport failure for an uncommitted write.
 */
export class ShiftWriteUnconfirmedError extends Error {
  constructor() {
    super('Speicherstatus noch unklar. Bitte Dienstplan prüfen und nicht erneut auf Sichern tippen.');
    this.name = 'ShiftWriteUnconfirmedError';
  }
}

function isDefinitiveWriteRejection(error: unknown): boolean {
  // HTTP 4xx is an explicit validation/permission response, except retryable
  // transient responses. 5xx and transport failures may follow a DB commit.
  const status = Number((error as { status?: number } | null)?.status);
  return status >= 400 && status < 500 && status !== 408 && status !== 429;
}

export async function confirmShiftWrite<T>(
  write: (signal: AbortSignal) => Promise<T>,
  verify: (signal: AbortSignal) => Promise<T | undefined>,
  options: { verifyDelayMs?: number; pollIntervalMs?: number; timeoutMs?: number } = {},
): Promise<T> {
  const controller = new AbortController();
  const verifyDelayMs = options.verifyDelayMs ?? 450;
  const pollIntervalMs = options.pollIntervalMs ?? 550;
  const timeoutMs = options.timeoutMs ?? 10000;
  let timeoutId: ReturnType<typeof setTimeout> | undefined;
  const delay = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

  // In the normal case, this wins as soon as the server returns its success.
  // Never submit the same mutation again from this helper.
  const oneWrite = Promise.resolve().then(() => write(controller.signal)).catch((error: unknown): Promise<T> => {
    if (isDefinitiveWriteRejection(error)) throw error;
    // Lost response / 5xx after commit? The readback can still prove success.
    // An unresolved promise lets readback or the hard deadline settle the race.
    return new Promise<T>(() => {});
  });

  const readback = async (): Promise<T> => {
    await delay(verifyDelayMs);
    while (!controller.signal.aborted) {
      try {
        const saved = await verify(controller.signal);
        if (saved !== undefined) return saved;
      } catch {
        // One failed GET does not prove the write failed.
      }
      if (!controller.signal.aborted) await delay(pollIntervalMs);
    }
    return new Promise<T>(() => {});
  };

  try {
    return await Promise.race([
      oneWrite,
      readback(),
      new Promise<T>((_, reject) => {
        timeoutId = setTimeout(() => reject(new ShiftWriteUnconfirmedError()), timeoutMs);
      }),
    ]);
  } finally {
    if (timeoutId !== undefined) clearTimeout(timeoutId);
    controller.abort();
  }
}
