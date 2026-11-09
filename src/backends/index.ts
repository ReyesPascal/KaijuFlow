/**
 * The active Backend. NzbDAV is the only Backend for now (spec #16 step 1);
 * the Backend setting that chooses between Backends comes with AltMount.
 */

import { buildNzbdavConfig } from '../nzbdav/utils.js';
import type { NZBDavConfig } from '../nzbdav/types.js';
import { createNzbdavBackend } from './nzbdav.js';
import type { Backend } from './types.js';

export type { Backend, BackendId, BackendSource, BackendStatus, MediaRequest, PrepareOptions, PreparedVideo } from './types.js';
export { PrepareCancelledError, isSourceFailure } from './types.js';

/**
 * The Backend KaijuFlow streams through. `nzbdavConfig` lets callers that
 * already resolved NzbDAV settings for this request reuse them; by default
 * they come from the saved config.
 */
export function getActiveBackend(nzbdavConfig: NZBDavConfig = buildNzbdavConfig()): Backend {
  return createNzbdavBackend(nzbdavConfig);
}
