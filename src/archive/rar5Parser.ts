/**
 * RAR5 Archive Parser
 *
 * Parses RAR5 headers using variable-length number (vint) encoding.
 * Handles file headers, encryption headers, and extra/data areas.
 *
 * RAR5 header format:
 *   CRC32 (4B) + header_size (vint) + header_type (vint) + header_flags (vint) + [extra fields based on type]
 *   header_size covers everything AFTER the CRC32 + header_size bytes
 *
 * Header types:
 *   1 = Main archive header
 *   2 = File header
 *   3 = Service header (e.g. comments)
 *   4 = Encryption header (archive-level encryption)
 *   5 = End of archive header
 *
 * File header (type 2) fields after header_flags:
 *   file_flags (vint) -> unpacked_size (vint) -> attributes (vint) -> mtime (uint32, if flag 0x02)
 *   -> data_crc32 (uint32, if flag 0x04) -> compression_info (vint) -> host_os (vint) -> name_length (vint) -> name (UTF-8)
 *
 * Compression info bits 0-5 = version (0 = stored, others = compressed)
 */

import type { ArchiveInfo } from './types.js';
import { readVInt, checkFileContentType } from './utils.js';

/**
 * Parse RAR5 archive header
 */
export function parseRAR5(data: Buffer): ArchiveInfo {
  const info: ArchiveInfo = {
    format: 'rar5',
    encrypted: false,
    compression: 'unknown',
    files: [],
    hasNestedArchive: false,
    hasISO: false
  };

  try {
    let offset = 8; // Skip RAR5 signature (8 bytes)

    while (offset + 7 < data.length) {
      // CRC32 (4 bytes)
      offset += 4;

      // Header size (vint) — covers everything from header_type to end of header
      const headerSize = readVInt(data, offset);
      if (!headerSize || headerSize.value === 0) break;
      offset += headerSize.length;

      const headerEnd = offset + headerSize.value;
      if (headerEnd > data.length) break;

      // Header type (vint)
      const headerType = readVInt(data, offset);
      if (!headerType) break;
      offset += headerType.length;

      // Header flags (vint)
      const headerFlags = readVInt(data, offset);
      if (!headerFlags) break;
      offset += headerFlags.length;

      const hasExtraArea = !!(headerFlags.value & 0x01);
      const hasDataArea = !!(headerFlags.value & 0x02);

      // Extra area size (vint) — present if flag 0x01 set, comes BEFORE type-specific fields
      let extraAreaSize = 0;
      if (hasExtraArea) {
        const eas = readVInt(data, offset);
        if (!eas) { offset = headerEnd; continue; }
        offset += eas.length;
        extraAreaSize = eas.value;
      }

      // Data area size (vint) — present if flag 0x02 set, comes BEFORE type-specific fields
      // The actual packed data of this size follows AFTER the header (after headerEnd)
      let dataAreaSize = 0;
      if (hasDataArea) {
        const das = readVInt(data, offset);
        if (!das) { offset = headerEnd; continue; }
        offset += das.length;
        dataAreaSize = das.value;
      }

      // Encryption header (type 4) — archive-level encryption
      if (headerType.value === 4) {
        info.encrypted = true;
      }

      // File header (type 2) — parse type-specific fields
      if (headerType.value === 2 && offset < headerEnd) {
        try {
          // File flags (vint)
          const fileFlags = readVInt(data, offset);
          if (!fileFlags) { offset = headerEnd + dataAreaSize; continue; }
          offset += fileFlags.length;

          // Unpacked size (vint)
          const unpackedSize = readVInt(data, offset);
          if (!unpackedSize) { offset = headerEnd + dataAreaSize; continue; }
          offset += unpackedSize.length;

          // Attributes (vint)
          const attributes = readVInt(data, offset);
          if (!attributes) { offset = headerEnd + dataAreaSize; continue; }
          offset += attributes.length;

          // mtime (uint32) — present if file_flags bit 1 (0x02) is set
          if (fileFlags.value & 0x02) {
            if (offset + 4 > headerEnd) { offset = headerEnd + dataAreaSize; continue; }
            offset += 4;
          }

          // Data CRC32 (uint32) — present if file_flags bit 2 (0x04) is set
          if (fileFlags.value & 0x04) {
            if (offset + 4 > headerEnd) { offset = headerEnd + dataAreaSize; continue; }
            offset += 4;
          }

          // Compression info (vint)
          const compressionInfo = readVInt(data, offset);
          if (!compressionInfo) { offset = headerEnd + dataAreaSize; continue; }
          offset += compressionInfo.length;

          // Compression version is bits 0-5 (0 = stored/no compression, >0 = compressed)
          const compressionVersion = compressionInfo.value & 0x3F;

          // Host OS (vint)
          const hostOS = readVInt(data, offset);
          if (!hostOS) { offset = headerEnd + dataAreaSize; continue; }
          offset += hostOS.length;

          // Name length (vint)
          const nameLength = readVInt(data, offset);
          if (!nameLength || offset + nameLength.length + nameLength.value > headerEnd) {
            offset = headerEnd + dataAreaSize;
            continue;
          }
          offset += nameLength.length;

          // Filename (UTF-8)
          const filename = data.toString('utf8', offset, offset + nameLength.value);
          offset += nameLength.value;

          const isStored = compressionVersion === 0;

          // Skip directory entries (file_flags bit 0)
          if (!(fileFlags.value & 0x01)) {
            info.files.push({
              name: filename,
              size: unpackedSize.value,
              compressed: !isStored
            });

            // Update overall compression status
            if (isStored && info.compression !== 'compressed') {
              info.compression = 'stored';
            } else if (!isStored) {
              info.compression = 'compressed';
            }

            // Check for nested archives and ISOs
            checkFileContentType(filename, info);
          }
        } catch {
          // If individual file header parsing fails, skip to next header
        }
      }

      // Skip past header + packed data area to reach next header
      offset = headerEnd + dataAreaSize;
    }
  } catch (err) {
    console.warn('Error parsing RAR5 header:', (err as Error).message);
  }

  // Default to compressed if no files were found to determine
  if (info.compression === 'unknown') {
    info.compression = 'compressed';
  }

  return info;
}

const RAR5_SIGNATURE = Buffer.from([0x52, 0x61, 0x72, 0x21, 0x1a, 0x07, 0x01, 0x00]);

/**
 * Read the RAR5 volume number (0-based) from the first bytes of a RAR part:
 * the main archive header right after the signature. A first volume carries
 * no number field and counts as 0. Returns null when the bytes are not a
 * readable RAR5 main header (RAR4, other formats, encrypted headers, cut off).
 * Used by Unscramble (ADR 0005).
 */
export function readRar5VolumeNumber(data: Buffer): number | null {
  if (data.length < RAR5_SIGNATURE.length || !data.subarray(0, RAR5_SIGNATURE.length).equals(RAR5_SIGNATURE)) return null;
  let offset = RAR5_SIGNATURE.length + 4; // signature + header CRC32
  const next = (): number | null => {
    const v = readVInt(data, offset);
    if (!v) return null;
    offset += v.length;
    return v.value;
  };
  if (next() === null) return null;       // header size
  if (next() !== 1) return null;          // header type: 1 = main archive header
  const headerFlags = next();
  if (headerFlags === null) return null;
  if (headerFlags & 0x01 && next() === null) return null; // extra area size
  if (headerFlags & 0x02 && next() === null) return null; // data area size
  const archiveFlags = next();
  if (archiveFlags === null) return null;
  if (!(archiveFlags & 0x02)) return 0;   // no volume number field: first volume
  return next();
}
