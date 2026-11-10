// How the fake Backends fail the first-byte request (#86). Shared by both fakes.
export function fault(mode, res, req) {
  if (mode === 'drop') { req.destroy(); return; }
  res.writeHead(mode === 'not-found' ? 404 : 400, { 'Content-Type': 'text/plain' });
  res.end(mode === 'not-found' ? 'not found' : 'bad request');
}
