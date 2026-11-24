/**
 * Keep-alive (#248): the self-redirects that keep a player waiting within the time it allows.
 * One rule for the time left, whatever the entry played (a press of Best or a list entry):
 *
 * - A play's first request may wait up to Stremio's 60 s timeout, less 5 s to spare.
 * - A request that comes after a self-redirect may wait up to the ExoPlayer budget, 8 s: ExoPlayer on
 *   Android gives up on a request that blocks longer. Every wait gets at least 1 s.
 * - When the time is up the request answers with a self-redirect to its own route, its redirect count one
 *   up (inside the `t` envelope, so it survives iOS handoff); the work it waited for goes on and the next
 *   request picks it up.
 * - After MAX_SELF_REDIRECTS redirects a request waits without a limit (the cap only stops endless loops).
 */

import type { Request, Response as ExpressResponse } from 'express';
import { incrementRedirectCounter } from './redirectHelpers.js';

const STREMIO_TIMEOUT_MS = 60_000;       // Stremio's built-in HTTP timeout
const STREMIO_SAFETY_MARGIN_MS = 5_000;  // Answered this long before Stremio's timeout
const EXO_PLAYER_BUDGET_MS = 8_000;      // The most a request after a self-redirect blocks (keeps ExoPlayer alive on Android)
const MIN_WAIT_MS = 1_000;
const MAX_SELF_REDIRECTS = Number(process.env.PLAY_MAX_SELF_REDIRECTS) || 500; // Supports long Walks without an endless loop

/** What a wait came to: the work's value, or the time ran out first (`timeUp`: the time left, not the wait's own cap). */
export type Waited<T> = { done: true; value: T } | { done: false; timeUp: boolean };

export interface KeepAlive {
  /** Self-redirects made before this request. */
  readonly redirectCount: number;
  /** Whether this request may still answer with a self-redirect. */
  canRedirect(): boolean;
  /** Whether this request's time is up: it should redirect before it starts more work. */
  timeUp(): boolean;
  /** Wait for work until the time left (no limit once no redirect remains), or `atMostMs` when that is sooner. */
  wait<T>(work: Promise<T>, atMostMs?: number): Promise<Waited<T>>;
  /** Answer with a self-redirect to this request's route, resuming at candidate `ci` when given. */
  redirect(res: ExpressResponse, ci?: number): void;
}

/** The keep-alive of one play request, which started at `startedAt` after `redirectCount` self-redirects. */
export function keepAlive(req: Request, redirectCount: number, startedAt = Date.now()): KeepAlive {
  const windowMs = redirectCount > 0 ? EXO_PLAYER_BUDGET_MS : STREMIO_TIMEOUT_MS - STREMIO_SAFETY_MARGIN_MS;
  const elapsed = () => Date.now() - startedAt;
  const canRedirect = () => redirectCount < MAX_SELF_REDIRECTS;
  return {
    redirectCount,
    canRedirect,
    timeUp: () => canRedirect() && elapsed() >= windowMs,
    async wait<T>(work: Promise<T>, atMostMs?: number): Promise<Waited<T>> {
      const leftMs = canRedirect() ? Math.max(MIN_WAIT_MS, windowMs - elapsed()) : Infinity;
      const limitMs = Math.min(leftMs, atMostMs ?? Infinity);
      if (limitMs === Infinity) return { done: true, value: await work };
      let timer: ReturnType<typeof setTimeout> | undefined;
      const ranOut = new Promise<Waited<T>>(resolve => {
        timer = setTimeout(() => resolve({ done: false, timeUp: limitMs === leftMs }), limitMs);
      });
      try {
        return await Promise.race([work.then(value => ({ done: true as const, value })), ranOut]);
      } finally {
        clearTimeout(timer);
      }
    },
    redirect(res, ci) {
      const at = ci !== undefined ? `, resuming at candidate ${ci + 1}` : '';
      console.log(`⏰ Self-redirect to keep the player waiting (${Math.round(elapsed() / 1000)}s elapsed, redirect ${redirectCount + 1}/${MAX_SELF_REDIRECTS}${at})`);
      res.redirect(302, incrementRedirectCounter(req, ci).href);
    },
  };
}
