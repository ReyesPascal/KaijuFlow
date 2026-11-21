/**
 * Configuration Accessors
 *
 * Exports the `config` object with getter-based accessors that read from
 * the shared configData state. This is the main Config object consumed
 * by the rest of the application.
 *
 * Environment variable overrides follow the priority:
 *   env var > config.json > hardcoded default
 */

import type { Config, SearchConfig, HealthCheckConfig, AutoPlayConfig, StreamDisplayConfig, SyncedIndexer, UltimateFallbackConfig } from '../types.js';
import { DEFAULT_INDEXER_TIMEOUT_SECONDS } from '../types.js';
import { getLatestVersions } from '../versionFetcher.js';
import { configData, ZYCLOPS_DEFAULT_ENDPOINT } from './schema.js';
import { UF_TIMEOUT_DEFAULTS } from '../play/timeoutDefaults.js';
import { DEFAULT_HEALTH_CHECK_CONNECTION_CAP } from '../health/nntpConnection.js';

/** Parse a 'true'/'false' env var string. Returns undefined if not set. */
function envBool(name: string): boolean | undefined {
  const v = process.env[name];
  if (v === undefined || v === '') return undefined;
  return v.toLowerCase() === 'true' || v === '1';
}

/** Return env var value if set (non-empty), otherwise undefined. */
function envStr(name: string): string | undefined {
  const v = process.env[name];
  return v !== undefined && v !== '' ? v : undefined;
}

/** Parse an env var as an integer. Returns undefined if not set or invalid. */
function envInt(name: string): number | undefined {
  const v = process.env[name];
  if (v === undefined || v === '') return undefined;
  const n = parseInt(v, 10);
  return Number.isFinite(n) ? n : undefined;
}

/** Validate an env var against a list of allowed values. */
function envEnum<T extends string>(name: string, allowed: T[]): T | undefined {
  const v = envStr(name);
  return v !== undefined && (allowed as string[]).includes(v) ? v as T : undefined;
}

// Export config in the format expected by the rest of the app
export const config: Config = {
  get addonEnabled() {
    return configData.addonEnabled !== false;
  },
  get indexers() {
    return configData.indexers;
  },
  get cacheEnabled() {
    return configData.cacheEnabled;
  },
  get cacheTTL() {
    return configData.cacheTTL;
  },
  get indexManager() {
    return envEnum('INDEX_MANAGER', ['newznab', 'prowlarr', 'nzbhydra']) || configData.indexManager;
  },
  get altmountUrl() {
    return envStr('ALTMOUNT_URL') || configData.altmountUrl;
  },
  get altmountApiKey() {
    return envStr('ALTMOUNT_API_KEY') || configData.altmountApiKey;
  },
  get altmountCategory() {
    return envStr('ALTMOUNT_CATEGORY') || configData.altmountCategory || 'kaijuflow';
  },
  get altmountPrepareTimeout() {
    return Math.max(1, configData.altmountPrepareTimeout ?? 300);
  },
  get playCacheTimeouts() {
    const env = envBool('INCLUDE_TIMEOUTS_AS_DEAD_NZBS');
    if (env !== undefined) return env;
    return configData.playCacheTimeouts !== false;
  },
  get playStreamBufferMB() {
    const envMB = envInt('PLAY_STREAM_BUFFER_MB') ?? envInt('STREAM_BUFFER_MB');
    if (envMB != null && envMB > 0) return Math.max(8, envMB);
    return Math.max(8, configData.playStreamBufferMB ?? 128);
  },
  get playPipeBufferMB() {
    const envMB = envInt('PLAY_PIPE_BUFFER_MB');
    if (envMB != null && envMB > 0) return Math.max(1, Math.min(16, envMB));
    return Math.max(1, Math.min(16, configData.playPipeBufferMB ?? 8));
  },
  get playDeliveryMethod(): 'pipe' | 'proxy' | 'direct' {
    return envEnum('PLAY_DELIVERY_METHOD', ['pipe', 'proxy', 'direct']) || configData.playDeliveryMethod || 'proxy';
  },
  get healthyNzbDbMode(): 'time' | 'storage' {
    return configData.healthyNzbDbMode || 'time';
  },
  get healthyNzbDbTTL() {
    return configData.healthyNzbDbTTL ?? 259200;
  },
  get healthyNzbDbMaxSizeMB() {
    return Math.min(50, Math.max(1, configData.healthyNzbDbMaxSizeMB ?? 50));
  },
  get filterDeadNzbs() {
    const env = envBool('FILTER_DEAD_NZBS');
    if (env !== undefined) return env;
    return configData.filterDeadNzbs !== false;
  },
  get deadNzbDbMode(): 'time' | 'storage' {
    return configData.deadNzbDbMode || 'storage';
  },
  get deadNzbDbTTL() {
    return configData.deadNzbDbTTL ?? 86400;
  },
  get deadNzbDbMaxSizeMB() {
    return Math.min(50, Math.max(1, configData.deadNzbDbMaxSizeMB ?? 50));
  },
  get proxyMode() {
    return envEnum('PROXY_MODE', ['disabled', 'http']) || configData.proxyMode || 'disabled';
  },
  get proxyUrl() {
    return envStr('PROXY_URL') || configData.proxyUrl;
  },
  get proxyIndexers() {
    return configData.proxyIndexers;
  },
  get searchConfig(): SearchConfig {
    const sc = configData.searchConfig || { includeSeasonPacks: true };
    const urlDedupEnv = envBool('URL_DEDUP');
    const absoluteEpFallbackEnv = envBool('ABSOLUTE_EPISODE_FALLBACK');
    const parallelAltTitleEnv = envBool('PARALLEL_ALTERNATE_TITLE_SEARCH');
    const junkFilterEnv = envBool('JUNK_FILTER');
    const cacheEmptyResultsEnv = envBool('CACHE_EMPTY_RESULTS');
    const tvdbEnglishEnv = envBool('TVDB_PREFER_ENGLISH_TITLE');
    const aliasTitleFallbackEnv = envBool('ALIAS_TITLE_FALLBACK');
    return {
      ...sc,
      absoluteEpisodeFallback: absoluteEpFallbackEnv ?? sc.absoluteEpisodeFallback ?? true,
      parallelAlternateTitleSearch: parallelAltTitleEnv ?? sc.parallelAlternateTitleSearch ?? false,
      tvdbPreferEnglishTitle: tvdbEnglishEnv ?? sc.tvdbPreferEnglishTitle ?? true,
      aliasTitleFallback: aliasTitleFallbackEnv ?? sc.aliasTitleFallback ?? true,
      ...(urlDedupEnv !== undefined && { urlDedup: urlDedupEnv }),
      ...(junkFilterEnv !== undefined && { junkFilter: junkFilterEnv }),
      ...(cacheEmptyResultsEnv !== undefined && { cacheEmptyResults: cacheEmptyResultsEnv }),
    };
  },
  get useTextSearch() {
    // Backward compat: derive from searchConfig
    const sc = configData.searchConfig;
    return sc ? (sc.movieSearchMethod === 'text' || sc.tvSearchMethod === 'text') : (configData.useTextSearch || false);
  },
  get includeSeasonPacks() {
    return configData.searchConfig?.includeSeasonPacks ?? configData.includeSeasonPacks ?? true;
  },
  get cardOrder() {
    return configData.cardOrder;
  },
  get userAgents() {
    const versions = getLatestVersions();
    const defaults = {
      indexerSearch: versions.prowlarr,
      nzbDownload: versions.sabnzbd,
      webdavOperations: versions.sabnzbd,
      general: versions.chrome
    };
    if (!configData.userAgents) return defaults;
    // Auto-generated fields match Prowlarr/*, SABnzbd/*, or Chrome/* patterns.
    // If saved value matches that pattern, replace with latest fetched version.
    // If user set a custom value, preserve it.
    const useLatest = (saved: string | undefined, pattern: RegExp, latest: string) =>
      !saved || pattern.test(saved) ? latest : saved;
    return {
      indexerSearch: useLatest(configData.userAgents.indexerSearch, /^Prowlarr\//, defaults.indexerSearch),
      nzbDownload: useLatest(configData.userAgents.nzbDownload, /^SABnzbd\//, defaults.nzbDownload),
      webdavOperations: useLatest(configData.userAgents.webdavOperations, /^SABnzbd\//, defaults.webdavOperations),
      general: useLatest(configData.userAgents.general, /Chrome\/[\d.]+/, defaults.general),
    };
  },
  get filters() {
    return configData.filters || {
      sortOrder: ['regexScore', 'quality', 'videoTag', 'seScore', 'size', 'encode', 'visualTag', 'audioTag', 'language', 'edition'],
      enabledSorts: {
        regexScore: false,
        quality: true,
        videoTag: true,
        size: true,
        encode: true,
        visualTag: true,
        audioTag: true,
        language: false,
        edition: false,
        seScore: false
      },
      enabledPriorities: {
        resolution: {},
        video: {},
        encode: {},
        visualTag: { '3D': false },
        audioTag: {},
        language: {},
        edition: {}
      },
      minFileSize: undefined,
      maxFileSize: undefined,
      minSeasonPackSize: undefined,
      maxSeasonPackSize: undefined,
      minSeasonPackEpisodeSize: undefined,
      maxSeasonPackEpisodeSize: undefined,
      maxStreams: undefined,
      maxStreamsPerResolution: undefined,
      maxStreamsPerQuality: undefined,
      resolutionPriority: ['4k', '1440p', '1080p', '720p', 'Unknown', '576p', '540p', '480p', '360p', '240p', '144p'],
      videoPriority: ['BluRay REMUX', 'REMUX', 'BDMUX', 'BRMUX', 'BluRay', 'WEB-DL', 'WEB', 'DLMUX', 'UHDRip', 'BDRip', 'WEB-DLRip', 'WEBRip', 'BRRip', 'DCP', 'WEBCap', 'VODR', 'HDTV', 'HDTVRip', 'SATRip', 'TVRip', 'PPVRip', 'DVD', 'DVDRip', 'PDTV', 'SDTV', 'HDRip', 'SCR', 'WORKPRINT', 'TeleCine', 'TeleSync', 'CAM', 'VHSRip', 'Unknown'],
      encodePriority: ['vvc', 'av1', 'hevc', 'vp9', 'avc', 'vc1', 'vp8', 'xvid', 'mpeg2', 'Unknown'],
      visualTagPriority: ['DV', 'HDR+DV', 'HDR10+', 'HDR', '10bit', 'AI', 'SDR', '3D', 'Unknown'],
      audioTagPriority: ['Atmos (TrueHD)', 'DTS:X', 'Atmos (DD+)', 'TrueHD', 'DTS-HD MA', 'FLAC', 'DTS-HD', 'DD+', 'DTS-ES', 'DTS', 'AAC', 'DD', 'Opus', 'PCM', 'MP3', 'Unknown'],
      languagePriority: ['English', 'Multi', 'Dual Audio', 'Dubbed', 'Arabic', 'Bengali', 'Bulgarian', 'Chinese', 'Croatian', 'Czech', 'Danish', 'Dutch', 'Estonian', 'Finnish', 'French', 'German', 'Greek', 'Gujarati', 'Hebrew', 'Hindi', 'Hungarian', 'Indonesian', 'Italian', 'Japanese', 'Kannada', 'Korean', 'Latino', 'Latvian', 'Lithuanian', 'Malay', 'Malayalam', 'Marathi', 'Norwegian', 'Persian', 'Polish', 'Portuguese', 'Punjabi', 'Romanian', 'Russian', 'Serbian', 'Slovak', 'Slovenian', 'Spanish', 'Swedish', 'Tamil', 'Telugu', 'Thai', 'Turkish', 'Ukrainian', 'Vietnamese'],
      editionPriority: ['Extended Edition', "Director's Cut", 'Superfan', 'Unrated', 'Uncensored', 'Uncut', 'Theatrical', 'IMAX', 'Special Edition', "Collector's Edition", 'Criterion Collection', 'Ultimate Edition', 'Anniversary Edition', 'Diamond Edition', 'Dragon Box', 'Color Corrected', 'Remastered', 'Standard']
    };
  },
  get movieFilters() {
    return configData.movieFilters;
  },
  get tvFilters() {
    return configData.tvFilters;
  },
  get healthChecks(): HealthCheckConfig {
    const hc = configData.healthChecks;

    if (!hc) {
      const defaults: HealthCheckConfig = {
        providers: [],
        maxTotalConnections: DEFAULT_HEALTH_CHECK_CONNECTION_CAP,
        verifyTlsCertificates: true,
      };
      // Inject env-based NNTP provider if configured
      const envHost = envStr('HEALTH_CHECK_NNTP_HOST');
      if (envHost) {
        defaults.providers = [{
          id: 'env-provider',
          name: 'Primary Provider (env)',
          host: envHost,
          port: envInt('HEALTH_CHECK_NNTP_PORT') ?? 563,
          useTLS: envBool('HEALTH_CHECK_NNTP_TLS') ?? true,
          username: envStr('HEALTH_CHECK_NNTP_USER') ?? '',
          password: envStr('HEALTH_CHECK_NNTP_PASS') ?? '',
          enabled: true,
          type: 'pool',
        }];
      }
      return defaults;
    }

    // Build the result with defaults
    const result: HealthCheckConfig = {
      ...hc,
      maxTotalConnections: hc.maxTotalConnections ?? DEFAULT_HEALTH_CHECK_CONNECTION_CAP,
      verifyTlsCertificates: hc.verifyTlsCertificates !== false,
    };

    // Inject env-based NNTP provider (prepended so it takes priority)
    const envHost = envStr('HEALTH_CHECK_NNTP_HOST');
    if (envHost) {
      const envProvider = {
        id: 'env-provider',
        name: 'Primary Provider (env)',
        host: envHost,
        port: envInt('HEALTH_CHECK_NNTP_PORT') ?? 563,
        useTLS: envBool('HEALTH_CHECK_NNTP_TLS') ?? true,
        username: envStr('HEALTH_CHECK_NNTP_USER') ?? '',
        password: envStr('HEALTH_CHECK_NNTP_PASS') ?? '',
        enabled: true,
        type: 'pool' as const,
      };
      // Replace if already injected, otherwise prepend
      const existing = result.providers.findIndex(p => p.id === 'env-provider');
      if (existing >= 0) {
        result.providers[existing] = envProvider;
      } else {
        result.providers = [envProvider, ...result.providers];
      }
    }

    return result;
  },
  get autoPlay(): AutoPlayConfig {
    return configData.autoPlay || {
      enabled: true,
      method: 'firstFile',
      attributes: ['resolution', 'quality', 'edition'],
    };
  },
  get streamDisplayConfig(): StreamDisplayConfig | undefined {
    return configData.streamDisplayConfig;
  },
  get syncedIndexers(): SyncedIndexer[] {
    return configData.syncedIndexers || [];
  },
  get prowlarrUrl() {
    return envStr('PROWLARR_URL') || configData.prowlarrUrl;
  },
  get prowlarrApiKey() {
    return envStr('PROWLARR_API_KEY') || configData.prowlarrApiKey;
  },
  get prowlarrTimeoutEnabled() {
    return configData.prowlarrTimeoutEnabled ?? true;
  },
  get prowlarrTimeout() {
    return configData.prowlarrTimeout ?? DEFAULT_INDEXER_TIMEOUT_SECONDS;
  },
  get nzbhydraUrl() {
    return envStr('NZBHYDRA_URL') || configData.nzbhydraUrl;
  },
  get nzbhydraApiKey() {
    return envStr('NZBHYDRA_API_KEY') || configData.nzbhydraApiKey;
  },
  get nzbhydraUsername() {
    return envStr('NZBHYDRA_USERNAME') || configData.nzbhydraUsername || '';
  },
  get nzbhydraPassword() {
    return envStr('NZBHYDRA_PASSWORD') || configData.nzbhydraPassword || '';
  },
  get nzbhydraTimeoutEnabled() {
    return configData.nzbhydraTimeoutEnabled ?? true;
  },
  get nzbhydraTimeout() {
    return configData.nzbhydraTimeout ?? DEFAULT_INDEXER_TIMEOUT_SECONDS;
  },
  get zyclopsEndpoint() {
    return configData.zyclopsEndpoint || ZYCLOPS_DEFAULT_ENDPOINT;
  },
  get easynewsEnabled() {
    return envBool('EASYNEWS_ENABLED') ?? configData.easynewsEnabled ?? false;
  },
  get easynewsUsername() {
    return envStr('EASYNEWS_USERNAME') || configData.easynewsUsername || '';
  },
  get easynewsPassword() {
    return envStr('EASYNEWS_PASSWORD') || configData.easynewsPassword || '';
  },
  get easynewsPagination() {
    return configData.easynewsPagination || false;
  },
  get easynewsMaxPages() {
    return configData.easynewsMaxPages || 3;
  },
  get easynewsTimeoutEnabled() {
    return configData.easynewsTimeoutEnabled ?? true;
  },
  get easynewsTimeout() {
    return configData.easynewsTimeout ?? DEFAULT_INDEXER_TIMEOUT_SECONDS;
  },
  get searchTimeoutOverride() {
    const raw = envInt('SEARCH_TIMEOUT');
    return raw !== undefined ? Math.max(1, Math.min(45, raw)) : undefined;
  },
  get easynewsMode() {
    return configData.easynewsMode || 'nzb';
  },
  get easynewsHealthCheck() {
    return configData.easynewsHealthCheck ?? true;
  },
  get indexerPriority() {
    return configData.indexerPriority;
  },
  get ultimateFallback(): UltimateFallbackConfig {
    const ur = configData.ultimateFallback;
    const enabled = envBool('ULTIMATE_FALLBACK_ENABLED') ?? ur?.enabled ?? false;
    const whenToResolve = envEnum('ULTIMATE_FALLBACK_WHEN_TO_RESOLVE', ['on-results', 'on-tile-selection']) ?? ur?.whenToResolve ?? 'on-results';
    // A clicked list entry that fails falls back to the next Source of the list (#190); an old config's
    // 'failure-video' is read as that too, since the Play-time check always falls back.
    const savedPick = envEnum('ULTIMATE_FALLBACK_USER_PICK_FALLBACK', ['uf-lobby', 'failure-video', 'fallback-chain']) ?? ur?.userPickFallback ?? 'fallback-chain';
    const userPickFallback = savedPick === 'uf-lobby' ? 'uf-lobby' : 'fallback-chain';
    // How many Sources the Play-time check checks at once, from the top of the list down (#190, default 3).
    const candidateCount = Math.max(1, Math.min(10, envInt('ULTIMATE_FALLBACK_CANDIDATE_COUNT') ?? ur?.candidateCount ?? 3));
    const preferenceMode = envEnum('ULTIMATE_FALLBACK_PREFERENCE_MODE', ['priority', 'speed']) ?? ur?.preferenceMode ?? 'priority';
    // Archive inspection is mandatory for UF — its container-matching guarantee
    // (each backup matches the primary's container type) depends on reading
    // archive headers at health-check time. Without it, archive candidates
    // come back with unknown container type and UF can't filter mismatches
    // before handing them to the Backend.
    const archiveInspection = true;
    const rawSample = envInt('ULTIMATE_FALLBACK_SAMPLE_COUNT') ?? ur?.sampleCount ?? 3;
    const sampleCount: 3 | 7 = rawSample === 7 ? 7 : 3;
    const maxAttempts = Math.max(0, Math.min(20, envInt('ULTIMATE_FALLBACK_MAX_ATTEMPTS') ?? ur?.maxAttempts ?? 0));
    const desiredBackups = Math.max(0, Math.min(10, envInt('ULTIMATE_FALLBACK_DESIRED_BACKUPS') ?? ur?.desiredBackups ?? 0));
    const backupProcessingLimit = Math.max(0, Math.min(20, envInt('ULTIMATE_FALLBACK_BACKUP_PROCESSING_LIMIT') ?? ur?.backupProcessingLimit ?? 3));
    const priorityMoviesTimeoutSeconds = Math.max(0, Math.min(90, envInt('ULTIMATE_FALLBACK_PRIORITY_MOVIES_TIMEOUT') ?? ur?.priorityMoviesTimeoutSeconds ?? UF_TIMEOUT_DEFAULTS.priority.movies));
    const priorityTvTimeoutSeconds = Math.max(0, Math.min(90, envInt('ULTIMATE_FALLBACK_PRIORITY_TV_TIMEOUT') ?? ur?.priorityTvTimeoutSeconds ?? UF_TIMEOUT_DEFAULTS.priority.tv));
    const prioritySeasonPackTimeoutSeconds = Math.max(0, Math.min(90, envInt('ULTIMATE_FALLBACK_PRIORITY_SEASON_PACK_TIMEOUT') ?? ur?.prioritySeasonPackTimeoutSeconds ?? UF_TIMEOUT_DEFAULTS.priority.seasonPack));
    const speedMoviesTimeoutSeconds = Math.max(0, Math.min(90, envInt('ULTIMATE_FALLBACK_SPEED_MOVIES_TIMEOUT') ?? ur?.speedMoviesTimeoutSeconds ?? UF_TIMEOUT_DEFAULTS.speed.movies));
    const speedTvTimeoutSeconds = Math.max(0, Math.min(90, envInt('ULTIMATE_FALLBACK_SPEED_TV_TIMEOUT') ?? ur?.speedTvTimeoutSeconds ?? UF_TIMEOUT_DEFAULTS.speed.tv));
    const speedSeasonPackTimeoutSeconds = Math.max(0, Math.min(90, envInt('ULTIMATE_FALLBACK_SPEED_SEASON_PACK_TIMEOUT') ?? ur?.speedSeasonPackTimeoutSeconds ?? UF_TIMEOUT_DEFAULTS.speed.seasonPack));
    return {
      enabled,
      whenToResolve,
      userPickFallback,
      candidateCount,
      preferenceMode,
      archiveInspection,
      sampleCount,
      maxAttempts,
      desiredBackups,
      backupProcessingLimit,
      priorityMoviesTimeoutSeconds,
      priorityTvTimeoutSeconds,
      prioritySeasonPackTimeoutSeconds,
      speedMoviesTimeoutSeconds,
      speedTvTimeoutSeconds,
      speedSeasonPackTimeoutSeconds,
      healthCheckIndexers: ur?.healthCheckIndexers,
    };
  },
};

/**
 * Resolved TV-scope accessors for Filters-menu toggles.
 * Precedence: env var > tvFilters > filters > default true.
 */
export function getTvRemakeFiltering(cfg: Config): boolean {
  const envVal = envBool('ENABLE_REMAKE_DETECTION');
  if (envVal !== undefined) return envVal;
  return (cfg.tvFilters?.enableRemakeFiltering ?? cfg.filters?.enableRemakeFiltering) !== false;
}

export function getTvAllowMultiEpisode(cfg: Config): boolean {
  const envVal = envBool('ALLOW_MULTI_EPISODE_FILES');
  if (envVal !== undefined) return envVal;
  return (cfg.tvFilters?.allowMultiEpisodeFiles ?? cfg.filters?.allowMultiEpisodeFiles) !== false;
}
