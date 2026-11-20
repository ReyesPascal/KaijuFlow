/**
 * Unscramble (ADR 0005, spec #42).
 *
 * A Scrambled RAR set is a RAR set whose parts are named only by numbers
 * (`<name>.NN` / `<name>.NNN`) in an order that need not match the real
 * volume order. Some Backends (AltMount v0.4.0) read the name numbers as
 * volume numbers and reject a complete Source. Unscramble reads the real RAR5
 * volume number from the first article of each part, using the health-check
 * providers under the health-check connection cap, and renames the parts to
 * `<name>.partNN.rar` in that order.
 *
 * Only file names inside NZB subjects change: the rest of the NZB text
 * (segments, article ids, sizes, other files, <head>) is kept byte for byte.
 * Unscramble never throws for a Source: anything it can't finish returns the
 * original NZB with a reason, and the Backend decides (ADR 0004).
 *
 * At most one Unscramble reads first articles at a time, process-wide, first
 * come first served (#119): auto-queue prepares several Sources at once, and
 * sharing the connection cap made each one slower than its time limit.
 */

import type * as net from 'net';
import type * as tls from 'tls';
import type { UsenetProvider } from '../types.js';
import { extractFilename } from '../health/fileClassifier.js';
import { NntpConnectionPool, DEFAULT_HEALTH_CHECK_CONNECTION_CAP } from '../health/nntpConnection.js';
import { downloadSegment } from './nntpSegmentDownloader.js';
import { readRar5VolumeNumber } from './rar5Parser.js';

/** Why the NZB came back unchanged. */
export type UnscrambleReason =
  | 'not-scrambled'     // no Scrambled RAR set in the NZB, from names alone (no reads made; a 7z set too, #193)
  | 'no-provider'       // no enabled health-check provider
  | 'missing-article'   // a part's first article is on no provider
  | 'read-error'        // a first article couldn't be read (connection errors on every provider)
  | 'not-rar5'          // a part isn't RAR5 (RAR4, a hash-named 7z/other split, encrypted headers)
  | 'duplicate-volume'  // two parts claim the same volume number
  | 'volume-gap'        // the real volume numbers don't cover 0..N-1
  | 'timeout';          // the time limit ran out first

export interface UnscrambleResult {
  /** NZB text to upload: Unscrambled when `changed`, else the original. */
  nzb: string;
  changed: boolean;
  /** Set when unchanged. */
  reason?: UnscrambleReason;
  /** Parts renamed when `changed`; else parts in number-named groups (0 when there is none). */
  parts: number;
  /** Time taken, in ms, the wait for the turn included. */
  ms: number;
  /** Part of `ms` spent waiting for the turn (0 when there was no wait). */
  waitMs: number;
}

export interface UnscrambleOptions {
  /** Most parallel reads (= connections). Default: the health-check connection cap default. */
  connections?: number;
  /**
   * Most time for the whole call, the wait for the turn included (the prepare
   * budget). No limit when unset. If it runs out while waiting, the original
   * comes back with reason `timeout` and nothing is read.
   */
  budgetMs?: number;
}

interface Part {
  /** Index range of the subject attribute value in the NZB text. */
  subjectStart: number;
  subjectEnd: number;
  /** Raw (XML-escaped) subject attribute value. */
  rawSubject: string;
  name: string;
  firstArticleId: string;
}

interface ScrambledSet {
  base: string;
  parts: Part[];
}

type ReadFailure = 'missing-article' | 'read-error' | 'not-rar5';

const NUMBER_NAMED = /^(.+)\.(\d{2,3})$/;
/** A 7z set's parts (`<name>.7z.001` ...): named as 7z, not by numbers alone, so never read (#193). */
const SEVEN_ZIP_BASE = /\.7z$/i;

/**
 * Unscramble the NZB's Scrambled RAR set(s). Waits for its turn first;
 * `timeLimitMs` counts from the start of the turn, capped by what is left of
 * `opts.budgetMs`. On timeout reads stop, connections close and the original
 * comes back.
 */
export async function unscrambleNzb(
  nzb: string,
  providers: UsenetProvider[],
  timeLimitMs: number,
  opts: UnscrambleOptions = {},
): Promise<UnscrambleResult> {
  const started = Date.now();
  let waitMs = 0;
  const done = (r: Omit<UnscrambleResult, 'ms' | 'waitMs'>): UnscrambleResult => ({ ...r, ms: Date.now() - started, waitMs });

  const sets = findScrambledSets(nzb);
  const parts = sets.reduce((n, s) => n + s.parts.length, 0);
  if (parts === 0) return done({ nzb, changed: false, reason: 'not-scrambled', parts });

  const ordered = [
    ...providers.filter(p => p.enabled && p.type === 'pool'),
    ...providers.filter(p => p.enabled && p.type !== 'pool'),
  ];
  if (ordered.length === 0) return done({ nzb, changed: false, reason: 'no-provider', parts });

  const asked = Date.now();
  const release = await takeTurn(opts.budgetMs === undefined ? undefined : opts.budgetMs - (asked - started));
  waitMs = Date.now() - asked;
  if (!release) return done({ nzb, changed: false, reason: 'timeout', parts });
  const limitMs = opts.budgetMs === undefined ? timeLimitMs : Math.min(timeLimitMs, opts.budgetMs - (Date.now() - started));
  const reader = new FirstArticleReader(ordered, opts.connections ?? DEFAULT_HEALTH_CHECK_CONNECTION_CAP);
  let timer: NodeJS.Timeout | undefined;
  const timedOut = new Promise<'timeout'>(resolve => { timer = setTimeout(() => resolve('timeout'), Math.max(0, limitMs)); });
  try {
    // Each number-named group is decided on its own: a non-RAR split next to
    // a Scrambled RAR set stays as it is, and the RAR set is still renamed.
    const renames = new Map<Part, string>();
    let firstReason: UnscrambleReason | undefined;
    for (const set of sets) {
      const outcome = await Promise.race([unscrambleSet(set, reader), timedOut]);
      if (outcome === 'timeout') return done({ nzb, changed: false, reason: 'timeout', parts });
      if (typeof outcome === 'string') firstReason ??= outcome;
      else for (const [part, name] of outcome) renames.set(part, name);
    }
    if (renames.size === 0) return done({ nzb, changed: false, reason: firstReason, parts });
    return done({ nzb: applyRenames(nzb, renames), changed: true, parts: renames.size });
  } finally {
    clearTimeout(timer);
    reader.stop();
    release();
  }
}

/** Unscrambles waiting for their turn, oldest first. */
const waiting: Array<() => void> = [];
let turnTaken = false;

/**
 * Wait for this Unscramble's turn to read first articles (one at a time,
 * process-wide, first come first served). Resolves with the function that ends
 * the turn, or null when `maxWaitMs` runs out first (no limit when unset).
 */
function takeTurn(maxWaitMs?: number): Promise<(() => void) | null> {
  let ended = false;
  const endTurn = () => {
    if (ended) return;
    ended = true;
    const next = waiting.shift();
    if (next) next(); else turnTaken = false;
  };
  if (!turnTaken) {
    turnTaken = true;
    return Promise.resolve(endTurn);
  }
  return new Promise(resolve => {
    let timer: NodeJS.Timeout | undefined;
    const start = () => { clearTimeout(timer); resolve(endTurn); };
    waiting.push(start);
    if (maxWaitMs !== undefined) {
      timer = setTimeout(() => {
        const at = waiting.indexOf(start);
        if (at >= 0) waiting.splice(at, 1);
        resolve(null);
      }, Math.max(0, maxWaitMs));
    }
  });
}

/**
 * New part names for one set, or why it stays as it is. Renamed only when
 * every part was read, every part is RAR5, and the volume numbers are unique
 * and cover 0..N-1.
 */
async function unscrambleSet(set: ScrambledSet, reader: FirstArticleReader): Promise<Map<Part, string> | UnscrambleReason> {
  const read = await reader.readAll(set.parts);
  if (typeof read === 'string') return read;
  const volumes = set.parts.map(p => read.get(p)!);
  if (new Set(volumes).size !== volumes.length) return 'duplicate-volume';
  if (volumes.some(v => v < 0 || v >= volumes.length)) return 'volume-gap';
  const width = Math.max(2, String(set.parts.length).length);
  return new Map(set.parts.map((p, i) => [p, `${set.base}.part${String(volumes[i] + 1).padStart(width, '0')}.rar`]));
}

/** Number-named files grouped by base name (a 7z set's parts left out); groups of at least two parts. */
function findScrambledSets(nzb: string): ScrambledSet[] {
  const groups = new Map<string, Part[]>();
  const fileRe = /<file\b[^>]*?\bsubject\s*=\s*"([^"]*)"[^>]*>([\s\S]*?)<\/file>/dg;
  for (const m of nzb.matchAll(fileRe)) {
    const rawSubject = m[1];
    const name = extractFilename(xmlUnescape(rawSubject)).trim();
    const numbered = NUMBER_NAMED.exec(name);
    if (!numbered || SEVEN_ZIP_BASE.test(numbered[1])) continue;
    const first = firstSegment(m[2]);
    if (!first) continue;
    const [subjectStart, subjectEnd] = m.indices![1];
    const part: Part = { subjectStart, subjectEnd, rawSubject, name, firstArticleId: first };
    const list = groups.get(numbered[1]) ?? [];
    list.push(part);
    groups.set(numbered[1], list);
  }
  return [...groups].filter(([, list]) => list.length >= 2).map(([base, list]) => ({ base, parts: list }));
}

/** Message id of the lowest-numbered segment in a <file> body. */
function firstSegment(fileBody: string): string | null {
  let best: { n: number; id: string } | null = null;
  for (const s of fileBody.matchAll(/<segment\b([^>]*)>([^<]*)<\/segment>/g)) {
    const n = parseInt(/\bnumber\s*=\s*"(\d+)"/.exec(s[1])?.[1] ?? '', 10);
    const id = xmlUnescape(s[2].trim()).replace(/^<|>$/g, '');
    if (!id || !Number.isFinite(n)) continue;
    if (!best || n < best.n) best = { n, id };
  }
  return best?.id ?? null;
}

/** Swap each part's file name inside its subject; nothing else in the text moves. */
function applyRenames(nzb: string, renames: Map<Part, string>): string {
  const edits = [...renames].sort(([a], [b]) => b.subjectStart - a.subjectStart);
  let out = nzb;
  for (const [part, newName] of edits) {
    const oldEscaped = xmlEscape(part.name);
    const at = part.rawSubject.indexOf(oldEscaped);
    const subject = at >= 0
      ? part.rawSubject.slice(0, at) + xmlEscape(newName) + part.rawSubject.slice(at + oldEscaped.length)
      : xmlEscape(xmlUnescape(part.rawSubject).replace(part.name, newName));
    out = out.slice(0, part.subjectStart) + subject + out.slice(part.subjectEnd);
  }
  return out;
}

function xmlUnescape(s: string): string {
  return s.replace(/&(#x[0-9a-f]+|#\d+|amp|lt|gt|quot|apos);/gi, (_, e: string) => {
    const k = e.toLowerCase();
    if (k === 'amp') return '&';
    if (k === 'lt') return '<';
    if (k === 'gt') return '>';
    if (k === 'quot') return '"';
    if (k === 'apos') return "'";
    return String.fromCodePoint(k.startsWith('#x') ? parseInt(k.slice(2), 16) : parseInt(k.slice(1), 10));
  });
}

function xmlEscape(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

/**
 * Reads first articles in parallel (at most `connections` at once), trying
 * providers in order for each part. Every connection goes through the
 * health-check connection cap. `stop()` ends all reads and closes sockets.
 */
class FirstArticleReader {
  private pool = new NntpConnectionPool();
  private inFlight = new Set<net.Socket | tls.TLSSocket>();
  private stopped = false;

  constructor(private providers: UsenetProvider[], private connections: number) {}

  /** Volume per part, or the first reason a part couldn't be read. */
  async readAll(parts: Part[]): Promise<Map<Part, number> | ReadFailure> {
    const result = new Map<Part, number>();
    let failure: ReadFailure | null = null;
    let next = 0;
    const worker = async () => {
      while (!this.stopped && failure === null && next < parts.length) {
        const part = parts[next++];
        const outcome = await this.readVolume(part.firstArticleId);
        if (typeof outcome === 'number') result.set(part, outcome);
        else failure ??= outcome;
      }
    };
    const workers = Math.max(1, Math.min(parts.length, Math.floor(this.connections) || 1));
    await Promise.all(Array.from({ length: workers }, worker));
    return failure ?? result;
  }

  private async readVolume(messageId: string): Promise<number | ReadFailure> {
    let sawMissing = false;
    for (const provider of this.providers) {
      if (this.stopped) return 'read-error';
      let socket: net.Socket | tls.TLSSocket | undefined;
      try {
        socket = await this.pool.acquire(provider);
        if (this.stopped) { socket.destroy(); return 'read-error'; }
        this.inFlight.add(socket);
        const data = await downloadSegment(socket, messageId);
        this.inFlight.delete(socket);
        this.pool.release(provider, socket);
        const volume = readRar5VolumeNumber(data);
        return volume === null ? 'not-rar5' : volume;
      } catch (err) {
        if (socket) {
          this.inFlight.delete(socket);
          if (/Article not found/.test((err as Error).message)) {
            sawMissing = true;
            this.pool.release(provider, socket);
          } else {
            socket.destroy();
          }
        }
      }
    }
    return sawMissing ? 'missing-article' : 'read-error';
  }

  stop(): void {
    this.stopped = true;
    for (const s of this.inFlight) s.destroy();
    this.inFlight.clear();
    this.pool.destroyAll();
  }
}
