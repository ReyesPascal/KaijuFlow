/**
 * Best's Walk (GLOSSARY: Walk): one play's progress down a list, grabbing and checking Sources a few at a time from
 * the top until one is healthy, the list runs out, or the Walk stops. Pure: it takes events (a grab done or failed, a
 * check's verdict, a prepare done or failed, a stop) and returns decisions (grab, check, hand to the Backend, cancel,
 * settle, keep a library hit beside the played Source, mark dead). The adapter in ultimateFallback.ts runs the
 * decisions against the NZB grab, the Play-time check and the Backend, and tells the Walk what they answered.
 *
 * Its rules, all here:
 * - At most `inFlight` Sources are walked at once (candidateCount); one that fails is replaced once, by the next
 *   Source of the list not remembered dead (#228: a failed grab used to be replaced twice).
 * - Only a Source the check found healthy is handed to the Backend, one at a time, the first in list order: a
 *   Source still grabbed or checked above it is waited for (#190). Only the Source being played is prepared (#192).
 * - A library hit (a Source the Backend already holds) plays without a grab, unless a Source above it is still
 *   grabbed or prepared; once one plays, the other library hits are kept beside it as backups.
 * - The limits on asking indexers are WalkLimits' (below), the same for a clicked list entry's walk-on (#255): a Walk
 *   makes at most WALK_MAX_GRABS grabs (30), then ends as if the list had run out, and says so once (#228); an indexer
 *   that refuses a grab (429, 5xx, 401/403, an error payload not 300, a network error, a timeout) is skipped for the
 *   rest of the Walk, said once: its other Sources are passed by unless a library hit, which needs no grab (ADR 0004).
 *   The grabs already under way when it refuses still reach it, so it is asked at most `inFlight` (candidateCount) times.
 * - Each Source of the list is a Release (#300; GLOSSARY: Release): one grab, one check, one dead mark, whichever of its
 *   indexers' NZBs the grab fetched (releaseGrab.ts). A Release is passed by for refusals only when every indexer that
 *   has it refused; one grab counts once against the 30, however many of its indexers it asked.
 * - Dead marks follow ADR 0004: a grab the indexer says is gone (404, other 4xx, error payload 300) or bad, a check that blocks a
 *   Source, or a prepare that fails for the Source's own reason, marks it dead; a refused grab, a check that cannot
 *   answer, or a Backend failure leaves it alive.
 */

/** About twice the deepest Walk measured (16 grabs, The Twilight Zone S02E06, #14 played), #228. */
export const WALK_MAX_GRABS = 30;

/**
 * The Walk's limits on asking indexers (ADR 0004, "The walk's grabs"; #228, #243), one set per Walk: Best's Walk keeps
 * one, and so does a clicked list entry's walk-on across the requests of its play (#255). Only a grab is limited: a
 * Source that needs none (a library hit, a Source remembered ready) is never held back by them.
 */
export class WalkLimits {
  private grabs = 0;
  private atCeiling = false;
  private readonly refusing = new Set<string>();

  /** Grabs the Walk made. */
  get grabCount(): number { return this.grabs; }

  /** The Walk made its WALK_MAX_GRABS grabs: it ends as if the list had run out. */
  get stopped(): boolean { return this.atCeiling; }

  /**
   * Count the grab the Walk is about to make. 'ceiling' when it already made WALK_MAX_GRABS, the first time (say it
   * once), 'stopped' every time after: no grab then.
   */
  grab(): 'grab' | 'ceiling' | 'stopped' {
    if (this.atCeiling) return 'stopped';
    if (this.grabs >= WALK_MAX_GRABS) { this.atCeiling = true; return 'ceiling'; }
    this.grabs++;
    return 'grab';
  }

  /** An indexer that refused a grab: its Sources are passed by for the rest of the Walk. */
  skips(indexer: string): boolean { return this.refusing.has(indexer); }

  /** The indexer refused a grab. True the first time (say it once). */
  refused(indexer: string): boolean {
    if (this.refusing.has(indexer)) return false;
    this.refusing.add(indexer);
    return true;
  }
}

export type WalkEvent =
  /** `refused`: the indexers that refused the grab before one of the Release's other Sources was fetched (#300). */
  | { type: 'grabbed'; index: number; refused?: readonly string[] }
  /** `badSource`: every indexer says the link is gone, or its NZB is bad (ADR 0004). `refused`: the indexers that refused. */
  | { type: 'grabFailed'; index: number; badSource: boolean; refused: readonly string[] }
  | { type: 'checked'; index: number; verdict: 'healthy' | 'blocked' | 'error'; episodeOnly?: boolean }
  | { type: 'prepared'; index: number; videoPath: string }
  | { type: 'prepareFailed'; index: number; badSource: boolean }
  | { type: 'stop' };

export type WalkEnd = 'ran-out' | 'ceiling' | 'stopped';

export type WalkDecision =
  | { type: 'grab'; index: number }
  | { type: 'check'; index: number }
  | { type: 'prepare'; index: number }
  | { type: 'cancel'; index: number }
  /** A library hit waits: a Source above it is still grabbed or prepared. */
  | { type: 'park'; index: number }
  /** The Source to play: prepared by the Backend, or a library hit. */
  | { type: 'settle'; index: number; via: 'prepare' | 'library' }
  /** No Source to play: the list ran out, the Walk hit its grabs, or it was stopped. */
  | { type: 'settleNone'; end: WalkEnd }
  /** An indexer refused a grab: its Sources are passed by for the rest of the Walk (logged once). */
  | { type: 'skipIndexer'; indexer: string }
  /** The Walk hit its grabs (logged once). */
  | { type: 'ceiling'; grabs: number }
  /** A library hit kept beside the played Source. */
  | { type: 'backup'; index: number }
  /** ADR 0004: a bad Source. `cause` says which mark: a gone grab, a blocked check (for this episode only, or the Source) or a prepare. */
  | { type: 'markDead'; index: number; cause: 'grab' | 'check' | 'check-episode' | 'prepare' };

export interface WalkOptions {
  /** Sources in the list, in list order. */
  size: number;
  /** Sources walked at once (candidateCount). */
  inFlight: number;
  /** A Source remembered dead: the Walk passes it by. Asked when the Walk reaches it. */
  isDead: (index: number) => boolean;
  /** The indexers a Release has a Source on (#300). */
  indexersOf: (index: number) => readonly string[];
  /** Library hits: list index -> the video path the Backend holds. */
  hits: ReadonlyMap<number, string>;
}

/** Where one Source of the Walk stands. */
export interface WalkMember {
  index: number;
  grab: 'none' | 'grabbing' | 'done' | 'failed';
  check: 'none' | 'checking' | 'healthy' | 'blocked' | 'error';
  prepare: 'idle' | 'preparing' | 'done' | 'failed' | 'cancelled';
  /** A library hit: waiting (parked), played, kept as a backup, or passed by (same video, other container). */
  library?: 'parked' | 'played' | 'backup' | 'duplicate' | 'mismatch';
}

const ext = (videoPath: string): string => {
  const base = videoPath.split('/').pop() ?? '';
  const dot = base.lastIndexOf('.');
  return dot > 0 ? base.slice(dot + 1).toUpperCase() : '';
};

export class Walk {
  private readonly members: WalkMember[] = [];
  private next = 0;
  private readonly limits = new WalkLimits();
  private played: number | null = null;
  private ended: WalkEnd | null = null;

  constructor(private readonly opts: WalkOptions) {}

  /** The first decisions: fill the Walk from the top of the list. */
  start(): WalkDecision[] {
    const out: WalkDecision[] = [];
    this.advance(out);
    return out;
  }

  on(event: WalkEvent): WalkDecision[] {
    const out: WalkDecision[] = [];
    if (this.ended === 'stopped') return out;
    if (event.type === 'stop') {
      for (const m of this.members) {
        if (m.prepare === 'preparing') { m.prepare = 'cancelled'; out.push({ type: 'cancel', index: m.index }); }
      }
      if (this.played === null && this.ended === null) out.push({ type: 'settleNone', end: 'stopped' });
      this.ended = 'stopped';
      return out;
    }
    const m = this.members.find(x => x.index === event.index);
    if (!m) return out;
    switch (event.type) {
      case 'grabbed':
        for (const indexer of event.refused ?? []) this.skipIndexer(indexer, out);
        m.grab = 'done';
        m.check = 'checking';
        out.push({ type: 'check', index: m.index });
        break;
      case 'grabFailed':
        m.grab = 'failed';
        for (const indexer of event.refused) this.skipIndexer(indexer, out);
        if (event.badSource) out.push({ type: 'markDead', index: m.index, cause: 'grab' });
        break;
      case 'checked':
        m.check = event.verdict;
        if (event.verdict === 'blocked') out.push({ type: 'markDead', index: m.index, cause: event.episodeOnly ? 'check-episode' : 'check' });
        break;
      case 'prepared':
        if (m.prepare !== 'preparing') break;
        m.prepare = 'done';
        this.settle(m, 'prepare', event.videoPath, out);
        break;
      case 'prepareFailed':
        if (m.prepare !== 'preparing') break;
        m.prepare = 'failed';
        if (event.badSource) out.push({ type: 'markDead', index: m.index, cause: 'prepare' });
        break;
    }
    this.advance(out);
    return out;
  }

  /** Nothing more will happen: the Walk settled or ended, and nothing it began is still under way. */
  get done(): boolean {
    if (this.ended === 'stopped') return true;
    if (this.played === null && this.ended === null) return false;
    return !this.members.some(m => m.grab === 'grabbing' || m.check === 'checking' || m.prepare === 'preparing');
  }

  /** Where each Source the Walk reached stands, in list order (for the summary). */
  snapshot(): readonly WalkMember[] { return this.members; }

  get grabCount(): number { return this.limits.grabCount; }

  /** An indexer that refused a grab in this Walk: the Release grab passes its Sources by (#300). */
  skips(indexer: string): boolean { return this.limits.skips(indexer); }

  /** Sources the Walk gave up on: no longer walked, and not because a stop cancelled their prepare (for the summary). */
  get failedCount(): number {
    return this.members.filter(m => this.finished(m) && m.prepare !== 'cancelled').length;
  }

  /** A member no longer walked: its grab failed, its check did not pass, or its prepare failed. */
  private finished(m: WalkMember): boolean {
    return m.grab === 'failed' || m.check === 'blocked' || m.check === 'error' || m.prepare === 'failed' || m.prepare === 'cancelled';
  }

  private settled(): boolean { return this.played !== null || this.ended !== null; }

  private advance(out: WalkDecision[]): void {
    if (this.settled()) return;
    this.unpark(out);
    if (this.settled()) return;
    // Replace what finished, once each: the Walk keeps `inFlight` Sources going.
    while (this.members.filter(m => !this.finished(m)).length < this.opts.inFlight && this.enter(out)) {
      if (this.settled()) return;
    }
    this.handOver(out);
    if (this.settled()) return;
    if (this.members.every(m => this.finished(m)) && !this.canEnter()) {
      this.ended = this.limits.stopped ? 'ceiling' : 'ran-out';
      out.push({ type: 'settleNone', end: this.ended });
    }
  }

  private canEnter(): boolean {
    if (this.limits.stopped) return false;
    let i = this.next;
    while (i < this.opts.size && this.passedBy(i)) i++;
    return i < this.opts.size;
  }

  /** A Release the Walk does not reach: remembered dead, or not a library hit and every indexer that has it refused. */
  private passedBy(index: number): boolean {
    if (this.opts.isDead(index)) return true;
    const indexers = this.opts.indexersOf(index);
    return !this.opts.hits.has(index) && indexers.length > 0 && indexers.every(i => this.limits.skips(i));
  }

  private skipIndexer(indexer: string, out: WalkDecision[]): void {
    if (this.limits.refused(indexer)) out.push({ type: 'skipIndexer', indexer });
  }

  /** Bring the next Source of the list into the Walk. False when none can come: the list ran out or the grabs did. */
  private enter(out: WalkDecision[]): boolean {
    if (this.limits.stopped) return false;
    while (this.next < this.opts.size && this.passedBy(this.next)) this.next++;
    if (this.next >= this.opts.size) return false;
    const index = this.next;
    if (!this.opts.hits.has(index) && this.limits.grab() !== 'grab') {
      out.push({ type: 'ceiling', grabs: this.limits.grabCount });
      return false;
    }
    this.next++;
    const m: WalkMember = { index, grab: 'none', check: 'none', prepare: 'idle' };
    this.members.push(m);
    if (this.opts.hits.has(index)) {
      m.library = 'parked';
      this.tryLibrary(m, out, true);
    } else {
      m.grab = 'grabbing';
      out.push({ type: 'grab', index });
    }
    return true;
  }

  /** List order: a library hit plays only once no Source above it is still grabbed or prepared. */
  private tryLibrary(m: WalkMember, out: WalkDecision[], entering: boolean): void {
    const blocked = this.members.some(x => x.index < m.index && (x.grab === 'grabbing' || x.prepare === 'preparing'));
    if (blocked) { if (entering) out.push({ type: 'park', index: m.index }); return; }
    this.settle(m, 'library', this.opts.hits.get(m.index)!, out);
  }

  private unpark(out: WalkDecision[]): void {
    for (const m of this.members) {
      if (m.library !== 'parked') continue;
      this.tryLibrary(m, out, false);
      if (this.settled()) return;
    }
  }

  /** Hand the Backend the first healthy Source in list order, when none is being prepared; wait on one still walked above it. */
  private handOver(out: WalkDecision[]): void {
    if (this.members.some(m => m.prepare === 'preparing')) return;
    for (const m of this.members) {
      if (this.finished(m)) continue;
      if (m.library === 'parked' || m.check !== 'healthy') return;
      if (m.prepare !== 'idle') continue;
      m.prepare = 'preparing';
      out.push({ type: 'prepare', index: m.index });
      return;
    }
  }

  /** The Source to play. The other library hits are kept beside it, unless they hold the same video or another container. */
  private settle(m: WalkMember, via: 'prepare' | 'library', videoPath: string, out: WalkDecision[]): void {
    this.played = m.index;
    if (via === 'library') m.library = 'played';
    out.push({ type: 'settle', index: m.index, via });
    const container = ext(videoPath);
    const held = new Set([videoPath]);
    for (const [index, path] of [...this.opts.hits].sort((a, b) => a[0] - b[0])) {
      if (index === m.index) continue;
      const member = this.members.find(x => x.index === index);
      const hitExt = ext(path);
      const verdict = held.has(path) ? 'duplicate' : container && hitExt && hitExt !== container ? 'mismatch' : 'backup';
      if (member?.library === 'parked') member.library = verdict;
      if (verdict !== 'backup') continue;
      held.add(path);
      out.push({ type: 'backup', index });
    }
  }
}
