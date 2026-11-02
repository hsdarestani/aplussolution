/**
 * A mobile write may commit on the server while its response is delayed/lost.
 * Read back persisted state before declaring success; never retry a POST/PATCH
 * automatically (a second attempt could create a duplicate shift).
 */
export async function confirmShiftWrite<T>(
  write: (signal: AbortSignal) => Promise<T>,
  verify: (signal: AbortSignal) => Promise<T | undefined>,
  options: { verifyDelayMs?: number; pollIntervalMs?: number; timeoutMs?: number } = {},
): Promise<T> {
  const controller = new AbortController();
  const verifyDelayMs = options.verifyDelayMs ?? 1800;
  const pollIntervalMs = options.pollIntervalMs ?? 1400;
  const timeoutMs = options.timeoutMs ?? 20000;
  let timeoutId: ReturnType<typeof setTimeout> | undefined;

  const delay = (duration: number) => new Promise<void>((resolve) => setTimeout(resolve, duration));
  const readback = async (): Promise<T> => {
    await delay(verifyDelayMs);
    while (!controller.signal.aborted) {
      try {
        const result = await verify(controller.signal);
        if (result !== undefined) return result;
      } catch {
        // A transient GET failure does not imply the write failed.
      }
      if (!controller.signal.aborted) await delay(pollIntervalMs);
    }
    // The winning write/timeout has already completed; this promise can stay
    // pending without affecting the caller.
    return new Promise<T>(() => {});
  };

  try {
    return await Promise.race([
      write(controller.signal),
      readback(),
      new Promise<T>((_, reject) => {
        timeoutId = setTimeout(
          () => reject(new Error('Speichern noch nicht bestätigt. Bitte Dienstplan prüfen, bevor du erneut sicherst.')),
          timeoutMs,
        );
      }),
    ]);
  } finally {
    if (timeoutId !== undefined) clearTimeout(timeoutId);
    controller.abort();
  }
}
