// Serve a byte buffer the way a real media server does: 200 for a full GET,
// 206 + Content-Range for a satisfiable range, 416 for a range past the end.
export function serveBytes(req, res, media) {
  const range = req.headers.range;
  const base = { 'Content-Type': 'video/x-matroska', 'Accept-Ranges': 'bytes' };
  if (!range) {
    res.writeHead(200, { ...base, 'Content-Length': media.length });
    res.end(req.method === 'HEAD' ? undefined : media);
    return;
  }
  const m = /^bytes=(\d*)-(\d*)$/.exec(range);
  let start = m && m[1] !== '' ? Number(m[1]) : NaN;
  let end = m && m[2] !== '' ? Number(m[2]) : media.length - 1;
  if (m && m[1] === '' && m[2] !== '') { start = Math.max(0, media.length - Number(m[2])); end = media.length - 1; }
  if (!Number.isFinite(start) || start >= media.length || end < start) {
    res.writeHead(416, { ...base, 'Content-Range': `bytes */${media.length}` });
    res.end();
    return;
  }
  end = Math.min(end, media.length - 1);
  res.writeHead(206, { ...base, 'Content-Length': end - start + 1, 'Content-Range': `bytes ${start}-${end}/${media.length}` });
  res.end(req.method === 'HEAD' ? undefined : media.subarray(start, end + 1));
}
