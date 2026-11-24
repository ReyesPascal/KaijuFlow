// Play-time check scenarios (#190, spec #183; GLOSSARY: Play-time check, Best entry, Unchecked Source).
// Each scenario asks for a title's stream list through the fake indexer, then plays an entry of it,
// and asserts only on what the player receives, what the fake news server was asked and what
// reached the fake AltMount; one scenario asserts on the log lines the brain tools read.
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import { syncBuiltinESMExports } from 'node:module';
import { assertBytes } from './bytes.mjs';
import { scrambledRarSet } from './fake-nntp.mjs';

const mediaFor = tag => Buffer.from(`KaijuFlow play-time bytes for ${tag}: 0123456789abcdefghijklmnopqrstuvwxyz`);
const GB = 1024 ** 3;
let nextImdb = 1000001;

/**
 * Offer movie Sources for a new title, in list order (same quality, sizes going down, so KaijuFlow's sort keeps
 * this order). Each spec: { tag, file? (its video file's name, a healthy one's), kind: 'healthy' | 'dead' | 'gone' | 'rejected' | 'never-ready' | 'first-byte-400' | 'scrambled-rar4' | 'disc-image' }
 * ('gone': the indexer answers 404 to every grab of it; 'first-byte-400': AltMount answers 400 to its first byte).
 * Returns { id, sources: [{ tag, title, media }] }.
 */
function offerMovie({ backend, indexer }, specs) {
  const id = `tt${nextImdb++}`;
  const items = specs.map((spec, i) => {
    const title = `KaijuFlow.PlayTime.${spec.tag}.2026.2160p.WEB-DL.H265-GRP`;
    const media = mediaFor(spec.tag);
    const kind = spec.kind ?? 'healthy';
    const link = kind === 'healthy' ? backend.addMovie(spec.tag, title, media, spec.file ? { file: spec.file } : {})
      : kind === 'dead' ? backend.addMovie(spec.tag, title, media, { dead: true })
      : kind === 'gone' ? backend.addGone(spec.tag)
      : kind === 'rejected' ? backend.addRejected(spec.tag, title)
      : kind === 'never-ready' ? backend.addNeverReady(spec.tag, title)
      : kind === 'first-byte-400' ? backend.addFirstByteFault(spec.tag, title, media, 'bad-request')
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
 * Offer, for S01E02 of a new daily show (TVDB: aired 2026-11-03), a season pack whose files are named by aired date,
 * not SxxExx (S01E01 to S01E03), on top, then a single-episode Source of S01E02. S01E02's file in the pack is gone
 * (its articles missing), the others are complete. Returns { id, pack, single }.
 */
function offerDailyPackThenEpisode({ backend, indexer, tvdb }, tag) {
  const show = `tt${nextImdb++}`;
  const aired = ['2026-11-02', '2026-11-03', '2026-11-04'];
  tvdb.addShow(show, `KaijuFlow Daily ${tag}`, aired.map((a, i) => ({ season: 1, episode: i + 1, aired: a })));
  const packTitle = `KaijuFlow.PlayTime.Daily.S01.1080p.WEB-DL.H264-${tag}`;
  const episodes = aired.map((a, i) => ({ season: 1, episode: i + 1, media: mediaFor(`${tag}-e${i + 1}`), name: `KaijuFlow.PlayTime.Daily.${a.replace(/-/g, '.')}.1080p.WEB-DL.H264-${tag}` }));
  const pack = { tag: `${tag}-pack`, title: packTitle, media: episodes[1].media, size: 30 * GB };
  pack.link = backend.addSeries(pack.tag, packTitle, episodes, { deadEpisodes: [2] });
  const single = { tag: `${tag}-single`, title: `KaijuFlow.PlayTime.Daily.S01E02.1080p.WEB-DL.H264-${tag}`, media: mediaFor(`${tag}-single`), size: 2 * GB };
  single.link = backend.addSeries(single.tag, single.title, [{ season: 1, episode: 2, media: single.media }]);
  indexer.offer(show, [pack, single]);
  return { id: `${show}:1:2`, pack, single };
}

/** Run fn with the fake TVDB's key in the settings, so titles get their episodes (and aired dates) from it. */
async function withTvdb(w, fn) {
  const saved = w.configData.searchConfig;
  w.configData.searchConfig = { ...saved, tvdbApiKey: w.tvdb.key };
  try { return await fn(); } finally { w.configData.searchConfig = saved; }
}

/**
 * A press of Best on a daily show's date-named pack (offerDailyPackThenEpisode) checks the pack on S01E02's file,
 * found by its aired date, so the pack whose S01E02 is gone never reaches AltMount and Best plays S01E02 from the
 * next Source. The same whether the press walks on its own (On Click) or joins its Head start (On Search).
 */
async function assertBestPlaysTheAiredEpisode(w, { id, pack, single }, headStart) {
  await withLogs(async lines => {
    const streams = await w.list('series', id);
    assert.equal(entryTitle(streams[1]), pack.title, 'the pack is the top Source');
    if (headStart) await bestDone(lines, id.split(':')[0]);
    const r = await play(streams[0].url);
    assert.equal(r.status, 200);
    assertBytes(r.body, single.media, 'Best plays S01E02 from the next Source');
  });
  assert.equal(w.backend.submitsFor(pack.tag), 0, 'the pack whose aired-date file is gone never reaches AltMount');
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

async function play(url, range, timeoutMs = 30000) {
  const res = await fetch(url, { headers: range ? { Range: range } : {}, signal: AbortSignal.timeout(timeoutMs) });
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

/**
 * A Walk ends when another title's list is asked for (GLOSSARY: Walk, #244): every check of the Sources tagged
 * `prefix` that was under way had its connection closed, unanswered, before that title's search reached the indexer.
 */
function assertStoppedBeforeSearch(w, prefix, nextId) {
  const search = w.indexer.searches.find(s => `tt${s.imdbid}` === nextId);
  assert.ok(search, `${nextId} was searched`);
  const asks = w.news.state.asks.filter(a => a.id.startsWith(prefix));
  assert.ok(asks.length > 0, `${prefix} was being checked`);
  for (const a of asks) {
    assert.ok(a.closed !== undefined, `${a.id}: its check was stopped, not answered`);
    assert.ok(a.closed <= search.at, `${a.id}: stopped ${a.closed - search.at} ms after ${nextId}'s search began, not before it`);
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

/**
 * A run's visit as the brain tools read it: the list request, a Browse pause long enough for the Head start, then a
 * press of Best. Returns KaijuFlow's lines, each after its time as `docker logs --timestamps` writes it, and the play.
 */
async function capturedVisit(w, id) {
  const visit = { id, t_start: new Date().toISOString() };
  const { lines, r } = await timedLines(async lines => {
    const streams = await w.list('movie', id);
    await bestDone(lines, id);
    return play(streams[0].url);
  });
  return { lines, visit, r };
}

/** Run fn(lines) and collect KaijuFlow's lines meanwhile, each after its time as `docker logs --timestamps` writes it. */
async function timedLines(fn) {
  const lines = [];
  const saved = console.log;
  console.log = (...a) => { lines.push(`${new Date().toISOString()} ${a.map(x => (typeof x === 'string' ? x : JSON.stringify(x))).join(' ')}`); };
  try { return { r: await fn(lines), lines }; } finally { console.log = saved; }
}

/** The step lines among KaijuFlow's lines, parsed. */
const stepsOf = lines => lines.filter(l => l.includes('[KF-STEP] ')).map(l => JSON.parse(l.split('[KF-STEP] ')[1]));

/**
 * What the brain tools read of one visit's play from KaijuFlow's lines: the real reader, brainreport.read_play, as
 * brainrun.collect_visit calls it (tools/brain, copied next to the scenarios by in-namespace.sh). visit: { id, t_start }.
 */
function brainRead(lines, visit) {
  const code = 'import json, sys; sys.path.insert(0, sys.argv[1]); import brainreport; a = json.load(sys.stdin); '
    + 'print(json.dumps(brainreport.read_play(a["text"], a["visit"])))';
  const r = spawnSync('python3', ['-I', '-c', code, `${process.env.A4_APP_ROOT}/brain`],
    { input: JSON.stringify({ text: lines.join('\n') + '\n', visit }), encoding: 'utf8' });
  assert.equal(r.status, 0, r.stderr);
  return JSON.parse(r.stdout);
}

/** Why a Source whose first byte AltMount answers 400 failed, in KaijuFlow's words without the file path. */
const FIRST_BYTE_400 = 'First byte failed (status 400); the Source is kept';

const isBest = s => s.name.includes('KaijuFlow ▶ Best');
/** The release name a list entry plays (from its tile envelope). */
const entryTitle = s => JSON.parse(Buffer.from(new URL(s.url).searchParams.get('t'), 'base64url').toString()).title;

/** How long the slow indexer takes to answer a search in the list deadline's scenarios (#301). */
const SLOW_INDEXER_MS = 1500;

/**
 * Offer movie Sources for a new title named `KaijuFlow PlayTime <name>` (2026) on the suite's indexer (fast) and on the
 * second one, which answers SLOW_INDEXER_MS late (#301). Each spec: { tag, kind?: 'healthy' | 'dead' }. A tag that
 * ends in `-CE` makes a maybe (`CE` between the name and the year), any other a sure Source. Sizes go down in the
 * order given, fast ones first. Returns { id, fast: [...], slow: [...] }, each { tag, title, media, link, size }.
 */
function offerFastAndSlow(w, name, fastSpecs, slowSpecs) {
  const id = `tt${nextImdb++}`;
  w.cinemeta.add(id, { name: `KaijuFlow PlayTime ${name}`, year: '2026' });
  let i = 0;
  const make = spec => {
    const group = spec.tag.endsWith('-CE') ? `${name}-CE` : name;
    const title = `KaijuFlow.PlayTime.${group}.2026.2160p.WEB-DL.H265-${spec.tag.replace(/-/g, '')}`;
    const media = mediaFor(spec.tag);
    const link = w.backend.addMovie(spec.tag, title, media, spec.kind === 'dead' ? { dead: true } : {});
    return { tag: spec.tag, title, media, link, size: (20 - i++) * GB };
  };
  const fast = fastSpecs.map(make), slow = slowSpecs.map(make);
  w.indexer.offer(id, fast);
  w.second.offer(id, slow);
  w.second.slow(SLOW_INDEXER_MS);
  return { id, fast, slow };
}

/**
 * Offer movie Releases for a new title on the suite's indexer and on the second one (#299), in list order (same
 * quality, sizes going down). Each spec: { tag, on: 'both' | 'one', apart? (the second indexer's size, off by this
 * fraction) }. The second indexer's copy has its own link. Returns { id, releases: [{ tag, title, size }] }.
 */
function offerReleases({ backend, indexer, second }, specs) {
  const id = `tt${nextImdb++}`;
  const first = [], other = [];
  const releases = specs.map((spec, i) => {
    const title = `KaijuFlow.PlayTime.${spec.tag}.2026.2160p.WEB-DL.H265-GRP`;
    const size = (20 - i) * GB;
    first.push({ title, size, link: backend.addMovie(spec.tag, title, mediaFor(spec.tag)) });
    if (spec.on === 'both') other.push({ title, size: Math.round(size * (1 + (spec.apart ?? 0.004))), link: second.nzbLink(`${spec.tag}-second`) });
    return { tag: spec.tag, title, size };
  });
  indexer.offer(id, first);
  second.offer(id, other);
  return { id, releases };
}

export const playTimeScenarios = [
  {
    // Releases (#299; GLOSSARY: Release): an upload the second indexer has too (its own link, a size 0.4 % off) is
    // listed once; one whose second copy is 2 % off in size is two uploads, listed twice.
    id: 'an-upload-on-two-indexers-is-listed-once',
    async run(w) {
      await withIndexer(w, w.second.entry, async () => {
        const { id, releases: [same, apart, alone] } = offerReleases(w, [{ tag: 'rel-same', on: 'both' }, { tag: 'rel-apart', on: 'both', apart: 0.02 }, { tag: 'rel-alone', on: 'one' }]);
        const streams = await w.list('movie', id);
        assert.ok(isBest(streams[0]), 'Best on top');
        assert.deepEqual(streams.slice(1).map(entryTitle).sort(), [same.title, apart.title, apart.title, alone.title].sort(),
          'the same upload once; the same name 2 % apart in size twice');
      });
    },
  },
  {
    // The stream limits (per resolution, per quality, total) count Releases (#299): with a limit of 2 and the top two
    // Releases on both indexers, the list holds those two Releases, not one Release twice.
    id: 'the-stream-limits-count-releases',
    async run(w) {
      const saved = w.configData.movieFilters;
      try {
        await withIndexer(w, w.second.entry, async () => {
          for (const limit of ['maxStreamsPerResolution', 'maxStreamsPerQuality', 'maxStreams']) {
            w.configData.movieFilters = { ...w.config.filters, [limit]: 2 };
            const { id, releases: [a, b] } = offerReleases(w, [{ tag: `lim-${limit}-a`, on: 'both' }, { tag: `lim-${limit}-b`, on: 'both' }, { tag: `lim-${limit}-c`, on: 'one' }]);
            const streams = await w.list('movie', id);
            assert.deepEqual(streams.filter(s => !isBest(s)).map(entryTitle), [a.title, b.title], `${limit} 2: the top two Releases`);
          }
        });
      } finally {
        w.configData.movieFilters = saved;
      }
    },
  },
  {
    // The list deadline (#301): the fast indexer's answer holds a sure Source, so the list goes out at its time, not
    // the slow one's. That Source is dead; the slow indexer's healthy Source arrives after the list and joins the
    // Head start's Walk, which waits for it instead of ending, and Best plays it. The next list request shows it.
    id: 'a-late-source-joins-a-walk-whose-fast-sources-failed',
    async run(w) {
      const { id, fast: [dead], slow: [late] } = offerFastAndSlow(w, 'late', [{ tag: 'late-fast', kind: 'dead' }], [{ tag: 'late-slow' }]);
      try {
        await withIndexer(w, w.second.entry, async () => {
          const t0 = Date.now();
          const { result: streams, lines } = await withLogs(async () => {
            const out = await w.list('movie', id);
            await new Promise(r => setImmediate(r)); // the list's own step line is written one turn after the answer
            return out;
          });
          const listed = Date.now() - t0;
          assert.ok(listed < SLOW_INDEXER_MS - 300, `the list went out at the fast indexer's time (${listed} ms)`);
          assert.deepEqual(stepsOf(lines).filter(x => x.step === 'list' && x.ref === id).map(x => x.not_waited_for), [['Second']], 'its list line names the indexer it did not wait for');
          assert.deepEqual(streams.filter(s => !isBest(s)).map(entryTitle), [dead.title], 'the fast indexer\'s Source alone');
          const r = await play(streams[0].url);
          assert.equal(r.status, 200, 'Best plays');
          assertBytes(r.body, late.media, 'Best plays the slow indexer\'s Source');
          assert.ok((await w.list('movie', id)).filter(s => !isBest(s)).map(entryTitle).includes(late.title), 'the next list shows the late Source');
        });
      } finally {
        w.second.slow(0);
      }
    },
  },
  {
    // The list deadline (#301): the fast indexer's answer holds only a maybe, so the list waits for the slow one and
    // holds both indexers' Sources; Best plays the slow indexer's sure Source, not the fast one's healthy maybe.
    id: 'the-list-waits-for-the-slow-indexer-when-the-fast-one-has-nothing-sure',
    async run(w) {
      const { id, fast: [maybe], slow: [sure] } = offerFastAndSlow(w, 'wait', [{ tag: 'wait-CE' }], [{ tag: 'wait-sure' }]);
      try {
        await withIndexer(w, w.second.entry, async () => {
          const t0 = Date.now();
          const { result: streams, lines } = await withLogs(async () => {
            const out = await w.list('movie', id);
            await new Promise(r => setImmediate(r)); // the list's own step line is written one turn after the answer
            return out;
          });
          const listedAt = Date.now();
          assert.deepEqual(stepsOf(lines).filter(x => x.step === 'list' && x.ref === id).map(x => 'not_waited_for' in x), [false], 'its list line names no indexer it did not wait for');
          assert.ok(listedAt - t0 >= SLOW_INDEXER_MS, `the list waited for the slow indexer (${listedAt - t0} ms)`);
          assert.deepEqual(streams.filter(s => !isBest(s)).map(entryTitle).sort(), [maybe.title, sure.title].sort(), 'both indexers\' Sources');
          const r = await play(streams[0].url);
          assert.equal(r.status, 200, 'Best plays');
          assertBytes(r.body, sure.media, 'Best plays the sure Source');
        });
      } finally {
        w.second.slow(0);
      }
    },
  },
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
    // The list's step lines (#249): each list request writes its parts (filters, sort, build, fallback group,
    // Head start) and one `list` line for the whole request with a trace of the process meanwhile; the first list of
    // a title searched, the second came from the search cache. The brain tools read a warm list's time from them.
    id: 'a-list-writes-its-step-lines-and-process-trace',
    async run(w) {
      const { id } = offerMovie(w, [{ tag: 'ls-a' }, { tag: 'ls-b' }]);
      const { lines } = await withLogs(async lines => {
        await w.list('movie', id);
        await bestDone(lines, id);
        await w.list('movie', id);
        await until(() => stepsOf(lines).filter(s => s.step === 'list').length === 2, 'two list lines');
      });
      const steps = stepsOf(lines).filter(s => s.ref === id);
      const lists = steps.filter(s => s.step === 'list');
      assert.deepEqual(lists.map(s => [s.cache, s.streams]), [['miss', 3], ['hit', 3]], 'one list line per request: Best and two Sources');
      for (const s of lists) {
        for (const f of ['ms', 'cpu_ms', 'gc_ms', 'gc_n', 'loop_max_ms', 'loop_p99_ms', 'heap_mb']) assert.ok(Number.isInteger(s[f]) && s[f] >= 0, `list ${s.cache}: ${f} ${s[f]}`);
        assert.ok(s.elu >= 0 && s.elu <= 1, `list ${s.cache}: elu ${s.elu}`);
      }
      const parts = ['list_filter', 'list_sort', 'fallback_group', 'list_build', 'head_start'];
      for (const name of parts) assert.equal(steps.filter(s => s.step === name).length, 2, `one ${name} line per list`);
      const filter = steps.find(s => s.step === 'list_filter');
      assert.deepEqual([filter.results, filter.kept], [2, 2], 'the filters saw both Sources and kept both');
      const group = steps.find(s => s.step === 'fallback_group');
      assert.equal(group.candidates, 2);
      assert.ok(group.groups >= 1, 'the group write says how many groups it saved');
    },
  },
  {
    // Head start, one title at a time (#206): a list request for another title stops the unfinished check of the
    // one before as it arrives, before its own search (#244), so none of its Sources reaches AltMount; a press of
    // its Best later still plays, checked then.
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
          assertStoppedBeforeSearch(w, 'stop-a', b.id);
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
      const { result: streamsA, lines } = await withLogs(async lines => {
        const out = await w.list('movie', a.id);
        await until(() => w.backend.submitsFor('stopimp-a1') === 1, 'the first title\'s import');
        await w.list('movie', b.id);
        await bestDone(lines, a.id);
        await bestDone(lines, b.id);
        return out;
      });
      assert.ok(lines.some(l => /\b0 dead\b/.test(l)), 'the stopped Walk reports 0 dead Sources');
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
    // A press of Best makes its title's run a play: a list request for another title that comes while the press
    // still waits for its video does not stop its Walk (Stremio asks for the next episode's list during a play, #244).
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
        const stopped = w.news.state.asks.filter(x => x.id.startsWith('claim-a') && x.closed !== undefined);
        assert.equal(stopped.length, 0, 'the waiting press\'s checks ran on, none stopped');
        assert.equal(w.backend.submitsFor('claim-a'), 1);
        assert.equal(w.backend.submitsFor('claim-b'), 1, 'the newer title has its Head start too');
      } finally {
        w.news.slow('claim-a', 0);
      }
    },
  },
  {
    // A Walk ends when another title's list is asked for (#244): once a press's video has arrived, its Walk's
    // leftover checks (here of a lower Source) are stopped as the next title's list request arrives, before its
    // search starts, so they don't compete with it for connections (#219: Night Moves into Upstream Color). The video
    // already playing goes on being served.
    id: 'a-newer-list-request-stops-a-played-walks-leftover-checks',
    async run(w) {
      const a = offerMovie(w, [{ tag: 'left-a1' }, { tag: 'left-a2' }]);
      const b = offerMovie(w, [{ tag: 'left-b1' }]);
      w.news.slow('left-a2', 4000);
      try {
        await withLogs(async lines => {
          const streams = await w.list('movie', a.id);
          const r = await play(streams[0].url);
          assert.equal(r.status, 200, 'Best plays');
          assertBytes(r.body, a.sources[0].media, 'Best plays the top Source');
          assert.ok(w.news.state.asks.some(x => x.id.startsWith('left-a2') && x.answered === null), 'the lower Source\'s check is still under way');
          await w.list('movie', b.id);
          assertStoppedBeforeSearch(w, 'left-a2', b.id);
          const seek = await play(streams[0].url, 'bytes=10-29');
          assert.equal(seek.status, 206, 'the video goes on being served after the next title\'s list request');
          assertBytes(seek.body, a.sources[0].media.subarray(10, 30), 'the same video');
          await bestDone(lines, b.id);
          // A stopped check answered nothing: no play_check line, so the brain tools don't count it in the next visit's wait.
          const steps = stepsOf(lines);
          assert.equal(steps.filter(s => s.step === 'play_check' && s.title === a.sources[1].title).length, 0, 'no play_check line for the stopped check');
        });
        assert.equal(w.backend.submitsFor('left-a2'), 0, 'the lower Source never reaches AltMount');
      } finally {
        w.news.slow('left-a2', 0);
      }
    },
  },
  {
    // The same for a grab (#244, #239 story 8): a played Walk's grab of a lower Source still waiting for the indexer
    // is cut off as the next title's list request arrives, before its search starts. The stop is not a failed grab:
    // no "Grab failed" line, and the Source is not dead (A's list still offers it).
    id: 'a-newer-list-request-cuts-off-a-played-walks-leftover-grab',
    async run(w) {
      const a = offerMovie(w, [{ tag: 'leftgrab-a1' }, { tag: 'leftgrab-a2' }]);
      const b = offerMovie(w, [{ tag: 'leftgrab-b1' }]);
      w.backend.slowGrabs('leftgrab-a2', 4000);
      try {
        await withLogs(async lines => {
          const streams = await w.list('movie', a.id);
          const r = await play(streams[0].url);
          assert.equal(r.status, 200, 'Best plays');
          assertBytes(r.body, a.sources[0].media, 'Best plays the top Source');
          const grab = () => w.backend.grabs.find(g => g.tag === 'leftgrab-a2');
          assert.ok(grab() && grab().answered === null, 'the lower Source\'s grab is still waiting for the indexer');
          await w.list('movie', b.id);
          const search = w.indexer.searches.find(s => `tt${s.imdbid}` === b.id);
          assert.ok(search, `${b.id} was searched`);
          assert.ok(grab().closed !== undefined, 'the grab was cut off, not answered');
          assert.ok(grab().closed <= search.at, `the grab was cut off ${grab().closed - search.at} ms after the next title's search began, not before it`);
          await bestDone(lines, b.id);
          assert.ok(!lines.some(l => l.includes('Grab failed') && l.includes(a.sources[1].title)), 'a stopped grab is not a failed grab');
        });
        const titles = (await w.list('movie', a.id)).filter(s => !isBest(s)).map(entryTitle);
        assert.ok(titles.includes(a.sources[1].title), 'the cut-off Source is not dead');
      } finally {
        w.backend.slowGrabs('leftgrab-a2', 0);
      }
    },
  },
  {
    // The same for a connect under way (#239 story 8): with one health-check connection allowed, a Head start's check
    // stuck in a stalled news server's greeting holds the only one, and its other check waits for it. The next title's
    // list request stops the Walk: that connect is closed before its search and the waiting one never opens, so the
    // next title's check gets the connection at once, not after the stuck connect's 10 s timeout.
    id: 'a-newer-list-request-closes-the-stopped-walks-connects',
    async run(w) {
      const a = offerMovie(w, [{ tag: 'conn-a1' }, { tag: 'conn-a2' }]);
      const b = offerMovie(w, [{ tag: 'conn-b1' }]);
      const saved = w.configData.healthChecks;
      w.configData.healthChecks = { ...saved, maxTotalConnections: 1 };
      const from = w.news.state.connections.length;
      const mine = () => w.news.state.connections.slice(from);
      w.news.hold(1);
      try {
        await withLogs(async lines => {
          await w.list('movie', a.id);
          await until(() => mine().some(c => c.held), 'the first title\'s connect, its greeting held');
          await w.list('movie', b.id);
          await bestDone(lines, b.id);
        });
        const search = w.indexer.searches.find(s => `tt${s.imdbid}` === b.id);
        assert.ok(search, `${b.id} was searched`);
        const held = mine().find(c => c.held);
        assert.ok(held.closed !== undefined && held.closed <= search.at, 'the stuck connect was closed before the next title\'s search');
        const ask = w.news.state.asks.find(x => x.id.startsWith('conn-b1'));
        assert.ok(ask, 'the next title was checked');
        assert.ok(ask.asked - search.at < 3000, `the next title's check got the connection ${ask.asked - search.at} ms after its search began`);
        assert.equal(mine().filter(c => !c.held && c.asked === 0).length, 0, 'the stopped Walk opened no connection after its stop');
      } finally {
        w.news.hold(0);
        w.configData.healthChecks = saved;
      }
    },
  },
  {
    // The brain tools read a visit from KaijuFlow's step lines only (tools/brain/docs/formats.md), from its list request
    // on: one play_check line per Source Best checked, the dead one too, and one `played` line when the press serves the
    // Source's video; the other healthy Source it checked is never prepared (#192). The real reader
    // (brainreport.read_play) reads them. The scenario's lines go out in its result (`capture`); scrubbed, they are
    // tools/brain/fixtures/2026-11-23-step-lines/kaijuflow-best-dead-first.txt, which the brain tests read.
    id: 'best-press-log-lines-the-brain-tools-read',
    async run(w) {
      const { id, sources } = offerMovie(w, [{ tag: 'log-dead', kind: 'dead' }, { tag: 'log-ok' }, { tag: 'log-backup' }]);
      const before = w.backend.submitted.length;
      const { lines, visit, r } = await capturedVisit(w, id);
      assertBytes(r.body, sources[1].media, 'Best plays the first healthy Source');
      const steps = stepsOf(lines);
      const check = tag => steps.filter(s => s.step === 'play_check' && s.title === sources.find(x => x.tag === tag).title);
      assert.deepEqual(check('log-dead').map(s => [s.ok, s.status]), [[false, 'blocked']], 'the dead Source\'s check is one line');
      assert.deepEqual(check('log-ok').map(s => [s.ok, s.status]), [[true, 'verified']], 'the played Source\'s check is one line');
      assert.deepEqual(steps.filter(s => s.step === 'played').map(s => [s.title, s.source]), [[sources[1].title, 'Parity']], 'the press writes one played line');
      assert.deepEqual(brainRead(lines, visit), { played_source: sources[1].title, cause: '' });
      assert.deepEqual(w.backend.submitted.slice(before), ['log-ok'], 'only the played Source is prepared: not the dead one, not the other healthy one (#192)');
      return { capture: lines };
    },
  },
  {
    // One `played` line per press (#242), not per request: the player's range probe and seek of the same entry within
    // 15 s write no second line, for a press of Best and for a list entry. The brain tools count one play per line.
    id: 'a-range-probe-or-seek-of-the-same-entry-writes-no-second-played-line',
    async run(w) {
      const { id, sources } = offerMovie(w, [{ tag: 'once-a' }, { tag: 'once-b' }]);
      const { lines } = await withLogs(async () => {
        const streams = await w.list('movie', id);
        const entry = streams.find(s => !isBest(s) && entryTitle(s) === sources[1].title);
        for (const url of [streams[0].url, entry.url]) {
          assert.equal((await play(url)).status, 200);
          assert.equal((await play(url, 'bytes=10-')).status, 206, 'a range probe');
          assert.equal((await play(url, 'bytes=20-30')).status, 206, 'a seek');
        }
      });
      const played = stepsOf(lines).filter(s => s.step === 'played').map(s => s.title);
      assert.deepEqual(played, [sources[0].title, sources[1].title], 'one played line for Best\'s press, one for the list entry');
    },
  },
  {
    // A player that left while its list entry was preparing gets nothing, so nothing was played: no `played` line
    // (the brain tools read a visit's played Source from it, story 29). No Head start, so only the list entry prepares.
    id: 'a-player-that-left-writes-no-played-line',
    run: w => withSettings(w, { whenToResolve: 'on-tile-selection' }, async () => {
      const { id, sources } = offerMovie(w, [{ tag: 'left-a' }]);
      w.backend.slowImports('left-a', 3000);
      try {
        const { lines } = await withLogs(async lines => {
          const streams = await w.list('movie', id);
          const entry = streams.find(s => !isBest(s) && entryTitle(s) === sources[0].title);
          await assert.rejects(play(entry.url, undefined, 1000), 'the player gives up after 1 s');
          await until(() => lines.some(l => l.includes('Stream ready') && l.includes(sources[0].title)), 'the prepare ending');
          await new Promise(r => setTimeout(r, 500));
        });
        const played = stepsOf(lines).filter(s => s.step === 'played' && s.title === sources[0].title);
        assert.equal(played.length, 0, 'no played line for a player that left');
      } finally {
        w.backend.slowImports('left-a', 0);
      }
    }),
  },
  {
    // #246: a list request writes its fallback group, with its play context, to disk once (config/fallback-groups.json).
    id: 'a-list-request-writes-its-fallback-group-once',
    async run(w) {
      const { id } = offerMovie(w, [{ tag: 'fbgonce-a' }, { tag: 'fbgonce-b' }]);
      const writes = await groupFileWrites(() => w.list('movie', id));
      assert.equal(writes, 1, 'one write of the fallback groups file');
    },
  },
  {
    // A refusal during a Head start (#206): AltMount refuses the first healthy Source before the press, so the
    // Head start prepares the next one, and the press plays it with no new import. The Head start writes a play_failed
    // line for the refused Source, so the brain tools name it the top pick and count a fallback, as for a press-started
    // Best. Scrubbed, the lines are tools/brain/fixtures/2026-11-23-step-lines/kaijuflow-head-start-refused-first.txt.
    id: 'head-start-refusal-log-lines-the-brain-tools-read',
    async run(w) {
      const { id, sources } = offerMovie(w, [{ tag: 'hsr-refused', kind: 'rejected' }, { tag: 'hsr-ok' }, { tag: 'hsr-other' }]);
      const before = w.backend.submitted.length;
      const { lines, visit, r } = await capturedVisit(w, id);
      assertBytes(r.body, sources[1].media, 'Best plays the next Source after the refusal');
      assert.equal(w.backend.submitsFor('hsr-refused'), 1, 'the refused Source was imported once, before the press');
      assert.deepEqual(w.backend.submitted.slice(before).filter(t => t !== 'hsr-refused'), ['hsr-ok'], 'the refusal makes one more import, the next Source');
      const hit = lines.findIndex(l => l.includes('/stream hit'));
      const failed = lines.findIndex(l => l.includes('"step":"play_failed"'));
      assert.ok(failed >= 0 && failed < hit, 'the Head start wrote the refusal before the press');
      const read = brainRead(lines, visit);
      assert.equal(read.played_source, sources[0].title, 'the top pick is the refused Source');
      assert.ok(read.cause, 'the refusal in KaijuFlow\'s words');
      assert.deepEqual(stepsOf(lines).filter(s => s.step === 'played').map(s => s.title), [sources[1].title], 'the press names the Source it played');
      return { capture: lines };
    },
  },
  {
    // A failed press of Best: its one Source is checked healthy, but AltMount answers 400 at the first byte, so the
    // press shows the failure video. The brain tools read the top pick and why it failed from the play_failed line,
    // in KaijuFlow's words without the file path. Scrubbed, the lines are
    // tools/brain/fixtures/2026-11-23-step-lines/kaijuflow-best-first-byte-failed.txt.
    id: 'failed-best-press-log-lines-the-brain-tools-read',
    async run(w) {
      const { id, sources } = offerMovie(w, [{ tag: 'fbf-400', kind: 'first-byte-400' }]);
      const { lines, visit, r } = await capturedVisit(w, id);
      assertFailureVideo(r);
      assert.equal(stepsOf(lines).filter(s => s.step === 'played').length, 0, 'no played line for a failure video');
      assert.deepEqual(brainRead(lines, visit), { played_source: sources[0].title, cause: FIRST_BYTE_400 });
      assert.ok(!lines.filter(l => l.includes('[KF-STEP] ')).some(l => /\/\S+\.mkv|https?:/.test(l)), 'step lines carry no path or address');
      return { capture: lines };
    },
  },
  {
    // A clicked list entry (the Head start off): the entry fails at the first byte and the next Source plays, so the
    // brain tools name the clicked entry the top pick, with its cause. A click of the same entry in a later list reuses
    // the delivery (the Stremio dedup cache) and still names what it plays. A clicked entry that is the only Source
    // shows the failure video, read the same way.
    id: 'list-entry-log-lines-the-brain-tools-read',
    run: w => withSettings(w, { whenToResolve: 'on-tile-selection' }, async () => {
      const click = async id => {
        const t_start = new Date().toISOString();
        const { lines, r } = await timedLines(async () => play((await w.list('movie', id))[1].url));
        return { r, read: brainRead(lines, { id, t_start }) };
      };
      const { id, sources } = offerMovie(w, [{ tag: 'lel-400', kind: 'first-byte-400' }, { tag: 'lel-ok' }]);
      const first = await click(id);
      assertBytes(first.r.body, sources[1].media, 'the next Source plays');
      assert.deepEqual(first.read, { played_source: sources[0].title, cause: FIRST_BYTE_400 });
      const again = await click(id);
      assertBytes(again.r.body, sources[1].media, 'the same delivery');
      assert.equal(w.backend.submitsFor('lel-ok'), 1, 'reused, not prepared again');
      assert.deepEqual(again.read, { played_source: sources[1].title, cause: '' });

      const only = offerMovie(w, [{ tag: 'lel-only', kind: 'first-byte-400' }]);
      const failed = await click(only.id);
      assertFailureVideo(failed.r);
      assert.deepEqual(failed.read, { played_source: only.sources[0].title, cause: FIRST_BYTE_400 });
    }),
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
    // Search Flow (#282): Best tries the sure Sources (the strict name rule passes them) before the maybe ones. The
    // maybe stays in the list, above the sure one where the sort puts it (`CE` between the name and the year is no
    // tag the strict rule allows; the indexer found it by ID, which no name rule drops); Best plays the sure one.
    id: 'best-tries-a-sure-source-before-a-maybe-above-it',
    async run(w) {
      const { id, sources } = offerMovie(w, [{ tag: 'flow-sure-CE' }, { tag: 'flow-sure' }]);
      w.cinemeta.add(id, { name: 'KaijuFlow PlayTime flow-sure', year: '2026' });
      const before = w.backend.submitted.length;
      const streams = await w.list('movie', id);
      assert.equal(streams.slice(1).map(entryTitle).join(' | '), sources.map(s => s.title).join(' | '), 'both Sources listed, the maybe on top');
      const r = await play(streams[0].url);
      assert.equal(r.status, 200, 'Best plays');
      assertBytes(r.body, sources[1].media, 'Best plays the sure Source');
      assert.equal(w.backend.submitted[before], 'flow-sure', 'the sure Source is the first AltMount gets');
    },
  },
  {
    // Search Flow's extra proof (#286): the video file name inside a maybe's NZB, read when the Play-time check fetches
    // it, makes the maybe sure. The maybe (`CE` between the name and the year; found by ID) holds a video file whose
    // name fits the title; with the dev switch on, the played line says it was made sure by it and names the file.
    id: 'a-maybe-whose-nzb-video-file-fits-is-sure',
    async run(w) {
      const file = 'KaijuFlow.PlayTime.flow-proof.2026.2160p.WEB-DL.H265-GRP.mkv';
      const { id, sources } = offerMovie(w, [{ tag: 'flow-proof-CE', file }]);
      w.cinemeta.add(id, { name: 'KaijuFlow PlayTime flow-proof', year: '2026' });
      const saved = w.configData.devDiagnostics;
      w.configData.devDiagnostics = true;
      try {
        const { result: r, lines } = await withLogs(async lines => {
          const streams = await w.list('movie', id);
          await bestDone(lines, id);
          return play(streams[0].url);
        });
        assert.equal(r.status, 200, 'Best plays');
        assertBytes(r.body, sources[0].media, 'Best plays the maybe');
        const steps = stepsOf(lines);
        assert.deepEqual(steps.filter(s => s.step === 'play_check' && s.title === sources[0].title).map(s => s.video), [file], 'the check names the NZB\'s video file');
        assert.deepEqual(steps.filter(s => s.step === 'played').map(s => [s.title, s.flow, s.proof, s.video]),
          [[sources[0].title, 'sure', 'nzb video', file]], 'played: sure by the NZB\'s video file');
      } finally {
        w.configData.devDiagnostics = saved;
      }
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
    // #246: a press of Best that walks on its own (On Click, no Head start) reads the play context the list made, so
    // it looks for a daily show's episode file by its aired date as the Head start does.
    id: 'on-click-best-finds-a-daily-episode-by-its-aired-date',
    run: w => withSettings(w, { whenToResolve: 'on-tile-selection' }, () =>
      withTvdb(w, () => assertBestPlaysTheAiredEpisode(w, offerDailyPackThenEpisode(w, 'dailyclick'), false))),
  },
  {
    // #246: the same layout under On Search: the Head start finds the same file.
    id: 'head-start-finds-a-daily-episode-by-its-aired-date',
    run: w => withTvdb(w, () => assertBestPlaysTheAiredEpisode(w, offerDailyPackThenEpisode(w, 'dailysearch'), true)),
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
      let lines;
      // Before the list: its Head start has no provider either.
      w.configData.healthChecks = { ...saved, providers: saved.providers.map(p => ({ ...p, enabled: false })) };
      try {
        const { result: streams, lines: captured } = await withLogs(async () => {
          const streams = await w.list('movie', id);
          assertFailureVideo(await play(streams[0].url));
          assertFailureVideo(await play(streams[1].url));
          return streams;
        });
        lines = captured;
      } finally {
        w.configData.healthChecks = saved;
      }
      assert.ok(lines.some(l => /\b2 dead\b/.test(l)), 'the Walk reports 2 dead Sources when no provider can check them');
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
      const steps = stepsOf(lines);
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
      const { result: r, lines } = await withLogs(() => play(streams[0].url));
      assert.equal(r.status, 200, 'Best plays');
      assertBytes(r.body, sources[5].media, 'Best plays the first Healthy Source, below the gone ones');
      assert.deepEqual(w.backend.submitted.slice(before), ['below-ok-6'], 'only the played Source reaches AltMount');
      const gone = w.backend.grabs.filter(g => g.tag.startsWith('below-gone-')).map(g => g.tag);
      assert.deepEqual([...gone].sort(), specs.slice(0, 5).map(s => s.tag).sort(), 'each gone Source grabbed once');
      assert.ok(lines.some(l => /\b5 dead\b/.test(l)), 'the Walk reports the five failed grabs');
    },
  },
  {
    // #245 (ADR 0005, amended 2026-11-23): the news server drops one of Unscramble's connections, a read-error. It is
    // retried once and the retry Unscrambles the set, so the Scrambled RAR set plays; AltMount gets only the renamed
    // NZB. The Walk's checks and Unscramble stay under the one connection cap (the default, 8) all along.
    id: 'an-unscramble-read-error-is-retried-and-the-source-plays',
    async run(w) {
      const top = offerScrambled(w, 'retryok');
      const { id } = top;
      w.indexer.offer(id, [top.item, healthyBelow(w, 'retryok-next', 10)]);
      w.news.drop(top.dropAt, 1);
      w.news.state.peak = w.news.state.open;
      try {
        const { result: r, lines } = await withLogs(async () => play((await w.list('movie', id))[0].url));
        assert.equal(r.status, 200, 'Best plays');
        assertBytes(r.body, top.item.media, 'the Scrambled RAR set plays');
        assert.deepEqual(unscrambleResults(lines, top.item.title), ['read-error', 'unscrambled'], 'one read-error, then the retry Unscrambles it');
        const uploaded = w.backend.uploadedNzbs(top.tag);
        assert.equal(uploaded.length, 1, 'one upload');
        assert.equal(w.backend.rarVolumeCheck(uploaded[0]), null, 'AltMount gets the parts renamed in real order');
        assert.equal(w.news.state.drops.filter(d => d.id.startsWith(top.dropAt)).length, 1, 'one of Unscramble\'s connections was dropped');
        assert.ok(w.news.state.peak <= 8, `the checks and Unscramble together held ${w.news.state.peak} connections, cap 8`);
      } finally {
        w.news.drop(top.dropAt, 0);
      }
    },
  },
  {
    // A Walk ends when another title's list is asked for (GLOSSARY: Walk, #244), its Unscramble under way too: a Head
    // start's Scrambled RAR set is checked and handed over, and its Unscramble is reading (one part's first article,
    // which the check doesn't read, held 5 s) when another title's list is asked for. The read is cut off before that
    // title's search, so the search has the connections to itself, and the set never reaches AltMount.
    id: 'a-newer-list-request-cuts-off-a-head-start-s-unscramble',
    async run(w) {
      const top = offerScrambled(w, 'stopuns');
      w.indexer.offer(top.id, [top.item]);
      const b = offerMovie(w, [{ tag: 'stopuns-b' }]);
      w.news.slow(top.dropAt, 5000);
      try {
        await withLogs(async lines => {
          await w.list('movie', top.id);
          await until(() => w.news.state.asks.some(a => a.id.startsWith(top.dropAt)), 'the Head start\'s Unscramble read');
          await w.list('movie', b.id);
          await bestDone(lines, top.id);
        });
        assertStoppedBeforeSearch(w, top.dropAt, b.id);
        await new Promise(r => setTimeout(r, 500)); // a prepare that went on would upload now
        assert.deepEqual(w.backend.uploadedNzbs(top.tag), [], 'the stopped Head start uploads nothing');
      } finally {
        w.news.slow(top.dropAt, 0);
      }
    },
  },
  {
    // #245: the retry gets a read-error too. Nothing is uploaded for the Scrambled RAR set (AltMount always rejects
    // the original) and the Walk moves on: the next Healthy Source plays. The set is not dead (ADR 0004), so its
    // title's next list still offers it. The retry runs with the Walk's other checks stopped: the next Source's check,
    // slowed so it is under way, asks nothing while the retry reads and is run again after it, not grabbed again.
    id: 'an-unscramble-that-fails-its-retry-is-not-uploaded-and-the-next-source-plays',
    async run(w) {
      const top = offerScrambled(w, 'retrybad');
      const { id } = top;
      const next = healthyBelow(w, 'retrybad-next', 10);
      w.indexer.offer(id, [top.item, next]);
      w.news.drop(top.dropAt);
      w.news.slow('retrybad-next-', 1500);
      try {
        const { result: r, lines } = await withLogs(async () => play((await w.list('movie', id))[0].url));
        assert.equal(r.status, 200, 'Best plays');
        assertBytes(r.body, next.media, 'the next Healthy Source plays');
        assert.deepEqual(unscrambleResults(lines, top.item.title), ['read-error', 'read-error'], 'a read-error, retried once');
        assert.deepEqual(w.backend.uploadedNzbs(top.tag), [], 'nothing is uploaded for the set');
        const drops = w.news.state.drops.filter(d => d.id.startsWith(top.dropAt));
        assert.equal(drops.length, 2, 'the first read and the retry each lost a connection');
        // The retry reads from the first drop to the second.
        const [from, to] = drops.map(d => d.at);
        const nextAsks = w.news.state.asks.filter(a => a.id.startsWith('retrybad-next-'));
        assert.ok(nextAsks.some(a => a.asked < from && (a.answered ?? Infinity) > from), 'the next Source\'s check was under way when the retry began');
        assert.deepEqual(nextAsks.filter(a => a.asked >= from && a.asked <= to).map(a => a.id), [], 'its check asks nothing while the retry reads');
        assert.ok(nextAsks.some(a => a.asked > to), 'its check runs again after the retry');
        assert.equal(w.backend.grabs.filter(g => g.tag === 'retrybad-next').length, 1, 'its check runs again, the Source is not grabbed again');
        // The tools read KaijuFlow only through step lines (#239): the stopped check writes no verdict, only its run
        // after the retry does.
        const checks = stepsOf(lines)
          .filter(s => s.step === 'play_check' && s.title === next.title).map(s => s.status);
        assert.deepEqual(checks, ['verified'], 'one play_check line for the next Source: the stopped check says nothing');
        w.news.drop(top.dropAt, 0);
        const again = (await w.list('movie', id)).filter(s => !isBest(s)).map(entryTitle);
        assert.ok(again.includes(top.item.title), 'the set is not dead: its title\'s next list still offers it');
      } finally {
        w.news.drop(top.dropAt, 0);
        w.news.slow('retrybad-next-', 0);
      }
    },
  },
  {
    // ADR 0004, "The walk's grabs" (#243): an indexer that refuses a grab (429, its download limit) says nothing about
    // its Sources. The Walk asks it once, passes its other Sources by for the rest of the Walk, says so once, and
    // plays a Healthy Source from another indexer; no refused Source is dead. Best walks one Source at a time here,
    // so "once" is exact (at 3 at a time, the grabs already under way reach it too).
    id: 'a-refusing-indexer-is-asked-once-and-skipped',
    run: w => assertRefusingIndexerSkipped(w, w.refusing, 'refused'),
  },
  {
    // The Source memory (#247) through the real routes, for a dated episode (review rule 4): The Witcher S01E01, aired
    // 2019-12-20 (TVDB), so its play context carries the aired date and the file pattern AltMount is sent names it.
    // A press of Best walks and remembers the ready Source; a click on the same Source's list entry then recalls it.
    // AltMount gets the Source once: the second play's video came from the memory, not from a new upload that
    // AltMount answered from its own library.
    id: 'a-dated-episode-ready-from-best-is-recalled-by-the-next-play',
    run: w => withTvdb(w, async () => {
      const show = `tt${nextImdb++}`;
      w.tvdb.addShow(show, 'The Witcher', [1, 2, 3].map(episode => ({ season: 1, episode, aired: '2019-12-20' }))); // all out that day
      const s = { tag: 'witcher-e01', title: 'The.Witcher.S01E01.2160p.NF.WEB-DL.H265-GRP', media: mediaFor('witcher-e01'), size: 8 * GB };
      s.link = w.backend.addSeries(s.tag, s.title, [{ season: 1, episode: 1, media: s.media }]);
      w.indexer.offer(show, [s]);
      const { lines } = await withLogs(async () => {
        const streams = await w.list('series', `${show}:1:1`);
        assert.equal(entryTitle(streams[1]), s.title);
        const best = await play(streams[0].url);
        assert.equal(best.status, 200);
        assertBytes(best.body, s.media, 'Best plays S01E01');
        assert.equal(w.backend.submitsFor(s.tag), 1, 'Best\'s Walk handed the Source to AltMount');
        const entry = await play(streams[1].url);
        assert.equal(entry.status, 200);
        assertBytes(entry.body, s.media, 'the list entry plays S01E01');
      });
      assert.ok(lines.some(l => /TVDB episode count: .*\[aired 2019-12-20\]/.test(l)), 'the play context has S01E01\'s aired date');
      assert.ok(lines.some(l => l.includes(`Stream ready (AltMount, reused): ${s.title}`)), 'the list entry\'s prepare recalled the ready Source');
      assert.equal(w.backend.submitsFor(s.tag), 1, 'AltMount got the Source once: the second play came from the Source memory');
    }),
  },
  {
    // ADR 0004, "The walk's grabs": an indexer that answers a grab with 200 and a Newznab error payload is sorted by
    // the payload's code, as an HTTP answer is by its status. Code 500 (its request limit) is a refusal, as a 429 is:
    // asked once at a time, skipped for the rest of the Walk, none of its Sources dead.
    id: 'an-indexer-answering-an-error-payload-is-asked-once-and-skipped',
    run: w => assertRefusingIndexerSkipped(w, w.limited, 'limited'),
  },
  {
    // A refusal does not cancel the other grabs already in flight: with 3 Sources at a time, the indexer is asked
    // 3 times, then skipped for the rest of this Walk.
    id: 'a-refusing-indexer-at-3-at-a-time-is-asked-3-times-and-skipped',
    run: w => assertRefusingIndexerSkipped(w, w.refusing, 'refused-three', 3),
  },
  {
    // #255: a clicked list entry's walk-on is a Walk too (GLOSSARY: Walk). Its Sources are walked one at a time, so
    // an indexer refusing every grab (429) is asked once, then its other Sources are passed by for the rest of the
    // walk-on, said once; a Healthy Source from another indexer below still plays, and no refused Source is dead.
    id: 'a-list-entry-walk-on-asks-a-refusing-indexer-once-and-skips-it',
    run: w => assertRefusingIndexerSkipped(w, w.refusing, 'entry-refused', 1, { listEntry: true }),
  },
  {
    // #255, a 200 with a Newznab error payload (code 500, its request limit) is a refusal too, as for Best's Walk.
    id: 'a-list-entry-walk-on-asks-an-indexer-answering-an-error-payload-once-and-skips-it',
    run: w => assertRefusingIndexerSkipped(w, w.limited, 'entry-limited', 1, { listEntry: true }),
  },
  {
    // #255: 40 Sources the indexer says are gone (404) from a clicked list entry down. The walk-on marks each one it
    // grabs dead, stops after 30 grabs, says so once, and the play ends as when the list runs out: the failure video.
    // The 10 below the 30th are not grabbed, so they stay in the list.
    id: 'a-list-entry-walk-on-of-gone-sources-stops-at-30-grabs-and-marks-them-dead',
    run: w => withSettings(w, { whenToResolve: 'on-tile-selection' }, async () => {
      const tags = [...Array(40).keys()].map(i => `entrygone-${i + 1}`);
      const { id, sources } = offerMovie(w, tags.map(tag => ({ tag, kind: 'gone' })));
      const { result: r, lines } = await withLogs(async () => {
        const streams = await w.list('movie', id);
        assert.equal(entryTitle(streams[1]), sources[0].title, 'the top Source is the first list entry');
        return play(streams[1].url, undefined, 60000);
      });
      assertFailureVideo(r);
      assertWalkStoppedAt30(w, lines, 'entrygone-', tags);
      const again = (await w.list('movie', id)).filter(e => !isBest(e)).map(entryTitle);
      for (const s of sources.slice(0, 30)) assert.ok(!again.includes(s.title), `${s.tag} is dead: the list no longer offers it`);
      for (const s of sources.slice(30)) assert.ok(again.includes(s.title), `${s.tag} was not grabbed: still offered`);
    }),
  },
  {
    // #255, the limits cost no play: a Healthy Source below a few gone Sources plays from a clicked list entry, each
    // gone Source grabbed once and marked dead, and only the played Source handed to AltMount.
    id: 'a-list-entry-plays-a-healthy-source-below-gone-sources',
    run: w => withSettings(w, { whenToResolve: 'on-tile-selection' }, async () => {
      const specs = [1, 2, 3, 4, 5].map(i => ({ tag: `entrybelow-gone-${i}`, kind: 'gone' })).concat([{ tag: 'entrybelow-ok-6' }, { tag: 'entrybelow-ok-7' }]);
      const { id, sources } = offerMovie(w, specs);
      const before = w.backend.submitted.length;
      const streams = await w.list('movie', id);
      const r = await play(streams[1].url);
      assert.equal(r.status, 200, 'the list entry plays');
      assertBytes(r.body, sources[5].media, 'the first Healthy Source below the gone ones plays');
      assert.deepEqual(w.backend.submitted.slice(before), ['entrybelow-ok-6'], 'only the played Source reaches AltMount');
      const gone = w.backend.grabs.filter(g => g.tag.startsWith('entrybelow-gone-')).map(g => g.tag);
      assert.deepEqual([...gone].sort(), specs.slice(0, 5).map(s => s.tag).sort(), 'each gone Source grabbed once');
      const again = (await w.list('movie', id)).filter(e => !isBest(e)).map(entryTitle);
      for (const s of sources.slice(0, 5)) assert.ok(!again.includes(s.title), `${s.tag} is dead: the list no longer offers it`);
      assert.ok(again.includes(sources[5].title), 'the played Source is still offered');
    }),
  },
  {
    // ADR 0004, "The walk's grabs" (#243): a link the indexer says is gone (404) is a Source failure. The Walk marks
    // each gone Source dead and walks on, so the next play's Walk does not grab them again. AltMount is down for the
    // first play, so that Walk ends without a play (its Healthy Source stays alive) and the next press walks again.
    id: 'gone-sources-are-dead-and-not-grabbed-again',
    async run(w) {
      const goneTags = ['g404-a', 'g404-b', 'g404-c'];
      const { id, sources } = offerMovie(w, [...goneTags.map(tag => ({ tag, kind: 'gone' })), { tag: 'g404ok' }]);
      const goneGrabs = () => w.backend.grabs.filter(g => goneTags.includes(g.tag)).map(g => g.tag).sort();
      w.backend.setDown(true); // before the list: its Head start meets AltMount down too
      try {
        const streams = await w.list('movie', id);
        assertFailureVideo(await play(streams[0].url));
      } finally {
        w.backend.setDown(false);
      }
      assert.deepEqual(goneGrabs(), goneTags, 'each gone Source grabbed once');
      const again = await w.list('movie', id);
      for (const s of sources.slice(0, 3)) assert.ok(!again.some(e => !isBest(e) && entryTitle(e) === s.title), `${s.tag} is dead: the list no longer offers it`);
      const r = await play(again[0].url);
      assert.equal(r.status, 200, 'Best plays once AltMount is back');
      assertBytes(r.body, sources[3].media, 'the Healthy Source');
      assert.deepEqual(goneGrabs(), goneTags, 'the next play\'s Walk grabs none of them again');
    },
  },
  {
    // The Delivery method as it is now serves every request of a play (#248): the player's next request of a list
    // entry (a seek or probe, which the Stremio dedup answers without a new prepare) goes out with the method set
    // since its first request, not the one that first request was served with.
    id: 'a-play-s-next-request-uses-the-delivery-method-as-it-is-now',
    async run(w) {
      const { id, sources } = offerMovie(w, [{ tag: 'dlvnow' }]);
      const saved = w.configData.playDeliveryMethod;
      try {
        w.configData.playDeliveryMethod = 'proxy';
        const { result: streams } = await withLogs(async lines => {
          const out = await w.list('movie', id);
          await bestDone(lines, id);
          return out;
        });
        const entry = streams.find(s => !isBest(s) && entryTitle(s) === sources[0].title);
        const first = await askOnce(entry.url);
        assert.equal(first.status, 302, 'with the fallback on, proxy answers with a redirect');
        assert.match(first.location, /\/play\/v\?/, 'proxy goes through KaijuFlow\'s video route');
        const imports = w.backend.submitsFor('dlvnow');
        w.configData.playDeliveryMethod = 'direct';
        const second = await askOnce(entry.url);
        assert.equal(second.status, 302);
        assert.match(second.location, /\/api\/files\/stream\?/, 'the next request goes direct, the method set now');
        assert.equal(w.backend.submitsFor('dlvnow'), imports, 'the next request makes no new import');
        const r = await play(second.location);
        assert.equal(r.status, 200);
        assertBytes(r.body, sources[0].media, 'the direct link plays the Source');
      } finally {
        w.configData.playDeliveryMethod = saved;
      }
    },
  },
  {
    // Keep-alive (#248): a request that comes after a self-redirect answers within the ExoPlayer budget (8 s; more
    // and ExoPlayer on Android gives up). A list entry still preparing answers with another self-redirect, and the
    // player that follows it gets the video once it is ready.
    id: 'a-list-entry-after-a-self-redirect-answers-within-the-exoplayer-budget',
    async run(w) {
      const { id, sources } = offerMovie(w, [{ tag: 'exo-entry' }]);
      w.backend.slowImports('exo-entry', 12000);
      try {
        const streams = await w.list('movie', id);
        const url = afterRedirects(streams.find(s => !isBest(s)).url, 1);
        const r = await askOnce(url);
        assertSelfRedirect(r, url, 2, 'a list entry still preparing');
        assertWithinExoPlayerBudget(r);
        const played = await play(r.location);
        assert.equal(played.status, 200);
        assertBytes(played.body, sources[0].media, 'the player following the redirects gets the video');
      } finally {
        w.backend.slowImports('exo-entry', 0);
      }
    },
  },
  {
    // Keep-alive (#248), one rule whatever the entry: a press of Best after a self-redirect answers within the
    // ExoPlayer budget too, while its Walk's Source is still preparing.
    id: 'a-press-of-best-after-a-self-redirect-answers-within-the-exoplayer-budget',
    async run(w) {
      const { id, sources } = offerMovie(w, [{ tag: 'exo-best' }]);
      w.backend.slowImports('exo-best', 12000);
      try {
        const streams = await w.list('movie', id);
        const url = afterRedirects(streams[0].url, 1);
        const r = await askOnce(url);
        assertSelfRedirect(r, url, 2, 'a press of Best still waiting');
        assertWithinExoPlayerBudget(r);
        const played = await play(r.location);
        assert.equal(played.status, 200);
        assertBytes(played.body, sources[0].media, 'the player following the redirects gets Best\'s video');
      } finally {
        w.backend.slowImports('exo-best', 0);
      }
    },
  },
  {
    // The first-Source switch (#192, kept by the owner): a list entry still loading after 25 s gets the next Source
    // prepared beside it, and the one ready first plays. The first is not dead: it keeps preparing.
    id: 'a-list-entry-still-loading-after-25-s-plays-the-next-source',
    async run(w) {
      const { id, sources } = offerMovie(w, [{ tag: 'switch-a' }, { tag: 'switch-b' }]);
      w.backend.slowImports('switch-a', 40000);
      try {
        await withPrepareTimeout(w, 60, async () => {
          const streams = await w.list('movie', id);
          const entry = streams.find(s => !isBest(s) && entryTitle(s) === sources[0].title);
          const asked = Date.now();
          const r = await play(entry.url, undefined, 45000);
          const took = Date.now() - asked;
          assert.equal(r.status, 200);
          assertBytes(r.body, sources[1].media, 'the next Source plays');
          assert.ok(took >= 24500 && took < 32000, `the next Source played after ${took} ms, from 25 s on`);
          const again = await w.list('movie', id);
          assert.ok(again.some(e => !isBest(e) && entryTitle(e) === sources[0].title), 'the first Source is not dead');
        });
      } finally {
        w.backend.slowImports('switch-a', 0);
      }
    },
  },
];

/**
 * Keep-alive scenarios that wait out a player's 60 s window (#248), in their own suite (parity-keep-alive.mjs):
 * each suite process has 120 s.
 */
export const keepAliveScenarios = [
  {
    // The first-Source switch (#192) left the first Source preparing, and the next one fails (AltMount rejects it):
    // the play goes back to the first and waits for it in the player's window, instead of the failure video (Codex's
    // review of #239). No Head start, so only the list entry prepares.
    id: 'after-the-25-s-switch-a-failed-next-source-goes-back-to-the-first',
    async run(w) {
      const { id, sources } = offerMovie(w, [{ tag: 'back-a' }, { tag: 'back-b', kind: 'rejected' }]);
      w.backend.slowImports('back-a', 32000);
      try {
        await withSettings(w, { whenToResolve: 'on-tile-selection' }, () => withPrepareTimeout(w, 60, async () => {
          const streams = await w.list('movie', id);
          const entry = streams.find(s => !isBest(s) && entryTitle(s) === sources[0].title);
          const asked = Date.now();
          const r = await play(entry.url, undefined, 50000);
          const took = Date.now() - asked;
          assert.equal(r.status, 200);
          assertBytes(r.body, sources[0].media, 'the first Source plays, not the failure video');
          // Its import takes 32 s; a self-redirect would have come only at 55 s.
          assert.ok(took >= 31000 && took < 50000, `it played once the first Source was ready (${took} ms), in the first request`);
          assert.equal(w.backend.submitsFor('back-b'), 1, 'the next Source was tried');
          assert.equal(w.backend.submitsFor('back-a'), 1, 'the first Source was prepared once: waited for, not handed over again');
        }));
      } finally {
        w.backend.slowImports('back-a', 0);
      }
    },
  },
  {
    // Keep-alive (#248): one rule for the time left. A request still waiting near the end of the player's 60 s
    // window (at 55 s, 5 s to spare) answers with a self-redirect, whatever entry it plays: here a list entry whose
    // one Source is still preparing, which held the request until its video came. No Head start: its Walk gives
    // AltMount 30 s for a movie and marks a Source that takes longer dead, which is the Walk's rule, not the player's.
    id: 'a-list-entry-still-preparing-at-55-s-redirects-to-itself',
    async run(w) {
      const { id, sources } = offerMovie(w, [{ tag: 'window' }]);
      w.backend.slowImports('window', 59000);
      try {
        await withSettings(w, { whenToResolve: 'on-tile-selection', priorityMoviesTimeoutSeconds: 90 }, () => withPrepareTimeout(w, 90, async () => {
          const streams = await w.list('movie', id);
          const url = streams.find(s => !isBest(s)).url;
          const r = await askOnce(url, 70000);
          assertSelfRedirect(r, url, 1, 'a list entry still preparing at 55 s');
          assert.ok(r.at >= 54000 && r.at < 57500, `it answered after ${r.at} ms, 5 s before the player's 60 s`);
          const played = await play(r.location);
          assert.equal(played.status, 200);
          assertBytes(played.body, sources[0].media, 'the player following the redirect gets the video');
        }));
      } finally {
        w.backend.slowImports('window', 0);
      }
    },
  },
];

/**
 * The go-back after the first-Source switch (#192) across a self-redirect, the first Source still preparing: in a
 * suite of its own (parity-go-back-preparing.mjs), since it waits out a player's 60 s window.
 */
export const goBackPreparingScenarios = [
  {
    // The switch leaves the first Source preparing (59 s import); the next one is still preparing when the request's
    // 55 s are up, so the request self-redirects to it. It fails in the next request (first byte 400 at about 57 s).
    // The first is still preparing: the play goes back to it, as it does when the next Source fails within the
    // first request, and plays it once it is ready, instead of the failure video.
    id: 'after-the-25-s-switch-a-next-source-failing-after-a-self-redirect-goes-back-to-the-first',
    async run(w) {
      const { id, sources } = offerMovie(w, [{ tag: 'backrd-a' }, { tag: 'backrd-b', kind: 'first-byte-400' }]);
      w.backend.slowImports('backrd-a', 59000);
      w.backend.slowImports('backrd-b', 30000);
      try {
        await withSettings(w, { whenToResolve: 'on-tile-selection' }, () => withPrepareTimeout(w, 90, async () => {
          const streams = await w.list('movie', id);
          const entry = streams.find(s => !isBest(s) && entryTitle(s) === sources[0].title);
          const asked = Date.now();
          const { result: r, lines } = await withLogs(() => play(entry.url, undefined, 100000));
          const took = Date.now() - asked;
          assert.ok(lines.some(l => l.includes('Self-redirect') && l.includes('resuming at candidate 2')),
            'the first request ran out of time while the next Source was preparing, and resumed at it');
          assert.equal(w.backend.submitsFor('backrd-b'), 1, 'the next Source was tried');
          assert.equal(r.status, 200);
          assertBytes(r.body, sources[0].media, `the first Source plays once it is ready, not the failure video (answered after ${took} ms); ${lines.filter(l => /User-pick attempt|Decoded rc=|Sending Source to AltMount|Self-redirect|Every later Source|Stream failed|All \\d+ candidate/.test(l)).join(' | ')}`);
          assert.ok(took >= 58000, `it played once the first Source was ready (${took} ms)`);
          assert.equal(w.backend.submitsFor('backrd-a'), 1, 'the first Source was prepared once: waited for, not handed over again');
        }));
      } finally {
        w.backend.slowImports('backrd-a', 0);
        w.backend.slowImports('backrd-b', 0);
      }
    },
  },
];

/**
 * The go-back after the first-Source switch (#192) across a self-redirect, the first Source ready meanwhile: in a
 * suite of its own (parity-go-back-ready.mjs), since it takes about 60 s and each suite process has 120 s.
 */
export const goBackReadyScenarios = [
  {
    // The switch leaves the first Source preparing (ready at 30 s); the next one is still preparing when the first
    // request's time is up (55 s, a self-redirect resumes at it) and fails at 60 s (AltMount's prepare timeout, 35 s).
    // Every later Source has failed and the first is ready: the play goes back to it, across the self-redirect too.
    id: 'after-the-switch-and-a-self-redirect-a-failed-next-source-goes-back-to-the-first',
    async run(w) {
      const { id, sources } = offerMovie(w, [{ tag: 'backok-a' }, { tag: 'backok-b' }]);
      w.backend.slowImports('backok-a', 30000);
      w.backend.slowImports('backok-b', 200000);
      try {
        await withSettings(w, { whenToResolve: 'on-tile-selection' }, () => withPrepareTimeout(w, 35, async () => {
          const streams = await w.list('movie', id);
          const entry = streams.find(s => !isBest(s) && entryTitle(s) === sources[0].title);
          const asked = Date.now();
          const { result: r, lines } = await withLogs(() => play(entry.url, undefined, 100000));
          const took = Date.now() - asked;
          assert.ok(lines.some(l => l.includes('Self-redirect') && l.includes('resuming at candidate 2')),
            'the first request ran out of time while the next Source was preparing, and resumed at it');
          assert.equal(r.status, 200);
          assertBytes(r.body, sources[0].media, `the first Source plays, not the failure video (answered after ${took} ms); ${lines.filter(l => /User-pick attempt|Decoded rc=|Self-redirect|Every later Source|Stream failed|All \\d+ candidate/.test(l)).join(' | ')}`);
          assert.ok(took >= 59000, `it played once the next Source had failed (${took} ms)`);
          assert.equal(w.backend.submitsFor('backok-a'), 1, 'the first Source was prepared once: recalled, not handed over again');
        }));
      } finally {
        w.backend.slowImports('backok-a', 0);
        w.backend.slowImports('backok-b', 0);
      }
    },
  },
];

/** The tile envelope a play URL carries (its `t`). */
const envelopeOf = url => JSON.parse(Buffer.from(new URL(url).searchParams.get('t'), 'base64url').toString());

/** The play URL as the player sends it after `rc` self-redirects. */
function afterRedirects(url, rc) {
  const u = new URL(url);
  u.searchParams.set('t', Buffer.from(JSON.stringify({ ...envelopeOf(url), rc })).toString('base64url'));
  return u.href;
}

/** A self-redirect: back to the same play route, its redirect count now `rc`. */
function assertSelfRedirect(r, url, rc, what) {
  assert.equal(r.status, 302, `${what}: a redirect`);
  assert.equal(new URL(r.location).pathname, new URL(url).pathname, `${what}: back to the same play route (${r.location})`);
  assert.equal(envelopeOf(r.location).rc, rc, `${what}: redirect ${rc}`);
}

/** A request after a self-redirect answers within the ExoPlayer budget (8 s), not before it. */
function assertWithinExoPlayerBudget(r) {
  assert.ok(r.at >= 7000 && r.at < 10500, `it answered after ${r.at} ms, within the 8 s ExoPlayer budget`);
}

/** Run fn with AltMount's prepare timeout (seconds) set, then put the suite's back. */
async function withPrepareTimeout(w, sec, fn) {
  const saved = w.configData.altmountPrepareTimeout;
  w.configData.altmountPrepareTimeout = sec;
  try { return await fn(); } finally { w.configData.altmountPrepareTimeout = saved; }
}

/** One request of a play, its redirect not followed: { status, location, at } (at: ms it took). */
async function askOnce(url, timeoutMs = 30000) {
  const asked = Date.now();
  const res = await fetch(url, { redirect: 'manual', signal: AbortSignal.timeout(timeoutMs) });
  await res.arrayBuffer().catch(() => {});
  return { status: res.status, location: res.headers.get('location'), at: Date.now() - asked };
}

/**
 * A press of Best on a title whose top four Sources come from an indexer that refuses every grab (`refuser`, one of
 * the play-time world's), then a Healthy Source of the suite's indexer. Best walks one Source at a time by default.
 * With a larger candidateCount, already in-flight grabs still reach the refuser, so the bound is one request per slot.
 * The skip is logged once, Best plays Healthy, and no refused Source is dead.
 */
function assertRefusingIndexerSkipped(w, refuser, prefix, candidateCount = 1, { listEntry = false } = {}) {
  // A clicked list entry walks on alone: the Head start off, so no Best run meets the refusal first (#255).
  const settings = listEntry ? { candidateCount, whenToResolve: 'on-tile-selection' } : { candidateCount };
  return withSettings(w, settings, () => withIndexer(w, refuser.entry, async () => {
    const id = `tt${nextImdb++}`;
    const refused = [1, 2, 3, 4].map(i => ({ tag: `${prefix}-${i}`, title: `KaijuFlow.PlayTime.${prefix}-${i}.2026.2160p.WEB-DL.H265-GRP`, size: (30 - i) * GB }));
    for (const s of refused) s.link = refuser.nzbLink(s.tag);
    refuser.offer(id, refused);
    const ok = { tag: `${prefix}-other-ok`, title: `KaijuFlow.PlayTime.${prefix}-other-ok.2026.2160p.WEB-DL.H265-GRP`, media: mediaFor(`${prefix}-other-ok`), size: 10 * GB };
    ok.link = w.backend.addMovie(ok.tag, ok.title, ok.media);
    w.indexer.offer(id, [ok]);
    const before = refuser.grabbedTags.length;
    const { result: r, lines } = await withLogs(async () => {
      const streams = await w.list('movie', id);
      assert.equal(streams.slice(1).map(entryTitle).join(' | '), [...refused, ok].map(s => s.title).join(' | '), 'the refusing indexer\'s Sources are on top');
      return play(streams[listEntry ? 1 : 0].url);
    });
    const who = listEntry ? 'the clicked list entry' : 'Best';
    assert.equal(r.status, 200, `${who} plays`);
    assertBytes(r.body, ok.media, `${who} plays the Healthy Source of the other indexer`);
    assert.deepEqual(refuser.grabbedTags.slice(before), refused.slice(0, candidateCount).map(s => s.tag),
      `the refusing indexer is asked at most ${candidateCount} time${candidateCount === 1 ? '' : 's'}, once per in-flight slot`);
    const skip = new RegExp(`${refuser.entry.name}.*skipped for the rest of the Walk`);
    assert.equal(lines.filter(l => skip.test(l)).length, 1, 'the skip is logged once');
    const again = await w.list('movie', id);
    for (const s of refused) assert.ok(again.some(e => !isBest(e) && entryTitle(e) === s.title), `${s.tag} is not dead: the list still offers it`);
  }));
}

/**
 * How many times KaijuFlow writes its fallback groups file (config/fallback-groups.json) while fn runs: fs.writeFileSync
 * is counted for the time (synced into KaijuFlow's `import * as fs` with syncBuiltinESMExports), then put back.
 */
async function groupFileWrites(fn) {
  const real = fs.writeFileSync;
  let writes = 0;
  fs.writeFileSync = (file, ...rest) => {
    if (String(file).endsWith('/config/fallback-groups.json')) writes++;
    return real(file, ...rest);
  };
  syncBuiltinESMExports();
  try { await fn(); } finally { fs.writeFileSync = real; syncBuiltinESMExports(); }
  return writes;
}

/** Run fn with this indexer added to the suite's, then put the suite's back. */
async function withIndexer(w, entry, fn) {
  const saved = w.configData.indexers;
  w.configData.indexers = [...saved, entry];
  try { return await fn(); } finally { w.configData.indexers = saved; }
}

/**
 * A Scrambled RAR set of 12 parts for a new movie title, its first articles on the news server; to offer on top of
 * the list. `dropAt` names one part's first article (one the Play-time check doesn't read) for `news.drop`.
 */
function offerScrambled(w, tag) {
  const id = `tt${nextImdb++}`;
  const title = `KaijuFlow.PlayTime.${tag}.2026.2160p.WEB-DL.H265-GRP`;
  const media = mediaFor(tag);
  const set = scrambledRarSet({ base: `${tag}0a1b2c3d4e5f`, parts: 12, startAt: 10, tag });
  for (const [articleId, bytes] of set.articles) w.news.articles.set(articleId, bytes);
  const link = w.backend.addScrambled(tag, title, media, set);
  return { id, tag, dropAt: `${tag}-v7-s1@`, item: { tag, title, media, link, size: 20 * GB } };
}

/** A Healthy Source to offer below, `sizeGb` big. */
function healthyBelow(w, tag, sizeGb) {
  const title = `KaijuFlow.PlayTime.${tag}.2026.2160p.WEB-DL.H265-GRP`;
  const media = mediaFor(tag);
  return { tag, title, media, link: w.backend.addMovie(tag, title, media), size: sizeGb * GB };
}

/** The `unscramble` step lines' results for a Source, in order. */
function unscrambleResults(lines, title) {
  return stepsOf(lines)
    .filter(s => s.step === 'unscramble' && s.title === title).map(s => s.result);
}

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

/** Run these play-time scenarios (all of playTimeScenarios unless told). Returns per-scenario results. */
export async function runPlayTimeParity(w, scenarios = playTimeScenarios) {
  const results = [];
  for (const s of scenarios) {
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
