// AltMount Backend review fixes (#16): videoSize from the probe, prepare timeout vs attempt budget,
// queue status, failure classification, test-connection answers. Real Backend module; fake AltMount on loopback.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import http from 'node:http';
import { createFakeAltmount, API_KEY } from './parity/fake-altmount.mjs';
const root = process.env.A4_APP_ROOT, output = process.env.INTEGRATION_RESULTS;
assert.ok(root && output && fs.existsSync(root + '/../app-import.started'));
assert.match(root, /kaijuflow-a4-[^/]+\/positive\/work$/);
assert.deepEqual(Object.keys(os.networkInterfaces()), ['lo']);
const report = { id: 'INT-ALTMOUNT-REVIEW-001', backend: 'altmount', boundaries: ['Fake AltMount', 'Synthetic media bytes'] };
const servers = [];
const listen = async handler => { const s = http.createServer(handler); await new Promise(r => s.listen(0, '127.0.0.1', r)); servers.push(s); return 'http://127.0.0.1:' + s.address().port; };
const steps = [];
const step = async (name, fn) => { await fn(); steps.push(name); };
try {
  const fake = await createFakeAltmount(listen);
  const { configData } = await import(root + '/dist/config/index.js');
  fake.configure(configData);
  const { createAltmountBackend, buildAltmountSettings } = await import(root + '/dist/backends/altmount.js');
  const { isSourceFailure } = await import(root + '/dist/backends/types.js');
  const backend = createAltmountBackend(buildAltmountSettings());
  const src = nzbUrl => ({ nzbUrl, title: 'T', contentType: 'movie' });
  const failureOf = async nzbUrl => { try { await backend.prepare(src(nzbUrl)); } catch (e) { return e; } assert.fail('prepare should fail'); };

  await step('videoSize comes from the probe', async () => {
    const media = Buffer.alloc(4321, 7);
    const video = await backend.prepare(src(fake.addMovie('size', 'Size', media)));
    await backend.probe(video);
    assert.equal(video.videoSize, 4321);
  });

  await step('prepare timeout is the smaller of the setting and the remaining budget', async () => {
    let n = 0;
    const tag = () => 'to' + n++;
    const e1 = await (async () => { fake.submitFields.length = 0; try { await backend.prepare(src(fake.addNeverReady(tag(), 'N')), { timeoutMs: 2500 }); } catch (e) { return e; } })();
    assert.equal(fake.submitFields[0].timeout, '3');
    assert.ok(isSourceFailure(e1) && e1.isTimeout === true, 'a timeout still counts as failed');
    fake.submitFields.length = 0;
    await backend.prepare(src(fake.addNeverReady(tag(), 'N')), { timeoutMs: 600_000 }).catch(() => {});
    assert.equal(fake.submitFields[0].timeout, '20');
    fake.submitFields.length = 0;
    await backend.prepare(src(fake.addNeverReady(tag(), 'N'))).catch(() => {});
    assert.equal(fake.submitFields[0].timeout, '20');
  });

  await step('an answer that is not streamable is a Source failure', async () => {
    const e = await failureOf(fake.addNotReady('queued', 'Q', 'queued'));
    assert.ok(isSourceFailure(e));
  });
  await step('completed and streamable both count as ready', async () => {
    const nzb = fake.addMovie('two', 'Two', Buffer.from('abc'));
    await backend.prepare(src(nzb));
    const v = await backend.prepare(src(nzb)); // reuse: completed + _cached
    assert.ok(v.videoPath);
  });

  await step('only queue-failed 500s are Source failures; Backend-side 500/503 are not', async () => {
    let i = 0;
    for (const m of ['Failed to check queue status', 'Queue item not found', 'Failed to list output media files', 'Failed to fetch completed item',
      'Progress broadcaster closed unexpectedly', 'Failed to open uploaded file', 'Failed to read uploaded file',
      'Failed to process NZB']) {
      const e = await failureOf(fake.addScripted('b' + i++, 'B', 500, { error: m }));
      assert.ok(!isSourceFailure(e), m);
    }
    assert.ok(!isSourceFailure(await failureOf(fake.addScripted('b503', 'B', 503, { error: 'starting' }))));
    assert.ok(isSourceFailure(await failureOf(fake.addScripted('bf1', 'B', 500, { error: 'NZB processing failed' }))));
    assert.ok(isSourceFailure(await failureOf(fake.addScripted('bf2', 'B', 500, { error: 'missing articles' }))));
  });

  await step('test connection answers', async () => {
    const answer = async (status, body) => {
      const url = await listen((req, res) => { req.resume(); res.writeHead(status); res.end(body); });
      return createAltmountBackend({ url, apiKey: API_KEY }).status({});
    };
    const off = await answer(404, '{"error":"Stremio integration is disabled"}');
    assert.match(off.message, /integration is turned off/);
    const notReady = await answer(503, '{"error":"Stremio integration is disabled"}');
    assert.match(notReady.message, /not ready/);
    assert.doesNotMatch(notReady.message, /turned off/);
    const odd404 = await answer(404, 'page not found');
    assert.doesNotMatch(odd404.message, /turned off/);
    const key = await answer(401, '');
    assert.match(key.message, /API key/);
    const ok = await answer(400, '{"error":"No file provided"}');
    assert.equal(ok.ok, true);
    const down = await createAltmountBackend({ url: 'http://127.0.0.1:1', apiKey: API_KEY }).status({});
    assert.equal(down.ok, false); assert.match(down.message, /not reachable/);
  });
  Object.assign(report, { status: 'pass', steps });
} catch (e) { Object.assign(report, { status: 'fail', steps, error: String(e?.stack || e) }); }
fs.writeFileSync(output, JSON.stringify(report, null, 2));
console.log('INTEGRATION RESULT', JSON.stringify(report));
for (const s of servers) s.closeAllConnections();
process.exit(report.status === 'pass' ? 0 : 1);
