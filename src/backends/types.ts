/**
 * Backend slot (spec #16, ADR 0001).
 *
 * A Backend turns one chosen Source into a Stream KaijuFlow can serve. Every
 * caller (stream handling, Ultimate Fallback, auto-queue, dashboard status)
 * talks to the Backend through this interface and never calls a Backend's own
 * code directly. AltMount is KaijuFlow's only Backend (#188).
 */

import type { StreamData } from '../play/types.js';
import type { BackendCapabilities } from './capabilities.js';

export type BackendId = 'altmount';

/** The id of the one Backend; ready entries are tagged with it. */
export const BACKEND_ID: BackendId = 'altmount';

/** A prepared video: the Backend's media reference, its size and job id. */
export type PreparedVideo = StreamData;

/** One Source handed to the Backend. */
export interface BackendSource {
  nzbUrl: string;
  title: string;
  contentType?: string;
  /** Regex selecting the episode file (TV), if any. */
  episodePattern?: string;
  episodesInSeason?: number;
  isSeasonPack?: boolean;
  indexerName?: string;
  /** Proxy exit IP hash from search time, checked when grabbing the NZB. */
  searchExitIp?: string;
}

export interface PrepareOptions {
  logPrefix?: string;
  /** How long to wait for the Backend job, in ms. 0 = no limit. */
  timeoutMs?: number;
  pollIntervalMs?: number;
  /** Called as soon as the Backend accepts the Source, with its job id. */
  onJob?: (jobId: string) => void;
  /** Checked between steps; when it returns true, prepare stops with PrepareCancelledError. */
  isCancelled?: () => boolean;
}

/** Options for probe. `title` and `source` only label the first-byte step line (#61). */
export interface ProbeOptions {
  logPrefix?: string;
  title?: string;
  source?: string;
}

/** A fetchable media URL plus the request headers it needs (server side only). */
export interface MediaRequest {
  url: URL;
  headers: Record<string, string>;
}

/** Result of a reachability/config check, for the dashboard and "test connection". */
export interface BackendStatus {
  ok: boolean;
  /** HTTP status the route should answer with (200 when ok). */
  httpStatus: number;
  message: string;
  testPath?: string;
}

export interface Backend {
  readonly id: BackendId;
  readonly label: string;
  /** What this Backend supports beyond prepare/probe/stream (Ultimate Fallback). */
  readonly capabilities: BackendCapabilities;

  /** Already prepared: existing prepared media for this Source, or null. Never prepares. */
  findPrepared(source: BackendSource, opts?: { logPrefix?: string; quiet?: boolean }): Promise<PreparedVideo | null>;

  /** Cheap check that a remembered prepared video still exists on the Backend. */
  stillPrepared(mediaPath: string): Promise<boolean>;

  /**
   * Prepare: hand the Source to the Backend and wait until its video is found.
   * Does not probe. Throws a Source failure (see isSourceFailure) when the
   * Source is bad, or another error when the Backend is unreachable/misconfigured.
   */
  prepare(source: BackendSource, opts?: PrepareOptions): Promise<PreparedVideo>;

  /** Probe: confirm the first byte is servable. Throws a Source failure for 404/410, 5xx and timeouts; a 400 or a refused/dropped connection is a plain error (ADR 0004). */
  probe(video: PreparedVideo, opts?: ProbeOptions): Promise<void>;

  /** Cancel: best effort only. Never proof that the Backend's work stopped. */
  cancel(jobId: string, reason?: string): Promise<void>;

  /** Where to fetch a prepared video from, with the headers it needs. */
  mediaRequest(mediaPath: string): MediaRequest;

  /** URL handed to the player in direct (redirect) mode. May carry Backend credentials. */
  directUrl(mediaPath: string): string;

  /** Reachability/config check. `settings` are unsaved values from the UI form; defaults to the saved ones. */
  status(settings?: Record<string, unknown>): Promise<BackendStatus>;
}

/** Prepare stopped because the caller cancelled it (not a Source failure). */
export class PrepareCancelledError extends Error {
  constructor() {
    super('Prepare cancelled');
    this.name = 'PrepareCancelledError';
  }
}

/**
 * Build the error a Backend throws when the Source itself is bad (isSourceFailure
 * is true for it). The flag keeps its historical name `isBadSource`: saved dead marks carry it.
 */
export function sourceFailure(message: string, isTimeout = false, isEpisodeSpecific = false): Error & { isBadSource: boolean; isTimeout: boolean; isEpisodeSpecific: boolean } {
  const err = new Error(message) as Error & { isBadSource: boolean; isTimeout: boolean; isEpisodeSpecific: boolean };
  err.isBadSource = true;
  err.isTimeout = isTimeout;
  err.isEpisodeSpecific = isEpisodeSpecific;
  return err;
}

/**
 * True when the error says the Source itself is bad (mark it dead), as opposed
 * to the Backend being unreachable or misconfigured (don't mark it dead).
 */
export function isSourceFailure(err: unknown): boolean {
  return (err as { isBadSource?: boolean } | null)?.isBadSource === true;
}
