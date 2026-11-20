// #120: the health check blocks a Source whose only real content is a bare disc image.
// Run: npm run test:unit
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { performHealthCheck } from '../../src/health/index.ts';
import { nzbWithNews, type F } from './health-nzb.ts';

/** Run the health check on an NZB with these files; `served` false leaves every article missing. */
async function check(files: F[], served = true) {
  const { url, provider, state } = await nzbWithNews(files, { served });
  const result = await performHealthCheck(url, [provider], 'test-agent', { archiveInspection: true, sampleCount: 3 });
  return { result, reads: state.reads };
}

const side = (): F[] => [
  { name: 'Movie.nfo' }, { name: 'Movie.url' },
  { name: 'Movie.par2' }, { name: 'Movie.vol000+01.par2' },
];

for (const ext of ['iso', 'IMG']) {
  test(`a bare .${ext} with nfo, url and par2 is blocked as Disc image with no segment reads`, async () => {
    const { result, reads } = await check([{ name: `Movie.${ext}`, segs: 5, bytes: 700000 }, ...side()]);
    assert.equal(result.status, 'blocked');
    assert.equal(result.message, 'Disc image');
    assert.equal(result.playable, false);
    assert.equal(reads.length, 0);
  });
}

test('an .iso next to a recognized video file does not block it', async () => {
  const { result } = await check([{ name: 'Movie.mkv' }, { name: 'Extras.iso', segs: 5, bytes: 700000 }]);
  assert.match(result.status, /^verified/);
});
