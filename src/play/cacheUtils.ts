/**
 * Cache Utilities
 * Re-exports cache stats and clear functions for external consumers.
 */

export { getCacheStats, clearStreamCache, clearReadyCache, forgetDeadSources, deleteCacheEntry, getCacheEntries, isStreamCached, saveCacheToDisk, evictReadyByVideoPath } from './streamCache.js';
