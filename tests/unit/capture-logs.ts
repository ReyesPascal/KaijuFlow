// Test helper: everything written to the console while `fn` runs, one line per call.
export async function captureLogs(fn: () => Promise<unknown>): Promise<string> {
  const lines: string[] = [];
  const saved = { log: console.log, warn: console.warn, error: console.error };
  const record = (...args: unknown[]) => {
    lines.push(args.map(a => (typeof a === 'string' ? a : JSON.stringify(a))).join(' '));
  };
  console.log = console.warn = console.error = record;
  try {
    await fn();
  } finally {
    Object.assign(console, saved);
  }
  return lines.join('\n');
}
