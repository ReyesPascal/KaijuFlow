// Step timing (#61): each indexer page logs one step line (first page and extra pages),
// with the indexer name and no key or URL.
// Run: npm run test:unit
import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { UsenetSearcher } from '../../src/parsers/usenetSearcher.ts';
import { parseStepLine } from '../../src/utils/stepTiming.ts';
import { captureLogs } from './capture-logs.ts';

const TOTAL = 3;
const item = (n: number) => `<item><title>Page.Movie.${n}</title><link>http://idx.invalid/nzb/${n}</link><pubDate>Mon, 01 Jan 2024 00:00:00 +0000</pubDate></item>`;
const fakeIndexer = http.createServer((req, res) => {
  const offset = Number(new URL(req.url ?? '', 'http://x').searchParams.get('offset') ?? 0);
  res.writeHead(200, { 'Content-Type': 'application/xml' });
  res.end(`<?xml version="1.0"?><rss version="2.0" xmlns:newznab="http://www.newznab.com/DTD/2010/feeds/attributes/"><channel><newznab:response offset="${offset}" total="${TOTAL}"/>${item(offset + 1)}</channel></rss>`);
});
await new Promise<void>(r => fakeIndexer.listen(0, '127.0.0.1', () => r()));
const url = `http://127.0.0.1:${(fakeIndexer.address() as { port: number }).port}/api`;
after(() => fakeIndexer.close());

test('every indexer page logs one indexer_page line with the indexer name, page number and no key or URL', async () => {
  const searcher = new UsenetSearcher({ name: 'FakeIdx', url, apiKey: 'SECRETKEY123', enabled: true, pagination: true, maxPages: 2 });
  let found = 0;
  const logs = await captureLogs(async () => { found = (await searcher.search('page movie', undefined, { enabled: true, maxPages: 2 })).length; });
  assert.equal(found, 3, 'all three pages should be fetched');
  const recs = logs.split('\n').map(l => parseStepLine(l)).filter((r): r is NonNullable<typeof r> => r !== null);
  assert.deepEqual(recs.map(r => [r.step, r.source, r.page, r.ok]), [
    ['indexer_page', 'FakeIdx', 1, true],
    ['indexer_page', 'FakeIdx', 2, true],
    ['indexer_page', 'FakeIdx', 3, true],
  ]);
  const stepText = logs.split('\n').filter(l => l.includes('[KF-STEP]')).join('\n');
  assert.doesNotMatch(stepText, /SECRETKEY123|127\.0\.0\.1|apikey/i);
});
