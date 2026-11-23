/**
 * Stream handling types shared by the stream handler, the caches and Ultimate
 * Fallback.
 */

import type { PlayContext } from './playContext.js';

export interface StreamData {
  nzoId: string;
  videoPath: string;
  videoSize: number;
  /** Files the Backend said it holds for this Source (names or paths), for the first-byte log line. */
  offered?: string[];
  /** Release name of the Source, set on Best's session so a press can name what it plays (#206). */
  sourceTitle?: string;
}

export interface FallbackCandidate {
  nzbUrl: string;
  title: string;
  indexerName: string;
  size?: number;
  isSeasonPack?: boolean;
  /** Proxy exit IP captured at search time. verifyProxyCircuit compares against
   *  this when grabbing the NZB, so a rotation+new-search between search and
   *  grab cannot silently pass verification. Persisted with the group (it's a
   *  hash, never the raw IP) so post-restart grabs still verify against the
   *  search-time IP. */
  searchExitIp?: string;
}

export interface FallbackGroup {
  candidates: FallbackCandidate[];
  /** What a play of this list is for, made once when the list was built (#246). */
  context: PlayContext;
  createdAt: number;
}
