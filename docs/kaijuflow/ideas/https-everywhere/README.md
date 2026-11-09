# Idea: HTTPS everywhere (manifest works on Apple and Android, no warnings)

Status: **idea, not planned.** Captured 2026-11-09 from a chat with the owner, to grill later. Nothing here is decided until the grill session settles it, except the starting domain (`thefetchingcat.com`, below).

Research behind this: [`../../research/APPLE_HTTPS_MANIFEST.md`](../../research/APPLE_HTTPS_MANIFEST.md).

## The problem

- A plain `http://192.168.x.x:1337/.../manifest.json` link does not work on Apple devices. Stremio's own addon docs say an addon URL must be on `127.0.0.1` or use HTTPS. Apple adds more blocks: mixed-content blocking in Safari and Stremio Web, App Transport Security in native apps, and the iOS Local Network prompt.
- The owner and a friend could only get Usenet Ultimate working on Apple devices through Tailscale. `tailscale serve` gives a real `https://…ts.net` name with a Let's Encrypt certificate.
- Tailscale was **laggy on an older TV**. The TV has to run the Tailscale app, which encrypts all the video on a weak processor, and traffic can be relayed through Tailscale's servers. So Tailscale is not a main option, a footnote at most.

## Who it's for

People who run **their own KaijuFlow** on their own computer. The goal is that anyone can install KaijuFlow and add the manifest on Android or Apple with no certificate warning and as little setup as possible.

Not the goal: lots of people sharing one server. That has other problems (Usenet provider connection limits and terms, reachability from outside the home, load on one machine).

## Options considered

| Option | Verdict | Why |
| --- | --- | --- |
| Self-signed certificate | No | Every Apple device needs a profile installed and trusted by hand. |
| Let's Encrypt IP-address certificate | No | Needs the server reachable from the internet; a LAN IP can't get one. |
| Tailscale (serve or Funnel) | Footnote only | Works, but laggy on older TVs and every device needs the app. |
| Caddy sidecar in docker-compose | Superseded | Works, with no noticeable speed cost (see below), but it's an extra container and docker editing for users. |
| **KaijuFlow gets the certificate itself** (Let's Encrypt, DNS-01) | **Leaning yes** | One container, one settings page, nothing on the router. |
| Cloudflare Tunnel | Guide only | For use away from home. Cloudflare's terms for video through tunnels are not checked. |

Speed: encryption is not a concern. Brain's i7-8665U measured about 4 GB/s AES-GCM on one core (`openssl speed`, 2026-11-09). A 4K remux at about 100 Mbit/s is under 1% of one core. The slow part is always Usenet, the Backend or WiFi.

## How KaijuFlow would get a certificate itself

1. **Point the name at itself.** It sets a DNS name, like `abc123.kf.thefetchingcat.com`, to point at its LAN IP, and updates it if the IP changes.
2. **Ask Let's Encrypt for a certificate** using the DNS-01 challenge.
3. **Prove ownership.** It puts the challenge code in a TXT record. No public reachability or open ports are needed.
4. **Serve HTTPS** with that certificate on its own port.
5. **Renew automatically**, roughly every 60 days. The private key never leaves the user's machine.

Who puts the DNS records in is the only difference between the two levels below.

### Level 2: zero setup, KaijuFlow's free name (main path)

The same idea as Plex's `plex.direct`. The owner's Porkbun domain plus a small Cloudflare Worker gives every install its own name automatically. The user does nothing: they install, scan the QR code, and it works.

Worker outline (free plan, the domain stays at Porkbun, so nameservers and static hosting are unchanged):

1. Owner's manual steps:
   - Make a free Cloudflare account.
   - Turn on Porkbun API access **for this one domain only** and create an API key and secret.
   - Pick a subdomain for installs, e.g. `kf.thefetchingcat.com`.
2. Set up the project: `npm create cloudflare@latest kaijuflow-names`, then `wrangler secret put PORKBUN_API_KEY` (and the secret). The Porkbun key lives only in the Worker; it is never shipped in KaijuFlow.
3. Add a Workers KV store that records which install owns which name.
4. Add four endpoints:
   - **register**: returns a random name and a per-install password.
   - **set address**: sets the A record.
   - **post challenge**: adds the TXT record.
   - **remove challenge**: deletes it.
5. Abuse guards:
   - Only private (home) IPs are allowed in A records.
   - Each install can only touch its own name.
   - Registrations are rate-limited per IP.
6. Deploy with `wrangler deploy`. Test against **Let's Encrypt staging** on the test container first.

Costs and limits:
- **Cost:** free. The Workers free plan allows 100k requests a day, and each install makes a handful every couple of months.
- **Let's Encrypt cap:** about 50 new certificates per registered domain per week (exact numbers to confirm). Apply for a higher limit if KaijuFlow takes off.

### Level 1: "Advanced: use my own domain" (fallback)

The user's own Porkbun API key or DuckDNS token posts the records, not the Worker. It reuses the Level 2 certificate code (maybe a day of extra work). It's needed for:
- The Worker being down, or no longer run someday (otherwise every user's HTTPS dies when certificates expire).
- The weekly Let's Encrypt cap.
- Users who don't want to register with someone else's service.

Porkbun note: API keys can usually change every domain on the account that has API access on. Turn it on for one domain only.

### Making it easy (applies to both levels)

- **First-launch wizard:** "Want this to work on iPhone, Apple TV and Android?"
- **Home address auto-detected**, so nobody types an IP.
- **Warning banner** when the link is `http://` and not `127.0.0.1`.
- **Automatic test** that the `https://` link works and the certificate is real, with plain-word fixes (e.g. router DNS rebind protection).
- **QR code** and an **Install in Stremio** button (`stremio://` link).
- **README section**, not a separate help site, covering:
  - the router rebind fix
  - away-from-home (Cloudflare Tunnel)
  - what to do if the free name stops working

## KaijuFlow code changes (small, not a rewrite)

KaijuFlow already builds every manifest and stream link from the incoming request: protocol and Host header, plus `X-Forwarded-Port`. See `src/utils/urlHelpers.ts:19-41`, used at `src/server.ts:197,204` and throughout `src/nzbdav/streamHandler.ts`. A request over `https://abc123.kf.thefetchingcat.com` already gets `https://abc123.kf.thefetchingcat.com` links back. The changes:

1. **Show the HTTPS link** in the settings page, QR code and install button once it's on.
2. **`BASE_URL` override** (`src/utils/urlHelpers.ts:20-23`). An `http://` `BASE_URL` currently wins over everything. Requests that arrive over HTTPS must not get an `http` base.
3. **`direct` delivery mode** 302-redirects to the plain-http Backend URL (`src/nzbdav/streamHandler.ts:545, 750-753, 864`, `directUrl` at `src/backends/altmount.ts:278`). Over HTTPS it must behave like `proxy`. This keeps every Backend (NzbDAV, AltMount) behind one HTTPS front door.
4. **Background jobs** (health checks, auto-queue) keep calling KaijuFlow over loopback (`src/addon/streamBuilder.ts:43`). No change.
5. **Keep the `http://` port working** alongside HTTPS so nothing breaks on update. Some apps already work over http on Android TVs (e.g. ARVIO). Users reinstall the addon once with the new link, because Stremio stores the exact install URL.

## Domain (decided to start)

- **`thefetchingcat.com`** (Porkbun, Porkbun nameservers) is the starting domain. On 2026-11-09 the owner removed the old website records. A `dig` that day returned no A records for the root, `www`, or a random subdomain, so the parking-page wildcard is gone too.
- The old site sent `Strict-Transport-Security: max-age=31536000; includeSubDomains`. Browsers that visited it will force HTTPS on every subdomain for up to a year. That's harmless here because the plan is HTTPS-only, but plain `http://` on a `thefetchingcat.com` name will not work in those browsers.
- A dedicated domain (like Plex's separate `plex.direct`) can come later if KaijuFlow is shared widely. Ruled out for now: `.lol`, because some blockers filter cheap endings, and `.us`, because WHOIS privacy isn't allowed (both unverified, from general knowledge).

## Deliverables the owner asked for

1. **An owner setup walkthrough**: plain-language, step by step, with every click in Porkbun and Cloudflare and every command on Brain, written so the owner can follow it alone. It covers:
   - Porkbun API access for `thefetchingcat.com` only
   - the Cloudflare account and Worker deploy
   - the secrets
   - a staging test on the test container
   - switching to the real Let's Encrypt
   - how to check it's healthy later
2. **The easiest possible user experience.** The target is zero setup: install KaijuFlow, open it, scan a QR code or tap "Install in Stremio", and it works on Android and Apple with no warnings. Every manual step that remains has to justify itself in the grill.

## Open questions for the grill

- Domain layout on `thefetchingcat.com`: which subdomain holds user names (`kf.`, `u.`, …)? Does the root stay empty, or get a KaijuFlow landing page (served by the Worker or GitHub Pages)?
- Is the owner OK running the Worker long-term, with every user depending on it?
- Name format: random id (`abc123.kf.thefetchingcat.com`) or IP-in-name like Plex (`192-168-1-50.abc123…`)? IP-in-name needs a custom DNS server, not just Porkbun records.
- Which HTTPS port? (1338 is the Brain test container; pick something else, e.g. 8443.)
- Keep HTTPS opt-in, or on by default with the wizard?
- Should `http://` stay on forever, or be switchable off?
- Over HTTPS, force `direct` to `proxy` silently, or warn?
- `BASE_URL` precedence once HTTPS exists: ignore an `http` value on HTTPS requests, or replace the setting?
- Level 1 providers: Porkbun and DuckDNS only, or Cloudflare DNS too?
- What happens to users if the Worker disappears: in-app prompt to switch to Level 1?
- Privacy note: the Worker sees each install's public IP and LAN IP. Say so in the README?
- Away from home: Cloudflare Tunnel guide only, or build anything?
- Build order: Level 2 first, then Level 1, then README (current leaning), or Level 1 first because it has no service to run?
- ACME library choice for Node (e.g. `acme-client`), and where certificates and keys are stored in the config volume.

## To verify before building (primary sources)

- DuckDNS: accepts a private IP in the A record; TXT-record API.
- Porkbun API: create/delete TXT and A endpoints, per-domain API toggle, rate limits.
- Let's Encrypt: exact per-domain weekly limit, renewal exemption, limit-increase process, current certificate lifetime (it's shrinking).
- Cloudflare Workers / KV free-plan limits.
- Stremio iOS app and third-party Apple players with a trusted HTTPS LAN name (the iOS app is closed source).
- `stremio://` install-link format.
- How common router DNS rebind protection is, and how to detect it from KaijuFlow.
- Let's Encrypt trust on old Android (7.1 and earlier).
- Cloudflare Tunnel terms for video streaming.
