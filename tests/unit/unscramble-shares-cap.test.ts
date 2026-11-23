// Unscramble and the health checks share one connection cap (ADR 0005 "One at a time", #245): while a Walk's
// checks run on their pool, an Unscramble reading a Scrambled RAR set on the same news server never takes the two
// together over the "Max Total Connections" setting. The fake news server counts open connections, as the health
// connection-cap test's does.
// Run: npm run test:unit
import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { NntpConnectionPool } from '../../src/health/index.ts';
import { configData } from '../../src/config/index.ts';
import { checkSource } from '../../src/play/playTimeCheck.ts';
import { cacheNzbContent } from '../../src/health/nzbContentCache.ts';
import { unscrambleNzb } from '../../src/archive/unscramble.ts';
import { scrambledRarSet, startFakeNntp } from '../integration/parity/fake-nntp.mjs';

const savedHealthChecks = configData.healthChecks;
const servers: Array<{ close(): Promise<void> }> = [];
after(async () => {
  configData.healthChecks = savedHealthChecks;
  for (const s of servers) await s.close();
});

/** A plain video Source of 5 articles, all on the news server. */
function videoSource(name: string, articles: Map<string, Buffer>) {
  const ids = [1, 2, 3, 4, 5].map(n => `${name}-seg${n}@fake`);
  for (const id of ids) articles.set(id, Buffer.from('x'));
  const segs = ids.map((id, i) => `<segment bytes="500000" number="${i + 1}">${id}</segment>`).join('');
  const nzb = `<?xml version="1.0"?><nzb xmlns="http://www.newzbin.com/DTD/2003/nzb">` +
    `<file subject="&quot;${name}.mkv&quot; yEnc (1/5)"><segments>${segs}</segments></file></nzb>`;
  const nzbUrl = `http://nzb.invalid/${name}.nzb`;
  cacheNzbContent(nzbUrl, nzb);
  return { nzbUrl, title: name, indexerName: 'Parity' };
}

/** A Walk's checks of 6 Sources on their pool and an Unscramble of a 24-part set, at once, under the cap `cap`. Returns the peak. */
async function checksAndUnscramble(cap: number, tag: string): Promise<number> {
  const set = scrambledRarSet({ base: `${tag}set`, parts: 24, tag: `${tag}set` });
  const articles = new Map(set.articles);
  const sources = Array.from({ length: 6 }, (_, i) => videoSource(`${tag}check${i}`, articles));
  const news = await startFakeNntp({ articles, delayMs: 30 });
  servers.push(news);
  news.slow(`${tag}check`, 30);
  configData.healthChecks = { ...savedHealthChecks, providers: [news.provider()], maxTotalConnections: cap } as typeof savedHealthChecks;
  const pool = new NntpConnectionPool();
  try {
    // The Walk's checks on their pool, and an Unscramble asking for 8 connections, the default cap.
    const [checks, unscrambled] = await Promise.all([
      Promise.all(sources.map(s => checkSource(s, pool))),
      unscrambleNzb(set.nzb, [news.provider()], 20000, { connections: 8 }),
    ]);
    assert.ok(checks.every(r => r.playable), 'every check passes');
    assert.equal(unscrambled.changed, true, `the set is Unscrambled (${unscrambled.reason})`);
  } finally {
    pool.destroyAll();
  }
  assert.ok(news.state.reads.some(id => id.startsWith(`${tag}set-`)) && news.state.stats.some(id => id.startsWith(`${tag}check`)), 'both read the news server');
  return news.state.peak;
}

test('without a tight cap, the checks and an Unscramble together open more than 3 connections', async () => {
  const peak = await checksAndUnscramble(100, 'open');
  assert.ok(peak > 3, `expected the uncapped run to exceed 3 connections, saw ${peak}`);
});

test('a Walk\'s checks and an Unscramble together stay under a cap of 3', async () => {
  const peak = await checksAndUnscramble(3, 'cap');
  assert.ok(peak <= 3, `peak ${peak} open connections, cap 3`);
});
