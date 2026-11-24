import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import https from 'node:https';
import { syncBuiltinESMExports } from 'node:module';
import { after, test } from 'node:test';
import { configData } from '../../src/config/index.ts';
import { clearProxyCache, probeSearchExitIp } from '../../src/proxy.ts';
import { grabSourceNzb } from '../../src/backends/sourceNzb.ts';

const savedProxyMode = configData.proxyMode;
const savedProxyUrl = configData.proxyUrl;
after(() => {
  configData.proxyMode = savedProxyMode;
  configData.proxyUrl = savedProxyUrl;
  clearProxyCache();
});

test('a stopped Walk releases its proxy verification wait', async () => {
  const originalRequest = https.request;
  const requests: Array<EventEmitter & { end(): void; destroy(): void; destroyed: boolean }> = [];
  let holdProbe = false;
  https.request = ((options: any, callback: (res: EventEmitter & { statusCode: number; headers: Record<string, string> }) => void) => {
    const req = Object.assign(new EventEmitter(), {
      destroyed: false,
      end() {
        if (options.hostname === 'api.ipify.org' && holdProbe) return;
        queueMicrotask(() => {
          const res = Object.assign(new EventEmitter(), { statusCode: 200, headers: {} });
          callback(res);
          res.emit('data', Buffer.from(JSON.stringify({ ip: '203.0.113.9' })));
          res.emit('end');
        });
      },
      destroy() { req.destroyed = true; queueMicrotask(() => req.emit('error', new Error('request destroyed'))); },
    });
    requests.push(req);
    return req as unknown as ReturnType<typeof https.request>;
  }) as typeof https.request;
  syncBuiltinESMExports();

  const controller = new AbortController();
  try {
    configData.proxyMode = 'http';
    configData.proxyUrl = 'http://127.0.0.1:8888';
    const url = 'https://proxy-stop.example/test.nzb';
    const searchExitIp = await probeSearchExitIp(url, 'test', 'Proxy stop');
    assert.ok(searchExitIp, 'the search received a proxy exit IP stamp');

    holdProbe = true;
    const pending = grabSourceNzb({ nzbUrl: url, title: 'T', indexerName: 'Proxy stop', searchExitIp }, { stop: controller.signal });
    await new Promise<void>(resolve => {
      const check = () => requests.length >= 2 ? resolve() : setTimeout(check, 5);
      check();
    });
    controller.abort();

    const outcome = await Promise.race([
      pending.then(() => 'resolved', () => 'rejected'),
      new Promise<'still-waiting'>(resolve => setTimeout(() => resolve('still-waiting'), 500)),
    ]);
    assert.equal(outcome, 'rejected', 'the grab stopped without waiting for the proxy probe timeout');
    assert.equal(requests[1].destroyed, true, 'the stopped Walk closed its live proxy verification request');
  } finally {
    controller.abort();
    for (const req of requests) req.destroy();
    https.request = originalRequest;
    syncBuiltinESMExports();
  }
});
