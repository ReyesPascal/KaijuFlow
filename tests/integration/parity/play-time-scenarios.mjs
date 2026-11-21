// Play-time check scenarios (#190, spec #183; GLOSSARY: Play-time check, Best entry, Unchecked Source).
// Each scenario asks for a title's stream list through the fake indexer, then plays an entry of it,
// and asserts only on what the player receives, what the fake news server was asked and what
// reached the fake AltMount.
import assert from 'node:assert/strict';
import { assertBytes } from './bytes.mjs';

const mediaFor = tag => Buffer.from(`KaijuFlow play-time bytes for ${tag}: 0123456789abcdefghijklmnopqrstuvwxyz`);
const GB = 1024 ** 3;
let nextImdb = 1000001;

/**
 * Offer movie Sources for a new title, in list order (same quality, sizes going down, so KaijuFlow's sort keeps
 * this order). Each spec: { tag, kind: 'healthy' | 'dead' | 'rejected' | 'scrambled-rar4' | 'disc-image' }.
 * Returns { id, sources: [{ tag, title, media }] }.
 */
function offerMovie({ backend, indexer }, specs) {
  const id = `tt${nextImdb++}`;
  const items = specs.map((spec, i) => {
    const title = `KaijuFlow.PlayTime.${spec.tag}.2026.2160p.WEB-DL.H265-GRP`;
    const media = mediaFor(spec.tag);
    const kind = spec.kind ?? 'healthy';
    const link = kind === 'healthy' ? backend.addMovie(spec.tag, title, media)
      : kind === 'dead' ? backend.addMovie(spec.tag, title, media, { dead: true })
      : kind === 'rejected' ? backend.addRejected(spec.tag, title)
      : backend.addRefused(spec.tag, title, kind);
    return { tag: spec.tag, title, media, link, size: (20 - i) * GB };
  });
  indexer.offer(id, items);
  return { id, sources: items };
}

async function play(url, range) {
  const res = await fetch(url, { headers: range ? { Range: range } : {}, signal: AbortSignal.timeout(30000) });
  return { status: res.status, headers: res.headers, body: Buffer.from(await res.arrayBuffer()) };
}

/** The failure video is a long video/mp4, much bigger than the synthetic media. */
function assertFailureVideo(r) {
  assert.equal(r.status, 200);
  assert.equal(r.headers.get('content-type'), 'video/mp4', 'player should get the failure video');
  assert.ok(r.body.length > 10_000, 'failure video is not Backend media');
}

const isBest = s => s.name.includes('KaijuFlow ▶ Best');
/** The release name a list entry plays (from its tile envelope). */
const entryTitle = s => JSON.parse(Buffer.from(new URL(s.url).searchParams.get('t'), 'base64url').toString()).title;

export const playTimeScenarios = [
  {
    // The list goes out at once, sorted and unchecked, with the Best entry on top and the full list below.
    id: 'list-at-once-unchecked-best-on-top',
    async run(w) {
      const { id, sources } = offerMovie(w, [{ tag: 'list-a' }, { tag: 'list-b' }, { tag: 'list-c', kind: 'dead' }]);
      const asked = w.news.state.stats.length + w.news.state.reads.length;
      const streams = await w.list('movie', id);
      assert.equal(streams.length, 4, 'Best plus every Source');
      assert.ok(isBest(streams[0]), `Best is on top (got ${streams[0].name})`);
      assert.equal(streams.slice(1).map(entryTitle).join(' | '), sources.map(s => s.title).join(' | '), 'the full list below, in sort order');
      assert.equal(w.news.state.stats.length + w.news.state.reads.length, asked, 'no article is checked before the list goes out');
      assert.equal(w.backend.submitted.length, 0, 'nothing reaches AltMount before a play');
      assert.ok(!streams.some(s => /✅|❌|🚫/.test(s.title)), 'no Source shows a health verdict');
    },
  },
  {
    // Best checks the top Sources and hands AltMount the first healthy one in list order; the dead top pick
    // (articles missing) never reaches AltMount. A second press plays the same Source without a new import.
    id: 'best-plays-first-healthy-when-first-is-dead',
    async run(w) {
      const { id, sources } = offerMovie(w, [{ tag: 'first-dead', kind: 'dead' }, { tag: 'second-ok' }, { tag: 'third-ok' }]);
      const streams = await w.list('movie', id);
      const r = await play(streams[0].url);
      assert.equal(r.status, 200, 'Best plays');
      assertBytes(r.body, sources[1].media, 'Best plays the first healthy Source in list order');
      assert.equal(w.backend.submitsFor('first-dead'), 0, 'the dead Source never reaches AltMount');
      assert.equal(w.backend.submitsFor('second-ok'), 1);
      const again = await play(streams[0].url);
      assertBytes(again.body, sources[1].media, 'a second press plays the same Source');
      assert.equal(w.backend.submitsFor('second-ok'), 1, 'without a new import');
    },
  },
  {
    // #189's only fail: the first Sources are all dead. Best keeps checking, 3 at a time from the top down, with
    // no fixed cap, and plays the 8th; no Source it did not find healthy reaches AltMount.
    id: 'best-plays-the-8th-when-the-first-7-are-dead',
    async run(w) {
      const specs = [...Array(7).keys()].map(i => ({ tag: `deep-dead-${i + 1}`, kind: 'dead' })).concat([{ tag: 'deep-ok-8' }, { tag: 'deep-ok-9' }]);
      const { id, sources } = offerMovie(w, specs);
      const before = w.backend.submitted.length;
      const streams = await w.list('movie', id);
      const r = await play(streams[0].url);
      assert.equal(r.status, 200, 'Best plays');
      assertBytes(r.body, sources[7].media, 'Best plays the 8th Source');
      const handed = w.backend.submitted.slice(before);
      assert.equal(handed[0], 'deep-ok-8', 'the 8th is the first Source AltMount gets');
      assert.ok(handed.every(tag => tag.startsWith('deep-ok-')), `only healthy Sources reach AltMount (got ${handed.join(', ')})`);
    },
  },
  {
    // A list entry is checked when it is clicked: a healthy one plays after its articles are checked; a dead one
    // never reaches AltMount and the play falls back to the next Source of the list.
    id: 'list-entry-is-checked-on-click',
    async run(w) {
      const { id, sources } = offerMovie(w, [{ tag: 'pick-dead', kind: 'dead' }, { tag: 'pick-next' }, { tag: 'pick-ok' }]);
      const streams = await w.list('movie', id);
      const checked = tag => w.news.state.stats.filter(x => x.startsWith(`${tag}-s`)).length;
      assert.equal(checked('pick-ok'), 0, 'not checked before the click');
      const ok = await play(streams[3].url);
      assert.equal(ok.status, 200);
      assertBytes(ok.body, sources[2].media, 'the clicked healthy entry plays');
      assert.ok(checked('pick-ok') > 0, 'its articles were checked on click');
      const r = await play(streams[1].url);
      assert.equal(r.status, 200);
      assertBytes(r.body, sources[1].media, 'a dead entry falls back to the next Source');
      assert.ok(checked('pick-dead') > 0, 'the dead entry was checked on click');
      assert.equal(w.backend.submitsFor('pick-dead'), 0, 'and never reached AltMount');
    },
  },
  {
    // No Healthy Source left: the play shows the failure video and nothing reaches AltMount.
    id: 'best-shows-the-failure-video-when-no-source-is-healthy',
    async run(w) {
      const { id } = offerMovie(w, [{ tag: 'none-1', kind: 'dead' }, { tag: 'none-2', kind: 'dead' }, { tag: 'none-3', kind: 'dead' }, { tag: 'none-4', kind: 'dead' }]);
      const before = w.backend.submitted.length;
      const streams = await w.list('movie', id);
      assertFailureVideo(await play(streams[0].url));
      assert.equal(w.backend.submitted.length, before, 'nothing reaches AltMount');
    },
  },
];

/** Run every play-time scenario. Returns per-scenario results. */
export async function runPlayTimeParity(w) {
  const results = [];
  for (const s of playTimeScenarios) {
    const before = w.backend.requests.length;
    try {
      await s.run(w);
      results.push({ id: s.id, status: 'pass' });
    } catch (e) {
      results.push({ id: s.id, status: 'fail', error: String(e?.stack || e), requests: w.backend.requests.slice(before).slice(-15) });
    }
  }
  return results;
}

export { play, assertFailureVideo, assertBytes };
