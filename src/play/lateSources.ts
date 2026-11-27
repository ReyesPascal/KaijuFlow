/**
 * Late Sources (#301): what a slower indexer's answer adds once the list went out without it. One way of taking them,
 * for the list's fallback group (fallbackManager.addToFallbackGroup) and for Best's Walk under way (ultimateFallback).
 */

import type { FallbackCandidate } from './types.js';

/** Same Source of a list: its NZB link and release name (as the list's entries find their candidate). */
const candidateKey = (c: FallbackCandidate): string => `${c.nzbUrl}\u0000${c.title}`;

/**
 * The late candidates `held` does not hold yet (same NZB link and release name), in their order. One it holds takes
 * the late one's fields but its Search Flow mark (`flow`, `flowWhy`, `proof`), so a late copy of a Release joins its
 * Sources (`sources`, #300) and the list's entry keeps its place and mark.
 */
export function mergeLate(held: readonly FallbackCandidate[], late: readonly FallbackCandidate[]): FallbackCandidate[] {
  const byKey = new Map(held.map(c => [candidateKey(c), c]));
  const fresh: FallbackCandidate[] = [];
  for (const c of late) {
    const mine = byKey.get(candidateKey(c));
    if (!mine) { fresh.push(c); continue; }
    const { flow: _flow, flowWhy: _why, proof: _proof, ...fields } = c;
    Object.assign(mine, fields);
  }
  return fresh;
}

/** Move the entries of a map keyed by list place along by `count` from place `at` on (late Sources put in at `at`). */
export function shiftPlaces<V>(byPlace: Map<number, V>, at: number, count: number): void {
  const moved = [...byPlace].map(([index, v]): [number, V] => [index >= at ? index + count : index, v]);
  byPlace.clear();
  for (const [index, v] of moved) byPlace.set(index, v);
}
