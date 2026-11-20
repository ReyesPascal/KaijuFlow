/** The Backend KaijuFlow streams through: AltMount, the only one (#188). */

import { buildAltmountSettings, createAltmountBackend } from './altmount.js';
import type { Backend } from './types.js';

export type { Backend, BackendId, BackendSource, BackendStatus, MediaRequest, PrepareOptions, PreparedVideo } from './types.js';
export { PrepareCancelledError, isSourceFailure } from './types.js';

/** The Backend, built from the saved AltMount settings. */
export function getActiveBackend(): Backend {
  return createAltmountBackend(buildAltmountSettings());
}
