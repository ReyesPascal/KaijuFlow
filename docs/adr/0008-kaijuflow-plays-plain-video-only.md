# KaijuFlow plays plain video only

KaijuFlow plays only Sources whose NZB holds a video file posted as is. Its health check blocks every other Source before sampling a segment: any archive (RAR4 or RAR5, stored or compressed, 7z, ZIP, encrypted or not) and any NZB whose files it cannot name as video or archive (obfuscated names). Usenet Ultimate and AltMount direct are not changed. Decided by the owner on 2026-11-15, after Test 2's first record (#156) was cancelled.

The owner's words: "HERE IS A NEW RULE FOR SOURCES, ONLY PLAIN VIDEO"; asked whether stored RAR, which both Backends can stream, is out too: "plain video only"; on where it applies: "kf AND uu FIND OUT AND ALTMOUNT DIREC DOESNT THATS JUST HOW IT IS", then "LEAVE UU UNCHANGED, APPLY RULE TO KF"; on obfuscated NZBs: "BLOCK UNKNOWN".

## Why

Test 2's first record (cancelled and deleted; the logs were read before) showed two Sources the health check passed and the Backend could not play:

- Avengers: Endgame (easy list): the top pick was a compressed 7z holding one MKV. The health check found every sampled segment and returned `Verified: compressed archive`, playable. AltMount answered "no valid files found in 7zip archive after filtering. Only uncompressed files are supported" and NzbDAV "Only uncompressed 7z files are supported." KaijuFlow and Usenet Ultimate failed it in both rounds.
- Coherence (hard list): the top pick was a Scrambled RAR4 set. Unscramble reads RAR5 only (ADR 0005), so the original NZB went up, and AltMount rejected it ("all files failed validation"). NzbDAV played the same Source.

Checking articles says a Source is complete, not that the Backend can stream what is inside it. A video file posted as is streams on every Backend.

## Consequences

- Fewer Sources. In that record about 19 of 117 health checks were plain video; most were 7z (compressed) or RAR5 (stored). A title with no plain-video Source among the Sources checked fails.
- The health check no longer inspects archives for a play decision. Unscramble (ADR 0005) is no longer reached for a played Source; its code stays.
- Usenet Ultimate (v1.4.1, as shipped) and AltMount direct keep playing archives. In a speed test this is part of KaijuFlow's health check, as skipping a dead Source is, not a break of like for like: the Sources, sort and one try stay the same for every setup (`tools/brain/docs/rules.md`, "Like for like").
- An obfuscated plain video (no file name that says video) is blocked too: the accepted cost of "BLOCK UNKNOWN".
- Like for like per title (#143) left a title out of the targets when two top picks state different resolutions. With archives blocked, KaijuFlow will often play a lower resolution than a setup that plays a 4K archive. Asked whether such titles are left out or counted, the owner said "COUNT THEM": KaijuFlow is judged on what it plays. So a pair whose KaijuFlow pick states the lower resolution is like for like; a pair whose other pick states the lower one is still left out, since a smaller file would favour the other setup.
