// Play-time check scenarios (#190, spec #183; GLOSSARY: Play-time check, Best entry, Unchecked Source).
// Each scenario asks for a title's stream list through the fake indexer, then plays an entry of it,
// and asserts only on what the player receives, what the fake news server was asked and what
// reached the fake AltMount; one scenario asserts on the log lines the brain tools read.
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

/**
 * Offer, for S01E02 of a new show, a season pack of loose videos (S01E01 to S01E03, one file per episode, the
 * layout of #189's edge2020 pack) on top, then a single-episode Source. `deadEpisodes`: the pack episodes whose
 * articles are missing. Returns { id, pack, single }.
 */
function offerPackThenEpisode({ backend, indexer }, tag, deadEpisodes) {
  const show = `tt${nextImdb++}`;
  const packTitle = `KaijuFlow.PlayTime.Pack.S01.2160p.WEB-DL.H265-${tag}`;
  const episodes = [1, 2, 3].map(episode => ({ season: 1, episode, media: mediaFor(`${tag}-e${episode}`) }));
  const pack = { tag: `${tag}-pack`, title: packTitle, media: episodes[1].media, size: 30 * GB };
  pack.link = backend.addSeries(pack.tag, packTitle, episodes, { deadEpisodes });
  const single = { tag: `${tag}-single`, title: `KaijuFlow.PlayTime.Pack.S01E02.2160p.WEB-DL.H265-${tag}`, media: mediaFor(`${tag}-single`), size: 8 * GB };
  single.link = backend.addSeries(single.tag, single.title, [{ season: 1, episode: 2, media: single.media }]);
  indexer.offer(show, [pack, single]);
  return { id: `${show}:1:2`, pack, single };
}

async function play(url, range) {
  const res = await fetch(url, { headers: range ? { Range: range } : {}, signal: AbortSignal.timeout(30000) });
  return { status: res.status, headers: res.headers, body: Buffer.from(await res.arrayBuffer()) };
}

/** Run fn(lines) and collect what KaijuFlow logs meanwhile (its console.log lines). */
async function withLogs(fn) {
  const lines = [];
  const saved = console.log;
  console.log = (...a) => { lines.push(a.map(x => (typeof x === 'string' ? x : JSON.stringify(x))).join(' ')); };
  try { return { result: await fn(lines), lines }; } finally { console.log = saved; }
}

/** Wait until Best's run has ended (its summary line "N checked · N healthy"), so every import it makes has been made. */
async function bestDone(lines) {
  const deadline = Date.now() + 20000;
  while (!lines.some(l => /Ultimate-Fallback \[[^\]]+\]\s+\d+ checked · \d+ healthy/.test(l))) {
    if (Date.now() > deadline) throw new Error('Best did not finish within 20 s');
    await new Promise(r => setTimeout(r, 25));
  }
}

/** How many of a Source's articles the fake news server was asked about (it was checked). */
const checked = (w, tag) => w.news.state.stats.filter(x => x.startsWith(`${tag}-s`)).length;

/** The failure video is a long video/mp4, much bigger than the synthetic media. */
function assertFailureVideo(r) {
  assert.equal(r.status, 200);
  assert.equal(r.headers.get('content-type'), 'video/mp4', 'player should get the failure video');
  assert.ok(r.body.length > 10_000, 'failure video is not Backend media');
}

/** Run fn with these Ultimate Fallback settings on top of the suite's, then put the suite's back. */
async function withSettings(w, patch, fn) {
  const saved = w.configData.ultimateFallback;
  w.configData.ultimateFallback = { ...saved, ...patch };
  try { return await fn(); } finally { w.configData.ultimateFallback = saved; }
}

/** Per Source tag, when the fake news server was first asked for one of its articles and when it last answered. */
function checkTimes(news, tags) {
  return tags.map(tag => {
    const mine = news.state.asks.filter(a => a.id.startsWith(`${tag}-`));
    return { tag, from: Math.min(...mine.map(a => a.asked)), to: Math.max(...mine.map(a => a.answered ?? Infinity)) };
  });
}

/** The most Sources whose checks were under way at one time. */
function mostAtOnce(times) {
  const edges = times.flatMap(t => [[t.from, 1], [t.to, -1]]).sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  let now = 0, most = 0;
  for (const [, d] of edges) { now += d; most = Math.max(most, now); }
  return most;
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
    // The brain tools read a Best press from KaijuFlow's log (tools/brain/docs/formats.md): one play_check line per
    // Source Best checked, the dead one too, and the played Source's name on the first prepare line after the
    // press's '/stream hit' line; the other healthy Source it checked is never prepared (#192). A scrubbed capture of these lines is
    // tools/brain/fixtures/2026-11-21-best/, which the brain tests read.
    id: 'best-press-log-lines-the-brain-tools-read',
    async run(w) {
      const { id, sources } = offerMovie(w, [{ tag: 'log-dead', kind: 'dead' }, { tag: 'log-ok' }, { tag: 'log-backup' }]);
      const streams = await w.list('movie', id);
      const lines = [];
      const saved = console.log;
      console.log = (...a) => { lines.push(`${new Date().toISOString()} ${a.map(x => (typeof x === 'string' ? x : JSON.stringify(x))).join(' ')}`); };
      let r;
      try { r = await play(streams[0].url); } finally { console.log = saved; }
      assertBytes(r.body, sources[1].media, 'Best plays the first healthy Source');
      const steps = lines.filter(l => l.includes('[KF-STEP] ')).map(l => JSON.parse(l.split('[KF-STEP] ')[1]));
      const check = tag => steps.filter(s => s.step === 'play_check' && s.title === sources.find(x => x.tag === tag).title);
      assert.deepEqual(check('log-dead').map(s => [s.ok, s.status]), [[false, 'blocked']], 'the dead Source\'s check is one line');
      assert.deepEqual(check('log-ok').map(s => [s.ok, s.status]), [[true, 'verified']], 'the played Source\'s check is one line');
      const hit = lines.findIndex(l => l.includes('/stream hit'));
      assert.ok(hit >= 0, 'the press writes its /stream hit line');
      const prepared = lines.slice(hit).map(l => l.match(/Starting new stream preparation: (.+?)\s*$/)?.[1]).filter(Boolean);
      assert.equal(prepared[0], sources[1].title, 'the first prepare line after the press names the played Source');
      assert.ok(!prepared.includes(sources[0].title), 'the dead Source is never prepared');
      assert.ok(!prepared.includes(sources[2].title), 'the other healthy Source is never prepared (#192)');
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
    // Prepare only the Source being played (#192): Best checks the top 3, all healthy, and AltMount gets one
    // import, the one played; the other two healthy Sources are checked but never imported.
    id: 'one-play-makes-one-altmount-import',
    async run(w) {
      const { id, sources } = offerMovie(w, [{ tag: 'one-a' }, { tag: 'one-b' }, { tag: 'one-c' }]);
      const streams = await w.list('movie', id);
      const before = w.backend.submitted.length;
      const { result: r } = await withLogs(async lines => {
        const out = await play(streams[0].url);
        await bestDone(lines);
        return out;
      });
      assert.equal(r.status, 200, 'Best plays');
      assertBytes(r.body, sources[0].media, 'Best plays the top Source');
      for (const s of sources) assert.ok(checked(w, s.tag) > 0, `${s.tag} was checked`);
      assert.deepEqual(w.backend.submitted.slice(before), ['one-a'], 'one play makes one AltMount import');
    },
  },
  {
    // A failure makes the next import (#192): AltMount refuses the top Source, so the next healthy one is
    // imported and played; the third, also healthy, is not imported.
    id: 'a-failure-makes-the-next-altmount-import',
    async run(w) {
      const { id, sources } = offerMovie(w, [{ tag: 'next-refused', kind: 'rejected' }, { tag: 'next-b' }, { tag: 'next-c' }]);
      const streams = await w.list('movie', id);
      const before = w.backend.submitted.length;
      const { result: r } = await withLogs(async lines => {
        const out = await play(streams[0].url);
        await bestDone(lines);
        return out;
      });
      assert.equal(r.status, 200, 'Best plays');
      assertBytes(r.body, sources[1].media, 'Best plays the next Source after the refusal');
      assert.ok(checked(w, 'next-c') > 0, 'the third Source was checked');
      assert.equal(w.backend.submitsFor('next-refused'), 1, 'the refused Source was imported once');
      assert.deepEqual(w.backend.submitted.slice(before).filter(t => t !== 'next-refused'), ['next-b'], 'the failure makes one more import, the next Source');
    },
  },
  {
    // Auto-queue makes no import before a play (#192): a list KaijuFlow remembers from before the Play-time check
    // was on carries health verdicts, and Auto-queue (on, all Healthy Sources) would prepare them all; with the
    // Play-time check on, asking for that list again reaches AltMount with nothing.
    id: 'auto-queue-makes-no-import-before-a-play',
    async run(w) {
      const savedFallback = w.configData.ultimateFallback, savedChecks = w.configData.healthChecks;
      try {
        // Before: the list-time check, with Auto-queue off so this step imports nothing either.
        w.configData.ultimateFallback = { ...savedFallback, enabled: false };
        w.configData.healthChecks = { ...savedChecks, inspectionMethod: 'fixed', nzbsToInspect: 2, autoQueueMode: 'off' };
        const { id } = offerMovie(w, [{ tag: 'aq-a' }, { tag: 'aq-b' }]);
        const checkedList = await w.list('movie', id);
        assert.ok(checkedList.some(s => `${s.name} ${s.title}`.includes('✅')), 'the list-time check found Healthy Sources');
        // Now: the Play-time check on, Auto-queue on for all.
        w.configData.ultimateFallback = savedFallback;
        w.configData.healthChecks = { ...savedChecks, autoQueueMode: 'all' };
        const before = w.backend.submitted.length;
        await w.list('movie', id);
        await new Promise(r => setTimeout(r, 2000)); // Auto-queue sends its prepares in the background
        assert.deepEqual(w.backend.submitted.slice(before), [], 'nothing reaches AltMount before a play');
      } finally {
        w.configData.ultimateFallback = savedFallback;
        w.configData.healthChecks = savedChecks;
      }
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
    // Best hands AltMount the first healthy Source in list order, whatever the preference mode says: a later
    // Source whose check finishes first waits for the earlier one (owner, 2026-11-20).
    id: 'best-plays-the-earlier-healthy-source-when-a-later-check-finishes-first',
    async run(w) {
      await withSettings(w, { preferenceMode: 'speed' }, async () => {
        const { id, sources } = offerMovie(w, [{ tag: 'order-slow' }, { tag: 'order-fast' }]);
        w.news.slow('order-slow-', 800);
        try {
          const before = w.backend.submitted.length;
          const streams = await w.list('movie', id);
          const r = await play(streams[0].url);
          assert.equal(r.status, 200, 'Best plays');
          const [slow, fast] = checkTimes(w.news, ['order-slow', 'order-fast']);
          assert.ok(fast.to < slow.to, 'the later Source\'s check finished first');
          assertBytes(r.body, sources[0].media, 'Best plays the earlier healthy Source');
          assert.equal(w.backend.submitted[before], 'order-slow', 'the earlier Source is the first AltMount gets');
        } finally {
          w.news.slow('order-slow-', 0);
        }
      });
    },
  },
  {
    // Best checks 3 Sources at a time, from the top down, until one is healthy or the list runs out, whatever
    // the attempts cap says (owner, 2026-11-20); 3 is candidateCount's default.
    id: 'best-checks-3-at-a-time-with-no-cap',
    async run(w) {
      await withSettings(w, { maxAttempts: 2 }, async () => {
        const tags = [...Array(7).keys()].map(i => `cap-dead-${i + 1}`).concat(['cap-ok-8']);
        const { id, sources } = offerMovie(w, tags.map(tag => ({ tag, kind: tag === 'cap-ok-8' ? 'healthy' : 'dead' })));
        w.news.slow('cap-', 150);
        try {
          const streams = await w.list('movie', id);
          const r = await play(streams[0].url);
          assert.equal(r.status, 200, 'Best plays');
          assertBytes(r.body, sources[7].media, 'Best plays the 8th Source: no cap');
          const times = checkTimes(w.news, tags);
          assert.equal(mostAtOnce(times), 3, `3 Sources are checked at a time (${JSON.stringify(times)})`);
          const [a, b, c] = times;
          assert.ok(Math.max(a.from, b.from, c.from) < Math.min(a.to, b.to, c.to), 'the first 3 are checked together');
          assert.ok(times.slice(3).every(t => t.from >= Math.min(a.to, b.to, c.to)), 'the 4th starts once one of the first 3 is done');
        } finally {
          w.news.slow('cap-', 0);
        }
      });
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
    // #203: in a season pack of loose videos the check samples the wanted episode's file, not the first one.
    // Its first episode is complete but S01E02 is gone: Best does not hand the pack to AltMount.
    id: 'best-checks-the-wanted-episode-of-a-pack',
    async run(w) {
      const { id, pack, single } = offerPackThenEpisode(w, 'packbest', [2]);
      const streams = await w.list('series', id);
      assert.equal(entryTitle(streams[1]), pack.title, 'the pack is the top Source');
      const r = await play(streams[0].url);
      assert.equal(r.status, 200);
      assertBytes(r.body, single.media, 'Best plays the next Source');
      assert.equal(w.backend.submitsFor(pack.tag), 0, 'the pack whose wanted episode is gone never reaches AltMount');
    },
  },
  {
    // #203, the reverse: the pack's first episode is gone but S01E02 is complete, so the pack passes the check
    // and is the first Source Best hands AltMount, told the episode.
    id: 'best-passes-a-pack-whose-wanted-episode-is-complete',
    async run(w) {
      const { id, pack } = offerPackThenEpisode(w, 'packok', [1]);
      const before = w.backend.submitted.length;
      const streams = await w.list('series', id);
      await play(streams[0].url);
      assert.equal(w.backend.submitted[before], pack.tag, 'the pack is the first Source AltMount gets');
      const f = w.backend.submitFields[before];
      assert.equal(`${f.season}x${f.episode}`, '1x2', 'AltMount is told the episode the check sampled');
    },
  },
  {
    // #203 from a list entry: a click on the pack checks the wanted episode's file and falls back to the next Source.
    id: 'list-entry-checks-the-wanted-episode-of-a-pack',
    async run(w) {
      const { id, pack, single } = offerPackThenEpisode(w, 'packpick', [2]);
      const streams = await w.list('series', id);
      const r = await play(streams[1].url);
      assert.equal(r.status, 200);
      assertBytes(r.body, single.media, 'the click falls back to the next Source');
      assert.equal(w.backend.submitsFor(pack.tag), 0, 'the pack whose wanted episode is gone never reaches AltMount');
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
    // A clicked list entry whose check cannot answer (the indexer does not hand out the NZB): the failure video,
    // nothing reaches AltMount, and the Source is not dead, so it plays once the indexer answers (ADR 0004).
    id: 'list-entry-check-that-cannot-answer-is-not-dead',
    async run(w) {
      const { id, sources } = offerMovie(w, [{ tag: 'unanswered-a' }, { tag: 'unanswered-b' }]);
      const before = w.backend.submitted.length;
      const streams = await w.list('movie', id);
      w.backend.setIndexerDown(503);
      try {
        assertFailureVideo(await play(streams[1].url));
      } finally {
        w.backend.setIndexerDown(0);
      }
      assert.equal(w.backend.submitted.length, before, 'nothing reaches AltMount');
      const again = await w.list('movie', id);
      const entry = again.find(s => !isBest(s) && entryTitle(s) === sources[0].title);
      assert.ok(entry, 'the Source is still offered');
      const r = await play(entry.url);
      assert.equal(r.status, 200);
      assertBytes(r.body, sources[0].media, 'it plays once the indexer answers');
    },
  },
  {
    // No enabled health-check provider: nothing can be checked, so nothing is handed to AltMount, from Best or
    // from a list entry, and no Source is dead: once a provider is back, Best plays the first.
    id: 'no-health-check-provider-nothing-is-handed-over',
    async run(w) {
      const { id, sources } = offerMovie(w, [{ tag: 'noprov-a' }, { tag: 'noprov-b' }]);
      const before = w.backend.submitted.length;
      const streams = await w.list('movie', id);
      const saved = w.configData.healthChecks;
      w.configData.healthChecks = { ...saved, providers: saved.providers.map(p => ({ ...p, enabled: false })) };
      try {
        assertFailureVideo(await play(streams[0].url));
        assertFailureVideo(await play(streams[1].url));
      } finally {
        w.configData.healthChecks = saved;
      }
      assert.equal(w.backend.submitted.length, before, 'nothing reaches AltMount');
      const again = await w.list('movie', id);
      const r = await play(again[0].url);
      assert.equal(r.status, 200);
      assertBytes(r.body, sources[0].media, 'Best plays the first Source once a provider is back');
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
