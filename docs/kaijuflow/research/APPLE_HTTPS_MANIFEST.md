# Apple devices and the HTTPS manifest problem

Research date: 2026-11-09. Planning evidence only; no code, server, or container was changed.

## Plain-English summary

- Stremio's own addon docs say an addon URL "must either be accessed on `127.0.0.1` or support HTTPS". A plain `http://192.168.4.40:1337/...` URL fails that rule. This is a Stremio rule, not only an Apple one. [stremio-addon-sdk docs/testing.md](https://github.com/Stremio/stremio-addon-sdk/blob/master/docs/testing.md) (line 11, checked at commit 796ca01).
- Apple adds its own layers on top: App Transport Security in native apps, mixed-content blocking in Safari/Stremio Web (an HTTPS page cannot fetch an `http://` addon), and the iOS Local Network permission.
- Tailscale worked because `tailscale serve` gives the server a real HTTPS address (`brain-1.tail1986dd.ts.net`) with a certificate from Let's Encrypt, which Apple devices trust. [Tailscale HTTPS docs](https://tailscale.com/kb/1153/enabling-https)
- A self-signed certificate will not work for a non-technical friend. Each Apple device would need a profile installed and manually trusted. [Apple support](https://support.apple.com/en-us/102390)
- Recommendation: build an optional "HTTPS front door" into KaijuFlow's docker-compose using Caddy and a real certificate for a name the owner controls. KaijuFlow already proxies video by default, so the fix covers both Backends, with one gap to close (the `direct` delivery mode, see below).
- The one-time cost is a domain (or free DuckDNS name) plus a DNS API token. Nothing on the router is needed, and the friend only pastes an `https://` link.

## 1. Root cause

| Layer | What it does | Source |
| --- | --- | --- |
| Stremio rule | Addon URL must be on `127.0.0.1` or be HTTPS. Applies to every Stremio client, Apple or not. The same docs name the clients as Stremio 4.4.10+ and Stremio Web. | [testing.md](https://github.com/Stremio/stremio-addon-sdk/blob/master/docs/testing.md) |
| Mixed content (Safari, Stremio Web) | Stremio Web is served over HTTPS. Browsers block insecure requests from a secure page, except to loopback (`127.0.0.1`/`localhost`), which count as secure. A LAN IP is not loopback, so `http://192.168.4.40` is blocked. Browsers only auto-upgrade images/audio/video, not the XHR/fetch used for manifests. | [MDN Mixed content](https://developer.mozilla.org/en-US/docs/Web/Security/Mixed_content) |
| App Transport Security (native apps) | ATS blocks plain HTTP by default. `NSAllowsLocalNetworking` relaxes it only for local targets, and `NSAllowsArbitraryLoads` disables it entirely. Whether an app sets either is the app author's choice. I could not retrieve the Apple page text (fetch returned only the title). The description that it covers unqualified hostnames, `.local` names and local IPs is from general knowledge and is **unverified here**. | [Apple: NSAllowsLocalNetworking](https://developer.apple.com/documentation/bundleresources/information-property-list/nsapptransportsecurity/nsallowslocalnetworking) |
| iOS Local Network privacy | iOS 14+ asks permission before an app talks to LAN devices. It is a separate prompt and does not fix HTTP vs HTTPS. Partly unverified (see ATS row; same fetch problem). | Apple docs, same area |

Which Stremio apps exist on Apple, and their Info.plist: the Stremio iOS/tvOS apps are closed source. The public repos I cloned (stremio-web, stremio-shell, stremio-core) contain no ATS settings and no HTTPS statements for addons. **Unverified:** the exact ATS configuration of the iOS app. The practical result (HTTP LAN addons failing) is consistent with the owner's experience and with the Stremio rule above, but the Apple-side mechanism per app is not confirmed from primary sources. Third-party players (Infuse, VidHub, etc.) have their own ATS settings and were not checked.

The stream URLs matter too: video fetched by a native player is a plain media request (not a Stremio manifest fetch), so ATS applies to it; inside Stremio Web, media over `http://` on an HTTPS page is at best auto-upgraded (MDN above), which fails if nothing answers on 443/HTTPS. So both the manifest and the stream URLs should be HTTPS.

## 2. Why Tailscale fixed it

`tailscale cert`/`serve` requests a certificate from Let's Encrypt for `<machine>.<tailnet>.ts.net` (DNS-01 challenge done by Tailscale), so the result is a publicly trusted HTTPS certificate. Keys stay local. Caveat from the same page: certificate names appear in public Certificate Transparency logs. [Tailscale: Enabling HTTPS](https://tailscale.com/kb/1153/enabling-https). The cost: every client device had to be on the tailnet to reach that name (the name only resolves inside it), which is why it was awkward for the friend.

## 3. Fix options

KaijuFlow facts that decide this (repo `/home/ryan/KaijuFlow`):

- Manifest/stream links are built from `BASE_URL` if set, otherwise the request's protocol and Host header: `src/utils/urlHelpers.ts:19-41` (`resolveBaseUrl`). `trust proxy` is already set (`src/server.ts:60`), so a reverse proxy sending `X-Forwarded-Proto: https` works. `src/server.ts:197-204` uses it for the manifest logo and request context. `INSTALLATION.md:253` already shows `BASE_URL=https://uu.${DUCKDNS_SUBDOMAIN}.duckdns.org` in a Caddy/DuckDNS-style example, so part of this pattern exists.
- Stream tiles point back to KaijuFlow (`/v?path=...`, `/stream/...`) built with `resolveBaseUrl(req)`: `src/nzbdav/streamHandler.ts:549, 762, 857, 913, 996, 1210`. The proxy fetches from the Backend server-side (`backend.mediaRequest`, `src/backends/altmount.ts:151-157`; WebDAV URL built at `src/backends/nzbdav.ts:25`). So by default the player only sees KaijuFlow's address.
- **Leak:** when delivery mode is `direct`, KaijuFlow answers with a 302 redirect to the Backend's own URL: `src/nzbdav/streamHandler.ts:545, 750-753, 864`. `backend.directUrl()` (`src/backends/altmount.ts:278`, interface `src/backends/types.ts:98`) returns the Backend's configured plain-HTTP address, including the AltMount `download_key`. On Apple this would be an http:// URL and a LAN address. Any HTTPS plan must disable or block `direct` mode, or proxy it. (Redirects from the proxy path to `/v` use the HTTPS base URL, so are fine.)
- `src/proxy.ts:135-145` already knows `BASE_URL` for log hiding, so no conflict.

### A. KaijuFlow serves HTTPS itself with a self-signed cert
Needs a profile install plus manual "full trust" on every iPhone/iPad/Apple TV/Mac ([Apple](https://support.apple.com/en-us/102390)); Stremio Web in Safari would still throw errors; friend must repeat per device. Not workable for a non-technical friend. Rejected.

### B. Real certificate through DNS-01 on a domain the owner controls (Caddy sidecar)
How: a name like `kaiju.example.com` (or a free DuckDNS subdomain) has an A record pointing at the LAN IP `192.168.4.40`. Caddy gets a Let's Encrypt certificate using the DNS-01 challenge (the DNS provider's API proves ownership, so nothing needs to be reachable from the internet), terminates HTTPS on 443, and forwards to KaijuFlow:1337. Set `BASE_URL=https://kaiju.example.com`. Private-IP A records are legal and work on any device that can reach the LAN IP; they only resolve to a private address, so the service is not exposed publicly. Needs from the user: a domain or DuckDNS name, a DNS API token, ports 443 free on the host. No router admin required, as long as the router does not strip private-IP DNS answers ("DNS rebind protection" - **unverified for the owner's router**; the fallback is to set the public DNS-record hostname in the router/Pi-hole, which needs admin). Friend only works at home, or via Tailscale/VPN away from home.
Pros: standard, one real cert, works with every client; Backend-agnostic because it fronts KaijuFlow only. Cons: needs a domain/DuckDNS account and a Caddy DNS plugin build (Caddy needs a DNS-provider module). This matches what the repo already documents (DuckDNS + Caddy, `INSTALLATION.md:253`).

### C. Wildcard "IP-in-hostname" services
Examples: sslip.io / nip.io (map `192-168-4-40.sslip.io` to the IP) and Stremio's `*.stremio.rocks` (`192-168-1-10.519b6502d940.stremio.rocks` seen in community Docker images; community-reported only, I found no official Stremio doc or source for the mechanism; the public Stremio repos contain no reference). These services supply DNS, but a **trusted certificate for that name** still has to come from somewhere. Stremio's cert is Stremio's and not usable by KaijuFlow. For sslip.io/nip.io the owner would need a certificate for a shared public domain, which Let's Encrypt rate limits make impractical and which the service operators do not hand out per user (**unverified**, no first-party source checked). Not recommended.

### D. Let's Encrypt IP-address certificates
Generally available since 2026-01-15; must be short-lived (about 6 days). [Let's Encrypt announcement](https://letsencrypt.org/2026/01/15/6day-and-ip-general-availability). Validation is HTTP-01 or TLS-ALPN-01 (community-reported by write-ups; the announcement page itself does not say), both of which need the IP to be reachable from the public internet. A private `192.168.x.x` address cannot get a public cert this way. Not usable for a LAN-only IP. Rejected.

### E. Tunnels and mesh (document, do not build)
- Tailscale `serve` (what the owner had): real HTTPS but every device needs Tailscale. Tailscale Funnel exposes it publicly (needs enabling, see [Tailscale docs](https://tailscale.com/kb/1153/enabling-https)). Funnel details were not independently checked.
- Cloudflare Tunnel: real HTTPS on a public name without opening ports; needs a Cloudflare account and domain. Not checked against current docs here; listed as a supported, documented alternative. Note that it routes video through Cloudflare, check their terms before streaming media via a tunnel (**unverified**).

### F. Is a Caddy sidecar the simplest real answer?
Yes, for owners who have a domain or a DuckDNS name. Combined with B it is the only option above that is LAN-only, free-ish, has a trusted cert, and keeps one door for both Backends.

## 4. Recommendation

Build option B as an opt-in docker-compose profile, with the DuckDNS path as the default recipe (because it needs no purchase).

What changes in KaijuFlow:

1. `docker-compose.yml`: add an optional `caddy` service (profile `https`) on 443, using a Caddy image with the chosen DNS-provider plugin, a `Caddyfile` template reverse-proxying to `kaijuflow:1337`, and a volume for certificates. Add `BASE_URL` to the KaijuFlow service environment.
2. A new `Caddyfile.example` (or `config/Caddyfile`) with `X-Forwarded-Proto https` and the DNS token read from an env var.
3. `src/nzbdav/streamHandler.ts` (and `deliveryMethod()` at line 500): when `BASE_URL` starts with `https://`, treat `direct` as `proxy` (or warn) so no plain-HTTP Backend URL is ever sent to a player. Add a test next to the existing streamHandler tests.
4. Settings/UI: a read-only "Manifest URL" display that uses `BASE_URL`, plus a warning banner if `BASE_URL` is empty or `http://` ("Apple devices need HTTPS"). Settings schema: `src/config/schema.ts` (not inspected in detail).
5. Docs: a short "HTTPS for Apple" section in `INSTALLATION.md` linking this note, with Tailscale `serve` and Cloudflare Tunnel as alternative recipes.

One-time owner steps: pick a DuckDNS (or own) name pointing at 192.168.4.40, paste the DNS token into `.env`, run `docker compose --profile https up -d`, then reinstall the addon with the new `https://` manifest URL. The friend: if on the same LAN, paste the https link; away from home they would need a tunnel or VPN because the name resolves to a private address.

Open items to verify before building: (a) that the owner's router returns private-IP answers for the chosen name; (b) the exact ATS/mixed-content behavior of the Stremio iOS app and each third-party player, by testing; (c) the DNS-provider Caddy plugin choice.
