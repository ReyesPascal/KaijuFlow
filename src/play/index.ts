/**
 * Play module: stream handling, caches and Ultimate Fallback.
 * Re-exports the public symbols of the stream handler, caches and Ultimate Fallback.
 */

// Types
export type { FallbackCandidate } from './types.js';

// Fallback management
export { createFallbackGroup, getFallbackGroup, clearFallbackGroups } from './fallbackManager.js';

// Stream cache
export { getOrCreateStream, getCacheKey, getDeadCacheKey, isStreamCached, isDeadNzbByUrl, addDeadNzbByUrl, evictReadyByVideoPath, clearTimeoutEntries, setReadyCacheEntry, setDeadNzbEntry } from './streamCache.js';

// Cache utilities
export { getCacheStats, clearStreamCache, clearReadyCache, clearFailedCache, deleteCacheEntry, getCacheEntries, saveCacheToDisk } from './cacheUtils.js';

// Ultimate-Fallback (combined retry-on-failure + health checking pipeline)
export { headStart, ultimateFallbackFromCandidates, cancelAllUltimateFallbacks, getSessionPromise, hasAnySessions, clearResolvedSessions } from './ultimateFallback.js';

// Shared utilities
export { buildEpisodePattern, buildDateEpisodePattern, isUltimateFallbackActive } from './utils.js';

// Stream handler (Express endpoint)
export { handleStream } from './streamHandler.js';
