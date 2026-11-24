// Fake news server + synthetic Scrambled RAR sets (#44). Loopback only.
// Serves made-up RAR5 first articles (yEnc) for BODY, counts reads and open
// connections. Shared by the Parity suite and the Unscramble unit tests.
import net from 'node:net';

const RAR5_SIGNATURE = Buffer.from([0x52, 0x61, 0x72, 0x21, 0x1a, 0x07, 0x01, 0x00]);

function vint(n) {
  const out = [];
  do { let b = n & 0x7f; n = Math.floor(n / 128); if (n > 0) b |= 0x80; out.push(b); } while (n > 0);
  return out;
}

/**
 * First bytes of RAR5 volume `volume` (0-based): signature, main archive
 * header (volume flag; volume number field when volume > 0), then filler that
 * stands in for the file header and packed data.
 */
export function rar5FirstArticle(volume, fillerBytes = 300) {
  const archiveFlags = 0x01 | (volume > 0 ? 0x02 : 0);
  const body = [...vint(1), ...vint(0), ...vint(archiveFlags), ...(volume > 0 ? vint(volume) : [])];
  const header = Buffer.from([0, 0, 0, 0, ...vint(body.length), ...body]); // CRC32 not checked
  const filler = Buffer.alloc(fillerBytes);
  for (let i = 0; i < fillerBytes; i++) filler[i] = (volume * 31 + i * 7) & 0xff; // includes NUL, CR, LF, '='
  return Buffer.concat([RAR5_SIGNATURE, header, filler]);
}

/**
 * First bytes of RAR5 volume `volume` as a real Scrambled set has them: the
 * main archive header, then a stored file header for `name` (the video each
 * volume holds a piece of), then filler for its packed data. The health check
 * reads the file header; Unscramble reads only the volume number.
 */
export function rar5VideoFirstArticle(volume, name = 'synthetic.mkv') {
  const plain = rar5FirstArticle(volume);
  const nameBytes = [...Buffer.from(name, 'utf8')];
  // Type 2 (file), header flags 0x02 (data area follows), data size, file flags 0,
  // unpacked size, attributes 0, compression info 0 (stored), host OS 0, name.
  const body = [...vint(2), ...vint(0x02), ...vint(750000), ...vint(0), ...vint(9000000), ...vint(0), ...vint(0), ...vint(0), ...vint(nameBytes.length), ...nameBytes];
  const fileHeader = Buffer.from([0, 0, 0, 0, ...vint(body.length), ...body]); // CRC32 not checked
  const mainEnd = plain.length - 300; // signature + main header; the rest is filler
  return Buffer.concat([plain.subarray(0, mainEnd), fileHeader, plain.subarray(mainEnd)]);
}

/** A RAR4 first article (old signature), for the "not RAR5" case. */
export function rar4FirstArticle() {
  return Buffer.concat([Buffer.from([0x52, 0x61, 0x72, 0x21, 0x1a, 0x07, 0x00]), Buffer.alloc(100, 0x41)]);
}

/** yEnc-encode bytes into NNTP body lines (dot-stuffed). */
function yencLines(data, name) {
  const lines = [`=ybegin part=1 line=128 size=${data.length} name=${name}`, `=ypart begin=1 end=${data.length}`];
  let line = '';
  for (const byte of data) {
    const c = (byte + 42) & 0xff;
    if (c === 0x00 || c === 0x0a || c === 0x0d || c === 0x3d) line += '=' + String.fromCharCode((c + 64) & 0xff);
    else line += String.fromCharCode(c);
    if (line.length >= 128) { lines.push(line); line = ''; }
  }
  if (line) lines.push(line);
  lines.push(`=yend size=${data.length} part=1`);
  return lines.map(l => (l.startsWith('.') ? '.' + l : l));
}

/** Deterministic shuffle (fixed seed), so a failing run is repeatable. */
export function shuffled(list, seed = 7) {
  const a = [...list];
  let s = seed;
  for (let i = a.length - 1; i > 0; i--) {
    s = (s * 1103515245 + 12345) % 2147483648;
    const j = s % (i + 1);
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

const xmlEscape = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

/**
 * A Scrambled RAR set: `parts` RAR5 volumes named `<base>.<n>` with n from
 * `startAt`, volumes shuffled across the names. Every part has 3 segments
 * listed out of order (first article = segment number 1). Also an .nfo and a
 * .par2 that must stay untouched. `tag` goes in a kf-tag meta so the fake
 * Backends know the Source; `head` = extra <meta> elements. Each first article
 * holds a stored video's file header, as a real set's do, so the Play-time
 * check passes the set (a clicked Source is always checked, #191).
 * Returns { nzb, articles: Map<messageId, Buffer>, parts: [{ name, volume, firstId }] }.
 */
export function scrambledRarSet({ base, parts, startAt = 10, width = 2, seed = 7, tag = base, head = '', firstArticle = rar5VideoFirstArticle }) {
  const volumes = shuffled([...Array(parts).keys()], seed);
  const articles = new Map();
  const list = volumes.map((volume, i) => {
    const name = `${base}.${String(startAt + i).padStart(width, '0')}`;
    const firstId = `${tag}-v${volume}-s1@fake`;
    articles.set(firstId, firstArticle(volume));
    return { name, volume, firstId };
  });
  const file = (name, ids) => `<file poster="kf@fake" date="1700000000" subject="${xmlEscape(`[1/${parts + 2}] - "${name}" yEnc (1/${ids.length})`)}">` +
    `<groups><group>alt.binaries.synthetic</group></groups><segments>` +
    ids.map(([n, id]) => `<segment bytes="750000" number="${n}">${id}</segment>`).join('') + `</segments></file>`;
  const files = [
    file(`${base}.nfo`, [[1, `${tag}-nfo@fake`]]),
    ...list.map(p => file(p.name, [[3, `${tag}-v${p.volume}-s3@fake`], [1, p.firstId], [2, `${tag}-v${p.volume}-s2@fake`]])),
    file(`${base}.par2`, [[1, `${tag}-par2@fake`]]),
  ];
  const nzb = `<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE nzb PUBLIC "-//newzBin//DTD NZB 1.1//EN" "http://www.newzbin.com/DTD/nzb/nzb-1.1.dtd">\n` +
    `<nzb xmlns="http://www.newzbin.com/DTD/2003/nzb"><head><meta type="name">${xmlEscape(base)}</meta><meta type="kf-tag">${xmlEscape(tag)}</meta>${head}</head>\n${files.join('\n')}\n</nzb>\n`;
  return { nzb, articles, parts: list };
}

/**
 * Start a fake news server and make it KaijuFlow's only health-check provider
 * (Parity harnesses). `config` is KaijuFlow's config accessor (for defaults).
 */
export async function useFakeNews(configData, config) {
  const news = await startFakeNntp();
  configData.healthChecks = { ...config.healthChecks, providers: [news.provider()] };
  return news;
}

/**
 * Start a fake news server. `articles`: Map<messageId, Buffer> (a missing id
 * answers 430). `delayMs` slows every BODY reply; `slow(prefix, ms)` slows every
 * reply for ids starting with prefix. Records `reads` (message ids whose bodies
 * were asked for), `stats` (ids asked for with STAT), `asks` ({ id, asked,
 * answered, closed } times in ms, per BODY or STAT; `closed`: when the asking
 * connection closed before the answer went out), `drops` ({ id, at } of BODY
 * asks answered by closing the connection, see `drop`), `connections`
 * ({ opened, closed, held, asked } per connection: `held`, its greeting held
 * back, see `hold`; `asked`, how many BODY or STAT asks it sent) and the
 * `peak` number of open connections.
 */
export async function startFakeNntp({ articles = new Map(), delayMs = 0 } = {}) {
  const state = { reads: [], stats: [], asks: [], drops: [], connections: [], open: 0, peak: 0 };
  const slowed = new Map(); // id prefix -> ms
  const dropped = new Map(); // id prefix -> BODY asks left to drop
  let toHold = 0; // connections left whose greeting is held back
  const sockets = new Set();
  const server = net.createServer(sock => {
    state.open++; state.peak = Math.max(state.peak, state.open);
    sockets.add(sock);
    const conn = { opened: Date.now(), closed: undefined, held: toHold > 0, asked: 0 };
    state.connections.push(conn);
    let counted = true;
    const mine = []; // this connection's asks
    const gone = () => {
      if (counted) { counted = false; state.open--; conn.closed = Date.now(); }
      sockets.delete(sock);
      for (const a of mine) if (a.answered === null && a.closed === undefined) a.closed = Date.now();
    };
    sock.on('end', gone); sock.on('close', gone); sock.on('error', () => {});
    // A news server stalled under load: the connection is open, its greeting never comes.
    if (conn.held) { toHold--; return; }
    sock.write('200 fake news ready\r\n');
    let buf = '';
    sock.on('data', d => {
      buf += d.toString('latin1');
      const lines = buf.split('\r\n');
      buf = lines.pop() || '';
      for (const line of lines) {
        if (line.startsWith('QUIT')) { gone(); sock.end('205 bye\r\n'); }
        else if (line.startsWith('AUTHINFO USER')) sock.write('381 more\r\n');
        else if (line.startsWith('AUTHINFO PASS')) sock.write('281 ok\r\n');
        else if (line.startsWith('BODY') || line.startsWith('STAT')) {
          const id = line.slice(line.indexOf('<') + 1, line.lastIndexOf('>'));
          const isBody = line.startsWith('BODY');
          // A dropped connection, as a news server under load closes one mid-read.
          const drop = isBody ? [...dropped.keys()].find(prefix => id.startsWith(prefix)) : undefined;
          if (drop !== undefined) {
            const left = dropped.get(drop) - 1;
            if (left > 0) dropped.set(drop, left); else dropped.delete(drop);
            state.drops.push({ id, at: Date.now() });
            sock.destroy();
            return;
          }
          conn.asked++;
          if (isBody) state.reads.push(id); else state.stats.push(id);
          const ask = { id, asked: Date.now(), answered: null };
          state.asks.push(ask);
          mine.push(ask);
          const reply = () => {
            ask.answered = Date.now();
            if (sock.destroyed) return;
            const data = articles.get(id);
            if (!data) { sock.write('430 no such article\r\n'); return; }
            if (!isBody) { sock.write(`223 0 <${id}>\r\n`); return; }
            sock.write(Buffer.from(`222 0 <${id}>\r\n` + yencLines(data, id).join('\r\n') + '\r\n.\r\n', 'latin1'));
          };
          const wait = Math.max(isBody ? delayMs : 0, ...[...slowed].filter(([prefix]) => id.startsWith(prefix)).map(([, ms]) => ms));
          if (wait > 0) setTimeout(reply, wait); else reply();
        } else sock.write('500 what\r\n');
      }
    });
  });
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  const { port } = server.address();
  return {
    host: '127.0.0.1',
    port,
    state,
    /** Served articles; scenarios add their sets here. */
    articles,
    /** Answer every BODY and STAT for ids starting with `prefix` after `ms` (0 = no extra wait). */
    slow(prefix, ms) { if (ms > 0) slowed.set(prefix, ms); else slowed.delete(prefix); },
    /** Hold back the greeting of the next `times` connections (0 = hold none): each stays open and silent until KaijuFlow closes it. */
    hold(times) { toHold = times; },
    /** Close the connection, unanswered, on the next `times` BODY asks for ids starting with `prefix` (0 = stop dropping). */
    drop(prefix, times = Infinity) { if (times > 0) dropped.set(prefix, times); else dropped.delete(prefix); },
    /**
     * A KaijuFlow health-check provider pointing at this server.
     * @param {string} [name]
     * @returns {import('../../../src/types.js').UsenetProvider}
     */
    provider(name = 'Fake News') {
      return { id: `fake-${port}`, name, host: '127.0.0.1', port, useTLS: false, username: 'kf', password: 'kf', enabled: true, type: 'pool' };
    },
    async close() {
      for (const s of sockets) s.destroy();
      await new Promise(r => server.close(() => r()));
    },
  };
}
