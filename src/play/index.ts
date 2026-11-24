/**
 * Play module: stream handling, caches and Ultimate Fallback.
 * Re-exports the public symbols of the stream handler, caches and Ultimate Fallback.
 */

// Types
export type { FallbackCandidate } from './types.js';

// Fallback management
export { createFallbackGroup, getFallbackGroup, clearFallbackGroups, fallbackGroupCount } from './fallbackManager.js';

// Source memory (ready and dead Sources, #247)
export { remember, recall } from './sourceMemory.js';

// Stream cache
export { getOrCreateStream, isStreamCached, evictReadyByVideoPath, clearTimeoutEntries } from './streamCache.js';

// Cache utilities
export { getCacheStats, clearStreamCache, clearReadyCache, forgetDeadSources, deleteCacheEntry, getCacheEntries, saveCacheToDisk } from './cacheUtils.js';

// Ultimate-Fallback (combined retry-on-failure + health checking pipeline)
export { headStart, listAsked, ultimateFallbackFromCandidates, cancelAllUltimateFallbacks, getSessionPromise, hasAnySessions, clearResolvedSessions } from './ultimateFallback.js';

// Shared utilities
export { isUltimateFallbackActive } from './utils.js';

// Stream handler (Express endpoint)
export { handleStream } from './streamHandler.js';
