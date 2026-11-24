// Exactly one post-A4 scenario. External services are fake; application modules are original.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import http from 'node:http';
import { assertBytes } from './parity/bytes.mjs';
import { createFakeAltmount } from './parity/fake-altmount.mjs';
import { useFakeNews } from './parity/fake-nntp.mjs';
import {createHash} from 'node:crypto';
const root=process.env.A4_APP_ROOT, output=process.env.INTEGRATION_RESULTS;
assert.ok(root && output && fs.existsSync(root+'/../app-import.started'));
assert.match(root,/kaijuflow-a4-[^/]+\/positive\/work$/);
assert.deepEqual(Object.keys(os.networkInterfaces()),['lo']);
const load=p=>import(root+'/dist/'+p+'.js');
const report={id:'INT-DISCOVERY-STREAM-001',source_commit:'c83a3c733b6394eb140a1c0a1dc500010a9f22e5',stages:[],boundaries:['Fake indexer (search + NZB link), fake news server (the play-time health check) and fake AltMount, which prepares at once','Original modules composed by harness; full server/search orchestrator and manifest authentication are outside this scenario','Synthetic bytes are not a decodable video; no playback or timing claim']};
const servers=[]; const requests=[];
const listen=async handler=>{const s=http.createServer(handler);await new Promise(r=>s.listen(0,'127.0.0.1',r));servers.push(s);return 'http://127.0.0.1:'+s.address().port;};
const media=Buffer.from('KaijuFlow synthetic media bytes: 0123456789ABCDEFGHIJKLMNOPQRSTU');
assert.equal(media.length,64);
const title='KaijuFlow.Fixture.2026.2160p.WEB-DL.H265';
const advertisedSize=128*1024*1024;
try {
  // The Backend: fake AltMount. The indexer's NZB link is the one the fake serves for this Source.
  const alt=await createFakeAltmount(listen);
  const {config,configData}=await load('config/index');
  alt.configure(configData);
  // The fake news server holds the Source's articles: it is checked when it is played (#191).
  alt.useNews(await useFakeNews(configData,config));
  const nzbLink=alt.addMovie('fixture',title,media);
  // The indexer: a Newznab search answer naming that link.
  const fake=await listen(async(req,res)=>{
    const u=new URL(req.url,'http://127.0.0.1');
    requests.push({method:req.method,path:u.pathname});
    if(u.pathname==='/search') {res.setHeader('Content-Type','application/xml');res.end(`<rss xmlns:newznab="http://www.newznab.com/DTD/2010/feeds/attributes/"><channel><newznab:response total="1" offset="0"/><item><title>${title}</title><link>${nzbLink}</link><pubDate>Sat, 07 Nov 2026 00:00:00 GMT</pubDate><newznab:attr name="size" value="${advertisedSize}"/><newznab:attr name="category" value="2040"/></item></channel></rss>`);return;}
    res.writeHead(404);res.end();
  });
  configData.easynewsHealthCheck=false;
  const {parseNewznabXmlWithMeta}=await load('parsers/newznabClient');
  const parsed=await parseNewznabXmlWithMeta(await (await fetch(fake+'/search')).text());
  assert.equal(parsed.total,1);assert.equal(parsed.results[0].title,title);assert.equal(parsed.results[0].size,advertisedSize);
  report.stages.push('original Newznab XML parsing');
  const {deduplicateAndPreFilter,applyUserFilters}=await load('addon/resultProcessor');
  const pre=deduplicateAndPreFilter(parsed.results);
  const filtered=applyUserFilters(pre.results,'movie',Date.now(),undefined,pre.deprioritizedPacks,{quiet:true});
  assert.equal(filtered.length,1);report.stages.push('original result processing/filtering');
  const {default:express}=await import(root+'/node_modules/express/index.js');
  const {handleStream}=await load('play/streamHandler');
  const {createPlayStreamRoutes}=await load('routes/play');
  const app=express();
  app.use('/stremio/:manifestKey/play',createPlayStreamRoutes({config,handleStream,getLatestVersions:()=>({chrome:'synthetic'})}));
  const base=await listen(app);
  const {requestContext}=await load('requestContext');
  const {buildStreams}=await load('addon/streamBuilder');
  const built=requestContext.run({baseUrl:base,pathPrefix:'/stremio',manifestKey:'synthetic-manifest'},()=>buildStreams({allResults:filtered,healthResults:new Map(),play:{sessionKey:'',type:'movie'},now:Date.now()}));
  assert.equal(built.streams.length,1);
  const tile=built.streams[0];const url=new URL(tile.url);
  assert.equal(url.origin,base);assert.match(url.pathname,/\/stremio\/synthetic-manifest\/play\/stream\//);
  const envelope=JSON.parse(Buffer.from(url.searchParams.get('t'),'base64url'));
  assert.equal(envelope.url,nzbLink);assert.equal(envelope.title,title);assert.equal(tile.behaviorHints.notWebReady,false);assert.ok(tile.name && tile.title);
  report.stages.push('original stream builder generates metadata and the Backend tile envelope');
  const response=await fetch(tile.url,{signal:AbortSignal.timeout(20000)});
  const delivered=Buffer.from(await response.arrayBuffer());
  assert.equal(response.status,200);assert.equal(response.headers.get('content-type'),'video/x-matroska');assert.equal(Number(response.headers.get('content-length')),64);assertBytes(delivered,media);
  assert.equal(alt.submitsFor('fixture'),1);
  assert.ok(alt.requests.some(r=>r.path==='/api/files/stream'&&r.range==='bytes=0-0'),'first-byte probe');
  const {getCacheEntries}=await load('play/streamCache');
  const cache=getCacheEntries();assert.ok(JSON.stringify(cache).includes(`/movies/${title}/fixture.mkv`));
  report.stages.push('original stream route → prepareStream → play-time health check → NZB grab → AltMount upload → first-byte probe → original proxy → exact synthetic bytes');
  Object.assign(report,{status:'pass',httpStatus:response.status,bytes:delivered.length,sha256:createHash('sha256').update(delivered).digest('hex'),advertisedSize,tileMetadata:{name:tile.name,title:tile.title,behaviorHints:tile.behaviorHints},requests:[...requests,...alt.requests]});
} catch(e) {Object.assign(report,{status:'fail',error:String(e),stack:e.stack,requests});}
fs.writeFileSync(output,JSON.stringify(report,null,2));
console.log('INTEGRATION RESULT',JSON.stringify(report));
for(const s of servers)s.closeAllConnections();
await Promise.all(servers.map(s=>new Promise(r=>s.close(r))));
process.exit(report.status==='pass'?0:1);
