#!/usr/bin/env bash
# Rebuilds the archive fixtures for tests/unit/health-pass-rule.test.ts (#184).
# Real archives from 7-Zip (p7zip 16.02), RAR 7.23 for RAR5 and RAR 6.24 for
# RAR4 (RAR 7 no longer writes RAR4; both from rarlab.com, on Brain under
# ~/.local/share/rarlab, or set RAR / RAR4) and Info-ZIP, holding a small
# made-up "Movie.mkv". Run from this folder: bash make.sh
set -euo pipefail
RAR=${RAR:-$HOME/.local/share/rarlab/rar/rar}
RAR4=${RAR4:-$HOME/.local/share/rarlab/624/rar/rar}
work=$(mktemp -d); trap 'rm -rf "$work"' EXIT
head -c 3000 /dev/urandom > "$work/Movie.mkv"
head -c 1000 /dev/urandom > "$work/Movie.rar"
printf 'Movie frame %.0s' $(seq 250) > "$work/Packable.mkv"   # compresses, so RAR really packs it
for i in $(seq -w 1 30); do head -c 40 /dev/urandom > "$work/Extra$i.txt"; done
rm -f ./*.7z ./*.7z.0* ./*.zip ./*.rar ./*.r0?
here=$PWD
(
  cd "$work"
  7z a -bd -mx0 "$here/stored.7z" Movie.mkv                         # Copy, plain header
  7z a -bd -mx0 "$here/stored-packed-header.7z" Movie.mkv Extra*.txt # Copy, LZMA-packed header
  7z a -bd -mx0 -v1k "$here/stored-split.7z" Movie.mkv               # Copy, split in volumes
  7z a -bd -mx5 "$here/compressed.7z" Movie.mkv                     # LZMA2
  7z a -bd -mx0 -psecret "$here/encrypted.7z" Movie.mkv             # Copy + AES, names readable
  7z a -bd -mx0 -psecret -mhe=on "$here/encrypted-names.7z" Movie.mkv # AES header too
  7z a -bd -mx0 "$here/nested.7z" Movie.rar                         # an archive inside
  zip -q -0 "$here/stored.zip" Movie.mkv
  "$RAR" a -idq -ma5 -m0 -v1k "$here/rar5-stored.rar" Movie.mkv     # .part1.rar ... .part4.rar
  "$RAR" a -idq -ma5 -m3 "$here/rar5-compressed.rar" Packable.mkv
  "$RAR" a -idq -ma5 -m0 -psecret "$here/rar5-encrypted.rar" Movie.mkv     # data encrypted, names readable
  "$RAR" a -idq -ma5 -m0 -hpsecret "$here/rar5-encrypted-names.rar" Movie.mkv # headers encrypted too
  "$RAR" a -idq -ma5 -m0 "$here/rar5-nested.rar" Movie.rar
  "$RAR4" a -idq -ma4 -m0 -v1k -vn "$here/rar4-stored.rar" Movie.mkv # old style: .rar, .r00, .r01 ...
) > /dev/null
ls -l
