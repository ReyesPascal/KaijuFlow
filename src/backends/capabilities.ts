/**
 * What the Backend can do beyond the core prepare/probe/stream path. Callers
 * ask backendCapabilities() instead of assuming, so turning a capability on
 * (Ultimate Fallback for AltMount, #190) touches only src/backends/.
 */

export interface BackendCapabilities {
  /** Can run Ultimate Fallback (play-time grab, parallel health checks, hand-off). Off until #190. */
  readonly ultimateFallback: boolean;
}

export const ALTMOUNT_CAPABILITIES: BackendCapabilities = { ultimateFallback: false };

/** Capabilities of the Backend (AltMount, the only one). */
export function backendCapabilities(): BackendCapabilities {
  return ALTMOUNT_CAPABILITIES;
}
