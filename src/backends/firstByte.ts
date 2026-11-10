/**
 * First-byte rule shared by every Backend (spec #77 part D, ADR 0004).
 *
 * The probe asks the Backend for the first byte of the prepared video.
 *  - 404 / 410: the file is gone, a bad Source (marked dead, as before).
 *  - 400, refused connection, dropped connection: says nothing about the
 *    Source. Failure video, Source stays alive.
 *  - 5xx and timeouts: today's handling, unchanged (bad Source after the retries).
 */

/** What a single first-byte answer means. */
export type FirstByteKind = 'gone' | 'keep-source' | 'other';

export function kindOfStatus(status: number): FirstByteKind {
  if (status === 404 || status === 410) return 'gone';
  if (status === 400) return 'keep-source';
  return 'other';
}

/** A refused or dropped connection (not a timeout: a timeout keeps today's handling). */
export function kindOfFetchError(err: unknown): FirstByteKind {
  const name = (err as { name?: string } | null)?.name;
  if (name === 'TimeoutError' || name === 'AbortError') return 'other';
  return 'keep-source';
}

/** The plain error thrown when the first byte failed but the Source is fine (not a Source failure). */
export function firstByteKeptError(videoPath: string, what: string): Error {
  return new Error(`First byte failed (${what}); the Source is kept: ${videoPath}`);
}

/** Last path part, so the log names files and never carries an address or key. */
const nameOf = (p: string) => p.replace(/\/+$/, '').split('/').pop() || p;

/** The one log line for a failed first byte: status, path asked for, names of the files offered. */
export function firstByteFailureLine(logPrefix: string, what: string, askedPath: string, offered: string[]): string {
  const names = offered.length ? offered.map(nameOf).join(', ') : 'none';
  return `${logPrefix}  ⚠️ First byte failed: ${what}; asked for ${askedPath}; Backend offered: ${names}`;
}

/** Log the line once. Looking up what the Backend offered is best effort and never throws. */
export async function logFirstByteFailure(
  logPrefix: string, what: string, askedPath: string, offered: () => Promise<string[]> | string[],
): Promise<void> {
  let names: string[] = [];
  try { names = await offered(); } catch { /* the line still goes out */ }
  console.warn(firstByteFailureLine(logPrefix, what, askedPath, names));
}
