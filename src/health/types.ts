/**
 * Health Check Types
 *
 * Shared type definitions for the health check system.
 */

export type HealthStatus =
  | 'verified'              // Video file confirmed available
  | 'verified_stored'       // Stored/uncompressed archive (fast to stream)
  | 'verified_archive'      // Compressed archive (confirmed available, needs decompression)
  | 'blocked'               // Missing segments or dead
  | 'error';                // Check failed (network error, provider failure, VPN change, etc.)

export interface HealthCheckResult {
  status: HealthStatus;
  message: string;
  playable: boolean;
  providersUsed?: string[];
  password?: string;
  containerType?: string;    // Video container (e.g. 'MKV', 'MP4') — from NZB subjects or archive file listing
  /** The check sampled the wanted episode's file of a pack of loose videos (#203): its verdict holds for that episode
   *  only, so a blocked pack is remembered dead for that episode, not for the others. */
  episodeOnly?: boolean;
}

export interface NzbFile {
  subject: string;
  segments: Array<{ messageId: string; bytes: number; number: number }>;
}

export interface NzbParseResult {
  files: NzbFile[];
  password?: string;
}

export interface HealthCheckOptions {
  archiveInspection: boolean;
  sampleCount: 3 | 7;
  /**
   * The episode selector the Source is played with (`BackendSource.episodePattern`, #203): the video
   * file whose name it matches is the one sampled, as that is the file AltMount is asked to play.
   * Without it, or when no video file matches, the first video file is sampled.
   */
  episodePattern?: string;
}
