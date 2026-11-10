import test from 'node:test';
import assert from 'node:assert/strict';
import { altmountUploadName } from '../../src/backends/altmount.js';

test('AltMount upload name drops a trailing video extension', () => {
  assert.equal(altmountUploadName('Oppenheimer.2023.2160p-FLUX.mkv'), 'Oppenheimer.2023.2160p-FLUX');
  assert.equal(altmountUploadName('Movie.2020.1080p.MP4'), 'Movie.2020.1080p');
  for (const ext of ['.avi', '.m4v', '.ts', '.mov', '.wmv']) assert.equal(altmountUploadName(`Movie${ext}`), 'Movie');
});

test('AltMount upload name keeps names without a video extension', () => {
  assert.equal(altmountUploadName('Movie.2020.1080p.WEB-DL.H265-GRP'), 'Movie.2020.1080p.WEB-DL.H265-GRP');
  assert.equal(altmountUploadName('Show.S01E01.mkv.part'), 'Show.S01E01.mkv.part');
  assert.equal(altmountUploadName('.mkv'), '.mkv');
});
