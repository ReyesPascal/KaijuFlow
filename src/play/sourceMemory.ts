import type { StreamData } from './types.js';
import type { PlayContext } from './playContext.js';
import { episodeOf } from './playContext.js';
import { getCacheKey, setReadyCacheEntry, findReadyStream } from './streamCache.js';

export interface RememberedSource { nzbUrl: string; title: string; indexerName?: string }

export function remember(outcome: { source: RememberedSource; play?: PlayContext; ready: StreamData }): void {
  const { episodePattern } = episodeOf(outcome.play);
  setReadyCacheEntry(getCacheKey(outcome.source.nzbUrl, outcome.source.title) + (episodePattern ? `:${episodePattern}` : ''), outcome.ready, outcome.source.indexerName);
}

export function recall(source: RememberedSource, play?: PlayContext): { ready?: StreamData } {
  const ready = findReadyStream(source.nzbUrl, source.title, episodeOf(play).filePattern);
  return ready ? { ready } : {};
}
