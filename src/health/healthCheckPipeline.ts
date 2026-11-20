/**
 * Health Check Pipeline
 *
 * Main orchestration for NZB health checks. Downloads and parses the NZB,
 * classifies files, samples segments of the video file, and verifies article
 * availability across providers.
 *
 * KaijuFlow plays plain video only (ADR 0008): an NZB with no file named as
 * video is blocked before any segment is sampled, whether it holds an archive
 * (RAR, 7z, ZIP; stored, compressed or encrypted), a bare disc image, or only
 * files it cannot name (obfuscated).
 */

import { isDiscImageName } from '../archive/index.js';
import type { UsenetProvider } from '../types.js';
import type { HealthCheckResult, HealthCheckOptions } from './types.js';
import { downloadAndParseNzb, CircuitChangedError } from './nzbParser.js';
import { extractFilename, isVideoFile, isCompressedArchive, getVideoContainerType } from './fileClassifier.js';
import { NntpConnectionPool } from './nntpConnection.js';
import { checkArticlesMultiProvider } from './articleChecker.js';

/**
 * Perform health check on an NZB using multiple providers.
 * `searchExitIp` is the proxy exit IP that was live when the candidate's search
 * ran; passed to the NZB downloader so circuit verification compares against
 * the original search's IP rather than a (possibly newer) global baseline.
 * `onCircuitAbort` is invoked once when the proxy circuit aborts so the
 * surrounding batch can stop scheduling further NZBs against the same
 * (still-broken) proxy state.
 */
export async function performHealthCheck(
  nzbUrl: string,
  providers: UsenetProvider[],
  userAgent: string,
  options: HealthCheckOptions = { archiveInspection: true, sampleCount: 3 },
  pool?: NntpConnectionPool,
  indexerName?: string,
  searchExitIp?: string,
  onCircuitAbort?: () => void
): Promise<HealthCheckResult> {
  // Create a short label for log lines so parallel checks can be distinguished
  // Updated after NZB parsing to use the actual content base name
  let nzbLabel = (() => {
    try {
      const url = new URL(nzbUrl);
      const path = url.pathname.split('/').filter(Boolean).pop() || url.hostname;
      return path.replace(/\.nzb$/i, '').substring(0, 30);
    } catch { return nzbUrl.substring(0, 30); }
  })();
  const log = (msg: string) => console.log(`  [${nzbLabel}] ${msg}`);

  try {
    // Download and parse NZB
    const { files, password } = await downloadAndParseNzb(nzbUrl, userAgent, indexerName, searchExitIp);

    if (files.length === 0) {
      return {
        status: 'blocked',
        message: 'No files in NZB',
        playable: false,
        password
      };
    }

    // Update label to use actual content name from NZB (more readable than URL hash)
    if (files.length > 0) {
      const firstName = extractFilename(files[0].subject);
      // Strip part numbers and extensions to get a clean base name
      const baseName = firstName.replace(/\.(7z|rar|zip|par2|nfo|sfv|nzb)(\.\d+)?$/i, '')
        .replace(/\.part\d+$/i, '').replace(/\.r\d+$/i, '').replace(/\.\d{3}$/i, '');
      if (baseName.length >= 5) {
        nzbLabel = baseName.substring(0, 25);
      }
    }

    const videoFiles = files.filter(f => isVideoFile(f.subject));
    const archiveFiles = files.filter(f => isCompressedArchive(f.subject));
    const containerType = videoFiles.length > 0 ? getVideoContainerType(videoFiles[0].subject) : undefined;

    log(`${files.length} files (${videoFiles.length} video, ${archiveFiles.length} archive)${containerType ? ` [${containerType}]` : ''}`);

    // Plain video only (ADR 0008): with no video file there is nothing to play.
    if (videoFiles.length === 0) {
      if (archiveFiles.length > 0) {
        log(`→ Blocked: archive, not plain video (${extractFilename(archiveFiles[0].subject)})`);
        return {
          status: 'blocked',
          message: 'Blocked: archive, not plain video',
          playable: false,
          password,
        };
      }
      const largest = files.reduce((a, b) => {
        const aSize = a.segments.reduce((s, seg) => s + seg.bytes, 0);
        const bSize = b.segments.reduce((s, seg) => s + seg.bytes, 0);
        return aSize > bSize ? a : b;
      });
      // A bare disc image is not playable on the Backends (#120).
      if (isDiscImageName(extractFilename(largest.subject))) {
        log(`→ Blocked: disc image (${extractFilename(largest.subject)})`);
        return {
          status: 'blocked',
          message: 'Disc image',
          playable: false,
          password,
        };
      }
      log(`→ Blocked: unknown files, not plain video (largest: ${extractFilename(largest.subject)})`);
      return {
        status: 'blocked',
        message: 'Blocked: unknown files, not plain video',
        playable: false,
        password,
      };
    }

    const fileToCheck = videoFiles[0];
    log(`Checking video: ${extractFilename(fileToCheck.subject)}`);

    // Sample articles from the video file
    const segments = fileToCheck.segments;

    if (segments.length === 0) {
      return {
        status: 'blocked',
        message: 'No segments found',
        playable: false,
        password,
        containerType,
      };
    }

    // Spread samples across segments within the file
    // 3 samples: first, middle, last — faster
    // 7 samples: spread across file at 0%, 20%, 40%, 50%, 60%, 80%, 100% — more thorough
    const samplesToCheck: string[] = [...new Set(
      (options.sampleCount === 3
        ? [
            segments[0]?.messageId,                                    // First
            segments[Math.floor(segments.length * 0.5)]?.messageId,   // Middle
            segments[segments.length - 1]?.messageId                   // Last
          ]
        : [
            segments[0]?.messageId,                                    // First
            segments[Math.floor(segments.length * 0.2)]?.messageId,   // 20%
            segments[Math.floor(segments.length * 0.4)]?.messageId,   // 40%
            segments[Math.floor(segments.length * 0.5)]?.messageId,   // Middle
            segments[Math.floor(segments.length * 0.6)]?.messageId,   // 60%
            segments[Math.floor(segments.length * 0.8)]?.messageId,   // 80%
            segments[segments.length - 1]?.messageId                   // Last
          ]
      ).filter(Boolean)
    )];

    log(`Checking ${samplesToCheck.length} segments across ${providers.filter(p => p.enabled).length} provider(s)`);

    // Multi-provider check with fallback
    const result = await checkArticlesMultiProvider(providers, samplesToCheck, pool);
    const usedBackup = result.providersUsed.some(p => p.type === 'backup');
    const providerNames = result.providersUsed.map(p => `${p.name} (${p.found}/${p.total})`);

    log(`Result: ${result.totalExists}/${samplesToCheck.length} found (${providerNames.join(', ')})`);

    // All samples exist
    if (result.totalExists === samplesToCheck.length) {
      const backupNote = usedBackup ? ' (with backup)' : '';
      log(`→ Verified${backupNote}`);
      return {
        status: 'verified',
        message: `Verified (${samplesToCheck.length} samples checked${backupNote})`,
        playable: true,
        providersUsed: providerNames,
        password,
        containerType,
      };
    }

    // Some missing — blocked
    if (result.totalMissing > 0) {

      const providerInfo = providerNames.length > 1
        ? ` (checked ${providerNames.length} providers)`
        : '';
      log(`→ Blocked: ${result.totalMissing}/${samplesToCheck.length} missing${providerInfo}`);
      return {
        status: 'blocked',
        message: `Missing ${result.totalMissing} of ${samplesToCheck.length} segments${providerInfo}`,
        playable: false,
        providersUsed: providerNames,
        password,
        containerType,
      };
    }

    log('→ Error: unexpected state');
    return {
      status: 'error',
      message: 'Could not verify all articles',
      playable: false,
      providersUsed: providerNames,
      password,
      containerType,
    };

  } catch (error) {
    if (error instanceof CircuitChangedError) {
      onCircuitAbort?.();
      return {
        status: 'error',
        message: 'Skipped: VPN circuit verification failed',
        playable: false
      };
    }
    const errorMsg = (error as Error).message;
    console.error(`❌ Health check error for ${nzbUrl.substring(0, 100)}:`, errorMsg);
    return {
      status: 'error',
      message: `Check failed: ${errorMsg}`,
      playable: false
    };
  }
}
