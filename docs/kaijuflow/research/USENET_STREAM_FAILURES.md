# How a Usenet stream fails, and how to tell each failure apart

Research for the planned **diagnosis system**: a tool that takes one failed play, matches it against a casebook of known causes by their signs, and confirms the match with a test. This page lists the ways a stream from Usenet can fail, what each one looks like, and a test that would confirm it.

Researched 2026-11-24. Words in **bold** are explained the first time they appear. Everything is cited. A sentence that starts with *Inference:* is my own reasoning from the sources, not something a source says.

**What was read, and at which version.** The code is quoted at fixed versions, so the line links stay true:

| What | Version read | Why this version |
|---|---|---|
| AltMount ([kipsilabs/altmount](https://github.com/kipsilabs/altmount); `javi11/altmount` now redirects there) | tag `v0.4.0` | the image KaijuFlow tests with is `ghcr.io/kipsilabs/altmount:v0.4.0` ([tools/brain/compose.test.yaml](../../../tools/brain/compose.test.yaml), line 37) |
| nntppool, AltMount's NNTP library ([javi11/nntppool](https://github.com/javi11/nntppool)) | tag `v5.0.0` | pinned in AltMount v0.4.0's [go.mod](https://github.com/kipsilabs/altmount/blob/v0.4.0/go.mod#L25) |
| rardecode, AltMount's RAR reader ([javi11/rardecode](https://github.com/javi11/rardecode)) | tag `v2.2.4` | [go.mod](https://github.com/kipsilabs/altmount/blob/v0.4.0/go.mod#L28) |
| nzbparser, AltMount's NZB reader ([javi11/nzbparser](https://github.com/javi11/nzbparser)) | tag `v0.5.5` | [go.mod](https://github.com/kipsilabs/altmount/blob/v0.4.0/go.mod#L27) |
| SABnzbd ([sabnzbd/sabnzbd](https://github.com/sabnzbd/sabnzbd)) | commit `4d9d995` (2026-11-23) | newest |
| NZBGet ([nzbgetcom/nzbget](https://github.com/nzbgetcom/nzbget), the maintained fork) | commit `3064f1c` (2026-11-23) | newest |
| KaijuFlow | commit `41a82c1` | this branch |

The settings quoted for "the live AltMount" are those of the test copy `altmount-kf`, read on 2026-11-24 with `python3 -I tools/brain/testbed.py read-settings` (secrets hidden).

---

## 0. The words, in one place

- **Usenet** is a worldwide network of news servers that copy messages to each other. A **provider** (Newshosting, for KaijuFlow) sells access to one such server farm.
- **NNTP** (Network News Transfer Protocol) is the language a program uses to talk to a news server. The client sends a command, the server answers with a line that starts with a three-digit **response code** ([RFC 3977, section 3.1](https://www.rfc-editor.org/rfc/rfc3977#section-3.1)).
- An **article** is one Usenet message. Each has a unique **message-id**, a name like `<abc123@example>` ([RFC 3977, section 3.6](https://www.rfc-editor.org/rfc/rfc3977#section-3.6)).
- A video is far too big for one article, so the poster cuts it into hundreds or thousands of pieces, one per article. One piece is a **segment** (the NZB's word) or **part** (yEnc's word). A typical one is about 768 KB ([AltMount rar/processor.go, line 690](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/importer/archive/rar/processor.go#L690)).
- **yEnc** is the way the binary bytes are written as text inside an article. Each part carries its size, its position in the file and a **CRC32**, a short checksum that changes if any byte changes ([yEnc 1.3](http://www.yenc.org/yenc-draft.1.3.txt)).
- An **NZB** is a small XML file that lists, for each file of a post, the message-id of every segment in order. KaijuFlow grabs it from an indexer ([NZB spec](https://sabnzbd.org/wiki/extra/nzb-spec)).
- **STAT** asks the server "do you have this article?" without downloading it. **BODY** downloads the article's content ([RFC 3977, sections 6.2.4 and 6.2.3](https://www.rfc-editor.org/rfc/rfc3977#section-6.2.4)).
- **Retention** is how long a provider keeps an article after it was posted: "the length of time, measured in days, that a Usenet provider keeps an article available to you after it was posted" ([Newshosting](https://www.newshosting.com/usenet/what-is-usenet-article-retention/)).
- A **backbone** is the storage system behind one or more provider brands. Brands that sell the same backbone serve the same articles and lose the same ones (section 5).
- A **takedown** is the removal of articles after a copyright notice. In the US it follows the **DMCA**, in the Netherlands **NTD** (notice and takedown) ([NewsDemon](https://www.newsdemon.com/usenet-takedowns)).
- A **RAR volume** is one file of a multi-file RAR archive (`.part01.rar`, `.part02.rar`, or the old `.rar`, `.r00`, `.r01`). A **stored** archive keeps the video's bytes as they are, so a byte range of the video is a byte range of the volumes; a **compressed** one does not ([RAR 5 technote](https://www.rarlab.com/technote.htm), "Compression information").
- **PAR2** files are repair data posted next to a release. They can rebuild missing pieces, but only by downloading and computing over whole blocks of the set ([PAR 2.0 spec](https://parchive.github.io/doc/Parity%20Volume%20Set%20Specification%20v2.0.html)).
- **AltMount** is KaijuFlow's Backend: it takes the NZB, checks it, reads the archive layout, and then serves the video over HTTP, fetching segments from the provider as the player asks for bytes.

---

## 1. NNTP itself: the codes that matter for a stream

Every answer from a news server starts with a three-digit code. These are the ones a stream meets, with what the standard says and what they mean for a play.

| Code | Standard text | Where it comes | What it means for a stream |
|---|---|---|---|
| `223` | "Article exists" | answer to STAT | The server knows that message-id. It does not prove the content is whole (section 2.5). [RFC 3977 §6.2.4](https://www.rfc-editor.org/rfc/rfc3977#section-6.2.4) |
| `222` | "Body follows" | answer to BODY | The segment is coming. [RFC 3977 §6.2.3](https://www.rfc-editor.org/rfc/rfc3977#section-6.2.3) |
| `430` | "No article with that message-id" | STAT, BODY, ARTICLE by message-id | This provider does not have this segment (now). The usual sign of a missing segment. [RFC 3977 §6.2.1–6.2.4](https://www.rfc-editor.org/rfc/rfc3977#section-6.2.1) |
| `423` | "No article with that number" | the same commands, asked by article *number* in a group | The same meaning in the other way of asking. Streaming tools ask by message-id, so `423` is rare; nntppool and SABnzbd treat it exactly like `430` ([nntppool errors.go, lines 68–75](https://github.com/javi11/nntppool/blob/v5.0.0/errors.go#L68-L75); [SABnzbd newswrapper.py, line 272](https://github.com/sabnzbd/sabnzbd/blob/4d9d9953d4315b27e61d083909de36888e8fc8db/sabnzbd/newswrapper.py#L272)). |
| `200` / `201` | greeting, service available | first line after connecting | Good. [RFC 3977 §5.1](https://www.rfc-editor.org/rfc/rfc3977#section-5.1) |
| `400` | "Service temporarily unavailable" | greeting, or any time | The server is closing this connection. As a greeting: "400 SHOULD be used if the issue is only temporary (for example, because of load)". Clients "SHOULD NOT simply reconnect immediately" ([§5.1.2](https://www.rfc-editor.org/rfc/rfc3977#section-5.1.2), [§3.2.1](https://www.rfc-editor.org/rfc/rfc3977#section-3.2.1)). |
| `502` | "Service permanently unavailable" / "Command unavailable" | greeting, or answer to AUTHINFO | As a greeting: "the client is not permitted under any circumstances to interact with the server" ([§5.1.2](https://www.rfc-editor.org/rfc/rfc3977#section-5.1.2)). In practice providers use `502` for a connection limit *and* for a refused login (see below). |
| `480` | authentication required | any command before login | The client did not log in ([§3.2.1](https://www.rfc-editor.org/rfc/rfc3977#section-3.2.1)). |
| `381` / `281` | "Password required" / "Authentication accepted" | AUTHINFO USER / PASS | A normal login ([RFC 4643 §2.3](https://www.rfc-editor.org/rfc/rfc4643#section-2.3)). |
| `481` | "Authentication failed/rejected" | AUTHINFO PASS | Wrong user name or password ([RFC 4643 §2.3](https://www.rfc-editor.org/rfc/rfc4643#section-2.3)). |
| `482` | "Authentication commands issued out of sequence" | AUTHINFO | A client bug, not a Source problem ([RFC 4643 §2.3](https://www.rfc-editor.org/rfc/rfc4643#section-2.3)). |
| `403` | internal fault | any | "the server experiences an internal fault or problem" ([§3.2.1](https://www.rfc-editor.org/rfc/rfc3977#section-3.2.1)). Says nothing about the Source. |
| no answer, connection closed | — | any time | An idle connection may be closed: a server "MAY have an inactivity autologout timer" of "at least three minutes", and when it expires the server "SHOULD close the connection without sending any response" ([§3.1](https://www.rfc-editor.org/rfc/rfc3977#section-3.1)). |

### 1.1 What the providers actually send

Providers bend the standard, and a diagnosis must read the text after the code, not just the code:

- Newshosting's own help pages name the error "502 Max Connections Reached": it "occurs when the software attempts to open more connections to the server than allowed by your Newshosting plan", and also when switching networks or when the account "is accessed from multiple locations at the same time" ([Newshosting KB 1014](https://support.newshosting.com/kb/article/1014-502-max-connections-reached/)).
- Newshosting also says "502 Authentication Failed" for a bad login ("incorrect credentials", an "expired credit card or account hold") and lists too many connections as a cause of that one too ([Newshosting KB 1012](https://support.newshosting.com/kb/article/1012-502-authentication-failed/)). It says "480 Authentication Required" when the login didn't happen, an account is inactive, or there are too many connections ([Newshosting KB 1193](https://support.newshosting.com/kb/article/1193-480-authentication-required/)).
- So `502` from Newshosting can mean "too many connections" or "your login is refused". SABnzbd tells them apart by words in the message: "exceed", "connections", "too many", "threads", "limit" mean a connection limit, unless the text also says "download", "byte" or "quota" ([SABnzbd downloader.py, lines 1072–1079](https://github.com/sabnzbd/sabnzbd/blob/4d9d9953d4315b27e61d083909de36888e8fc8db/sabnzbd/downloader.py#L1072-L1079)). It treats `481`, `482`, `452`, `381`, or a `500`/`502` with login words as a refused login and stops using that server ([lines 865–893](https://github.com/sabnzbd/sabnzbd/blob/4d9d9953d4315b27e61d083909de36888e8fc8db/sabnzbd/downloader.py#L865-L893)).
- AltMount's library does not read the text: it treats *any* `502` or `400`, in the greeting or as the answer to AUTHINFO, as "max connections reached" ([nntppool nntp.go, lines 136–165](https://github.com/javi11/nntppool/blob/v5.0.0/nntp.go#L136-L165)), cuts its connection count and tries again after 5 s ([lines 57–59](https://github.com/javi11/nntppool/blob/v5.0.0/nntp.go#L57-L59)). *Inference:* with Newshosting, a refused login (`502 Authentication Failed`) looks the same to AltMount as a connection limit. A diagnosis should test the login directly (section 7, case N2).

### 1.2 Timeouts

- AltMount gives each segment fetch 15 s per attempt and retries once ([usenet_reader.go, lines 830–835 and 890–899](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/usenet/usenet_reader.go#L890-L899)). nntppool names a timed-out attempt `"<provider>: attempt expired after <time> awaiting dispatch"` (no free connection: "the provider is saturated") or `"... awaiting response"` (sent, no answer) ([nntppool errors.go, lines 9–44](https://github.com/javi11/nntppool/blob/v5.0.0/errors.go#L9-L44)).
- A missing article is slow to answer. nntppool's own notes: "slow spool lookups for aged articles have been measured at ~7.5s to a 430 on a healthy connection" ([errors.go, lines 13–14](https://github.com/javi11/nntppool/blob/v5.0.0/errors.go#L13-L14)), and "Newshosting takes ~1.2 s per 430 and serialises them per connection", so checking a mostly dead release "parks every connection it touches for seconds" and once dropped live playback "from ~70 MB/s to ~5 MB/s" ([nntp.go, lines 773–778](https://github.com/javi11/nntppool/blob/v5.0.0/nntp.go#L773-L778)). *Inference:* a slow stream next to a health check of a dead Source is a sign in its own right, not a provider outage.
- AltMount stops a read from the player after `streaming.read_timeout_seconds` (120 s on the live copy) and logs `Read exceeded the streaming read timeout, interrupting reader` ([metadata_remote_file.go, line 1095](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/nzbfilesystem/metadata_remote_file.go#L1095)).

---

## 2. Missing or damaged articles

### 2.1 The ways an article goes missing

1. **Takedown.** A rights holder names articles by message-id and the provider deletes them: "the copyright holder identifies specific articles by their Message-IDs" and "the provider removes those articles from their servers" ([NewsDemon](https://www.newsdemon.com/usenet-takedowns)). *Inference:* notices name the articles of a whole post, so a takedown usually removes many segments of every file at once, often all of them.
2. **Past retention.** The article is older than the provider keeps. Newshosting claims "6636+ days" ([Newshosting](https://www.newshosting.com/usenet/what-is-usenet-article-retention/)), so for Newshosting this is rare; it matters for a fallback provider with shorter retention (section 5).
3. **Incomplete post.** Some segments never reached the servers when it was posted, or the NZB lists articles that do not belong to the file. The NZB's subject line says how many segments to expect: "The segment counter (xx/yy) ... is replaced with (1/yy). You can use the yy to confirm all segments are present" ([NZB spec](https://sabnzbd.org/wiki/extra/nzb-spec)).
4. **A transient miss.** A provider can answer `430` and then serve the same article moments later. AltMount's code says so: "A 430 is not proof the article is gone: backends desync and serve the same segment moments later (issue #749)" ([usenet_reader.go, lines 209–212](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/usenet/usenet_reader.go#L209-L212); [issue #749](https://github.com/kipsilabs/altmount/issues/749), "Streaming failure detected played half-way. File okay when re-added").

### 2.2 Damaged articles: yEnc CRC errors

The article is there but its bytes are wrong. yEnc carries the part's size, its `begin`/`end` position and a `pcrc32` checksum; if the sizes differ "the attachment is corrupt" and the decoded part "must be discarded" ([yEnc 1.3](http://www.yenc.org/yenc-draft.1.3.txt), "Trailer lines" and "Multipart binaries"). The spec also says "Advanced newsreaders might fetch corrupt messages even from other sources".

- nntppool returns the body together with the error `nntp: yEnc CRC mismatch` ([errors.go, line 84](https://github.com/javi11/nntppool/blob/v5.0.0/errors.go#L84); [client.go, lines 264–266](https://github.com/javi11/nntppool/blob/v5.0.0/client.go#L264-L266)). AltMount turns it into a "data corruption" error that goes to its repair pipeline ([usenet_reader.go, lines 250–268 and 867–874](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/usenet/usenet_reader.go#L250-L268)).
- NZBGet logs `Decoding <article> failed: CRC-Error` and tries the next server ([ArticleDownloader.cpp, lines 537–540 and 69–70](https://github.com/nzbgetcom/nzbget/blob/3064f1cf69788e2f3bd536f68153524ceadd85b7/daemon/nntp/ArticleDownloader.cpp#L537-L540)). SABnzbd logs `CRC Error in <article>` ([decoder.py, lines 242–247](https://github.com/sabnzbd/sabnzbd/blob/4d9d9953d4315b27e61d083909de36888e8fc8db/sabnzbd/decoder.py#L242-L247)).
- AltMount does not zero-fill a corrupt segment; only missing ones (section 6.4).

### 2.3 Telling the cases apart

| What you see | Most likely cause | Why |
|---|---|---|
| Every sampled segment of every file answers `430` | takedown, or past retention | whole post gone |
| A few scattered `430`s, the rest `223` | incomplete post, or a few articles removed | damage, not removal |
| `430`s only at the end of a file, beyond what its size needs | the NZB lists extra dead articles past the file's end; harmless | AltMount checks for this: [past_end.go, lines 48–57](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/importer/parser/past_end.go#L48-L57) |
| `430`s only in a separately posted `.nfo` or other small side file | a side file expired on its own; says nothing about the video | [processor.go, lines 556–558](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/importer/processor.go#L556-L558) |
| Segment numbers missing from the NZB itself (1, 2, 4, 5 …) | the NZB is incomplete; no provider is involved | [gaps.go, lines 26–39](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/importer/parser/gaps.go#L26-L39) |
| `430` once, `223` a moment later | a transient miss (2.1, point 4) | |
| `223`, but BODY gives a CRC mismatch | a damaged article | |
| `223` on Newshosting, `430` on another provider (or the reverse) | the two are on different backbones, or one has had a takedown the other has not | section 5 |
| Old post date (NZB `date` attribute) beyond a provider's retention | past retention on that provider | the NZB `date` is "not completely reliable" ([NZB spec](https://sabnzbd.org/wiki/extra/nzb-spec)) |

AltMount uses the same split. Its import check samples the release in a first wave of 8 articles; if at least 8 are missing and at least half of those checked are missing, the release is judged dead: `Fast-fail release probe judged the release dead from its first wave` ([fast_fail_verdict.go, lines 22 and 115](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/importer/validation/fast_fail_verdict.go#L115); thresholds in [fast_fail.go, lines 222–223 and 240–242](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/importer/validation/fast_fail.go#L222-L242)). Otherwise a single miss sends it to a slower per-file check that maps exactly which files are broken ([processor.go, lines 569–580](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/importer/processor.go#L569-L580)).

SABnzbd measures "availability": the share of non-PAR2 bytes present, and allows up to 5 bad articles regardless ([nzb/object.py, lines 1295–1321](https://github.com/sabnzbd/sabnzbd/blob/4d9d9953d4315b27e61d083909de36888e8fc8db/sabnzbd/nzb/object.py#L1295-L1321); [constants.py, line 94](https://github.com/sabnzbd/sabnzbd/blob/4d9d9953d4315b27e61d083909de36888e8fc8db/sabnzbd/constants.py#L94)). When it can't finish it says `Aborted, cannot be completed` ([object.py, line 946](https://github.com/sabnzbd/sabnzbd/blob/4d9d9953d4315b27e61d083909de36888e8fc8db/sabnzbd/nzb/object.py#L946)). NZBGet computes a "critical health": how much may be missing before the PAR2 files can no longer repair it ([DownloadInfo.cpp, lines 334–351](https://github.com/nzbgetcom/nzbget/blob/3064f1cf69788e2f3bd536f68153524ceadd85b7/daemon/queue/DownloadInfo.cpp#L334-L351)).

### 2.4 What a sampling health check can and cannot prove

KaijuFlow's health check STATs a few segments: 3 (first, middle, last) or 7 spread across the file, or one per part across an archive set ([healthCheckPipeline.ts, lines 280–321](../../../src/health/healthCheckPipeline.ts); [archiveGrouper.ts, lines 70–114](../../../src/health/archiveGrouper.ts)). AltMount's own import check samples 1% of segments (`import.segment_sample_percentage: 1` on the live copy; default 1, [config/manager.go, line 2299](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/config/manager.go#L2299)).

It **can** prove:
- that a whole-post removal has *not* happened (a takedown or retention loss takes out every sample);
- that the provider is reachable and the login works (if the samples answer at all).

It **cannot** prove:
- that every segment is there. *Inference:* if a post has *k* missing segments out of *n* and the check samples *s* at random, the chance it sees none of them is about (1 − k/n)^s. With 3 samples, 10 missing segments out of 5,000 go unseen about 99% of the time. KaijuFlow's samples are fixed positions, not random, so the same holes are always missed.
- that the bytes are right: `223` says the server knows the message-id, not that the yEnc CRC will match ([RFC 3977 §6.2.4](https://www.rfc-editor.org/rfc/rfc3977#section-6.2.4): STAT "behaves identically to the ARTICLE command except that ... the article ... is NOT presented"). AltMount itself saw an article that exists but whose fetch still fails, and logs `article exists but a second fetch failed, treating the miss as real` ([usenet_reader.go, lines 786–790](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/usenet/usenet_reader.go#L786-L790)).
- that the Backend can stream what is inside. That is why ADR 0009 checks archive type, not only articles ([ADR 0009](../../adr/0009-health-check-passes-what-altmount-streams.md)).
- that a `430` is permanent (2.1, point 4).

How KaijuFlow's check reads the answers matters for diagnosis. Its STAT reader counts `223` as present and `430` as missing, but also counts **every other three-digit code as missing**, and, when the server closes the connection, counts **all still-unanswered articles as missing** ([articleChecker.ts, lines 59–74 and 95–106](../../../src/health/articleChecker.ts)). *Inference:* a `400`, `480`, `502` or a dropped connection in the middle of a check shows up as `Missing N of M segments`, the same message a real takedown gives ([healthCheckPipeline.ts, line 359](../../../src/health/healthCheckPipeline.ts)). A diagnosis should not trust that message alone; the check's log line `Unexpected NNTP response during article check: <line>` ([articleChecker.ts, line 72](../../../src/health/articleChecker.ts)) is the sign it was not a real miss.

---

## 3. Archives

### 3.1 RAR4 and RAR5, and how volumes are put in order

- A RAR5 file starts with the 8 bytes `52 61 72 21 1A 07 01 00` ("Rar!" + 3 bytes); RAR4 with the 7 bytes `52 61 72 21 1A 07 00` ([RAR 5 technote](https://www.rarlab.com/technote.htm), "RAR 5.0 signature").
- In RAR5, the main archive header of every volume except the first carries its **volume number**: "Not present for first volume, 1 for second volume, 2 for third and so on" (flag `0x0002`), and flag `0x0001` says "Archive is a part of multivolume set" ([technote](https://www.rarlab.com/technote.htm), "Main archive header"). So the first article of each part tells its real place.
- In RAR4 the main header has only a "first volume" flag (`MHD_FIRSTVOLUME 0x0100`); the volume number is stored in the **end-of-archive** header (`EARC_VOLNUMBER 0x0008`) ([unrar headers.hpp, lines 37 and 73](https://github.com/pmachapman/unrar/blob/master/headers.hpp#L37), a mirror of RARLAB's unrar source). *Inference:* that is at the end of each volume, so ordering a RAR4 set means reading the last article of every part, not the first; this is why Unscramble reads RAR5 only ([ADR 0005](../../adr/0005-unscramble-rar-sets-before-upload.md)) and `rarorder.py` reports RAR4 only as `first` or `?` ([rarorder.py, lines 51–53](../../../tools/brain/rarorder.py)).
- Names follow three schemes: `name.partNN.rar`; `name.rar` then `name.r00`, `name.r01` … (rolling to `.s00` after `.r99`); and `name.001`, `name.002` ([AltMount rarname.go, lines 12–39](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/importer/rarname/rarname.go#L12-L39)).
- AltMount v0.4.0 puts volumes in order **by name**: it finds the part numbered 0 ([rar/processor.go, lines 411–451](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/importer/archive/rar/processor.go#L411-L451)) and keeps each name's number ([rar/utils.go, lines 497–560](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/importer/archive/rar/utils.go#L497-L560)). Files with no extension at all are renamed `.r00`, `.r01` … in NZB order (same lines). rardecode then works out each next volume's name from a fixed digit width; AltMount notes that "a set numbered without consistent padding (e.g. part09 → part010) can make it stop early" ([rar/processor.go, lines 207–212](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/importer/archive/rar/processor.go#L207-L212)).

### 3.2 Missing volumes

- If the volumes rardecode followed cover much less than the volumes supplied, AltMount fails with `RAR archive "<name>" is truncated: followed <a> of <b> volume bytes across <c> of <d> volumes` ([rar/processor.go, lines 301–304](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/importer/archive/rar/processor.go#L301-L304)).
- If a file inside is not covered by its segments: `RAR file "<name>" is incomplete: segments cover only <a> of <b> bytes` ([lines 353–356](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/importer/archive/rar/processor.go#L353-L356)).
- One missing segment's worth of bytes is patched by repeating a segment; more than about 800 KB fails with `missing <n> bytes exceeds single segment threshold (800000 bytes), cannot auto-patch`, inside `incomplete NZB data for <file> (part <volume>): ...` ([lines 636–700](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/importer/archive/rar/processor.go#L636-L700)).
- A volume whose last article is gone but whose headers were read is let through; "the missing bytes surface as a hole at read time" ([lines 176–183](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/importer/archive/rar/processor.go#L176-L183)).
- rardecode's own words for a set that ends too soon: `rardecode: multi-volume archive continues in next file`, `rardecode: unexpected end of archive`, `rardecode: bad volume number` ([archive.go, line 27](https://github.com/javi11/rardecode/blob/v2.2.4/archive.go#L27); [reader.go, line 34](https://github.com/javi11/rardecode/blob/v2.2.4/reader.go#L34); [archive50.go, line 80](https://github.com/javi11/rardecode/blob/v2.2.4/archive50.go#L80)), wrapped by AltMount as `failed to iterate RAR archive "<name>": <rardecode error>` ([rar/processor.go, line 197](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/importer/archive/rar/processor.go#L197)).

### 3.3 Obfuscated names

The poster gives files meaningless names so indexers' copyright robots can't read them. SABnzbd's test for this: "exactly 32 hex digits", "40+ lower case hex digits and/or dots", and similar patterns ([deobfuscate_filenames.py, lines 109–134](https://github.com/sabnzbd/sabnzbd/blob/4d9d9953d4315b27e61d083909de36888e8fc8db/sabnzbd/deobfuscate_filenames.py#L109-L134)).

- A name can be recovered from the PAR2 index: each file is identified by "an MD5 Hash of their name, length and the MD5 Hash of their first 16kB" ([PAR 2.0 spec](https://parchive.github.io/doc/Parity%20Volume%20Set%20Specification%20v2.0.html), "Conventions"). So hashing the first 16 KB of a file and looking it up in the PAR2 gives its real name.
- AltMount v0.4.0 does this, but only when the NZB has a PAR2 index *and* some name is untrustworthy ([parser.go, lines 228–236](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/importer/parser/parser.go#L228-L236)). It also recognises RAR4, RAR5 and 7z by their first bytes ([fileinfo/detector.go, lines 35–51](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/importer/parser/fileinfo/detector.go#L35-L51)).
- *Inference:* a Scrambled RAR set with no PAR2 in its NZB keeps its number names, which AltMount reads as the order; ADR 0005's case. The glossary keeps "obfuscated" and "scrambled" apart for this reason ([GLOSSARY.md](../../../GLOSSARY.md), "Scrambled RAR set").

### 3.4 Stored or compressed

Only a stored archive can be streamed: in RAR5, "Bits 8 - 10 (0x0380 mask) define the compression method ... 0 means no compression" ([technote](https://www.rarlab.com/technote.htm), "Compression information"). A compressed file has to be decompressed from its start, so a seek in the middle is impossible. AltMount's messages:

- `compressed media files are not supported: <name> (uses <method> compression)` ([rar/processor.go, lines 385–388](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/importer/archive/rar/processor.go#L385-L388)); `compressed files are not supported: <name>` (lines 399–402);
- `no valid files found in RAR archive. Compressed or encrypted RARs are not supported` ([line 201](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/importer/archive/rar/processor.go#L201));
- for 7z: `no valid files found in 7zip archive. Compressed or encrypted archives are not supported` and `no valid files found in 7zip archive after filtering. Only uncompressed files are supported` ([sevenzip/processor.go, lines 215 and 238](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/importer/archive/sevenzip/processor.go#L215-L238)). The second is the one KaijuFlow saw for Avengers: Endgame ([ADR 0008](../../adr/0008-kaijuflow-plays-plain-video-only.md)).

A **solid** archive (flag `0x0004`, "Solid archive", or the per-file `0x0040` bit where "RAR continues to use the compression dictionary left after processing preceding files", [technote](https://www.rarlab.com/technote.htm)) is a kind of compressed archive and cannot be streamed either.

### 3.5 Encrypted archives

- RAR5 marks an encrypted archive with an "Archive encryption header" (header type 4) before everything else, which hides even the file list; files can also be encrypted one by one (the "File encryption record") ([technote](https://www.rarlab.com/technote.htm)). rardecode's errors: `rardecode: archive encrypted, password required`, `rardecode: archived files encrypted, password required`, `rardecode: incorrect password` ([archive.go, lines 25–26](https://github.com/javi11/rardecode/blob/v2.2.4/archive.go#L25-L26); [archive50.go, line 75](https://github.com/javi11/rardecode/blob/v2.2.4/archive50.go#L75)).
- An NZB can carry the password: `<meta type="password">` ([NZB spec](https://sabnzbd.org/wiki/extra/nzb-spec), "Metadata Defined Types").
- AltMount v0.4.0 passes a password to rardecode when it has one ([rar/processor.go, lines 168–173](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/importer/archive/rar/processor.go#L168-L173)) and has a decrypting reader for AES ([filesystem/decrypting_fs.go](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/importer/filesystem/decrypting_fs.go)). *Inference:* an encrypted stored RAR with its password in the NZB may stream on AltMount; KaijuFlow blocks it because it was never seen to play (`Encrypted archive (password in NZB)`, [altmountPassRule.ts, line 22](../../../src/health/altmountPassRule.ts); ADR 0009).

### 3.6 PAR2 repair, and what streaming can't do without it

PAR2 rebuilds lost data from "slices", "consecutive equal-sized chunks of each file", with a Reed-Solomon code ([PAR 2.0 spec](https://parchive.github.io/doc/Parity%20Volume%20Set%20Specification%20v2.0.html), "Design goals"). To rebuild one slice you need the recovery blocks and the other slices of the set. *Inference:* a stream reads a few segments ahead of the player; it cannot stop to download and compute over a large part of the set at the moment a hole is reached. So a missing segment inside an archive has only three outcomes: AltMount fills it with zeros (only for a plain video; section 6.4), the stream fails, or an import waits for a repair before playing.

- AltMount v0.4.0 can wait: `Deferring import: archive set has missing articles, queueing PAR2 repair` ([processor.go, line 787](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/importer/processor.go#L787)), but only when PAR2 repair on import is on. On the live copy `par2_repair.enabled` and `par2_repair.repair_on_import` are both `false`, so an archive set with a missing article fails at import.

### 3.7 Nested archives and disc images

- A RAR inside a RAR, or a RAR inside a 7z. AltMount has code for both (`failed to process nested RAR archives`, `nested RAR "<name>" contained no extractable files`, [rar/processor.go, lines 242 and 772–776](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/importer/archive/rar/processor.go#L772-L776); [sevenzip/processor.go, lines 245 and 896–900](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/importer/archive/sevenzip/processor.go#L896-L900)) behind the setting `import.allow_nested_rar_extraction` (unset on the live copy). A zero-filled hole is never allowed in a nested file ([nzbfilesystem/holes.go, lines 33–38](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/nzbfilesystem/holes.go#L33-L38)). KaijuFlow blocks them (`Nested archive`).
- An NZB inside the archive (an "embedded NZB"): `embedded NZB nesting limit exceeded`, `embedded NZB cycle detected`, `invalid embedded NZB` ([nested_nzb_chain.go, lines 40–56](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/importer/nested_nzb_chain.go#L40-L56); [nested_nzb.go, lines 215–268](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/importer/nested_nzb.go#L215-L268)).
- A disc image (`.iso`). AltMount v0.4.0's code expands a Blu-ray ISO by default (`expandEnabled := true`, [processor.go, lines 1255–1260](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/importer/processor.go#L1255-L1260)) and fails with `bare-ISO expansion failed: ...` (line 1293), with ISO/UDF reading errors such as `udf: FSD (tag 256) not found in first 1024 sectors of partition` ([iso/fs.go, line 622](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/importer/archive/iso/fs.go#L622)). KaijuFlow saw AltMount refuse a bare disc image ([ADR 0009](../../adr/0009-health-check-passes-what-altmount-streams.md)). *Inference:* the reason is not pinned down (a DVD rather than Blu-ray image, or `.iso` not being in `import.allowed_file_extensions`); KaijuFlow blocks disc images anyway.

---

## 4. The NZB file

- **Malformed XML.** nzbparser fails with `unable to parse NZB file: <XML error>` ([nzbparser.go, line 98](https://github.com/javi11/nzbparser/blob/v0.5.5/nzbparser.go#L98)); AltMount adds `failed to parse NZB file` ([processor.go, line 1008](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/importer/processor.go#L1008)). An NZB with no files: `embedded NZB contains no files` for an inner one ([nested_nzb.go, line 268](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/importer/nested_nzb.go#L268)); KaijuFlow's own check says `No files in NZB` ([healthCheckPipeline.ts, line 75](../../../src/health/healthCheckPipeline.ts)). An upload that is not `.nzb`: `Only .nzb or .nzb.gz files are allowed` ([nzb_stremio_handlers.go, line 195](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/api/nzb_stremio_handlers.go#L195)).
- **Wrong segment sizes.** The `bytes` attribute is the "Size of the article, in bytes" ([NZB spec](https://sabnzbd.org/wiki/extra/nzb-spec)), i.e. the encoded article, a little larger than the video bytes it carries. A stream needs the decoded size of each segment to know which segment holds byte *x*. AltMount does not trust the NZB here: it reads the yEnc header of a first and a middle segment (`=ybegin ... size=`, `=ypart begin= end=`) and rebuilds every segment's size from it ([parser.go, lines 241–260 and 282–340](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/importer/parser/parser.go#L282-L340)); it also reads the file size posters put at the end of the subject (`... yEnc (1/170) 710427259`, [subjectsize.go, lines 10–23](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/importer/parser/subjectsize.go#L10-L23)). Its checks: `file '<name>' is incomplete: expected <a> bytes (decrypted) but found <b> bytes (missing <c> bytes)` ([validation/segments.go, line 71](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/importer/validation/segments.go#L71)), `non-positive size <n> in segment <i> for file <name>` (line 43), `metadata gap: only <a> of <b> bytes are covered by segments` ([usenet/range.go, line 211](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/usenet/range.go#L211)). *Inference:* when the sizes are wrong in a way these checks miss, a seek lands on the wrong bytes: the video plays from the start but breaks or freezes after a jump.
- **Wrong segment count / gaps in numbering.** The subject's `(1/yy)` gives the expected count. AltMount fills gaps in the numbering with placeholders so later bytes keep their positions, but only up to a quarter of the file, since "the numbering is more likely wrong than the post damaged" beyond that; it logs `NZB omits articles; inserted gap placeholders` ([gaps.go, lines 10–39](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/importer/parser/gaps.go#L10-L39); [processor.go, line 1032](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/importer/processor.go#L1032)). It also knows that "Obfuscating posters randomise N", so differing `(1/N)` totals may be fake ([gaps.go, lines 55–58](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/importer/parser/gaps.go#L55-L58)). An empty message-id: `empty message ID in segment <i> for file <name> (cannot retrieve data)` ([validation/segments.go, line 47](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/importer/validation/segments.go#L47)).
- **Duplicate posts.** The same file listed twice, or a segment listed twice. nzbparser can keep "only the first occurrence of duplicate file entries" and drop duplicate segments ([nzbparser.go, lines 24 and 225–252](https://github.com/javi11/nzbparser/blob/v0.5.5/nzbparser.go#L225-L252)), and it sorts files and segments by number ([lines 122–126](https://github.com/javi11/nzbparser/blob/v0.5.5/nzbparser.go#L122-L126)). *Inference:* a duplicate counted twice makes a file look bigger than it is, which trips the "incomplete" checks above; reposts of the same release under a new name are separate Sources with separate articles, so one can be gone while the other plays.
- **The poster's name and subject.** `poster` is a "Copy of the From: field", `subject` "A slightly munged copy of the article's subject" ([NZB spec](https://sabnzbd.org/wiki/extra/nzb-spec)). Obfuscating posters use random poster names and subjects; the file name in the subject then means nothing (section 3.3). KaijuFlow's tools read the name between quotes in the subject ([statcheck.py](../../../tools/brain/statcheck.py), `articles()`), so they inherit this.

---

## 5. Provider-side

- **Backbones.** Brands that resell one backbone share its storage: "Providers that share a backbone share the same takedown processing. When an article is removed from the shared backbone, it disappears from every provider on that backbone simultaneously" ([NewsDemon](https://www.newsdemon.com/usenet-takedowns); a vendor page selling its own backbone, so a vendor's claim). Newshosting says it gives "direct access to a Tier-1 Usenet backbone" whose servers are not "rented from third parties" ([Newshosting KB 1600](https://support.newshosting.com/kb/article/1600-newshosting-advantages-of-a-tier-1-usenet-provider/)).
- **What "same backbone" means for a fallback provider.** A **fill** or **backup** server is asked only when the main one says an article is missing: "If the primary server responds that an article is unavailable, NZBGet automatically attempts to retrieve that article from the next server in the priority list" ([NZBGet docs](https://nzbget.com/documentation/primary-vs-fill-servers-explained/)). nntppool works the same way (`Backup ... only used when main providers return 430`), and lets an operator mark providers that "resell the same upstream storage under different hostnames (e.g. two brands on one backbone)" with a `StorageGroup`, so "a 430 from one skips the rest in the group" ([nntp.go, lines 2038–2039 and 3096–3104](https://github.com/javi11/nntppool/blob/v5.0.0/nntp.go#L3096-L3104)). *Inference:* a fallback on the same backbone as Newshosting adds connections, not articles; after a takedown it is missing exactly what Newshosting is missing. The live AltMount has one provider (`providers[0]`, Newshosting, 25 connections, not a backup), so there is no fallback at all today.
- **Retention per provider.** A provider can declare how far back it reaches. nntppool asks an in-range provider first and an over-age one last, and skips it entirely with `StrictMaxAge` ([retention.go, lines 18–56](https://github.com/javi11/nntppool/blob/v5.0.0/retention.go#L18-L56)). On the live copy `max_article_age_days` is 0 (no limit declared).
- **Takedowns per provider.** Takedowns are per provider and per country: "Takedown notices remove articles from the specific provider that receives the notice" ([NewsDemon](https://www.newsdemon.com/usenet-takedowns)). This is why a different backbone can fill a takedown gap.
- **Rate and connection limits.** A plan has a connection count (Newshosting's help cites up to 100 on some plans, [KB 1014](https://support.newshosting.com/kb/article/1014-502-max-connections-reached/)). Going over gives `502` (section 1.1). The same account used by AltMount, KaijuFlow's health check and Unscramble at once shares one limit; KaijuFlow's tests showed its own checks and Unscramble share one process-wide cap ([ADR 0005](../../adr/0005-unscramble-rar-sets-before-upload.md), amendment of 2026-11-23). *Inference:* the provider counts AltMount's 25 connections and KaijuFlow's together. A quota (bytes per period) is a client setting in nntppool (`nntp: download quota exceeded`, [errors.go, line 86](https://github.com/javi11/nntppool/blob/v5.0.0/errors.go#L86)), not a server answer.
- **DNS.** The name `news.newshosting.com` must turn into a real address. On 2026-11-17 the home router answered it "with a dead 10.x address", so a **DNS sinkhole** (a name pointed at a dead address on purpose, here by the router) broke every connection; the run preflight now refuses a 10.x answer or a failed lookup ([tools/brain/docs/rules.md, check 9](../../../tools/brain/docs/rules.md); [RUNBOOK.md, step 4](../../../tools/brain/RUNBOOK.md)). *Inference:* to AltMount this looks like a connection that never opens (a timeout, not a code), so every segment fails as a transport error, never as `430`. A program in a container may use a different DNS server than the machine, so the preflight passing does not prove AltMount resolves the name the same way.

---

## 6. AltMount: how it reads, what it checks, what it says

### 6.1 The import (when KaijuFlow uploads the NZB)

KaijuFlow posts the NZB to `POST /api/nzb/streams` with category `kaijuflow` and waits for the answer ([src/backends/altmount.ts, lines 264–281](../../../src/backends/altmount.ts)). AltMount then:

1. puts gap placeholders into the NZB (section 4) — `NZB omits articles; inserted gap placeholders`;
2. runs the **fast-fail check**, stage `Checking segment availability` ([processor.go, line 1040](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/importer/processor.go#L1040)): STATs 1% of the release, first 8 articles then the rest (section 2.3);
3. if something is missing: trims dead articles past a file's end and checks again; maps exactly which files are broken (`Mapping missing segments`); lets a plain video with damage within `acceptable_missing_segments_percentage` (2 on the live copy) import "degraded" — `Importing file as degraded despite missing segments (within acceptable-missing threshold)` ([line 671](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/importer/processor.go#L671)); otherwise logs `Skipping file due to early fast-fail segment check error` ([line 697](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/importer/processor.go#L697)). A missing segment in an archive set breaks the whole set ([lines 761–777](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/importer/processor.go#L761-L777)). If nothing importable is left, the release fails ([line 798](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/importer/processor.go#L798)).
4. reads the first segments of every file, recovers names from PAR2 if useful, and normalises segment sizes from yEnc headers (sections 3.3, 4);
5. reads the archive headers (section 3) and writes the file layout ("metadata") it will stream from.

The error a failed import leaves is the text of the Go error chain. The common ones (the outer words are added by [processor.go, lines 1071–1087](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/importer/processor.go#L1071-L1087)):

| Text | Meaning |
|---|---|
| `fast-fail segment check failed: no regular files were successfully processed (all files failed validation)` | missing articles left nothing to import ([multifile/processor.go, line 25](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/importer/multifile/processor.go#L25)) |
| `no files were successfully processed (all files failed validation)` | the same, from the archive step ([archive/common.go, line 34](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/importer/archive/common.go#L34)); KaijuFlow saw it for a Scrambled RAR4 set ([ADR 0008](../../adr/0008-kaijuflow-plays-plain-video-only.md)) |
| `fast-fail segment check inconclusive: fast-fail validation inconclusive: <n> segment(s) remained unverified after <k> attempts: ...` | the check could not get answers (timeouts, connection trouble); says nothing about the Source ([fast_fail.go, lines 34 and 186](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/importer/validation/fast_fail.go#L186)) |
| `cannot fast-fail import: usenet connection pool unavailable: ...` | AltMount has no working provider ([fast_fail_verdict.go, line 72](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/importer/validation/fast_fail_verdict.go#L72)) |
| `NZB validation failed: ...` | the NZB's own data does not add up (section 4) |
| `corrupted file: missing <n> bytes (<p>% of total size)` | segments don't cover the file ([archive/common.go, line 142](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/importer/archive/common.go#L142)) |
| `failed to iterate RAR archive "<name>": ...`, `RAR archive ... is truncated ...`, `compressed media files are not supported ...`, `no valid first RAR part found in archive` | archive cases (section 3) |
| `NZB processing timed out` (HTTP 408) | the import did not finish within the wait ([nzb_stremio_handlers.go, lines 433–435](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/api/nzb_stremio_handlers.go#L433-L435)) |

**Where the text shows.** The HTTP answer is `500` with JSON `{"success":false,"error":{"code":...,"message":...,"details":...}}` ([api/response.go, lines 69–78](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/api/response.go#L69-L78)). On a fresh import the error text is the `message` ([nzb_stremio_handlers.go, lines 424–430](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/api/nzb_stremio_handlers.go#L424-L430)). For a queue item that had already failed, the `message` is only `NZB processing failed` and the real text is in `details` (line 364), which AltMount empties outside development mode ([response.go, lines 16–23](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/api/response.go#L16-L23)). *Inference:* a re-upload of the same failed NZB loses the reason; AltMount's own log (`/config/altmount.log`) and its queue still hold it. KaijuFlow logs the first 300 characters as `AltMount could not process the Source: <text>` ([altmount.ts, lines 290–304](../../../src/backends/altmount.ts)).

*Inference, worth a ticket:* KaijuFlow treats every `500` as a bad Source unless the text matches a short list of AltMount-side failures ([altmount.ts, line 98](../../../src/backends/altmount.ts)). The "inconclusive" and "connection pool unavailable" texts above are not on that list, so a provider or DNS outage during AltMount's import would mark a good Source dead, against [ADR 0004](../../adr/0004-dead-means-bad-source.md). Not tested.

### 6.2 Reading segments on demand (when the player plays)

The player asks `GET /api/files/stream?path=...` with a byte range ([altmount.ts, line 180](../../../src/backends/altmount.ts)). AltMount opens the stored layout, works out which segments hold those bytes, and fetches them from the provider, up to `streaming.max_prefetch` (60) segments ahead ([config/manager.go, lines 1206–1207](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/config/manager.go#L1206-L1207)). For a stored RAR the bytes of the video are bytes of the volumes, so the same works inside an archive. Go's `http.ServeContent` sends the answer ([api/stream_handler.go, line 248](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/api/stream_handler.go#L248); [Go docs](https://pkg.go.dev/net/http#ServeContent)).

Per segment ([usenet_reader.go, lines 761–790 and 890–910](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/usenet/usenet_reader.go#L761-L790)):

- a `430`/`423` from every provider is "permanent failure — do not retry", except one quick re-check (STAT, 2 s) per reader; if the re-check finds it, it logs `article present on re-check, retrying transient miss`;
- a timeout is retried at once; other errors once, after 50–150 ms;
- a CRC mismatch becomes a data-corruption error.

### 6.3 What the player sees when a read fails

- Before any byte is sent, a file that can't be opened gives `File not found` (404) or `Failed to open file` (500) ([stream_handler.go, lines 179–186](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/api/stream_handler.go#L179-L186)). Over WebDAV, a file with missing articles gives 404 `File unavailable due to missing articles` ([webdav/file_system.go, lines 98–104](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/webdav/file_system.go#L98-L104)).
- After the answer has started, a failed segment can't change the status code any more. *Inference:* the player gets a shorter body than promised and the connection ends; in KaijuFlow this shows as a dropped connection or a frozen video, not as an HTTP error.
- AltMount's log then says one of: `Missing segment exceeds padding caps, failing stream` ([nzbfilesystem/holes.go, line 130](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/nzbfilesystem/holes.go#L130)); `Streaming failure not confirmed on re-check, not condemning the file` ([metadata_remote_file.go, line 2649](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/nzbfilesystem/metadata_remote_file.go#L2649)); `Streaming failure detected, triggering immediate ARR repair`, `... but masked (threshold not reached), skipping repair`, `... but health system disabled, marking corrupted without triggering repair`, or `... deleting corrupted file instead of triggering repair` ([lines 2742–2815](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/nzbfilesystem/metadata_remote_file.go#L2742-L2815)). nntppool's last-resort error is `nntp: all providers exhausted: <last error>` ([nntp.go, lines 3663–3669](https://github.com/javi11/nntppool/blob/v5.0.0/nntp.go#L3663-L3669)).

### 6.4 Holes: zero-filling a missing segment

For a plain, unencrypted, non-nested video file, AltMount fills a missing segment with zeros and plays on, within caps: at most 4 missing segments in a row, 64 in all, and 2% of the file ([holes/holes.go, lines 25–36](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/holes/holes.go#L25-L36); [nzbfilesystem/holes.go, lines 33–38](https://github.com/kipsilabs/altmount/blob/v0.4.0/internal/nzbfilesystem/holes.go#L33-L38)). The file is then marked degraded. *Inference:* a few zeroed segments show as a short glitch or a jump, not a stop; a stop means the caps were exceeded, the file was not eligible (archive member, encrypted, nested), or the damage was a CRC error rather than a missing article.

---

## 7. The casebook

Each case: **signs** (the exact text, code or pattern, and where it shows) and a **confirming test** a tool could run afterwards. "KF log" means KaijuFlow's log; "AM log" means AltMount's log or queue item.

**Before the tests can run.** `tools/brain/nntp.py` reads the provider from `~/altmount-stack/config/config.yaml` ([nntp.py, line 4](../../../tools/brain/nntp.py)); that file does not exist on Brain today (checked 2026-11-24; the test copies keep their configs under `~/kaijuflow-test`, which the guard hook keeps closed). So `statcheck.py` and `rarorder.py` need that path fixed, or the provider passed in, before a diagnosis tool can use them. Their STAT reader also counts only `223` as present, so the same caution as section 2.4 applies.

### Articles

**A1. Whole post gone (takedown or retention).**
Signs: KF check `Missing 3 of 3 segments` (or 7 of 7); AM log `Fast-fail release probe judged the release dead from its first wave`; AM error `fast-fail segment check failed: no regular files were successfully processed (all files failed validation)`.
Test: `python3 -I tools/brain/statcheck.py <file.nzb>` (STAT every article). Confirmed if nearly every article of every file answers `430` *and* a fresh STAT of the same articles a minute later still says `430` (rules out A4). To split takedown from retention: compare the NZB's `date` with the provider's retention (*inference:* within retention means takedown).

**A2. Some segments missing (incomplete post or partial removal).**
Signs: KF check passes (samples found) but AM rejects, or AM log `Fast-fail release probe found a missing segment, escalating to per-file sweep` then `Skipping file due to early fast-fail segment check error`; or the video plays and stops at the same point every time; AM log `Missing segment exceeds padding caps, failing stream`.
Test: `statcheck.py`: confirmed if a minority of articles answer `430`, clustered in one or a few files; also check the NZB's segment numbers against the subject's `(1/yy)` (missing numbers = A2 in the NZB itself, case Z2).

**A3. Damaged article (yEnc CRC).**
Signs: AM error containing `nntp: yEnc CRC mismatch` or `crc mismatch`; STAT says `223` for the failing segment.
Test: BODY the segment named in AM's log (the `segment_id` field), decode it and compare the computed CRC32 with `pcrc32=` in its `=yend` line ([yEnc 1.3](http://www.yenc.org/yenc-draft.1.3.txt)). `rarorder.py`'s `ydecode()` does the decoding but no CRC check yet; *inference:* adding one is a few lines.

**A4. Transient miss.**
Signs: AM log `article present on re-check, retrying transient miss` or `Streaming failure not confirmed on re-check, not condemning the file`; the same Source plays on a second try.
Test: STAT the failing segment three times a few seconds apart; confirmed if any answer is `223`.

**A5. Extra dead articles past a file's end (harmless).**
Signs: misses only at the very end of a file; AM trims them and imports.
Test: compare the number of segments the file needs (decoded size ÷ part size from the yEnc header) with the number listed; confirmed if only the extras answer `430`.

### Archives

**R1. Scrambled RAR set (numbers that don't match volume order).**
Signs: names like `<hash>.10` … `<hash>.103`; AM `no files were successfully processed (all files failed validation)` or `RAR archive "<name>" is truncated: ...`; KF log `unscramble` step with a reason other than success.
Test: `python3 -I tools/brain/rarorder.py <file.nzb>`: confirmed if the RAR5 volume numbers read from the first article of each part do not follow the name numbers. For RAR4 it can only tell `first` or `?`.

**R2. Missing volume.**
Signs: AM `RAR archive ... is truncated: followed <a> of <b> volume bytes across <c> of <d> volumes` or `failed to iterate RAR archive ...: rardecode: multi-volume archive continues in next file`.
Test: `rarorder.py` (RAR5): confirmed if a volume number is absent from the sequence 0…N; or STAT the first article of each part (a part whose first article is `430` is a missing volume in practice).

**R3. Badly padded names (`part09` → `part010`).**
Signs: AM `... is truncated ...` with all articles present.
Test: list the names; confirmed if the digit count changes within the set and `statcheck.py` finds nothing missing.

**R4. Compressed or solid archive.**
Signs: AM `compressed media files are not supported: <name> (uses <method> compression)`, `no valid files found in RAR archive. Compressed or encrypted RARs are not supported`, or the 7z `Only uncompressed files are supported`; KF check `Compressed archive`.
Test: read the file header from the first article: RAR5 compression method bits `0x0380` not 0, or solid flag `0x0040` ([technote](https://www.rarlab.com/technote.htm)). KaijuFlow's archive inspection already does this ([src/archive/rar5Parser.ts](../../../src/archive/rar5Parser.ts)).

**R5. Encrypted archive.**
Signs: AM `... Compressed or encrypted RARs are not supported` or a rardecode `password required` / `incorrect password` text; KF `Encrypted archive (no password)` / `(password in NZB)`.
Test: RAR5: an archive encryption header (type 4) right after the signature, or a file encryption record in the file header ([technote](https://www.rarlab.com/technote.htm)); RAR4: `MHD_PASSWORD 0x0080` or `LHD_PASSWORD 0x0004` ([unrar headers.hpp, lines 36 and 41](https://github.com/pmachapman/unrar/blob/master/headers.hpp#L36)). Look for `<meta type="password">` in the NZB.

**R6. Missing segment inside an archive set, no PAR2 repair.**
Signs: AM `fast-fail segment check failed: ...` for a RAR set while `statcheck.py` shows few misses; on the live copy never `Deferring import ...` (repair is off).
Test: `statcheck.py`: confirmed if the misses are inside RAR volumes and `par2_repair.repair_on_import` is `false`.

**R7. Nested archive, embedded NZB, disc image.**
Signs: AM `failed to process nested RAR archives`, `nested RAR ... contained no extractable files`, an `embedded NZB ...` text, or `bare-ISO expansion failed: ...`; KF `Nested archive` / `Disc image`.
Test: list the file names in the archive header (KaijuFlow's archive inspection); confirmed by an inner `.rar`/`.7z`/`.nzb`/`.iso`.

### The NZB

**Z1. Malformed NZB.**
Signs: AM `failed to parse NZB file: unable to parse NZB file: <XML error>`; KF `No files in NZB`.
Test: parse the NZB with an XML parser; confirmed if it fails or yields no `<file>`.

**Z2. Gaps or wrong counts in the NZB.**
Signs: AM log `NZB omits articles; inserted gap placeholders`; or `file '<name>' is incomplete: expected <a> bytes ... but found <b> bytes`.
Test: for each `<file>`, compare the highest segment `number` and the count with `yy` in its subject `(1/yy)`; confirmed if numbers are missing or the count is short. No provider needed.

**Z3. Wrong segment sizes.**
Signs: plays from the start, breaks or shows garbage after a seek; first byte fine.
Test: BODY the first and a middle segment, read `=ybegin size=` and `=ypart begin= end=`, and compare (end − begin + 1) with the NZB's `bytes` (should be a little smaller, about 1–2%, yEnc's overhead). *Inference:* a large mismatch confirms it.

**Z4. Duplicate entries.**
Signs: a file listed twice in the NZB; size checks fail.
Test: count `<file>` entries with the same subject name and segments with the same message-id; confirmed if any repeat.

### Provider and network

**N1. Connection limit.**
Signs: `502` or `400` greeting/AUTHINFO with "connections", "too many", "limit" in the text; nntppool `nntp: server max connections reached`; KF `Unexpected NNTP response during article check: 502 ...` followed by `Missing ...`; several plays or checks at once.
Test: open one connection with `nntp.py`'s `Conn` while nothing else runs; confirmed if it logs in and STAT works, and fails again only when many connections are open (count AltMount's 25 plus KaijuFlow's at the time of the failure).

**N2. Refused login.**
Signs: `481`, or Newshosting's `502 Authentication Failed`; in AltMount it looks like N1 (section 1.1).
Test: one `Conn`: the `AUTHINFO PASS` answer is not `281` (`nntp.py` raises `auth failed`). If it fails with one connection and nothing else running, it is the login, not the limit.

**N3. DNS sinkhole or failed lookup.**
Signs: no NNTP code at all, only connection timeouts or "connection refused"; AM `cannot fast-fail import: usenet connection pool unavailable: ...` or `fast-fail segment check inconclusive: ...`; every Source fails at once.
Test: `dig +short news.newshosting.com @<the home router>`: confirmed if empty or a 10.x address (preflight check 9). Also resolve the name from inside the AltMount container (*inference:* it may use another DNS server).

**N4. Provider slow or saturated.**
Signs: `attempt expired after <t> awaiting dispatch` or `... awaiting response`; AM `Read exceeded the streaming read timeout, interrupting reader`; slow play next to a big health check.
Test: time a STAT of a known-good article and a BODY of one segment, with and without the health check running; confirmed if times rise sharply only under load.

**N5. Backbone difference (once a second provider exists).**
Signs: `223` on one provider, `430` on the other for the same message-id.
Test: STAT the same articles on each provider; confirmed if the answers differ. If both answer `430`, a fallback on the same backbone can't help.

### Seen in KaijuFlow, not a Usenet fault

**K1. Check miss from a non-430 answer.** KF `Missing N of M segments` preceded by `Unexpected NNTP response during article check: ...`. Not a Source problem (section 2.4). Test: re-run the check alone; confirmed if it passes.

**K2. Good Source marked dead after an AltMount-side provider problem.** KF `AltMount could not process the Source: ... inconclusive ...` or `... connection pool unavailable ...`. *Inference* from section 6.1, not yet seen. Test: N3/N4 tests at the time, and the same Source played again after the provider is fine.

---

## 8. What this means for the diagnosis system (my inferences)

- Read **AltMount's error text**, not only KaijuFlow's message: the cases differ in AltMount's words, and KaijuFlow's `Missing N of M segments` hides connection trouble.
- The single most useful test is a full **STAT sweep** of the NZB (`statcheck.py`), repeated once after a short wait: it splits A1, A2, A4, A5 and R6 by how many and which articles are missing, and costs no download.
- The second is reading the **first article of each part** (`rarorder.py`) and the **yEnc header** of a first and middle segment: it splits R1–R5 and Z3.
- Provider cases (N1–N4) are tested with **one connection while nothing else runs**, so the test itself does not add to the load.
- Fix `nntp.py`'s config path first, and make its readers keep the raw code of every answer rather than "present / missing".

## Sources

Standards and formats: [RFC 3977 (NNTP)](https://www.rfc-editor.org/rfc/rfc3977) · [RFC 4643 (NNTP authentication)](https://www.rfc-editor.org/rfc/rfc4643) · [yEnc 1.3](http://www.yenc.org/yenc-draft.1.3.txt) · [NZB spec (SABnzbd wiki copy of Newzbin's)](https://sabnzbd.org/wiki/extra/nzb-spec) · [RAR 5.0 technote](https://www.rarlab.com/technote.htm) · [unrar headers.hpp (mirror)](https://github.com/pmachapman/unrar/blob/master/headers.hpp) · [PAR 2.0 spec](https://parchive.github.io/doc/Parity%20Volume%20Set%20Specification%20v2.0.html) · [Go net/http ServeContent](https://pkg.go.dev/net/http#ServeContent)

Code: [AltMount v0.4.0](https://github.com/kipsilabs/altmount/tree/v0.4.0) · [nntppool v5.0.0](https://github.com/javi11/nntppool/tree/v5.0.0) · [rardecode v2.2.4](https://github.com/javi11/rardecode/tree/v2.2.4) · [nzbparser v0.5.5](https://github.com/javi11/nzbparser/tree/v0.5.5) · [SABnzbd 4d9d995](https://github.com/sabnzbd/sabnzbd/tree/4d9d9953d4315b27e61d083909de36888e8fc8db) · [NZBGet 3064f1c](https://github.com/nzbgetcom/nzbget/tree/3064f1cf69788e2f3bd536f68153524ceadd85b7) · [AltMount issue #749](https://github.com/kipsilabs/altmount/issues/749)

Providers: [Newshosting KB 1014, 502 Max Connections Reached](https://support.newshosting.com/kb/article/1014-502-max-connections-reached/) · [KB 1012, 502 Authentication Failed](https://support.newshosting.com/kb/article/1012-502-authentication-failed/) · [KB 1193, 480 Authentication Required](https://support.newshosting.com/kb/article/1193-480-authentication-required/) · [KB 1600, Tier-1 backbone](https://support.newshosting.com/kb/article/1600-newshosting-advantages-of-a-tier-1-usenet-provider/) · [Newshosting, article retention](https://www.newshosting.com/usenet/what-is-usenet-article-retention/) · [NewsDemon, DMCA vs NTD](https://www.newsdemon.com/usenet-takedowns) · [NZBGet, primary vs fill servers](https://nzbget.com/documentation/primary-vs-fill-servers-explained/)

KaijuFlow: [ADR 0004](../../adr/0004-dead-means-bad-source.md) · [ADR 0005](../../adr/0005-unscramble-rar-sets-before-upload.md) · [ADR 0008](../../adr/0008-kaijuflow-plays-plain-video-only.md) · [ADR 0009](../../adr/0009-health-check-passes-what-altmount-streams.md) · [articleChecker.ts](../../../src/health/articleChecker.ts) · [healthCheckPipeline.ts](../../../src/health/healthCheckPipeline.ts) · [altmountPassRule.ts](../../../src/health/altmountPassRule.ts) · [altmount.ts](../../../src/backends/altmount.ts) · [nntp.py](../../../tools/brain/nntp.py) · [statcheck.py](../../../tools/brain/statcheck.py) · [rarorder.py](../../../tools/brain/rarorder.py)
