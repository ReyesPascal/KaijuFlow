/**
 * Step timing (spec #58, ticket #61).
 *
 * One structured log line per step, in one format a tool can parse from
 * `docker logs`: the tag `[KF-STEP] ` followed by a single-line JSON object.
 * Fields: step, source, ms, ok, t (end time, ISO), then ref / title / extras.
 * Lines never carry URLs or keys: callers pass names and numbers only.
 * Format reference: the "Step lines" section of tools/brain/README.md.
 */
import { AsyncLocalStorage } from 'node:async_hooks';

export const STEP_LOG_TAG = '[KF-STEP]';

export const STEP_NAMES = [
  'indexer_page', 'play_check', 'nzb_fetch', 'unscramble', 'upload', 'import_wait', 'first_byte', 'played', 'play_failed',
  // The stream list's own steps (#249): the whole request (`list`, with the process trace), then its parts.
  'list', 'list_filter', 'list_sort', 'list_build', 'fallback_group', 'head_start',
] as const;
export type StepName = (typeof STEP_NAMES)[number];

export interface StepFields {
  step: StepName;
  /** Source or indexer name; omit when the step has none. */
  source?: string;
  ok?: boolean;
  /** Title the step worked for, when known. */
  title?: string;
  [extra: string]: unknown;
}

const refStore = new AsyncLocalStorage<string>();

/** Run `fn` with a request reference (the Stremio id) added to every step line inside it. */
export function withStepRef<T>(ref: string, fn: () => T): T {
  return refStore.run(ref, fn);
}

/** Write one step line. */
export function logStep(fields: StepFields & { ms: number }): void {
  const { step, source, ms, ok = true, title, ...extra } = fields;
  const ref = refStore.getStore();
  const rec: Record<string, unknown> = { step, source, ms: Math.round(ms), ok, t: new Date().toISOString(), ref, title, ...extra };
  console.log(`${STEP_LOG_TAG} ${JSON.stringify(rec)}`);
}

/** Run `fn`, then log one line with the elapsed time (ok=false when it throws). Never changes the result. */
export async function timeStep<T>(fields: StepFields, fn: () => Promise<T>, after?: (result: T) => Partial<StepFields>): Promise<T> {
  const t0 = Date.now();
  let result: T;
  try {
    result = await fn();
  } catch (err) {
    logStep({ ...fields, ok: false, ms: Date.now() - t0 });
    throw err;
  }
  logStep({ ...fields, ...(after?.(result) ?? {}), ms: Date.now() - t0 });
  return result;
}

/** Run a synchronous `fn`, then log one line with the elapsed time (ok=false when it throws). Never changes the result. */
export function timeStepSync<T>(fields: StepFields, fn: () => T, after?: (result: T) => Partial<StepFields>): T {
  const t0 = performance.now();
  let result: T;
  try {
    result = fn();
  } catch (err) {
    logStep({ ...fields, ok: false, ms: performance.now() - t0 });
    throw err;
  }
  logStep({ ...fields, ...(after?.(result) ?? {}), ms: performance.now() - t0 });
  return result;
}

/**
 * A play's two events (#242), lines with `ms` 0: `played`, a Source's video is served to the player now; `play_failed`,
 * a Source failed for the play, with KaijuFlow's reason. The brain tools learn a visit's top pick and why it failed
 * only from these lines (brainreport.read_play), so the console lines beside them can be reworded freely.
 */
export function logPlayed(title: string, source: string | undefined): void {
  logStep({ step: 'played', source: source || undefined, title, ms: 0 });
}

export function logPlayFailed(title: string, source: string | undefined, err: unknown): void {
  logStep({ step: 'play_failed', source: source || undefined, title, ms: 0, ok: false, reason: stepReason(err) });
}

/** An error's message as a step line may carry it: one line, no address (`<url>`), no file path after a colon. */
export function stepReason(err: unknown): string {
  const message = err instanceof Error ? err.message : String(err);
  return (message.split('\n')[0] ?? '')
    .replace(/\b[a-z][a-z0-9+.-]*:\/\/\S+/gi, '<url>')
    .replace(/:\s*\/\S.*$/, '')
    .trim()
    .slice(0, 200);
}

/** Time one page request to an indexer (`source` = indexer name, `page` 1 = first page). Never changes the result. */
export function timeIndexerPage<T>(source: string, page: number, fn: () => Promise<T>): Promise<T> {
  return timeStep({ step: 'indexer_page', source, page }, fn);
}

/** Parse one log line (docker prefixes allowed); null when it is not a step line. */
export function parseStepLine(line: string): (Record<string, any> & { step: string; ms: number }) | null {
  const i = line.indexOf(`${STEP_LOG_TAG} `);
  if (i < 0) return null;
  try {
    return JSON.parse(line.slice(i + STEP_LOG_TAG.length + 1));
  } catch {
    return null;
  }
}
