/**
 * Address KaijuFlow uses for its own links (the EasyNews NZB links, which are
 * also their dead-NZB cache keys).
 *
 * KaijuFlow change: use 127.0.0.1 instead of localhost. Inside Docker,
 * "localhost" can resolve to IPv6 ::1 first; if the server is not reachable
 * on ::1 the self-request fails (Auto-queue's did, before #226 deleted it).
 * 127.0.0.1 is always IPv4 loopback.
 *
 * Every caller must use this one helper so the EasyNews NZB links the play side
 * marks dead match the keys the list looks up (addon/index.ts).
 */
export function getSelfUrl(port: string | number = process.env.PORT || 1337): string {
  return `http://127.0.0.1:${port}`;
}
