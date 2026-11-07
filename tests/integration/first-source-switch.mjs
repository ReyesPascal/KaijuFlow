// KaijuFlow finding 5: first-source switch. Fake NzbDAV; application modules are real.
// Source 1 never finishes preparing; source 2 completes at once. Expect KaijuFlow to
// serve source 2 after the switch window, and NOT mark source 1 dead.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import http from 'node:http';
const root=process.env.A4_APP_ROOT, output=process.env.INTEGRATION_RESULTS;
assert.ok(root && output && fs.existsSync(root+'/../app-import.started'));
assert.match(root,/kaijuflow-a4-[^/]+\/positive\/work$/);
assert.deepEqual(Object.keys(os.networkInterfaces()),['lo']);
const SWITCH_MS=800;
process.env.NZBDAV_FIRST_SOURCE_SWITCH_MS=String(SWITCH_MS); // read when streamHandler loads
const load=p=>import(root+'/dist/'+p+'.js');
const report={id:'INT-FIRST-SOURCE-SWITCH-001',switchMs:SWITCH_MS,boundaries:['Fake NzbDAV; source 1 stays Downloading forever','Synthetic 64-byte media, not decodable video','Ultimate Fallback enabled with a 2-candidate fallback group']};
const servers=[]; const requests=[];
const listen=async handler=>{const s=http.createServer(handler);await new Promise(r=>s.listen(0,'127.0.0.1',r));servers.push(s);return 'http://127.0.0.1:'+s.address().port;};
const media=Buffer.from('KaijuFlow source-two bytes, served after the first-source switch!!');
const slowTitle='KaijuFlow.Slow.Source.2026.2160p.WEB-DL.H265';
const fastTitle='KaijuFlow.Fast.Source.2026.2160p.WEB-DL.H265';
const fastPath='/content/Movies/'+fastTitle+'/fast.mkv';
const advertisedSize=128*1024*1024;
const submitted=new Set();
try {
  const fake=await listen(async(req,res)=>{
    const u=new URL(req.url,'http://127.0.0.1');
    requests.push({method:req.method,path:u.pathname,mode:u.searchParams.get('mode')});
    const json=x=>{res.setHeader('Content-Type','application/json');res.end(JSON.stringify(x));};
    if(u.pathname==='/slow.nzb'||u.pathname==='/fast.nzb'){
      const tag=u.pathname.slice(1,5);
      res.setHeader('Content-Type','application/x-nzb');
      res.end(`<nzb><file subject="${tag}"><groups><group>alt.synthetic</group></groups><segments><segment bytes="64" number="1">${tag}@invalid</segment></segments></file></nzb>`);return;
    }
    if(u.pathname==='/api'){
      const mode=u.searchParams.get('mode');
      if(mode==='addfile'){let body='';for await(const c of req)body+=c;const job=body.includes('slow@invalid')?'slow-job':'fast-job';submitted.add(job);json({status:true,nzo_ids:[job]});return;}
      if(mode==='queue'){json({queue:{slots:submitted.has('slow-job')?[{nzo_id:'slow-job',status:'Downloading',filename:slowTitle,percentage:'5'}]:[]}});return;}
      if(mode==='history'){json({history:{slots:submitted.has('fast-job')?[{nzo_id:'fast-job',status:'Completed',name:fastTitle}]:[]}});return;}
      json({status:true});return;
    }
    if(req.method==='PROPFIND'){
      if(!submitted.has('fast-job')){res.writeHead(404);res.end();return;}
      res.writeHead(207,{'Content-Type':'application/xml'});
      const entry=(p,dir)=>`<d:response><d:href>${p}</d:href><d:propstat><d:prop><d:resourcetype>${dir?'<d:collection/>':''}</d:resourcetype><d:getcontentlength>${dir?0:advertisedSize}</d:getcontentlength><d:getcontenttype>${dir?'httpd/unix-directory':'video/x-matroska'}</d:getcontenttype></d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>`;
      res.end('<?xml version="1.0"?><d:multistatus xmlns:d="DAV:">'+entry('/content/Movies/'+fastTitle+'/',true)+entry(fastPath,false)+'</d:multistatus>');return;
    }
    if(u.pathname===fastPath && req.method==='GET'){
      if(req.headers.range==='bytes=0-0'){res.writeHead(206,{'Content-Length':1,'Content-Range':`bytes 0-0/${media.length}`,'Content-Type':'video/x-matroska'});res.end(media.subarray(0,1));return;}
      res.writeHead(200,{'Content-Type':'video/x-matroska','Content-Length':media.length,'Accept-Ranges':'bytes'});res.end(media);return;
    }
    res.writeHead(404);res.end();
  });
  const {config,configData}=await load('config/index');
  Object.assign(configData,{streamingMode:'nzbdav',indexManager:'manual',nzbdavUrl:fake,nzbdavWebdavUrl:fake,nzbdavApiKey:'synthetic-key',nzbdavWebdavUser:'',nzbdavWebdavPassword:'',nzbdavMoviesCategory:'Movies',nzbdavStreamingMethod:'proxy',
    ultimateFallback:{...configData.ultimateFallback,enabled:true,maxAttempts:0,userPickFallback:'fallback-chain'}});
  const slowUrl=fake+'/slow.nzb', fastUrl=fake+'/fast.nzb';
  const {createFallbackGroup}=await load('nzbdav/fallbackManager');
  createFallbackGroup('int-switch-group',[{nzbUrl:slowUrl,title:slowTitle,indexerName:'A'},{nzbUrl:fastUrl,title:fastTitle,indexerName:'B'}],'movie');
  const {default:express}=await import(root+'/node_modules/express/index.js');
  const {handleStream}=await load('nzbdav/streamHandler');
  const {createNzbdavStreamRoutes}=await load('routes/nzbdav');
  const app=express();
  app.use('/stremio/:manifestKey/nzbdav',createNzbdavStreamRoutes({config,handleStream,getLatestVersions:()=>({chrome:'synthetic'})}));
  const base=await listen(app);
  const t=Buffer.from(JSON.stringify({url:slowUrl,title:slowTitle,indexer:'A',fbg:'int-switch-group',ty:'movie'})).toString('base64url');
  const started=Date.now();
  const response=await fetch(`${base}/stremio/synthetic-manifest/nzbdav/stream/movie.mkv?t=${t}`,{signal:AbortSignal.timeout(15000)});
  const delivered=Buffer.from(await response.arrayBuffer());
  const elapsedMs=Date.now()-started;
  assert.equal(response.status,200,'expected source 2 to play');
  assert.deepEqual(delivered,media,'expected source 2 bytes');
  assert.ok(elapsedMs>=SWITCH_MS,`served before the switch window (${elapsedMs} ms)`);
  assert.ok(elapsedMs<SWITCH_MS+8000,`switch took too long (${elapsedMs} ms)`);
  assert.ok(submitted.has('slow-job'),'source 1 was never submitted');
  const {isDeadNzb,isDeadNzbByUrl,getDeadCacheKey}=await load('nzbdav/streamCache');
  assert.equal(isDeadNzb(getDeadCacheKey(slowUrl)),false,'source 1 was marked dead');
  assert.equal(isDeadNzbByUrl(slowUrl),false,'source 1 was marked dead by URL');
  Object.assign(report,{status:'pass',httpStatus:response.status,elapsedMs,bytes:delivered.length,slowSubmitted:true,slowMarkedDead:false});
} catch(e) {Object.assign(report,{status:'fail',error:String(e),requests:requests.slice(-20)});}
fs.writeFileSync(output,JSON.stringify(report,null,2));
console.log('INTEGRATION RESULT',JSON.stringify(report));
for(const s of servers)s.closeAllConnections();
process.exit(report.status==='pass'?0:1);
