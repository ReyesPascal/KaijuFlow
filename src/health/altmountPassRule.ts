/**
 * What the health check passes (ADR 0009, #184).
 *
 * AltMount is KaijuFlow's one Backend, and the health check passes a Source
 * only when AltMount is shown to stream it: plain video, stored RAR5 (in
 * volume order, hash-named, or put in order by Unscramble at play time) and
 * stored 7z. Everything else is blocked, each case with its own message.
 * Nothing that was not seen to play passes: "proven only".
 */

import type { ArchiveInfo } from '../archive/index.js';
import { hasVideoContent } from '../archive/index.js';

/**
 * Why AltMount can't stream this archive, or null when it can. `info` is the
 * archive inspection (null when no provider could read the header);
 * `password` is the NZB's password, if it has one.
 */
export function whyAltMountCannotStream(info: ArchiveInfo | null, password?: string): string | null {
  if (!info) return 'Archive header unreadable';
  // Encrypted with or without a password: not seen to play.
  if (info.encrypted) return password ? 'Encrypted archive (password in NZB)' : 'Encrypted archive (no password)';
  if (info.hasNestedArchive) return 'Nested archive';
  if (info.format === 'zip') return 'ZIP archive';
  // Unscramble reads RAR5 only, and AltMount refused a Scrambled RAR4 set ("all files failed validation").
  if (info.format === 'rar4') return 'RAR4 archive';
  if (info.format === 'unknown' || info.files.length === 0) return 'Archive header unreadable';
  // AltMount: "Only uncompressed files are supported".
  if (info.compression !== 'stored') return 'Compressed archive';
  if (!hasVideoContent(info)) return 'No video files in archive';
  return null;
}
