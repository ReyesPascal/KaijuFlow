/**
 * What the Backend can do beyond the core prepare/probe/stream path. Callers
 * ask backendCapabilities() instead of assuming, so a capability is turned on
 * or off only in src/backends/.
 */

export interface BackendCapabilities {
  /** Can run Ultimate Fallback (play-time grab, parallel health checks, hand-off): the Play-time check's engine. On for AltMount since #190. */
  readonly ultimateFallback: boolean;
}

export const ALTMOUNT_CAPABILITIES: BackendCapabilities = { ultimateFallback: true };

/** Capabilities of the Backend (AltMount, the only one). */
export function backendCapabilities(): BackendCapabilities {
  return ALTMOUNT_CAPABILITIES;
}
