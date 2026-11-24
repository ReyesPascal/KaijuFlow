// Search Flow (#282, spec #279; GLOSSARY: Search Flow): the loose rule (the inherited isTextSearchMatch) decides what
// stays in a title's list, the strict rule (the quick check's right-title rule, ported) only sorts: a Source that
// passes strict is sure, one the loose rule keeps alone is maybe. Both copies of the strict rule (this one and
// tools/brain/quickcheck.py's) are tested on one shared table of real release names, tests/fixtures/release-names/.
// Run: npm run test:unit
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import { strictMatch, looseMatch, searchFlow, markSources, sureFirst, flowTitleOf, videoProof, type FlowTitle } from '../../src/parsers/searchFlow.ts';
import { UsenetSearcher } from '../../src/parsers/usenetSearcher.ts';
import { deduplicateAndPreFilter, applyUserFilters } from '../../src/addon/resultProcessor.ts';

interface Row { release: string; type: string; label: string; date: string; other: string; right: string; strict: string; loose: string }

/** The shared release-name table, one row per real release name and the title it was matched against. */
function table(): Row[] {
  const [head, ...lines] = fs.readFileSync(new URL('../fixtures/release-names/table.tsv', import.meta.url), 'utf8').trimEnd().split('\n');
  const cols = head.split('\t');
  return lines.map(line => Object.fromEntries(line.split('\t').map((v, i) => [cols[i], v])) as unknown as Row);
}

/** A row's title as KaijuFlow knows it: a film's name and year, an episode's show, season, episode and air date. */
function titleOf(row: Row): FlowTitle {
  const otherNames = row.other ? row.other.split('|') : [];
  if (row.type === 'movie') return { type: 'movie', name: row.label, otherNames, year: row.date.slice(0, 4) };
  const m = /^(.*) S(\d+)E(\d+)$/.exec(row.label);
  return m
    ? { type: 'series', name: m[1], otherNames, season: Number(m[2]), episode: Number(m[3]), aired: row.date }
    : { type: 'series', name: row.label, otherNames, aired: row.date };
}

test('the strict rule gives every row of the shared table the answer the quick check gives it', () => {
  const rows = table();
  assert.ok(rows.length >= 60, 'the table holds the real release names');
  for (const row of rows) {
    const { ok, why } = strictMatch(row.release, titleOf(row));
    assert.equal(ok ? 'pass' : why, row.strict, `${row.release} as ${row.label}`);
  }
});

test('the loose rule gives every row of the shared table its answer', () => {
  for (const row of table()) assert.equal(looseMatch(row.release, titleOf(row)) ? 'keep' : 'drop', row.loose, `${row.release} as ${row.label}`);
});

/** The first row of the table for this release and label. */
function row(release: string, label: string): Row {
  const found = table().find(r => r.release === release && r.label === label);
  assert.ok(found, `${release} as ${label} is in the table`);
  return found;
}

test('an obscure real release the strict rule fails stays as a maybe, with the strict rule\'s why', () => {
  const joker = row('Joker 1080p WEB-DL DD5.1 H264 (2019) NL Subs', 'Joker');
  assert.deepEqual(searchFlow(joker.release, titleOf(joker)), { flow: 'maybe', why: 'the name "Joker" is not followed by a year (2019 wanted)' });
  const matrix = row('The Matrix 1 (1999).English.1080p-NoGroup', 'The Matrix');
  assert.equal(searchFlow(matrix.release, titleOf(matrix)).flow, 'maybe');
});

test('a release the strict rule passes is sure, even one the loose rule would drop', () => {
  const reacher = row('REACHER.TV.S01E01.Welcome.to.Margrave.1080p.AMZN.WEB-DL.DDP5.1.H.265-NINJACENTRAL', 'Reacher S01E01');
  assert.equal(reacher.loose, 'drop');
  assert.deepEqual(searchFlow(reacher.release, titleOf(reacher)), { flow: 'sure', why: 'the name and episode fit' });
  const avatar = row('Avatar.2009.{edition-Extended}.1080p.BluRay.DDP.5.1.10bit.H.265-iVy.part01.rar', 'Avatar');
  assert.deepEqual(searchFlow(avatar.release, titleOf(avatar)), { flow: 'sure', why: 'the name and year fit' });
  const pack = row('a.b.mm efnet - req 96401 - Pushing.Daisies.S01.DVDRip - 037 315 - pd.103.dvdrip-rwd.r00', 'Pushing Daisies S01E03');
  assert.deepEqual(searchFlow(pack.release, titleOf(pack)), { flow: 'sure', why: 'the name and season fit (a season pack)' });
});

test('a release neither rule fits is dropped, with why', () => {
  const wick = row('John Wick Chapter 4 2023 1080p AMZN WEB-DL DDP5 1 H 265-ViSTA', 'John Wick');
  assert.deepEqual(searchFlow(wick.release, titleOf(wick)), { flow: 'dropped', why: 'the name "John Wick" is not followed by a year (2014 wanted)' });
});

test('over the whole table no release the strict rule passes is dropped, and every right release the loose rule keeps stays', () => {
  for (const r of table()) {
    const { flow } = searchFlow(r.release, titleOf(r));
    if (r.strict === 'pass') assert.equal(flow, 'sure', r.release);
    if (r.right === 'yes' && r.loose === 'keep') assert.notEqual(flow, 'dropped', r.release);
  }
});

// --------------------------------------------------------------------------- a title's list

/** A Newznab indexer answering a name search (q) and an ID search (imdbid) with its own release names. */
async function fakeIndexer(byName: string[], byId: string[]) {
  const xml = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;');
  const sizeOf = (t: string) => [...t].reduce((h, c) => (h * 31 + c.charCodeAt(0)) % 997, 7); // one size per release
  const item = (t: string) => `<item><title>${xml(t)}</title><link>http://idx.invalid/nzb/${encodeURIComponent(t)}</link>` +
    `<pubDate>Sat, 07 Nov 2026 00:00:00 GMT</pubDate><newznab:attr name="size" value="${4 * 1024 ** 3 + sizeOf(t) * 10 * 1024 ** 2}"/></item>`;
  const server = http.createServer((req, res) => {
    const u = new URL(req.url ?? '', 'http://x');
    const items = u.searchParams.get('imdbid') ? byId : u.searchParams.get('q') ? byName : [];
    res.writeHead(200, { 'Content-Type': 'application/xml' });
    res.end(`<?xml version="1.0"?><rss version="2.0" xmlns:newznab="http://www.newznab.com/DTD/2010/feeds/attributes/"><channel>` +
      `<newznab:response offset="0" total="${items.length}"/>${items.map(item).join('')}</channel></rss>`);
  });
  await new Promise<void>(r => server.listen(0, '127.0.0.1', () => r()));
  return { url: `http://127.0.0.1:${(server.address() as { port: number }).port}/api`, close: () => server.close() };
}

test('a list from an indexer asked by name and by ID keeps every loose match, marks each sure or maybe with why, and Best tries sure first', async () => {
  // Release names of Joker (2019) from the store's recordings, and two of other films an answer may hold.
  const geneMige = 'Joker 2019 1080p BluRay x264-GeneMige';
  const nlSubs = 'Joker 1080p WEB-DL DD5.1 H264 (2019) NL Subs'; // the obscure one: the year after the video tags
  const cobolJob = 'Inception.The.Cobol.Job.2010.1080p.BDRip.x264.AC3-ViSiON';
  const amzn = 'Joker (2019) 1080p AMZN.WEB-DL DDP5.1 H264 NL Sub';
  const tigole = 'Joker (2019) (1080p BluRay x265 10bit Tigole)';
  const realStory = 'Oppenheimer The Real Story-2023-1080p WEBRip-LAMA';
  const indexer = await fakeIndexer([nlSubs, geneMige, cobolJob], [tigole, amzn, geneMige, realStory]);
  try {
    const searcher = new UsenetSearcher({ name: 'FakeIdx', url: indexer.url, apiKey: 'k', enabled: true });
    const ctx = { type: 'movie', title: 'Joker', year: '2019' };
    const found = [
      ...await searcher.searchMovie('tt7286456', ctx.title, ctx.year, undefined, undefined, 'text'),
      ...await searcher.searchMovie('tt7286456', ctx.title, ctx.year, undefined, undefined, 'imdb'),
    ];
    // The list path's steps: dedup, Search Flow's marks, the user's filters and sort.
    const pre = deduplicateAndPreFilter(found);
    const list = applyUserFilters(markSources(pre.results, flowTitleOf(ctx)), 'movie', Date.now(), undefined, pre.deprioritizedPacks, { quiet: true });
    assert.deepEqual(new Map(list.map(s => [s.title, [s.flow, s.flowWhy]])), new Map([
      [nlSubs, ['maybe', 'the name "Joker" is not followed by a year (2019 wanted)']],
      [geneMige, ['sure', 'the name and year fit']],
      [tigole, ['sure', 'the name and year fit']], // found by ID
      [amzn, ['sure', 'the name and year fit']],
      [realStory, ['maybe', 'the name "Joker" is not in it; the loose rule does not fit it either']], // found by ID
    ]));
    assert.equal(list.length, 5, 'the Source found both ways is listed once; the other film of the name answer is dropped');
    const best = sureFirst(list).map(s => s.title);
    assert.deepEqual(best.slice(0, 3).sort(), [amzn, geneMige, tigole].sort());
    assert.deepEqual(best.slice(3), list.map(s => s.title).filter(t => t === nlSubs || t === realStory), 'then the maybes, in list order');
    assert.deepEqual(best.slice(0, 3), list.map(s => s.title).filter(t => best.slice(0, 3).includes(t)), 'the sure ones in list order');
  } finally {
    indexer.close();
  }
});

// --------------------------------------------------------------------------- extra proof (#286)

/** A row of the table as a Source of a title's list, with what Kaiju Search knows of it. */
function source(r: Row, more: Record<string, unknown> = {}) {
  return { title: r.release, indexerName: 'FakeIdx', size: 4 * 1024 ** 3, ...more };
}

test('a maybe the ID search returned too is sure; the same release found by name alone stays a maybe', () => {
  const joker = row('Joker 1080p WEB-DL DD5.1 H264 (2019) NL Subs', 'Joker');
  const [both] = markSources([source(joker, { foundBy: ['id', 'name'] })], titleOf(joker));
  assert.deepEqual([both.flow, both.proof, both.flowWhy],
    ['sure', 'id', 'the ID search returned it too; by its name alone: the name "Joker" is not followed by a year (2019 wanted)']);
  const [named] = markSources([source(joker, { foundBy: ['name'] })], titleOf(joker));
  assert.deepEqual([named.flow, named.proof], ['maybe', undefined]);
});

test('a maybe that fits another TMDB/TVDB name of the title is sure; without that name it stays a maybe', () => {
  const blowOut = row('Blow.Out.Der.Tod.loescht.alle.Spuren.1981.German.EAC3.DL.1080p.BluRay.x265-VECTOR', 'Blow Out');
  // TMDB's German title of Blow Out (1981).
  const [named] = markSources([source(blowOut)], { ...titleOf(blowOut), knownNames: ['Blow Out - Der Tod löscht alle Spuren'] });
  assert.deepEqual([named.flow, named.proof, named.flowWhy], ['sure', 'other name',
    'it fits another name of the title, "Blow Out - Der Tod löscht alle Spuren"; by its name alone: the name "Blow Out" is not followed by a year (1981 wanted); the loose rule does not fit it either']);
  const [unnamed] = markSources([source(blowOut)], titleOf(blowOut));
  assert.deepEqual([unnamed.flow, unnamed.proof], ['maybe', undefined]);
});

test('a maybe whose own runtime fits the title\'s is sure; one whose runtime is another film\'s, or that has none, stays a maybe', () => {
  const joker = row('Joker 1080p WEB-DL DD5.1 H264 (2019) NL Subs', 'Joker');
  const title = { ...titleOf(joker), runtime: 122 * 60 }; // TMDB: 122 min
  const [fits] = markSources([source(joker, { duration: 7314 })], title); // 2:01:54, as EasyNews gives a runtime
  assert.deepEqual([fits.flow, fits.proof, fits.flowWhy], ['sure', 'runtime',
    'its runtime fits (122 min, the title\'s 122 min); by its name alone: the name "Joker" is not followed by a year (2019 wanted)']);
  const [other] = markSources([source(joker, { duration: 100 * 60 })], title);
  const [none] = markSources([source(joker)], title);
  assert.deepEqual([other.flow, none.flow], ['maybe', 'maybe']);
});

test('a maybe the size of a sure Source in the list (the same upload under another name) is sure; another size stays a maybe', () => {
  const joker = row('Joker 1080p WEB-DL DD5.1 H264 (2019) NL Subs', 'Joker');
  // A real release name of the store's recordings, as another indexer lists it.
  const sure = { title: 'Joker 2019 1080p BluRay x264-GeneMige', indexerName: 'Other', size: 2_147_483_648 };
  const [, same] = markSources([sure, source(joker, { size: 2_147_483_648 })], titleOf(joker));
  assert.deepEqual([same.flow, same.proof, same.flowWhy], ['sure', 'size',
    'it is the size of a sure Source, Joker 2019 1080p BluRay x264-GeneMige; by its name alone: the name "Joker" is not followed by a year (2019 wanted)']);
  const [, other] = markSources([sure, source(joker, { size: 2_400_000_000 })], titleOf(joker));
  assert.equal(other.flow, 'maybe');
});

test('extra proof never makes sure a release whose name says another year, season or episode', () => {
  const ep9 = row('Pushing.Daisies.S01E09.Corpsicle.EAC3.5.1.1080p.Bluray.x265-iVy.part01.rar', 'Pushing Daisies S01E08');
  const [m] = markSources([source(ep9, { foundBy: ['id', 'name'] })], titleOf(ep9));
  assert.deepEqual([m.flow, m.flowWhy], ['maybe', 'it is S01E09, not S01E08']);
});

test('a maybe whose NZB holds a video file that fits the title is sure; a file that does not fit leaves it a maybe', () => {
  const joker = row('Joker 1080p WEB-DL DD5.1 H264 (2019) NL Subs', 'Joker');
  const [maybe] = markSources([source(joker)], titleOf(joker));
  const fits = videoProof(maybe, 'Joker.2019.1080p.WEB-DL.DD5.1.H264.mkv', titleOf(joker));
  assert.deepEqual(fits && [fits.flow, fits.proof, fits.flowWhy], ['sure', 'nzb video',
    'the video file inside its NZB fits, Joker.2019.1080p.WEB-DL.DD5.1.H264.mkv; by its name alone: the name "Joker" is not followed by a year (2019 wanted)']);
  assert.equal(videoProof(maybe, 'Joker.Folie.a.Deux.2024.1080p.mkv', titleOf(joker)), undefined);
  assert.equal(videoProof(maybe, undefined, titleOf(joker)), undefined, 'no video file named (an archive)');
  const sure = markSources([{ title: 'Joker 2019 1080p BluRay x264-GeneMige' }], titleOf(joker))[0];
  assert.equal(videoProof(sure, 'Joker.2019.1080p.WEB-DL.DD5.1.H264.mkv', titleOf(joker)), undefined, 'a sure Source needs no proof');
});
