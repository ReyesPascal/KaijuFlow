# KaijuFlow

KaijuFlow is the owner's maintained fork of Usenet Ultimate. It finds Usenet releases for a title, checks they are complete, and hands them to a backend that turns them into a playable video.

## Language

**KaijuFlow**:
The owner's maintained fork of Usenet Ultimate v1.4.1, continued because the original is no longer maintained.
_Avoid_: KF (in docs), UU fork

**Upstream**:
The original Usenet Ultimate project at v1.4.1, which KaijuFlow was forked from and no longer tracks.
_Avoid_: Usenet Ultimate (when you mean KaijuFlow), original

### Finding and playing

**Source**:
One NZB that search found for a title, whether or not it is complete. A Source might be streamed; it is not yet a Stream.
_Avoid_: result, release, NZB (when you mean the search result), "source" for code

**Healthy Source**:
A Source that passed a health check, so its articles are believed to be available.
_Avoid_: verified result, good source

**Stream**:
The playable link a Backend produced for one Source.
_Avoid_: tile, source (when you mean the link)

**Backend**:
A separate service that takes one Source, prepares it, and serves its video file to the player. NzbDAV, AltMount and InfiniDysk are Backends.
_Avoid_: streamer, engine, provider (providers are Usenet servers)

**Parity**:
The bar for supporting a new Backend: any Source that plays through NzbDAV also plays through the new Backend, seeking works, and a Source that fails shows the failure video and is not offered again.
_Avoid_: compatibility, support (unqualified)

### Preparing a Source

**Scrambled RAR set**:
A Source whose RAR parts are named only by numbers that do not match their real volume order.
_Avoid_: obfuscated release (obfuscated names can still be in order), broken RAR, shuffled parts

**Unscramble**:
Renaming the parts of a Scrambled RAR set into a normal RAR volume series in their real volume order, before the Source goes to the Backend.
_Avoid_: reorder, repair, fix names
