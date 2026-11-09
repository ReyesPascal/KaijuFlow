/**
 * What each Backend can do beyond the core prepare/probe/stream path. Callers
 * ask the active Backend (via backendCapabilities) instead of checking which
 * Backend id is selected, so a new Backend only declares its own capabilities.
 */

import { config as globalConfig } from '../config/index.js';
import type { BackendId } from './types.js';

export interface BackendCapabilities {
  /** Keeps a browsable library of prepared media (Ultimate Library, library cleanup/delete screens). */
  readonly library: boolean;
  /** Can run Ultimate Fallback (relies on library-style jobs and cancel). */
  readonly ultimateFallback: boolean;
}

export const NZBDAV_CAPABILITIES: BackendCapabilities = { library: true, ultimateFallback: true };
export const ALTMOUNT_CAPABILITIES: BackendCapabilities = { library: false, ultimateFallback: false };

const BY_ID: Record<BackendId, BackendCapabilities> = {
  nzbdav: NZBDAV_CAPABILITIES,
  altmount: ALTMOUNT_CAPABILITIES,
};

/** Capabilities of the Backend selected by the Backend setting (or `id`). */
export function backendCapabilities(id: BackendId = globalConfig.backend): BackendCapabilities {
  return BY_ID[id];
}
