// #184, ADR 0009: KaijuFlow's health check passes only what AltMount streams:
// plain video, stored RAR5 (in volume order, hash-named, or Scrambled, which
// Unscramble puts in order) and stored 7z. It blocks the rest before sampling
// a segment. Goes through the batch call the health-check coordinator makes,
// on real archives (tests/fixtures/archives/make.sh).
// Run: npm run test:unit
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { performBatchHealthChecks } from '../../src/health/index.ts';
import { archiveFixture, nzbWithNews, type F } from './health-nzb.ts';

type Opts = { served?: boolean; password?: string; missing?: string[]; archiveInspection?: boolean };

/** Health-check one NZB the way the coordinator does (one batch). */
async function check(files: F[], { archiveInspection = true, ...opts }: Opts = {}) {
  const { url, provider, state } = await nzbWithNews([...files, ...side()], opts);
  const { results } = await performBatchHealthChecks([url], [provider], 'test-agent', 3, { archiveInspection, sampleCount: 3 });
  return { result: results.get(url)!, reads: state.reads, stats: state.stats };
}

const side = (): F[] => [{ name: 'Movie.nfo' }, { name: 'Movie.par2' }, { name: 'Movie.vol000+01.par2' }];
/** A fixture posted under `name`, cut into three articles. */
const fx = (fixture: string, name = fixture): F => ({ name, segs: 3, data: archiveFixture(fixture) });
const rar5Parts = [1, 2, 3, 4].map(i => `rar5-stored.part${i}.rar`);
const rar4Parts = ['rar4-stored.rar', 'rar4-stored.r00', 'rar4-stored.r01', 'rar4-stored.r02'];
/** Number-named parts in an order that is not the volume order (a Scrambled set). */
const scrambled = (parts: string[]): F[] => [2, 0, 3, 1].map((v, i) => fx(parts[v], `Movie.${10 + i}`));

const verified: Array<[string, F[]]> = [
  ['a stored RAR5 set in volume order', rar5Parts.map(p => fx(p))],
  ['a hash-named stored RAR5 set', rar5Parts.map((p, i) => fx(p, `a1b2c3d4e5f60718aa${i}`))],
  ['a Scrambled stored RAR5 set', scrambled(rar5Parts)],
  ['a stored 7z', [fx('stored.7z')]],
  ['a stored 7z with a packed header', [fx('stored-packed-header.7z')]],
  ['a stored 7z split in volumes', [1, 2, 3, 4].map(i => fx(`stored-split.7z.00${i}`))],
];

for (const [what, files] of verified) {
  test(`${what} is verified as a stored archive`, async () => {
    const { result, stats } = await check(files);
    assert.equal(result.status, 'verified_stored', result.message);
    assert.equal(result.playable, true);
    assert.equal(result.containerType, 'MKV');
    assert.ok(stats.length > 0, 'segments are sampled');
  });
}

test('a plain MKV is verified', async () => {
  const { result, stats } = await check([{ name: 'Movie.2160p.mkv', segs: 4, bytes: 700000 }]);
  assert.equal(result.status, 'verified');
  assert.equal(result.containerType, 'MKV');
  assert.equal(stats.length, 3, 'three segments are sampled');
});

const blocked: Array<[string, F[], string, Opts?]> = [
  ['a compressed 7z', [fx('compressed.7z')], 'Compressed archive'],
  ['a compressed RAR5', [fx('rar5-compressed.rar')], 'Compressed archive'],
  ['an encrypted 7z', [fx('encrypted.7z')], 'Encrypted archive (no password)'],
  ['an encrypted 7z with its password in the NZB', [fx('encrypted.7z')], 'Encrypted archive (password in NZB)', { password: 'secret' }],
  ['a 7z with encrypted names', [fx('encrypted-names.7z')], 'Encrypted archive (no password)'],
  ['an encrypted RAR5', [fx('rar5-encrypted.rar')], 'Encrypted archive (no password)'],
  ['an encrypted RAR5 with its password in the NZB', [fx('rar5-encrypted.rar')], 'Encrypted archive (password in NZB)', { password: 'secret' }],
  ['a RAR5 with encrypted names', [fx('rar5-encrypted-names.rar')], 'Encrypted archive (no password)'],
  ['a 7z holding an archive', [fx('nested.7z')], 'Nested archive'],
  ['a RAR5 holding an archive', [fx('rar5-nested.rar')], 'Nested archive'],
  ['a ZIP', [fx('stored.zip')], 'ZIP archive'],
  ['a Scrambled RAR4 set', scrambled(rar4Parts), 'RAR4 archive'],
  ['an old-style RAR4 set (.rar, .r00)', rar4Parts.map(p => fx(p)), 'RAR4 archive'],
  ['an archive whose first part is missing', rar5Parts.map(p => fx(p)), 'Archive header unreadable', { missing: [rar5Parts[0]] }],
  ['an archive with no header it can read', [{ name: 'Movie.part1.rar', segs: 3, data: Buffer.alloc(3000, 0x41) }], 'Archive header unreadable'],
  ['a compressed 7z with archive inspection off', [fx('compressed.7z')], 'Compressed archive', { archiveInspection: false }],
];

for (const [what, files, message, opts] of blocked) {
  test(`${what} is blocked before sampling: ${message}`, async () => {
    const { result, stats } = await check(files, opts);
    assert.equal(result.status, 'blocked');
    assert.equal(result.message, message);
    assert.equal(result.playable, false);
    assert.deepEqual(stats, [], 'no segment is sampled');
  });
}

const byName: Array<[string, F[], string]> = [
  ['files with no video or archive name', [{ name: 'Movie.2160p.bin', segs: 4, bytes: 700000 }], 'No video or archive file named'],
  ['a bare disc image', [{ name: 'Movie.iso', segs: 4, bytes: 700000 }], 'Disc image'],
];

for (const [what, files, message] of byName) {
  test(`${what} is blocked on the names alone: ${message}`, async () => {
    const { result, reads, stats } = await check(files);
    assert.equal(result.status, 'blocked');
    assert.equal(result.message, message);
    assert.deepEqual(reads, [], 'no article body is read');
    assert.deepEqual(stats, [], 'no segment is sampled');
  });
}

test('a stored RAR5 set with a later part missing is still blocked by sampling', async () => {
  const { result } = await check(rar5Parts.map(p => fx(p)), { missing: [rar5Parts[2]] });
  assert.equal(result.status, 'blocked');
  assert.match(result.message, /^Missing \d+ of \d+ segments/);
});
