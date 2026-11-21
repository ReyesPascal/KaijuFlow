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

/** Offer single-episode Sources of S01E02 for a new show, in list order. Each spec: { tag, dead? }. */
function offerEpisode({ backend, indexer }, specs) {
  const show = `tt${nextImdb++}`;
  const items = specs.map((spec, i) => {
    const title = `KaijuFlow.PlayTime.Show.S01E02.2160p.WEB-DL.H265-${spec.tag}`;
    const media = mediaFor(spec.tag);
    const link = backend.addSeries(spec.tag, title, [{ season: 1, episode: 2, media }], { dead: spec.dead });
    return { tag: spec.tag, title, media, link, size: (8 - i) * GB };
  });
  indexer.offer(show, items);
  return { id: `${show}:1:2`, sources: items };
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
    // ADR 0009 at play time: an archive the pass rule blocks (a Scrambled RAR4 set, which AltMount refused in Test 1,
    // and a bare disc image) is skipped; Best plays the next Source and AltMount never sees the blocked ones.
    id: 'pass-rule-blocks-at-play-time',
    async run(w) {
      const { id, sources } = offerMovie(w, [{ tag: 'rule-rar4', kind: 'scrambled-rar4' }, { tag: 'rule-iso', kind: 'disc-image' }, { tag: 'rule-ok' }]);
      const streams = await w.list('movie', id);
      const r = await play(streams[0].url);
      assert.equal(r.status, 200);
      assertBytes(r.body, sources[2].media, 'Best plays the Source the pass rule lets through');
      const asked = tag => w.news.state.reads.concat(w.news.state.stats).filter(x => x.startsWith(`${tag}-`)).length;
      assert.ok(asked('rule-rar4') > 0, 'the RAR4 set was checked at play time');
      assert.equal(w.backend.submitsFor('rule-rar4'), 0, 'the Scrambled RAR4 set never reaches AltMount');
      assert.equal(w.backend.submitsFor('rule-iso'), 0, 'the disc image never reaches AltMount');
      const pick = await play(streams[1].url);
      assertBytes(pick.body, sources[2].media, 'a click on the blocked archive falls back to the next playable Source');
      assert.equal(w.backend.submitsFor('rule-rar4'), 0, 'still never reaches AltMount');
    },
  },
  {
    // An AltMount refusal of a checked Source marks it dead and moves on to the next Source that passes the
    // check, from Best and from a list entry (the fallback-to-next path on AltMount, owner 2026-11-20).
    id: 'altmount-refusal-marks-dead-and-moves-on',
    async run(w) {
      const { id, sources } = offerMovie(w, [{ tag: 'refuse-top', kind: 'rejected' }, { tag: 'refuse-dead', kind: 'dead' }, { tag: 'refuse-ok' }]);
      const streams = await w.list('movie', id);
      const r = await play(streams[0].url);
      assert.equal(r.status, 200);
      assertBytes(r.body, sources[2].media, 'Best moves on to the next healthy Source');
      assert.equal(w.backend.submitsFor('refuse-top'), 1, 'the refused Source was handed over once');
      assert.equal(w.backend.submitsFor('refuse-dead'), 0, 'the dead one is skipped');
      const pick = await play(streams[1].url);
      assertBytes(pick.body, sources[2].media, 'a click on the refused entry falls back to the next Source');
      assert.equal(w.backend.submitsFor('refuse-top'), 1, 'the refused Source is dead: not handed over again');
      const relisted = await w.list('movie', id);
      assert.ok(!relisted.some(s => !isBest(s) && entryTitle(s) === sources[0].title), 'a dead Source is not offered again');
    },
  },
  {
    // A list entry AltMount refuses falls back to the next Source (fresh title, nothing remembered).
    id: 'list-entry-refused-falls-back-to-next',
    async run(w) {
      const { id, sources } = offerMovie(w, [{ tag: 'entry-refused', kind: 'rejected' }, { tag: 'entry-next' }]);
      const streams = await w.list('movie', id);
      const r = await play(streams[1].url);
      assert.equal(r.status, 200);
      assertBytes(r.body, sources[1].media, 'the next Source plays');
      assert.equal(w.backend.submitsFor('entry-refused'), 1);
      assert.equal(w.backend.submitsFor('entry-next'), 1);
    },
  },
  {
    // A failed list entry falls back to the next Source even when an older config still says "failure video"
    // for a failed entry (the old default): with the Play-time check a failure falls back (#190).
    id: 'list-entry-falls-back-whatever-an-old-config-says',
    async run(w) {
      const saved = w.configData.ultimateFallback;
      w.configData.ultimateFallback = { ...saved, userPickFallback: 'failure-video' };
      try {
        const { id, sources } = offerMovie(w, [{ tag: 'old-dead', kind: 'dead' }, { tag: 'old-next' }]);
        const streams = await w.list('movie', id);
        const r = await play(streams[1].url);
        assert.equal(r.status, 200);
        assertBytes(r.body, sources[1].media, 'the next Source plays');
      } finally {
        w.configData.ultimateFallback = saved;
      }
    },
  },
  {
    // An episode: Best checks the episode's Sources and AltMount is told which episode to play.
    id: 'best-plays-an-episode',
    async run(w) {
      const { id, sources } = offerEpisode(w, [{ tag: 'epdead', dead: true }, { tag: 'epok' }]);
      const streams = await w.list('series', id);
      assert.ok(isBest(streams[0]), 'Best is on top of an episode list too');
      const r = await play(streams[0].url);
      assert.equal(r.status, 200);
      assertBytes(r.body, sources[1].media, 'Best plays the healthy episode Source');
      assert.equal(w.backend.submitsFor('epdead'), 0);
      const f = w.backend.submitFields.at(-1);
      assert.equal(`${f.season}x${f.episode}`, '1x2', 'AltMount is told the episode');
    },
  },
  {
    // AltMount unreachable while Best is pressed: the failure video, but the checked Source is not dead, so
    // it plays once AltMount is back (ADR 0004).
    id: 'best-with-altmount-unreachable-not-dead',
    async run(w) {
      const { id, sources } = offerMovie(w, [{ tag: 'down-ok' }]);
      const streams = await w.list('movie', id);
      w.backend.setDown(true);
      try {
        assertFailureVideo(await play(streams[0].url));
      } finally {
        w.backend.setDown(false);
      }
      const again = await w.list('movie', id);
      assert.ok(again.some(s => !isBest(s) && entryTitle(s) === sources[0].title), 'the Source is still offered');
      const r = await play(again[0].url);
      assert.equal(r.status, 200);
      assertBytes(r.body, sources[0].media, 'it plays once AltMount is back');
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
