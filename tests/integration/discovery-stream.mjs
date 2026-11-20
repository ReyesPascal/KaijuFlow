// Exactly one post-A4 scenario. External services are fake; application modules are original.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import http from 'node:http';
import { assertBytes } from './parity/bytes.mjs';
import {createHash} from 'node:crypto';
const root=process.env.A4_APP_ROOT, output=process.env.INTEGRATION_RESULTS;
assert.ok(root && output && fs.existsSync(root+'/../app-import.started'));
assert.match(root,/kaijuflow-a4-[^/]+\/positive\/work$/);
assert.deepEqual(Object.keys(os.networkInterfaces()),['lo']);
const load=p=>import(root+'/dist/'+p+'.js');
const report={id:'INT-DISCOVERY-STREAM-001',source_commit:'c83a3c733b6394eb140a1c0a1dc500010a9f22e5',stages:[],boundaries:['Synthetic pre-existing verified verdict; no NNTP verification in this scenario','Fake NzbDAV completes immediately; no actual NZB retrieval/unpacking','WebDAV listing advertises 128 MiB to meet original 100 MiB selection threshold; delivered fixture is only 64 bytes','Original modules composed by harness; full server/search orchestrator and manifest authentication are outside this scenario','Synthetic bytes are not a decodable video; no playback or timing claim']};
const servers=[]; const requests=[];
const listen=async handler=>{const s=http.createServer(handler);await new Promise(r=>s.listen(0,'127.0.0.1',r));servers.push(s);return 'http://127.0.0.1:'+s.address().port;};
const media=Buffer.from('KaijuFlow synthetic media bytes: 0123456789ABCDEFGHIJKLMNOPQRSTU');
assert.equal(media.length,64);
const title='KaijuFlow.Fixture.2026.2160p.WEB-DL.H265';
const filePath='/content/Movies/'+title+'/fixture.mkv';
const advertisedSize=128*1024*1024;
let submitted=false, uploaded='';
try {
  const fake=await listen(async(req,res)=>{
    const u=new URL(req.url,'http://127.0.0.1');
    requests.push({method:req.method,path:u.pathname,mode:u.searchParams.get('mode'),range:req.headers.range||null});
    const json=x=>{res.setHeader('Content-Type','application/json');res.end(JSON.stringify(x));};
    if(u.pathname==='/search') {res.setHeader('Content-Type','application/xml');res.end(`<rss xmlns:newznab="http://www.newznab.com/DTD/2010/feeds/attributes/"><channel><newznab:response total="1" offset="0"/><item><title>${title}</title><link>${fake}/fixture.nzb</link><pubDate>Sat, 07 Nov 2026 00:00:00 GMT</pubDate><newznab:attr name="size" value="${advertisedSize}"/><newznab:attr name="category" value="2040"/></item></channel></rss>`);return;}
    if(u.pathname==='/fixture.nzb'){res.setHeader('Content-Type','application/x-nzb');res.end('<nzb><file subject="synthetic"><groups><group>alt.synthetic</group></groups><segments><segment bytes="64" number="1">fixture@invalid</segment></segments></file></nzb>');return;}
    if(u.pathname==='/api'){
      assert.equal(u.searchParams.get('apikey'),'synthetic-key');
      if(u.searchParams.get('mode')==='addfile') {assert.equal(req.method,'POST');for await(const chunk of req)uploaded+=chunk; assert.ok(uploaded.includes('<nzb>'));submitted=true;json({status:true,nzo_ids:['synthetic-job']});return;}
      if(u.searchParams.get('mode')==='queue'){json({queue:{slots:[]}});return;}
      if(u.searchParams.get('mode')==='history'){json({history:{slots:[{nzo_id:'synthetic-job',status:'Completed',name:title}]}});return;}
    }
    if(req.method==='PROPFIND'){
      assert.equal(req.headers.authorization,'Basic '+Buffer.from('fixture:fixture').toString('base64'));
      if(!submitted){res.writeHead(404);res.end();return;}
      res.writeHead(207,{'Content-Type':'application/xml'});
      const entry=(p,dir)=>`<d:response><d:href>${p}</d:href><d:propstat><d:prop><d:resourcetype>${dir?'<d:collection/>':''}</d:resourcetype><d:getcontentlength>${dir?0:advertisedSize}</d:getcontentlength><d:getcontenttype>${dir?'httpd/unix-directory':'video/x-matroska'}</d:getcontenttype></d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>`;
      res.end('<?xml version="1.0"?><d:multistatus xmlns:d="DAV:">'+entry('/content/Movies/'+title+'/',true)+entry(filePath,false)+'</d:multistatus>');return;
    }
    if(u.pathname===filePath && req.method==='GET'){
      assert.equal(req.headers.authorization,'Basic '+Buffer.from('fixture:fixture').toString('base64'));
      if(req.headers.range==='bytes=0-0'){res.writeHead(206,{'Content-Length':1,'Content-Range':'bytes 0-0/64','Content-Type':'video/x-matroska'});res.end(media.subarray(0,1));return;}
      assert.equal(req.headers.range,undefined);
      res.writeHead(200,{'Content-Type':'video/x-matroska','Content-Length':media.length,'Accept-Ranges':'bytes'});res.end(media);return;
    }
    res.writeHead(404);res.end();
  });
  const {config,configData}=await load('config/index');
  Object.assign(configData,{streamingMode:'nzbdav',indexManager:'manual',easynewsHealthCheck:false,nzbdavUrl:fake,nzbdavWebdavUrl:fake,nzbdavApiKey:'synthetic-key',nzbdavWebdavUser:'fixture',nzbdavWebdavPassword:'fixture',nzbdavMoviesCategory:'Movies',nzbdavStreamingMethod:'proxy',ultimateFallback:{...configData.ultimateFallback,enabled:false}});
  configData.healthChecks={...configData.healthChecks,enabled:true,inspectionMethod:'fixed',nzbsToInspect:1,hideBlocked:false,autoQueue:false,providers:[{host:'127.0.0.1',port:119,enabled:true,username:'fixture',password:'fixture',type:'pool'}]};
  const {parseNewznabXmlWithMeta}=await load('parsers/newznabClient');
  const parsed=await parseNewznabXmlWithMeta(await (await fetch(fake+'/search')).text());
  assert.equal(parsed.total,1);assert.equal(parsed.results[0].title,title);assert.equal(parsed.results[0].size,advertisedSize);
  report.stages.push('original Newznab XML parsing');
  const {deduplicateAndPreFilter,applyUserFilters}=await load('addon/resultProcessor');
  const pre=deduplicateAndPreFilter(parsed.results);
  const filtered=applyUserFilters(pre.results,'movie',Date.now(),undefined,pre.deprioritizedPacks,{quiet:true});
  assert.equal(filtered.length,1);report.stages.push('original result processing/filtering');
  const {coordinateHealthChecks}=await load('addon/healthCheckCoordinator');
  const health=await coordinateHealthChecks({allResults:filtered,type:'movie',preExistingHealth:new Map([[filtered[0].link,{status:'verified',message:'Synthetic pre-verified result',playable:true}]])});
  assert.equal(health.healthResults.get(filtered[0].link).status,'verified');
  report.stages.push('original Fixed coordinator consumes synthetic pre-verified verdict');
  const {default:express}=await import(root+'/node_modules/express/index.js');
  const {handleStream}=await load('nzbdav/streamHandler');
  const {createNzbdavStreamRoutes}=await load('routes/nzbdav');
  const app=express();
  app.use('/stremio/:manifestKey/nzbdav',createNzbdavStreamRoutes({config,handleStream,getLatestVersions:()=>({chrome:'synthetic'})}));
  const base=await listen(app);
  const {requestContext}=await load('requestContext');
  const {buildStreams}=await load('addon/streamBuilder');
  const built=requestContext.run({baseUrl:base,pathPrefix:'/stremio',manifestKey:'synthetic-manifest'},()=>buildStreams({allResults:health.filteredResults,healthResults:health.healthResults,type:'movie',now:Date.now()}));
  assert.equal(built.streams.length,1);
  const tile=built.streams[0];const url=new URL(tile.url);
  assert.equal(url.origin,base);assert.match(url.pathname,/\/stremio\/synthetic-manifest\/nzbdav\/stream\//);
  const envelope=JSON.parse(Buffer.from(url.searchParams.get('t'),'base64url'));
  assert.equal(envelope.url,fake+'/fixture.nzb');assert.equal(envelope.title,title);assert.equal(tile.behaviorHints.notWebReady,false);assert.ok(tile.name && tile.title);
  report.stages.push('original stream builder generates metadata and the Backend tile envelope');
  const response=await fetch(tile.url,{signal:AbortSignal.timeout(20000)});
  const delivered=Buffer.from(await response.arrayBuffer());
  assert.equal(response.status,200);assert.equal(response.headers.get('content-type'),'video/x-matroska');assert.equal(Number(response.headers.get('content-length')),64);assertBytes(delivered,media);
  assert.ok(submitted && uploaded.includes('fixture@invalid'));
  for(const mode of ['addfile','queue','history'])assert.ok(requests.some(r=>r.mode===mode));
  assert.ok(requests.some(r=>r.method==='PROPFIND'));assert.ok(requests.some(r=>r.range==='bytes=0-0'));
  const {getCacheEntries}=await load('nzbdav/streamCache');
  const cache=getCacheEntries();assert.ok(JSON.stringify(cache).includes(filePath));
  report.stages.push('original stream route → prepareStream → NZB download/upload → queue/history polling → WebDAV selection/probe → original proxy → exact synthetic bytes');
  Object.assign(report,{status:'pass',httpStatus:response.status,bytes:delivered.length,sha256:createHash('sha256').update(delivered).digest('hex'),advertisedSize,tileMetadata:{name:tile.name,title:tile.title,behaviorHints:tile.behaviorHints},requests});
} catch(e) {Object.assign(report,{status:'fail',error:String(e),stack:e.stack,requests});}
fs.writeFileSync(output,JSON.stringify(report,null,2));
console.log('INTEGRATION RESULT',JSON.stringify(report));
for(const s of servers)s.closeAllConnections();
await Promise.all(servers.map(s=>new Promise(r=>s.close(r))));
process.exit(report.status==='pass'?0:1);
