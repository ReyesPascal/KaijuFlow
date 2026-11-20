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
