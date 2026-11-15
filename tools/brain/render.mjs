// Render check: screenshot a page at given widths and flag layout faults, so a page is looked at before it is published.
//   cd ~/.local/share/kf-render && node <repo>/tools/brain/render.mjs <page.html | artboard.dc.html> <out-dir> [width ...]
// Default widths: 1280 390. Needs Playwright with Chromium; on Brain it is installed in ~/.local/share/kf-render
// (npm i playwright && npx playwright install chromium), so run it from that folder.
// Flags: TOO WIDE (wider than the screen), CUT OFF (content taller than a fixed box), SQUEEZED (text in a sliver).
// A Design-canvas artboard (.dc.html) is unwrapped from its <x-dc> block; any other file is loaded as it is.
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';

// Playwright is resolved from the folder the command is run in, not from the repo (the repo does not depend on it).
const { chromium } = createRequire(path.join(process.cwd(), 'x.js'))('playwright');

const [file, outDir, ...ws] = process.argv.slice(2);
if (!file || !outDir) { console.error('usage: node render.mjs <artboard.dc.html> <out-dir> [width ...]'); process.exit(2); }
const widths = ws.length ? ws.map(Number) : [1280, 390];
const src = fs.readFileSync(file, 'utf8');
const dc = src.match(/<x-dc>([\s\S]*?)<\/x-dc>/);
let html = src;
if (dc) {
  const helmet = (dc[1].match(/<helmet>([\s\S]*?)<\/helmet>/) || [, ''])[1];
  const body = dc[1].replace(/<helmet>[\s\S]*?<\/helmet>/, '');
  html = `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">${helmet}</head><body>${body}</body></html>`;
}
fs.mkdirSync(outDir, { recursive: true });
const name = path.basename(file).replace(/(\.dc)?\.html$/, '');
const browser = await chromium.launch();
for (const w of widths) {
  for (const scheme of ['light']) {
    const page = await browser.newPage({ viewport: { width: w, height: 900 }, colorScheme: scheme, deviceScaleFactor: 1 });
    await page.setContent(html, { waitUntil: 'networkidle' });
    await page.evaluate(() => document.fonts.ready);
    const info = await page.evaluate(() => {
      const vw = document.documentElement.clientWidth;
      const wide = [...document.querySelectorAll('body *')].filter((e) => {
        const r = e.getBoundingClientRect();
        if (r.right <= vw + 1 || r.width === 0) return false;
        for (let p = e.parentElement; p; p = p.parentElement) {
          const o = getComputedStyle(p).overflowX;
          if (o === 'auto' || o === 'scroll' || o === 'hidden') return false; // inside its own scroll box
        }
        return true;
      }).slice(0, 5).map((e) => `${e.tagName.toLowerCase()}.${e.className} right=${Math.round(e.getBoundingClientRect().right)}`);
      // Content cut off inside a fixed-size box (a one-page report whose content is taller than the sheet).
      const clipped = [...document.querySelectorAll('body *')].filter((e) => {
        const s = getComputedStyle(e);
        return (s.overflowY === 'hidden' || s.overflowY === 'clip') && e.scrollHeight > e.clientHeight + 1;
      }).slice(0, 3).map((e) => `${e.tagName.toLowerCase()}.${e.className} content ${e.scrollHeight}px in ${e.clientHeight}px`);
      // Text squeezed into a very narrow column (a collapsed grid): blocks under 60px wide holding 20+ characters.
      const squeezed = [...document.querySelectorAll('p,li,td,th,h1,h2,h3,dd,dt')].filter((e) => {
        const r = e.getBoundingClientRect();
        return r.width > 0 && r.width < 60 && (e.innerText || '').trim().length >= 20;
      }).slice(0, 3).map((e) => `${e.tagName.toLowerCase()} "${(e.innerText || '').trim().slice(0, 24)}" ${Math.round(e.getBoundingClientRect().width)}px wide`);
      return { height: document.documentElement.scrollHeight, scrollW: document.documentElement.scrollWidth, vw, wide, clipped, squeezed,
               fonts: [...document.fonts].filter((f) => f.status === 'loaded').map((f) => f.family).filter((v, i, a) => a.indexOf(v) === i) };
    });
    const out = path.join(outDir, `${name}-${w}.png`);
    await page.screenshot({ path: out, fullPage: true });
    console.log(`${name} @${w}: height ${info.height}px, page width ${info.scrollW}/${info.vw}${info.wide.length ? ', TOO WIDE: ' + info.wide.join('; ') : ''}${info.clipped.length ? ', CUT OFF: ' + info.clipped.join('; ') : ''}${info.squeezed.length ? ', SQUEEZED: ' + info.squeezed.join('; ') : ''}; fonts: ${info.fonts.join(', ') || 'none loaded'} -> ${out}`);
    await page.close();
  }
}
await browser.close();
