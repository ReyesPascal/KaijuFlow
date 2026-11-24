/**
 * Address KaijuFlow uses to call itself (auto-queue, Easynews NZB keys,
 * dead-NZB cache keys).
 *
 * KaijuFlow change: use 127.0.0.1 instead of localhost. Inside Docker,
 * "localhost" can resolve to IPv6 ::1 first; if the server is not reachable
 * on ::1 the self-request fails ("Auto-queue failed ... ::1:1337").
 * 127.0.0.1 is always IPv4 loopback.
 *
 * Every caller must use this one helper so dead-NZB cache keys written in
 * healthCheckCoordinator match the keys looked up in addon/index.ts.
 */
export function getSelfUrl(port: string | number = process.env.PORT || 1337): string {
  return `http://127.0.0.1:${port}`;
}
