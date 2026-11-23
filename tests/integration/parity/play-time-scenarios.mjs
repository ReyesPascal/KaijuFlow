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
 * this order). Each spec: { tag, kind: 'healthy' | 'dead' | 'gone' | 'rejected' | 'never-ready' | 'scrambled-rar4' | 'disc-image' }
 * ('gone': the indexer answers 404 to every grab of it).
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
      : kind === 'gone' ? backend.addGone(spec.tag)
      : kind === 'rejected' ? backend.addRejected(spec.tag, title)
      : kind === 'never-ready' ? backend.addNeverReady(spec.tag, title)
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

/**
 * A pack blocked on its wanted episode (S01E02, `id`) is remembered dead for that episode only (#203): S01E02's list no
 * longer offers it, S01E03's still does.
 */
async function assertDeadForThisEpisodeOnly(w, id, pack) {
  const titles = async episodeId => (await w.list('series', episodeId)).filter(s => !isBest(s)).map(entryTitle);
  assert.ok(!(await titles(id)).includes(pack.title), 'the pack is dead for the episode its check blocked');
  assert.ok((await titles(id.replace(/:2$/, ':3'))).includes(pack.title), 'another episode\'s list still offers the pack');
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

/** Wait until a log line passes test, or fail after 20 s naming what. */
async function until(test, what) {
  const deadline = Date.now() + 20000;
  while (!test()) {
    if (Date.now() > deadline) throw new Error(`${what} not within 20 s`);
    await new Promise(r => setTimeout(r, 25));
  }
}

/** Wait until Best's run has ended (its summary line "N checked · N healthy"), so every import it makes has been made.
 *  With a title id, only that title's run counts. */
async function bestDone(lines, id = '') {
  const done = new RegExp(`Ultimate-Fallback \\[[^\\]]*${id}[^\\]]*\\]\\s+\\d+ checked · \\d+ healthy`);
  await until(() => lines.some(l => done.test(l)), `Best's run${id ? ` for ${id}` : ''}`);
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

/**
 * A run's visit as the brain tools read it: the list request, a Browse pause long enough for the Head start, then a
 * press of Best. Returns KaijuFlow's lines, each after its time as `docker logs --timestamps` writes it, and the play.
 */
async function capturedVisit(w, id) {
  const lines = [];
  const saved = console.log;
  console.log = (...a) => { lines.push(`${new Date().toISOString()} ${a.map(x => (typeof x === 'string' ? x : JSON.stringify(x))).join(' ')}`); };
  try {
    const streams = await w.list('movie', id);
    await bestDone(lines, id);
    const r = await play(streams[0].url);
    return { lines, r };
  } finally { console.log = saved; }
}

const isBest = s => s.name.includes('KaijuFlow ▶ Best');
/** The release name a list entry plays (from its tile envelope). */
const entryTitle = s => JSON.parse(Buffer.from(new URL(s.url).searchParams.get('t'), 'base64url').toString()).title;

export const playTimeScenarios = [
  {
    // The list goes out at once, sorted and unchecked, with the Best entry on top and the full list below: it waits
    // for no check (the Head start's checks answer after it).
    id: 'list-at-once-unchecked-best-on-top',
    async run(w) {
      const { id, sources } = offerMovie(w, [{ tag: 'list-a' }, { tag: 'list-b' }, { tag: 'list-c', kind: 'dead' }]);
      w.news.slow('list-', 500);
      try {
        const streams = await w.list('movie', id);
        const listed = Date.now();
        assert.equal(streams.length, 4, 'Best plus every Source');
        assert.ok(isBest(streams[0]), `Best is on top (got ${streams[0].name})`);
        assert.equal(streams.slice(1).map(entryTitle).join(' | '), sources.map(s => s.title).join(' | '), 'the full list below, in sort order');
        const answered = w.news.state.asks.filter(a => a.id.startsWith('list-') && a.answered !== null && a.answered <= listed);
        assert.equal(answered.length, 0, 'no check had answered when the list went out');
        assert.ok(!streams.some(s => /✅|❌|🚫/.test(s.title)), 'no Source shows a health verdict');
      } finally {
        w.news.slow('list-', 0);
      }
    },
  },
  {
    // Head start (#206): a list request alone starts Best's check and one AltMount import, the first healthy
    // Source; a press of Best then plays it with no new import.
    id: 'head-start-checks-and-prepares-best-before-a-play',
    async run(w) {
      const { id, sources } = offerMovie(w, [{ tag: 'hs-dead', kind: 'dead' }, { tag: 'hs-ok' }, { tag: 'hs-other' }]);
      const before = w.backend.submitted.length;
      const { result: streams } = await withLogs(async lines => {
        const out = await w.list('movie', id);
        await bestDone(lines, id);
        return out;
      });
      for (const s of sources) assert.ok(checked(w, s.tag) > 0, `${s.tag} was checked before any play`);
      assert.deepEqual(w.backend.submitted.slice(before), ['hs-ok'], 'one AltMount import before any play, the first healthy Source');
      const r = await play(streams[0].url);
      assert.equal(r.status, 200, 'Best plays');
      assertBytes(r.body, sources[1].media, 'Best plays the Source its Head start prepared');
      assert.deepEqual(w.backend.submitted.slice(before), ['hs-ok'], 'the press makes no new import');
    },
  },
  {
    // Head start, one title at a time (#206): a list request for another title stops the unfinished check of the
    // one before, so none of its Sources reaches AltMount; a press of its Best later still plays, checked then.
    id: 'a-newer-list-request-stops-the-head-start-before-it',
    async run(w) {
      const a = offerMovie(w, [{ tag: 'stop-a1' }, { tag: 'stop-a2' }]);
      const b = offerMovie(w, [{ tag: 'stop-b1' }]);
      const before = w.backend.submitted.length;
      const aTags = ['stop-a1', 'stop-a2'];
      w.news.slow('stop-a', 1500);
      let streamsA;
      try {
        await withLogs(async lines => {
          streamsA = await w.list('movie', a.id);
          await until(() => w.news.state.asks.some(x => x.id.startsWith('stop-a')), 'the first title\'s check');
          await w.list('movie', b.id);
          await bestDone(lines, a.id);
          const answered = w.news.state.asks.filter(x => x.id.startsWith('stop-a') && x.answered !== null);
          assert.equal(answered.length, 0, 'the first title\'s run ended mid-check, stopped');
          await bestDone(lines, b.id);
        });
        await new Promise(r => setTimeout(r, 1700)); // the first title's checks would have answered by now
        for (const tag of aTags) assert.equal(w.backend.submitsFor(tag), 0, `${tag} never reaches AltMount`);
        assert.deepEqual(w.backend.submitted.slice(before), ['stop-b1'], 'only the newest title\'s Head start imports');
      } finally {
        w.news.slow('stop-a', 0);
      }
      const r = await play(streamsA[0].url);
      assert.equal(r.status, 200, 'a press of the stopped title\'s Best still plays');
      assertBytes(r.body, a.sources[0].media, 'its Best checks and prepares on the press');
      assert.equal(w.backend.submitsFor('stop-a1'), 1);
    },
  },
  {
    // Head start, one title at a time (#206), stopped mid-import: a list request for another title while the first
    // title's import is under way stops its run. AltMount ends an import it has begun on its own (KaijuFlow cannot
    // stop it), but KaijuFlow hands it nothing more for the first title: that import fails and no next Source follows.
    id: 'a-newer-list-request-stops-the-head-start-mid-import',
    async run(w) {
      const a = offerMovie(w, [{ tag: 'stopimp-a1', kind: 'never-ready' }, { tag: 'stopimp-a2' }]);
      const b = offerMovie(w, [{ tag: 'stopimp-b1' }]);
      const before = w.backend.submitted.length;
      const { result: streamsA } = await withLogs(async lines => {
        const out = await w.list('movie', a.id);
        await until(() => w.backend.submitsFor('stopimp-a1') === 1, 'the first title\'s import');
        await w.list('movie', b.id);
        await bestDone(lines, a.id);
        await bestDone(lines, b.id);
        return out;
      });
      await new Promise(r => setTimeout(r, 600)); // the first title's import has failed by now (AltMount answers 408 after 300 ms)
      assert.equal(w.backend.submitsFor('stopimp-a2'), 0, 'the first title\'s next Source never reaches AltMount');
      assert.deepEqual(w.backend.submitted.slice(before), ['stopimp-a1', 'stopimp-b1'], 'the import under way, then only the newest title\'s');
      const r = await play(streamsA[0].url);
      assert.equal(r.status, 200, 'a press of the stopped title\'s Best still plays');
      assertBytes(r.body, a.sources[1].media, 'checked and prepared on the press');
    },
  },
  {
    // A player that asks for the list only when it plays (no Browse pause): the press joins the Head start just
    // begun and plays, with one import.
    id: 'a-player-that-asks-only-at-play-still-plays',
    async run(w) {
      const { id, sources } = offerMovie(w, [{ tag: 'atplay-a' }, { tag: 'atplay-b' }]);
      const before = w.backend.submitted.length;
      const { result: r } = await withLogs(async lines => {
        const streams = await w.list('movie', id);
        const out = await play(streams[0].url);
        await bestDone(lines, id);
        return out;
      });
      assert.equal(r.status, 200, 'Best plays');
      assertBytes(r.body, sources[0].media, 'Best plays the top Source');
      assert.deepEqual(w.backend.submitted.slice(before), ['atplay-a'], 'one import');
    },
  },
  {
    // A press of Best makes its title's run a play: a list request for another title that comes while Best is
    // still checking does not stop it (Stremio asks for the next episode's list during a play).
    id: 'a-newer-list-request-does-not-stop-a-pressed-best',
    async run(w) {
      const a = offerMovie(w, [{ tag: 'claim-a' }]);
      const b = offerMovie(w, [{ tag: 'claim-b' }]);
      w.news.slow('claim-a', 800);
      try {
        const { result: r } = await withLogs(async lines => {
          const streams = await w.list('movie', a.id);
          const pressed = play(streams[0].url);
          await until(() => lines.some(l => l.includes(a.id) && l.includes('Best pressed')), 'the press');
          await w.list('movie', b.id);
          const out = await pressed;
          await bestDone(lines, b.id);
          return out;
        });
        assert.equal(r.status, 200, 'the pressed Best plays');
        assertBytes(r.body, a.sources[0].media, 'its Source, though another title\'s list came meanwhile');
        assert.equal(w.backend.submitsFor('claim-a'), 1);
        assert.equal(w.backend.submitsFor('claim-b'), 1, 'the newer title has its Head start too');
      } finally {
        w.news.slow('claim-a', 0);
      }
    },
  },
  {
    // The brain tools read a visit from KaijuFlow's log (tools/brain/docs/formats.md), from its list request on: one
    // play_check line per Source Best checked, the dead one too, and the top pick's name on the first prepare line
    // after the Head start's 'Head start: checking' line (#206), or after the press's '/stream hit' line without one;
    // the press writes 'Best plays' with the Source it played; the other healthy Source it checked is never prepared
    // (#192). The scenario's lines go out in its result (`capture`); scrubbed, they are
    // tools/brain/fixtures/2026-11-21-best/kaijuflow-best-dead-first.txt, which the brain tests read.
    id: 'best-press-log-lines-the-brain-tools-read',
    async run(w) {
      const { id, sources } = offerMovie(w, [{ tag: 'log-dead', kind: 'dead' }, { tag: 'log-ok' }, { tag: 'log-backup' }]);
      const { lines, r } = await capturedVisit(w, id);
      assertBytes(r.body, sources[1].media, 'Best plays the first healthy Source');
      const steps = lines.filter(l => l.includes('[KF-STEP] ')).map(l => JSON.parse(l.split('[KF-STEP] ')[1]));
      const check = tag => steps.filter(s => s.step === 'play_check' && s.title === sources.find(x => x.tag === tag).title);
      assert.deepEqual(check('log-dead').map(s => [s.ok, s.status]), [[false, 'blocked']], 'the dead Source\'s check is one line');
      assert.deepEqual(check('log-ok').map(s => [s.ok, s.status]), [[true, 'verified']], 'the played Source\'s check is one line');
      const hit = lines.findIndex(l => l.includes('/stream hit'));
      assert.ok(hit >= 0, 'the press writes its /stream hit line');
      const played = lines.slice(hit).map(l => l.match(/(?:Starting new stream preparation|Best plays): (.+?)\s*$/)?.[1]).filter(Boolean);
      assert.equal(played[0], sources[1].title, 'the first prepare or Best plays line after the press names the played Source');
      const prepared = lines.map(l => l.match(/Starting new stream preparation: (.+?)\s*$/)?.[1]).filter(Boolean);
      assert.deepEqual(prepared, [sources[1].title], 'only the played Source is prepared: not the dead one, not the other healthy one (#192)');
      return { capture: lines };
    },
  },
  {
    // A refusal during a Head start (#206): AltMount refuses the first healthy Source before the press, so the
    // Head start prepares the next one, and the press plays it with no new import. The brain tools count it a fallback
    // like a press-started one: the first prepare line after 'Head start: checking' names the refused top pick.
    // Scrubbed, the scenario's lines are tools/brain/fixtures/2026-11-21-best/kaijuflow-head-start-refused-first.txt.
    id: 'head-start-refusal-log-lines-the-brain-tools-read',
    async run(w) {
      const { id, sources } = offerMovie(w, [{ tag: 'hsr-refused', kind: 'rejected' }, { tag: 'hsr-ok' }, { tag: 'hsr-other' }]);
      const before = w.backend.submitted.length;
      const { lines, r } = await capturedVisit(w, id);
      assertBytes(r.body, sources[1].media, 'Best plays the next Source after the refusal');
      assert.equal(w.backend.submitsFor('hsr-refused'), 1, 'the refused Source was imported once, before the press');
      assert.deepEqual(w.backend.submitted.slice(before).filter(t => t !== 'hsr-refused'), ['hsr-ok'], 'the refusal makes one more import, the next Source');
      const hit = lines.findIndex(l => l.includes('/stream hit'));
      const start = lines.findLastIndex((l, i) => i < hit && l.includes('Head start: checking'));
      assert.ok(start >= 0 && hit > start, 'the Head start began before the press');
      const prepared = lines.slice(start).map(l => l.match(/Starting new stream preparation: (.+?)\s*$/)?.[1]).filter(Boolean);
      assert.deepEqual(prepared, [sources[0].title, sources[1].title], 'the Head start prepared the top pick, then the next one');
      assert.ok(lines.slice(hit).some(l => l.endsWith(`Best plays: ${sources[1].title}`)), 'the press names the Source it played');
      return { capture: lines };
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
      const before = w.backend.submitted.length;
      const { result: r } = await withLogs(async lines => {
        const streams = await w.list('movie', id);
        const out = await play(streams[0].url);
        await bestDone(lines, id);
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
      const before = w.backend.submitted.length;
      const { result: r } = await withLogs(async lines => {
        const streams = await w.list('movie', id);
        const out = await play(streams[0].url);
        await bestDone(lines, id);
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
    // Best checks 3 Sources at a time, from the top down, until one is healthy or the list runs out (owner,
    // 2026-11-20; the attempts cap setting was deleted in #228, only the Walk's 30 grabs bound it); 3 is
    // candidateCount's default.
    id: 'best-checks-3-at-a-time-with-no-cap',
    async run(w) {
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
    },
  },
  {
    // A list entry is checked when it is clicked: a healthy one plays after its articles are checked; a dead one
    // never reaches AltMount and the play falls back to the next Source of the list. With the Head start off, so
    // nothing is checked before the click.
    id: 'list-entry-is-checked-on-click',
    run: w => withSettings(w, { whenToResolve: 'on-tile-selection' }, async () => {
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
    }),
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
    // A list entry AltMount refuses falls back to the next Source (fresh title, nothing remembered: the Head start
    // off, so no Best run has met the refusal first).
    id: 'list-entry-refused-falls-back-to-next',
    run: w => withSettings(w, { whenToResolve: 'on-tile-selection' }, async () => {
      const { id, sources } = offerMovie(w, [{ tag: 'entry-refused', kind: 'rejected' }, { tag: 'entry-next' }]);
      const streams = await w.list('movie', id);
      const r = await play(streams[1].url);
      assert.equal(r.status, 200);
      assertBytes(r.body, sources[1].media, 'the next Source plays');
      assert.equal(w.backend.submitsFor('entry-refused'), 1);
      assert.equal(w.backend.submitsFor('entry-next'), 1);
    }),
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
    // Its first episode is complete but S01E02 is gone: Best does not hand the pack to AltMount. The pack is
    // remembered dead for S01E02 only: S01E03's list still offers it.
    id: 'best-checks-the-wanted-episode-of-a-pack',
    async run(w) {
      const { id, pack, single } = offerPackThenEpisode(w, 'packbest', [2]);
      const streams = await w.list('series', id);
      assert.equal(entryTitle(streams[1]), pack.title, 'the pack is the top Source');
      const r = await play(streams[0].url);
      assert.equal(r.status, 200);
      assertBytes(r.body, single.media, 'Best plays the next Source');
      assert.equal(w.backend.submitsFor(pack.tag), 0, 'the pack whose wanted episode is gone never reaches AltMount');
      await assertDeadForThisEpisodeOnly(w, id, pack);
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
    // #203 from a list entry: a click on the pack checks the wanted episode's file and falls back to the next Source;
    // the pack is remembered dead for that episode only.
    id: 'list-entry-checks-the-wanted-episode-of-a-pack',
    async run(w) {
      const { id, pack, single } = offerPackThenEpisode(w, 'packpick', [2]);
      const streams = await w.list('series', id);
      const r = await play(streams[1].url);
      assert.equal(r.status, 200);
      assertBytes(r.body, single.media, 'the click falls back to the next Source');
      assert.equal(w.backend.submitsFor(pack.tag), 0, 'the pack whose wanted episode is gone never reaches AltMount');
      await assertDeadForThisEpisodeOnly(w, id, pack);
    },
  },
  {
    // AltMount unreachable while Best is pressed: the failure video, but the checked Source is not dead, so
    // it plays once AltMount is back (ADR 0004).
    id: 'best-with-altmount-unreachable-not-dead',
    async run(w) {
      const { id, sources } = offerMovie(w, [{ tag: 'down-ok' }]);
      w.backend.setDown(true); // before the list: its Head start meets AltMount down too
      try {
        const streams = await w.list('movie', id);
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
      w.backend.setIndexerDown(503); // before the list: its Head start cannot get the NZBs either
      try {
        const streams = await w.list('movie', id);
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
      const saved = w.configData.healthChecks;
      // Before the list: its Head start has no provider either.
      w.configData.healthChecks = { ...saved, providers: saved.providers.map(p => ({ ...p, enabled: false })) };
      try {
        const streams = await w.list('movie', id);
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
  {
    // #193 (spec #183, Seam 1): a stored 7z set, its parts named `<name>.7z.001` ..., holds no RAR names, so
    // Unscramble skips it from the names alone, before reading any article, and it goes up as it is; the check
    // passes it (stored 7z, ADR 0009) and it plays.
    id: 'a-stored-7z-set-is-skipped-by-unscramble-and-plays',
    async run(w) {
      const id = `tt${nextImdb++}`;
      const title = 'KaijuFlow.PlayTime.SevenZip.2026.2160p.WEB-DL.H265-GRP';
      const media = mediaFor('sevenzip');
      const link = w.backend.addSevenZip('sevenzip', title, media);
      w.indexer.offer(id, [{ tag: 'sevenzip', title, media, link, size: 20 * GB }]);
      const original = await (await fetch(link)).text();
      const { result: r, lines } = await withLogs(async lines => {
        const streams = await w.list('movie', id);
        await bestDone(lines, id);
        return play(streams[0].url);
      });
      const steps = lines.filter(l => l.startsWith('[KF-STEP] ')).map(l => JSON.parse(l.slice('[KF-STEP] '.length)));
      assert.deepEqual(steps.filter(s => s.step === 'play_check' && s.title === title).map(s => s.status), ['verified_stored'], 'the check passes it');
      // no RAR-named or number-named parts: Unscramble ends before reading anything (its reads: unscramble-step.test.ts)
      assert.deepEqual(steps.filter(s => s.step === 'unscramble' && s.title === title).map(s => [s.result, s.parts]), [['not-scrambled', 0]],
        'Unscramble decides from its names alone');
      assert.deepEqual(w.backend.uploadedNzbs('sevenzip'), [original], 'it goes up as it is');
      assert.equal(r.status, 200, 'the 7z set plays');
      assertBytes(r.body, media, 'its video');
    },
  },
  {
    // A Best run that ends before checking anything settles its session (#206): here the Head start found every
    // Source dead, so the press's own run finds them all remembered dead and ends at once. The press goes on to the
    // failure video at once, not after the lobby's wait for a session that never answers.
    id: 'a-press-whose-best-run-ends-early-goes-on-at-once',
    async run(w) {
      const { id } = offerMovie(w, [{ tag: 'gone-1', kind: 'dead' }, { tag: 'gone-2', kind: 'dead' }]);
      const { result: streams } = await withLogs(async lines => {
        const out = await w.list('movie', id);
        await bestDone(lines, id);
        return out;
      });
      const pressed = Date.now();
      assertFailureVideo(await play(streams[0].url));
      assert.ok(Date.now() - pressed < 10000, `the press ends at once (took ${Date.now() - pressed} ms)`);
    },
  },
  {
    // #228 (GLOSSARY: Walk): 40 Sources the indexer says are gone, every grab answering 404. A failed grab is replaced
    // once, so no more grabs are under way than Best checks at a time (3); the Walk stops after 30 grabs, says so
    // once, and the press ends as when the list runs out: the failure video, no Source grabbed twice. With the Head
    // start off, so the press walks on its own.
    id: 'a-walk-of-gone-sources-stops-at-30-grabs',
    run: w => withSettings(w, { whenToResolve: 'on-tile-selection' }, async () => {
      const tags = [...Array(40).keys()].map(i => `walkgone-${i + 1}`);
      const { id } = offerMovie(w, tags.map(tag => ({ tag, kind: 'gone' })));
      w.backend.slowGrabs('walkgone-', 40);
      try {
        const { result: r, lines } = await withLogs(async () => {
          const streams = await w.list('movie', id);
          return play(streams[0].url);
        });
        assertFailureVideo(r);
        assertWalkStoppedAt30(w, lines, 'walkgone-', tags);
      } finally {
        w.backend.slowGrabs('walkgone-', 0);
      }
    }),
  },
  {
    // The 30 grabs are one Walk's (GLOSSARY: Walk): a press that joins its title's Head start continues that Walk and
    // its count, so the Head start and the press together grab 30 of the 40 gone Sources, not 30 each.
    id: 'a-press-that-joins-a-head-start-continues-its-walk',
    async run(w) {
      const tags = [...Array(40).keys()].map(i => `joingone-${i + 1}`);
      const { id } = offerMovie(w, tags.map(tag => ({ tag, kind: 'gone' })));
      w.backend.slowGrabs('joingone-', 60);
      try {
        const { result: r, lines } = await withLogs(async () => {
          const streams = await w.list('movie', id);
          await until(() => w.backend.grabs.some(g => g.tag.startsWith('joingone-')), 'the Head start\'s first grab');
          return play(streams[0].url);
        });
        assertFailureVideo(r);
        assertWalkStoppedAt30(w, lines, 'joingone-', tags);
      } finally {
        w.backend.slowGrabs('joingone-', 0);
      }
    },
  },
  {
    // The Walk's limits cost no play: a Healthy Source below a few gone Sources plays, as it did before #228, each
    // gone Source grabbed once and only the played Source handed to AltMount.
    id: 'best-plays-a-healthy-source-below-failed-grabs',
    async run(w) {
      const specs = [1, 2, 3, 4, 5].map(i => ({ tag: `below-gone-${i}`, kind: 'gone' })).concat([{ tag: 'below-ok-6' }, { tag: 'below-ok-7' }]);
      const { id, sources } = offerMovie(w, specs);
      const before = w.backend.submitted.length;
      const streams = await w.list('movie', id);
      const r = await play(streams[0].url);
      assert.equal(r.status, 200, 'Best plays');
      assertBytes(r.body, sources[5].media, 'Best plays the first Healthy Source, below the gone ones');
      assert.deepEqual(w.backend.submitted.slice(before), ['below-ok-6'], 'only the played Source reaches AltMount');
      const gone = w.backend.grabs.filter(g => g.tag.startsWith('below-gone-')).map(g => g.tag);
      assert.deepEqual([...gone].sort(), specs.slice(0, 5).map(s => s.tag).sort(), 'each gone Source grabbed once');
    },
  },
];

/**
 * One Walk over gone Sources (#228): 30 grabs reached the indexer, the top 30 of the list, none twice, never more than
 * 3 under way at once (a failed grab replaced once), and one log line saying the Walk stopped at 30.
 */
function assertWalkStoppedAt30(w, lines, prefix, tags) {
  const grabs = w.backend.grabs.filter(g => g.tag.startsWith(prefix));
  const grabbed = grabs.map(g => g.tag);
  assert.equal(new Set(grabbed).size, grabbed.length, `no Source grabbed twice (${grabbed.length} grabs of ${new Set(grabbed).size} Sources)`);
  const most = mostAtOnce(grabs.map(g => ({ from: g.asked, to: g.answered ?? Infinity })));
  assert.ok(most <= 3, `at most 3 grabs under way at once, a failed grab replaced once (${most} at once)`);
  assert.equal(grabbed.length, 30, 'the Walk stops after 30 grabs');
  assert.deepEqual([...grabbed].sort(), tags.slice(0, 30).sort(), 'the top 30 of the list');
  const said = lines.filter(l => /Walk stopped: 30 grabs/.test(l));
  assert.equal(said.length, 1, `one log line says the Walk stopped (${said.length})`);
}

/** Run every play-time scenario. Returns per-scenario results. */
export async function runPlayTimeParity(w) {
  const results = [];
  for (const s of playTimeScenarios) {
    const before = w.backend.requests.length;
    try {
      const out = await s.run(w);
      // A scenario's captured log lines (`capture`) ride in its result, for the brain tools' fixtures.
      results.push({ id: s.id, status: 'pass', ...(out?.capture ? { capture: out.capture } : {}) });
    } catch (e) {
      results.push({ id: s.id, status: 'fail', error: String(e?.stack || e), requests: w.backend.requests.slice(before).slice(-15) });
    }
  }
  return results;
}
