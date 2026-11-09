// What the fake Backends need to know about an uploaded NZB (#44).
// rarVolumeCheck copies real AltMount v0.4.0's two RAR volume rules, checked on
// 1338 (2026-11-09): Interstellar NOSiViD named .10-.103 failed ("missing"
// .00-.09), queue item `renametest` (part01..part94 in name order) failed with
// "bad volume number", queue item `ordertest` (part01..part94 in real volume
// order) was streamable.

const unescape = s => s.replace(/&quot;/g, '"').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');

/** Which registered Source an NZB is: its kf-tag meta, else its first subject. */
export function nzbTag(nzbText) {
  return /<meta type="kf-tag">([^<]+)<\/meta>/.exec(nzbText)?.[1] ?? /subject="([^"]+)"/.exec(nzbText)?.[1];
}

function files(nzbText) {
  return [...nzbText.matchAll(/<file\b[^>]*\bsubject="([^"]*)"[^>]*>([\s\S]*?)<\/file>/g)].map(m => {
    const subject = unescape(m[1]);
    const name = /"([^"]+)"/.exec(subject)?.[1] ?? subject;
    const segs = [...m[2].matchAll(/<segment\b[^>]*\bnumber="(\d+)"[^>]*>([^<]+)<\/segment>/g)].map(s => ({ n: +s[1], id: s[2] }));
    segs.sort((a, b) => a.n - b.n);
    return { name, firstId: segs[0]?.id };
  });
}

/**
 * Why AltMount v0.4.0 would fail this NZB's RAR set, or null if it would take it.
 * volumeOf: first-article id -> real RAR volume (0-based) for synthetic parts.
 */
export function rarVolumeCheck(nzbText, volumeOf) {
  const groups = new Map(); // base -> [{ num, firstId }]
  for (const f of files(nzbText)) {
    const m = /^(.+?)(?:\.part(\d+)\.rar|\.(\d+))$/i.exec(f.name);
    if (!m) continue;
    const key = `${m[1]}|${m[2] ? 'part' : 'num'}`;
    groups.set(key, [...(groups.get(key) ?? []), { num: +(m[2] ?? m[3]), firstId: f.firstId }]);
  }
  for (const [key, parts] of groups) {
    if (parts.length < 2) continue;
    parts.sort((a, b) => a.num - b.num);
    // Rule 1: name numbers are taken as volume numbers; a hole or a late start = missing volumes.
    const start = key.endsWith('|part') ? 1 : parts[0].num <= 1 ? parts[0].num : 0;
    const holes = parts.some((p, i) => p.num !== start + i);
    if (holes) return `missing volumes in ${key.split('|')[0]}`;
    // Rule 2: parts are opened in name order; a part holding another volume = bad volume number.
    if (parts.some((p, i) => volumeOf.has(p.firstId) && volumeOf.get(p.firstId) !== i)) return 'bad volume number';
  }
  return null;
}
