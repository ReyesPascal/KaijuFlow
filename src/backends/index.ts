/** The active Backend, chosen by the Backend setting (spec #16). */

import { config as globalConfig } from '../config/index.js';
import { buildAltmountSettings, createAltmountBackend } from './altmount.js';

import { buildNzbdavConfig } from '../nzbdav/utils.js';
import type { NZBDavConfig } from '../nzbdav/types.js';
import { createNzbdavBackend } from './nzbdav.js';
import type { Backend, BackendId } from './types.js';

export type { Backend, BackendId, BackendSource, BackendStatus, MediaRequest, PrepareOptions, PreparedVideo } from './types.js';
export { PrepareCancelledError, isSourceFailure } from './types.js';

/**
 * The Backend KaijuFlow streams through. `nzbdavConfig` lets callers that
 * already resolved NzbDAV settings for this request reuse them; by default
 * they come from the saved config. `id` overrides the Backend setting (the
 * "test connection" check for a Backend that is not active yet).
 */
export function getActiveBackend(nzbdavConfig?: NZBDavConfig, id: BackendId = globalConfig.backend): Backend {
  if (id === 'altmount') return createAltmountBackend(buildAltmountSettings());
  return createNzbdavBackend(nzbdavConfig ?? buildNzbdavConfig());
}
