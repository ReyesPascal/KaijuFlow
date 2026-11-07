// A4 synthetic-only runtime tests. This script MUST ONLY run after the verified
// A4 network namespace gate and with A4_APP_ROOT pointing to copied dist files.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import path from 'node:path';
import fs from 'node:fs';
import os from 'node:os';
import http from 'node:http';

const ROOT = process.env.A4_APP_ROOT;
if (!ROOT || !process.env.A4_RESULTS || !fs.existsSync(path.join(path.dirname(ROOT), 'app-import.started'))) {
  throw new Error('FAIL CLOSED: A4 gate sentinel or disposable root missing');
}
assert.deepEqual(Object.keys(os.networkInterfaces()), ['lo']);
assert.match(ROOT, /kaijuflow-a4-[^/]+\/positive\/work$/);
const require = createRequire(path.join(ROOT, 'package.json'));
const express = require('express');
const cors = require('cors');
const sdk = require('stremio-addon-sdk');
const src = name => import(pathToFileURL(path.join(ROOT, 'dist', name)).href);
const report = { schema_version: 1, gate: 'A4-ISO-000 PASS', source_commit: 'c83a3c733b6394eb140a1c0a1dc500010a9f22e5', environment: 'disposable netns/no non-loopback interface/no credentials', cases: [] };
let failures = 0;
const record = (id, status, measurements, notes) => {
  report.cases.push({ id, status, measurements, notes });
  if (status !== 'pass') failures++;
  console.log('A4 CASE', id, status, JSON.stringify(measurements));
};
async function serve(app) {
  const server = http.createServer(app);
  await new Promise((resolve, reject) => { server.once('error',reject); server.listen(0, '127.0.0.1',resolve); });
  return { port: server.address().port, close: () => new Promise(resolve => { server.closeAllConnections(); server.close(resolve); }) };
}
async function request(port, url, opts = {}) {
  const r = await fetch('http://127.0.0.1:'+port+url, { ...opts, signal: AbortSignal.timeout(7000) });
  const text = await r.text();
  let json; try { json = JSON.parse(text); } catch {}
  return { status:r.status, headers:r.headers, json, textLength:text.length };
}
const jsonReq = (method, value, token) => ({
  method,
  headers:{'Content-Type':'application/json', ...(token?{Authorization:'Bearer '+token}:{})},
  body:JSON.stringify(value)
});
const auth = await src('auth/auth.js');
const authMw = await src('auth/authMiddleware.js');
const { createAuthRoutes } = await src('routes/auth.js');
const { config, updateSettings } = await src('config/index.js');
const { configData, CONFIG_FILE } = await src('config/schema.js');
let jwt, manifestKey;

try {
  const app = express();
  app.use(express.json({ limit:'5mb' }), cors());
  app.use('/api', createAuthRoutes({
    config, hasAnyUsers: auth.hasAnyUsers, createUser:auth.createUser,
    authenticateUser:auth.authenticateUser, generateToken:auth.generateToken,
    verifyToken:auth.verifyToken, getUserById:auth.getUserById,
    getLatestVersions: () => ({ chrome:'synthetic' })
  }));
  app.use('/api', authMw.requireAuth);
  app.get('/api/private-fixture', (req,res) => res.json({ username:req.user.username }));
  const s=await serve(app);
  try {
    const status=await request(s.port,'/api/auth/status');
    assert.equal(status.json?.status,'setup_required');
    assert.equal((await request(s.port,'/api/private-fixture')).status,401);
    assert.equal((await request(s.port,'/api/private-fixture',{headers:{Authorization:'Bearer junk'}})).status,401);
    assert.equal((await request(s.port,'/api/auth/setup',jsonReq('POST',{username:'synthetic-user',password:'abcd1234'}))).status,200);
    assert.equal((await request(s.port,'/api/auth/setup',jsonReq('POST',{username:'again',password:'abcd1234'}))).status,403);
    assert.equal((await request(s.port,'/api/auth/login',jsonReq('POST',{username:'synthetic-user',password:'wrong'}))).status,401);
    const login=await request(s.port,'/api/auth/login',jsonReq('POST',{username:'synthetic-user',password:'abcd1234'}));
    assert.equal(login.status,200);
    jwt=login.json.token;
    assert.equal(typeof jwt,'string');
    assert.equal((await request(s.port,'/api/private-fixture',{headers:{Authorization:'Bearer '+jwt}})).status,200);
    assert.equal((await request(s.port,'/api/private-fixture?token='+encodeURIComponent(jwt))).status,200);
    assert.equal((await request(s.port,'/api/auth/status',{headers:{Authorization:'Bearer '+jwt}})).json?.status,'authenticated');
    const user=auth.getUserById(auth.verifyToken(jwt).userId);
    manifestKey=user.manifests[0].id;
    assert.equal(typeof manifestKey,'string');
    record('A4-HTTP-001','pass',{setup:200,missingJWT:401,invalidJWT:401,duplicateSetup:403,wrongPassword:401,bearer:200,queryToken:200},'Actual original auth router, JWT implementation and middleware; all credentials synthetic');
  } finally { await s.close(); }
} catch (e) { record('A4-HTTP-001','fail',{error:String(e)},'Original auth path did not meet synthetic assertions'); }

try {
  assert.ok(manifestKey,'auth fixture required');
  const { addonBuilder, getRouter } = sdk;
  const builder=new addonBuilder({
    id:'org.kaijuflow.a4.fixture', version:'0.0.1', name:'A4 Synthetic',
    description:'Disposable Stremio fixture', resources:['stream'], types:['movie'],
    catalogs:[], idPrefixes:['tt']
  });
  builder.defineStreamHandler(async () => ({ streams:[] }));
  const addon=builder.getInterface();
  const router=express.Router({mergeParams:false});
  router.get('/manifest.json',(_req,res)=>res.json({...addon.manifest, a4CustomManifest:true}));
  router.use(getRouter(addon));
  const app=express();
  app.use(cors());
  app.use('/stremio/:manifestKey',authMw.validateManifestKey,router);
  app.use('/:manifestKey',authMw.validateManifestKey,router);
  const s=await serve(app);
  try {
    const values={};
    for(const prefix of ['/stremio/'+manifestKey,'/'+manifestKey]) {
      const manifest=await request(s.port,prefix+'/manifest.json');
      const stream=await request(s.port,prefix+'/stream/movie/tt1234567.json');
      const extra=await request(s.port,prefix+'/stream/movie/tt1234567/quality=4k.json');
      assert.equal(manifest.status,200);
      assert.equal(manifest.json?.a4CustomManifest,true);
      assert.equal(stream.status,200);
      assert.deepEqual(stream.json?.streams,[]);
      assert.equal(extra.status,200);
      assert.equal(manifest.headers.get('access-control-allow-origin'),'*');
      values[prefix.startsWith('/stremio/')?'prefixed':'legacy']={manifest:manifest.status,stream:stream.status,extra:extra.status};
    }
    const bad=await request(s.port,'/stremio/invalid-manifest-key/manifest.json');
    assert.equal(bad.status,404);
    record('A4-SDK-002','pass',{...values,invalidKey:404},'Actual pinned SDK getRouter under app-equivalent custom-manifest/mount ordering; synthetic stream handler (not real addon)');
  } finally { await s.close(); }
} catch(e) { record('A4-SDK-002','fail',{error:String(e)},'SDK routing fixture failed, or manifest key setup unavailable'); }

try {
  assert.ok(manifestKey,'auth fixture required');
  const { createNzbdavStreamRoutes } = await src('routes/nzbdav.js');
  const deletes=[];
  const fake=await serve((req,res)=>{
    if(req.method==='DELETE'){
      deletes.push({url:req.url,depth:req.headers.depth||null});
      res.writeHead(req.url.includes('FailPack')?503:204);res.end();return;
    }
    res.writeHead(200,{'Content-Type':'application/json'});res.end('{"history":{"slots":[]}}');
  });
  const app=express();
  const deps={
    config,handleStream:async(_req,res)=>res.end(),
    getCacheStats:()=>({}),clearStreamCache:()=>{},clearReadyCache:()=>0,
    clearFailedCache:()=>0,deleteCacheEntry:()=>false,getCacheEntries:()=>[],
    isStreamCached:()=>false,getLatestVersions:()=>({chrome:'synthetic'})
  };
  configData.nzbdavUrl='http://127.0.0.1:'+fake.port;
  configData.nzbdavWebdavUrl='http://127.0.0.1:'+fake.port;
  configData.nzbdavWebdavUser='';configData.nzbdavWebdavPassword='';
  app.use('/stremio/:manifestKey/nzbdav',authMw.validateManifestKey,createNzbdavStreamRoutes(deps));
  const server=await serve(app);
  const tile=(p,scope='pack')=>'?t='+encodeURIComponent(Buffer.from(JSON.stringify({sk:'synthetic-key',p,scope})).toString('base64url'));
  const endpoint='/stremio/'+manifestKey+'/nzbdav/library-delete';
  try {
    const invalid=await request(server.port,endpoint+tile('/notcontent/Movie'));
    assert.equal(deletes.length,0);
    const head=await request(server.port,endpoint+tile('/content/movies/TestPack'),{method:'HEAD'});
    const afterHEAD=deletes.length;
    await request(server.port,endpoint+tile('/content/movies/TestPack'),{method:'GET'});
    const afterReplay=deletes.length;
    await request(server.port,endpoint+tile('/content/movies/FailPack'),{method:'GET'});
    const failCount1=deletes.filter(x=>x.url?.includes('FailPack')).length;
    await request(server.port,endpoint+tile('/content/movies/FailPack'),{method:'GET'});
    const failCount2=deletes.filter(x=>x.url?.includes('FailPack')).length;
    // Bounded, loopback-only regression expansion. Unique paths avoid the existing 30s dedup window.
    const priorInvalid = deletes.length;
    await request(server.port,endpoint+tile('/content/movies/../CrossRoot'));
    await request(server.port,endpoint+tile('/content/movies/Bad/Deep','pack'));
    await request(server.port,endpoint+'?t=not-valid-json-base64');
    const invalidAdditional = deletes.length-priorInvalid;
    const unauthorizedBefore=deletes.length;
    const unauthorized = await request(server.port,'/stremio/invalid-manifest-key/nzbdav/library-delete'+tile('/content/movies/Unauthorized'));
    const unauthorizedDeletes=deletes.length-unauthorizedBefore;

    const concurrentPath='/content/movies/ConcurrentPack';
    const concurrentBefore=deletes.filter(x=>x.url?.includes('ConcurrentPack')).length;
    await Promise.all(Array.from({length:4},()=>request(server.port,endpoint+tile(concurrentPath))));
    const concurrentDeletes=deletes.filter(x=>x.url?.includes('ConcurrentPack')).length-concurrentBefore;

    // A4-DELETEALL-007: the token store and original delete-all handler are exercised,
    // not reimplemented. All targets and endpoints are disposable synthetic loopback.
    const { registerDeleteAllTargets } = await src('nzbdav/deleteAllTargetsStore.js');
    const allEndpoint='/stremio/'+manifestKey+'/nzbdav/library-delete-all';
    const allTile = (tk,id='a4-deleteall-failure') => '?t='+encodeURIComponent(Buffer.from(JSON.stringify({
      sk:'synthetic-key',type:'movie',id,tk
    })).toString('base64url'));
    const missBefore=deletes.length;
    const missing=await request(server.port,allEndpoint+allTile('not-registered','a4-deleteall-invalid-token'));
    const missDeletes=deletes.length-missBefore;
    const allToken=registerDeleteAllTargets([{path:'/content/movies/FailAllPack',scope:'pack'}]);
    const allUrl=allEndpoint+allTile(allToken);
    const allBefore=deletes.filter(x=>x.url?.includes('FailAllPack')).length;
    const allFirst=await request(server.port,allUrl,{method:'GET'});
    const allCountFirst=deletes.filter(x=>x.url?.includes('FailAllPack')).length-allBefore;
    const allReplay=await request(server.port,allUrl,{method:'GET'});
    const allCountReplay=deletes.filter(x=>x.url?.includes('FailAllPack')).length-allBefore;
    const invalidAllBefore=deletes.length;
    const invalidAll=await request(server.port,'/stremio/invalid-manifest-key/nzbdav/library-delete-all'+allTile(allToken));
    const invalidAllDeletes=deletes.length-invalidAllBefore;
    const allMetrics={missingTokenResponse:missing.status,missingTokenDeletes:missDeletes,
      firstResponse:allFirst.status,replayResponse:allReplay.status,
      firstAttemptCount:allCountFirst,replayAttemptCount:allCountReplay,
      invalidManifestResponse:invalidAll.status,invalidManifestDeletes:invalidAllDeletes};
    const allViolations=[];
    if(missDeletes!==0) allViolations.push('missing token caused DELETE');
    if(allCountFirst!==1) allViolations.push('first delete-all did not attempt one DELETE');
    if(allCountReplay!==2) allViolations.push('failed delete-all 503 did not retry');
    if(invalidAll.status!==404 || invalidAllDeletes!==0) allViolations.push('unauthorized delete-all reached WebDAV');
    record('A4-DELETEALL-007',allViolations.length?'fail':'pass',allMetrics,
      allViolations.length?allViolations.join('; '):'Original delete-all handler and token registry, failed WebDAV 503 replay');

    // Existing handler treats 404/410 as a successful absence; 503 is not success.
    const metrics={invalidDeletes:0,headResponse:head.status,headRemoteDeletes:afterHEAD,replayRemoteDeletes:afterReplay,failedFirst:failCount1,failedReplay:failCount2,invalidAdditional,unauthorizedStatus:unauthorized.status,unauthorizedDeletes,concurrentDeletes};
    const violations=[];
    if(afterHEAD!==0) violations.push('HEAD initiated WebDAV DELETE');
    if(afterReplay!==1) violations.push('dedup/replay count differs from one');
    if(failCount2!==2) violations.push('failed DELETE is deduped instead of retried');
    if(invalidAdditional!==0) violations.push('invalid/traversal/deep-pack envelope remotely deleted');
    if(unauthorized.status!==404 || unauthorizedDeletes!==0) violations.push('invalid manifest reached deletion');
    if(concurrentDeletes!==1) violations.push('concurrent same-key delete was not coalesced');
    record('A4-DELETE-003',violations.length?'fail':'pass',metrics,violations.length?violations.join('; '):'Original imported handler; no live WebDAV; remote side-effect count measured');
  } finally { await server.close();await fake.close(); }
} catch(e) { record('A4-DELETE-003','fail',{error:String(e)},'Original deletion route could not complete sandbox fixture'); }

try {
  const { createSettingsRoutes } = await src('routes/settings.js');
  const app=express();
  app.use(express.json({limit:'5mb'}));
  app.use('/api',authMw.requireAuth);
  app.use('/api',createSettingsRoutes({
    config,updateSettings,
    fetchLatestVersions:async()=>{},
    getLatestVersions:()=>({chrome:'synthetic',prowlarr:'synthetic',sabnzbd:'synthetic'}),
    testProxyConnection:async()=>({connected:false}),
    clearSearchCache:()=>{}
  }));
  const s=await serve(app);
  try {
    const one=await request(s.port,'/api/settings',jsonReq('PUT',{cacheTTL:9300},jwt));
    assert.equal(one.status,200);
    assert.equal(one.json?.cacheTTL,9300);
    assert.equal(configData.cacheTTL,9300);
    assert.equal(JSON.parse(fs.readFileSync(CONFIG_FILE,'utf8')).cacheTTL,9300);
    const two=await request(s.port,'/api/settings',jsonReq('PUT',{cacheTTL:9400},jwt));
    assert.equal(two.status,200);
    const disk=JSON.parse(fs.readFileSync(CONFIG_FILE,'utf8'));
    assert.equal(disk.cacheTTL,9400);
    const bad=await request(s.port,'/api/settings',{
      method:'PUT',headers:{Authorization:'Bearer '+jwt,'Content-Type':'application/json'},body:'{broken-json'
    });
    assert.equal(bad.status,400);
    const oversized=await request(s.port,'/api/settings',jsonReq('PUT',{extra:'A'.repeat(5*1024*1024+100)},jwt));
    assert.equal(oversized.status,413);
    assert.equal(JSON.parse(fs.readFileSync(CONFIG_FILE,'utf8')).cacheTTL,9400);
    const metrics={save:one.status,replacement:two.status,memory:configData.cacheTTL,disk:disk.cacheTTL,invalidJSON:bad.status,oversize:oversized.status};
    record('A4-AUTOSAVE-004','pass',metrics,'Real settings route plus synchronous persistence; UI debounce and reordering of in-flight UI responses NOT exercised');
  } finally {await s.close();}
} catch(e) {record('A4-AUTOSAVE-004','fail',{error:String(e)},'Settings backend behavior not confirmed; UI timer/concurrency remain unverified');}

// Original provider /test handshake against a disposable NNTP greeting and
// AUTHINFO server (loopback only). No external NNTP or real account is contacted.
try {
  const net=await import('node:net');
  const {createHealthCheckRoutes}=await src('routes/healthCheck.js');
  const commands=[];
  const fake=net.createServer(socket=>{
    socket.write('200 A4 synthetic NNTP ready\r\n');
    let pending='';
    socket.on('data',buf=>{
      pending+=buf.toString();
      while(pending.includes('\r\n')){
        const pos=pending.indexOf('\r\n');
        const cmd=pending.slice(0,pos);pending=pending.slice(pos+2);
        commands.push(cmd.startsWith('AUTHINFO PASS')?'AUTHINFO PASS [redacted]':cmd);
        if(cmd==='AUTHINFO USER synthetic-user')socket.write('381 password required\r\n');
        else if(cmd==='AUTHINFO PASS synthetic-pass')socket.write('281 authenticated\r\n');
        else socket.write('481 authentication rejected\r\n');
      }
    });
  });
  await new Promise(resolve=>fake.listen(0,'127.0.0.1',resolve));
  const port=fake.address().port;
  const app=express();app.use(express.json());app.use('/api',authMw.requireAuth);
  app.use('/api/health-check',createHealthCheckRoutes({
    getProviders:()=>[],addProvider:x=>x,updateProvider:(_,x)=>x,
    deleteProvider:()=>{},reorderProviders:()=>{}
  }));
  const s=await serve(app);
  try {
    const endpoint='/api/health-check/test';
    const missing=await request(s.port,endpoint,jsonReq('POST',{host:'',port:0},jwt));
    assert.equal(missing.status,400);
    const ok=await request(s.port,endpoint,jsonReq('POST',{
      host:'127.0.0.1',port,useTLS:false,username:'synthetic-user',password:'synthetic-pass'
    },jwt));
    assert.equal(ok.status,200);
    assert.equal(ok.json?.success,true);
    assert.deepEqual(commands,['AUTHINFO USER synthetic-user','AUTHINFO PASS [redacted]']);
    record('A4-NNTP-HANDSHAKE-008','pass',{missing:400,authenticated:200,commands:commands.length},
      'Original NNTP connection test route; local fake 200/381/281 handshake, no STAT or article availability check');
  }finally{await s.close();await new Promise(resolve=>fake.close(resolve));}
}catch(e){record('A4-NNTP-HANDSHAKE-008','fail',{error:String(e)},'Original NNTP auth route synthetic loopback test');}

// Article-level original STAT checker: two entirely synthetic NNTP servers
// demonstrate pipelining, missing articles and backup provider recovery.
try {
  const net=await import('node:net');
  const {checkArticlesMultiProvider}=await src('health/articleChecker.js');
  const seen={pool:[],backup:[]};
  const servers=[];
  async function fakeNntp(role){
    const server=net.createServer(socket=>{
      socket.write('200 A4 local article fixture\r\n');
      let buffer='';
      socket.on('data',data=>{
        buffer+=data.toString();
        while(buffer.includes('\r\n')){
          const k=buffer.indexOf('\r\n'),cmd=buffer.slice(0,k);
          buffer=buffer.slice(k+2);
          if(!cmd.startsWith('STAT <')){socket.write('500 unknown command\r\n');continue;}
          seen[role].push(cmd);
          const exists=role==='pool'?cmd.includes('a4-one'):cmd.includes('a4-two');
          socket.write(exists?'223 1 article found\r\n':'430 no such article\r\n');
        }
      });
    });
    await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
    servers.push(server);return server.address().port;
  }
  const poolPort=await fakeNntp('pool'),backupPort=await fakeNntp('backup');
  const providers=[
    {id:'a4-pool',name:'synthetic-pool',type:'pool',enabled:true,host:'127.0.0.1',port:poolPort,useTLS:false,username:'',password:''},
    {id:'a4-backup',name:'synthetic-backup',type:'backup',enabled:true,host:'127.0.0.1',port:backupPort,useTLS:false,username:'',password:''}
  ];
  try {
    const result=await checkArticlesMultiProvider(providers,['a4-one','a4-two']);
    assert.equal(result.totalExists,2);
    assert.equal(result.totalMissing,0);
    assert.deepEqual(seen.pool,['STAT <a4-one>','STAT <a4-two>']);
    assert.deepEqual(seen.backup,['STAT <a4-two>']);
    assert.equal(result.providersUsed.length,2);
    await assert.rejects(()=>checkArticlesMultiProvider([],['a4-one']),/No enabled providers/);
    record('A4-STAT-FALLBACK-009','pass',
      {poolCommands:seen.pool.length,backupCommands:seen.backup.length,exists:result.totalExists,missing:result.totalMissing},
      'Original articleChecker STAT pipeline and backup-provider fallback against two fake NNTP servers');
  }finally{await Promise.all(servers.map(server=>new Promise(resolve=>server.close(resolve))));}
}catch(e){record('A4-STAT-FALLBACK-009','fail',{error:String(e)},'Original article checker synthetic fallback fixture');}

// Original archive classification/grouping: fabricated NZB segment structures only.
try {
  const group=await src('health/archiveGrouper.js');
  const cls=await src('health/fileClassifier.js');
  const mk=(i)=>({subject:'[1/3] - "A4.Movie.part00'+i+'.rar" yEnc (1/1)',
    segments:[{messageId:'a4-archive-'+i,bytes:128,number:1}]});
  const files=[mk(3),mk(1),mk(2)];
  const groups=group.groupArchiveParts(files);
  assert.equal(groups.length,1);
  assert.deepEqual(groups[0].map(f=>cls.extractFilename(f.subject)),
    ['A4.Movie.part001.rar','A4.Movie.part002.rar','A4.Movie.part003.rar']);
  assert.equal(group.findFirstArchivePart(files).subject,mk(1).subject);
  const samples=group.selectMultiPartSamples(files,3);
  assert.deepEqual(samples,['a4-archive-1','a4-archive-2','a4-archive-3']);
  const collected=group.collectAllArchiveSegments(files);
  assert.deepEqual(collected.map(x=>x.messageId),samples);
  assert.equal(cls.isCompressedArchive(mk(1).subject),true);
  assert.equal(cls.isVideoFile('"Movie.mkv" yEnc (1/1)'),true);
  assert.equal(cls.isVideoFile('"Movie.sample.mkv" yEnc (1/1)'),false);
  record('A4-ARCHIVE-GROUP-010','pass',
    {groups:groups.length,parts:groups[0].length,samples:samples.length,orderedSegments:collected.length},
    'Original archive grouping, first-part discovery, sample selection, file classifier; not archive decompression/yEnc decode');
}catch(e){record('A4-ARCHIVE-GROUP-010','fail',{error:String(e)},'Original archive fixture failed');}

// Original BODY transfer and yEnc decode, synthetic article with exact bytes.
// One fake socket returns 222 with dot-terminated body and one returns 430.
try {
  const net=await import('node:net');
  const {downloadSegment}=await src('archive/nntpSegmentDownloader.js');
  const magic=await src('archive/formatDetector.js');
  const servers=[];
  async function fakeBody(mode){
    const server=net.createServer(socket=>{
      let pending='';
      socket.on('data',b=>{
        pending+=b.toString();
        if(pending.includes('\r\n')){
          if(mode==='found')socket.write('222 1 <a4-body> body follows\r\n=ybegin line=128 size=3 name=a4.bin\r\nklm\r\n=yend size=3\r\n.\r\n');
          else socket.write('430 missing\r\n');
          pending='';
        }
      });
    });
    await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));servers.push(server);
    return server.address().port;
  }
  const okPort=await fakeBody('found'),badPort=await fakeBody('missing');
  const ok=net.connect({host:'127.0.0.1',port:okPort});
  const bad=net.connect({host:'127.0.0.1',port:badPort});
  try {
    const bytes=await downloadSegment(ok,'a4-body');
    assert.deepEqual(bytes,Buffer.from('ABC'));
    await assert.rejects(()=>downloadSegment(bad,'missing'),/Article not found/);
    assert.equal(magic.isRAR4(Buffer.from([0x52,0x61,0x72,0x21,0x1a,0x07,0])),true);
    assert.equal(magic.isRAR5(Buffer.from([0x52,0x61,0x72,0x21,0x1a,0x07,1,0])),true);
    assert.equal(magic.isZip(Buffer.from([0x50,0x4b,3,4])),true);
    assert.equal(magic.is7Zip(Buffer.from([0x37,0x7a,0xbc,0xaf,0x27,0x1c])),true);
    record('A4-YENC-011','pass',{bodyBytes:bytes.length,decoded:'ABC',missing:430,detectors:4},
      'Original BODY message handler and yEnc decoder plus archive signatures; no full archive extraction');
  }finally{
    ok.destroy();bad.destroy();
    await Promise.all(servers.map(s=>new Promise(resolve=>s.close(resolve))));
  }
}catch(e){record('A4-YENC-011','fail',{error:String(e)},'Original yEnc BODY fixture failed');}

// Original /v WebDAV proxy. Fake upstream returns exact 200/206/416 and
// 404 on loopback. Tests forwarding, 416 recovery and same-origin fallback.
try {
  assert.ok(manifestKey,'auth fixture required');
  const {createNzbdavStreamRoutes}=await src('routes/nzbdav.js');
  const body=Buffer.from('0123456789','ascii');
  const upstreamRanges=[];
  const fake=await serve((req,res)=>{
    const range=req.headers.range;
    upstreamRanges.push(range||'(none)');
    if(req.url.includes('MissingMedia')){
      res.writeHead(404);res.end();return;
    }
    if(!range){res.writeHead(200,{'Content-Type':'video/mp4','Content-Length':body.length,'Accept-Ranges':'bytes'});res.end(body);return;}
    const match=/^bytes=(\d+)-(\d*)$/.exec(range);
    const start=match?Number(match[1]):Infinity;
    const end=match&&match[2]?Math.min(Number(match[2]),body.length-1):body.length-1;
    if(start>=body.length || end<start){res.writeHead(416,{'Content-Range':'bytes */10'});res.end();return;}
    const payload=body.subarray(start,end+1);
    res.writeHead(206,{'Content-Type':'video/mp4','Content-Length':payload.length,
      'Content-Range':'bytes '+start+'-'+end+'/10','Accept-Ranges':'bytes'});
    res.end(payload);
  });
  configData.nzbdavWebdavUrl='http://127.0.0.1:'+fake.port;
  configData.nzbdavUrl='http://127.0.0.1:'+fake.port;
  configData.nzbdavStreamingMethod='pipe';
  configData.nzbdavWebdavUser='';configData.nzbdavWebdavPassword='';
  const deps={
    config,handleStream:async(_req,res)=>res.end(),getCacheStats:()=>({}),
    clearStreamCache:()=>{},clearReadyCache:()=>0,clearFailedCache:()=>0,
    deleteCacheEntry:()=>false,getCacheEntries:()=>[],isStreamCached:()=>false,
    getLatestVersions:()=>({chrome:'synthetic'})
  };
  const app=express();
  app.use('/stremio/:manifestKey/nzbdav',authMw.validateManifestKey,createNzbdavStreamRoutes(deps));
  const s=await serve(app);
  try{
    const endpoint='/stremio/'+manifestKey+'/nzbdav/v?path='+encodeURIComponent('/content/movies/A4Media');
    const full=await fetch('http://127.0.0.1:'+s.port+endpoint);
    assert.equal(full.status,200);assert.equal(await full.text(),'0123456789');
    const partial=await fetch('http://127.0.0.1:'+s.port+endpoint,{headers:{Range:'bytes=2-5'}});
    assert.equal(partial.status,206);
    assert.equal(partial.headers.get('content-range'),'bytes 2-5/10');
    assert.equal(await partial.text(),'2345');
    const recovered=await fetch('http://127.0.0.1:'+s.port+endpoint,{headers:{Range:'bytes=100-'}});
    assert.equal(recovered.status,200);assert.equal(await recovered.text(),'0123456789');
    assert.deepEqual(upstreamRanges.slice(0,4),['(none)','bytes=2-5','bytes=100-','(none)']);
    const missing='/stremio/'+manifestKey+'/nzbdav/v?path='+encodeURIComponent('/content/movies/MissingMedia');
    const gone=await fetch('http://127.0.0.1:'+s.port+missing);
    assert.equal(gone.status,404);
    const fb='/stremio/'+manifestKey+'/nzbdav/stream/ultimate-fallback';
    const fallback=await fetch('http://127.0.0.1:'+s.port+missing+'&_fb='+encodeURIComponent(fb),
      {redirect:'manual'});
    assert.equal(fallback.status,302);
    const location=new URL(fallback.headers.get('location'));
    assert.equal(location.hostname,'127.0.0.1');
    assert.equal(location.pathname,fb);
    assert.equal(location.searchParams.get('_norange'),'1');
    record('A4-PROXY-FALLBACK-014','pass',
      {upstream404:404,redirect:302,noRange:location.searchParams.get('_norange'),sameOrigin:true},
      'Original video proxy 404 marks stale path and redirects to same-origin fallback with range reset');
    record('A4-RANGE-PROXY-012','pass',
      {full:200,partial:206,recovered416:200,missing:404,upstreamRequests:upstreamRanges.length},
      'Original /v proxy, byte-for-byte 200/206 and 416 recovery, upstream 404 without fallback; no actual 4K playback');
  }finally{await s.close();await fake.close();}
}catch(e){record('A4-RANGE-PROXY-012','fail',{error:String(e)},'Original WebDAV proxy Range fixture failed');}

// Actual Prowlarr/NZBHydra sync route against synthetic localhost HTTP
// integrations. All IDs/keys are fabricated; the original axios logic runs.
try {
  const {createIntegrationRoutes}=await src('routes/integrations.js');
  const fake=await serve((req,res)=>{
    if(req.url==='/api/v1/indexer'){
      res.writeHead(200,{'Content-Type':'application/json'});
      res.end(JSON.stringify([
        {id:23,name:'A4Synced',protocol:'usenet',enable:true,
          fields:[{name:'baseUrl',value:'http://127.0.0.1'}],
          capabilities:{movieSearchParams:['ImdbId','Q'],tvSearchParams:['TvdbId','Q']}},
        {id:24,name:'DisabledA4',protocol:'usenet',enable:false},
        {id:25,name:'TorrentA4',protocol:'torrent',enable:true}
      ]));return;
    }
    if(req.url.startsWith('/api?') && req.url.includes('t=caps')){
      res.writeHead(200,{'Content-Type':'text/xml'});
      res.end('<caps><searching><movie-search supportedParams="imdbid,q"/><tv-search supportedParams="tvdbid,q"/></searching></caps>');return;
    }
    if(req.url==='/api/stats/indexers'){
      res.writeHead(200,{'Content-Type':'application/json'});
      res.end(JSON.stringify([{indexerName:'HydraA4',state:'ENABLED'},
        {indexerName:'DisabledHydraA4',state:'DISABLED_USER'}]));return;
    }
    res.writeHead(404);res.end();
  });
  const app=express();app.use(express.json());app.use('/api',authMw.requireAuth);
  app.use('/api',createIntegrationRoutes({
    config,updateSettings,
    reorderSyncedIndexers:items=>{configData.syncedIndexers=items;},
    getLatestVersions:()=>({chrome:'synthetic'})
  }));
  const s=await serve(app);
  try{
    const url='http://127.0.0.1:'+fake.port;
    const unauth=await request(s.port,'/api/prowlarr/sync',jsonReq('POST',{url,apiKey:'fixture'},'invalid'));
    assert.equal(unauth.status,401);
    configData.syncedIndexers=[{id:'23',name:'OldA4',enabledForSearch:false,
      enabledForHealthCheck:true,movieSearchMethod:['text'],tvSearchMethod:['text']}];
    const prowlarr=await request(s.port,'/api/prowlarr/sync',
      jsonReq('POST',{url,apiKey:'fixture'},jwt));
    assert.equal(prowlarr.status,200);
    assert.equal(prowlarr.json?.total,1);
    assert.equal(prowlarr.json?.indexers?.[0]?.id,'23');
    assert.equal(prowlarr.json?.indexers?.[0]?.enabledForSearch,false);
    assert.deepEqual(prowlarr.json?.indexers?.[0]?.movieSearchMethod,['text']);
    assert.equal((await request(s.port,'/api/synced-indexers/23',
      jsonReq('PUT',{enabledForHealthCheck:false,id:'override'},jwt))).json?.id,'23');
    const hydra=await request(s.port,'/api/nzbhydra/sync',
      jsonReq('POST',{url,apiKey:'fixture'},jwt));
    assert.equal(hydra.status,200);
    assert.equal(hydra.json?.total,2); // includes user-disabled status, which is excluded from synced results
    assert.equal(hydra.json?.indexers?.length,1);
    assert.equal(hydra.json?.indexers?.[0]?.name,'HydraA4');
    const reordered=await request(s.port,'/api/synced-indexers/reorder',
      jsonReq('POST',{syncedIndexers:hydra.json.indexers},jwt));
    assert.equal(reordered.status,200);
    record('A4-SYNC-013','pass',
      {unauth:401,prowlarr:prowlarr.json.total,hydra:hydra.json.total,
        preservedSettings:true,reorder:200},
      'Original Prowlarr/NZBHydra sync routers with localhost fake responses and synthetic settings');
  }finally{await s.close();await fake.close();}
}catch(e){record('A4-SYNC-013','fail',{error:String(e)},'Original synced indexer fixture failed');}

// Original cache recovery markers, exercised with only disposable keys.
try {
  const cache=await src('nzbdav/streamCache.js');
  const video='/content/movies/A4BrokenVideo.mkv';
  assert.equal(cache.isVideoPathBroken(video),false);
  cache.markVideoPathBroken(video);
  assert.equal(cache.isVideoPathBroken(video),true);
  cache.clearVideoPathBroken(video);
  assert.equal(cache.isVideoPathBroken(video),false);
  const key='a4-test-manifest:movie:tt9999999::';
  assert.equal(cache.consumeLibraryBypass(key),false);
  cache.markLibraryBypass(key);
  assert.equal(cache.consumeLibraryBypass(key),true);
  assert.equal(cache.consumeLibraryBypass(key),false);
  record('A4-CACHE-015','pass',{brokenPathMarkClear:true,bypassOneShot:true},
    'Original broken-video-path and library bypass cache marker state, no persisted stream/cache parity claimed');
}catch(e){record('A4-CACHE-015','fail',{error:String(e)},'Original cache marker fixture failed');}

// Real health-check pipeline with cached fabricated NZB XML and a local STAT
// responder. Runs both 3-sample and 7-sample verification policies.
try {
  const net=await import('node:net');
  const {cacheNzbContent}=await src('health/nzbContentCache.js');
  const {performHealthCheck}=await src('health/healthCheckPipeline.js');
  const url='http://127.0.0.1/fixture-a4-health.nzb';
  const segments=Array.from({length:7},(_,i)=>
    '<segment bytes="200" number="'+(i+1)+'">a4-health-'+(i+1)+'</segment>').join('');
  const xml='<?xml version="1.0"?><nzb><file subject="A4.Fixture.Video.mkv"><segments>'+segments+'</segments></file></nzb>';
  cacheNzbContent(url,xml); // no external NZB fetch/circuit validation
  let missing=false;
  const seen=[];
  const server=net.createServer(socket=>{
    socket.write('200 synthetic health server\r\n');
    let buffer='';
    socket.on('data',chunk=>{
      buffer+=chunk.toString();
      while(buffer.includes('\r\n')){
        const i=buffer.indexOf('\r\n');const command=buffer.slice(0,i);buffer=buffer.slice(i+2);
        if(!command.startsWith('STAT <'))continue;
        seen.push(command);
        socket.write(missing&&command.includes('a4-health-7')?'430 missing\r\n':'223 found\r\n');
      }
    });
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const provider={id:'a4-health-provider',name:'A4 Health',type:'pool',enabled:true,
    host:'127.0.0.1',port:server.address().port,useTLS:false,username:'',password:''};
  try {
    const three=await performHealthCheck(url,[provider],'A4 synthetic',{archiveInspection:false,sampleCount:3});
    assert.equal(three.status,'verified');assert.equal(three.playable,true);
    assert.equal(seen.length,3);
    const seven=await performHealthCheck(url,[provider],'A4 synthetic',{archiveInspection:false,sampleCount:7});
    assert.equal(seven.status,'verified');assert.equal(seven.playable,true);
    assert.equal(seen.length,10);
    missing=true;
    const blocked=await performHealthCheck(url,[provider],'A4 synthetic',{archiveInspection:false,sampleCount:3});
    assert.equal(blocked.status,'blocked');assert.equal(blocked.playable,false);
    record('A4-HEALTH-SAMPLING-016','pass',
      {threeSamples:3,sevenSamples:7,blockedStatus:blocked.status},
      'Original health-check pipeline, synthetic cached NZB + 3/7 STAT policies; does not assert UI Smart/Fixed full orchestration');
  }finally{await new Promise(resolve=>server.close(resolve));}
}catch(e){record('A4-HEALTH-SAMPLING-016','fail',{error:String(e)},'Original end-to-end synthetic NZB health pipeline fixture failed');}

// Provider and indexer CRUD: invoke the original Express routers with in-memory
// synthetic repository callbacks. No NNTP credentials or external indexer traffic.
try {
  const {createHealthCheckRoutes}=await src('routes/healthCheck.js');
  const {createIndexerRoutes}=await src('routes/indexers.js');
  let providers=[],indexers=[],n=0;
  const app=express();app.use(express.json());app.use('/api',authMw.requireAuth);
  app.use('/api/health-check',createHealthCheckRoutes({
    getProviders:()=>providers,
    addProvider:p=>{const v={...p,id:'fixture-'+(++n)};providers.push(v);return v;},
    updateProvider:(id,v)=>{const i=providers.findIndex(x=>x.id===id);if(i<0)throw Error('not found');return providers[i]={...providers[i],...v};},
    deleteProvider:id=>{const i=providers.findIndex(x=>x.id===id);if(i<0)throw Error('not found');providers.splice(i,1);},
    reorderProviders:ids=>{if(ids.length!==providers.length||ids.some(x=>!providers.some(p=>p.id===x)))throw Error('invalid ids');providers=ids.map(id=>providers.find(x=>x.id===id));}
  }));
  app.use('/api/indexers',createIndexerRoutes({
    config,getIndexers:()=>indexers,
    addIndexer:x=>{if(indexers.some(i=>i.name===x.name))throw Error('duplicate name');const v={...x,enabled:true};indexers.push(v);return v;},
    updateIndexer:(name,x)=>{const i=indexers.findIndex(v=>v.name===name);if(i<0)throw Error('not found');return indexers[i]={...indexers[i],...x};},
    deleteIndexer:name=>{const i=indexers.findIndex(x=>x.name===name);if(i<0)throw Error('not found');indexers.splice(i,1);},
    reorderIndexers:items=>{if(items.length!==indexers.length||items.some(x=>!indexers.some(i=>i.name===x.name)))throw Error('invalid order');indexers=items;},
    fetchIndexerCaps:async()=>({categories:[]}),
    proxyFetch:async()=>({ok:true,status:200,statusText:'OK',text:async()=>'<rss><channel><item><title>Synthetic.Movie</title></item></channel></rss>'}),
    getLatestVersions:()=>({chrome:'synthetic',prowlarr:'synthetic'})
  }));
  const s=await serve(app);
  const base='/api/health-check/providers',ix='/api/indexers';
  const req=(url,opts)=>request(s.port,url,{headers:{Authorization:'Bearer '+jwt,...opts?.headers},...opts});
  try {
    assert.equal((await request(s.port,base)).status,401);
    assert.equal((await req(base,{method:'POST',...jsonReq('POST',{name:'bad'},jwt)})).status,400);
    const a=await req(base,jsonReq('POST',{name:'SyntheticA',host:'127.0.0.1',username:'dummy',password:'dummy'},jwt));
    const b=await req(base,jsonReq('POST',{name:'SyntheticB',host:'127.0.0.1'},jwt));
    assert.equal(a.status,201);assert.equal(b.status,201);
    assert.equal(a.json.port,563);assert.equal(a.json.useTLS,true);
    const reorder=await req(base+'/reorder',jsonReq('POST',{orderedIds:[b.json.id,a.json.id]},jwt));
    assert.equal(reorder.status,200);assert.equal(providers[0].id,b.json.id);
    assert.equal((await req(base+'/'+encodeURIComponent(a.json.id),jsonReq('PUT',{enabled:false},jwt))).json.enabled,false);
    assert.equal((await req(base+'/'+encodeURIComponent(a.json.id),{method:'DELETE'})).status,204);
    assert.equal(providers.length,1);
    record('A4-PROVIDER-005','pass',{anonymous:401,created:2,reordered:reorder.status,deleted:1},'Original provider CRUD and reorder router; synthetic in-memory callbacks');
    assert.equal((await req(ix,jsonReq('POST',{name:'bad'},jwt))).status,400);
    assert.equal((await req(ix,jsonReq('POST',{name:'BadTimeout',url:'http://127.0.0.1',apiKey:'dummy',timeout:46},jwt))).status,400);
    const one=await req(ix,jsonReq('POST',{name:'IndexA',url:'http://127.0.0.1',apiKey:'dummy'},jwt));
    const two=await req(ix,jsonReq('POST',{name:'IndexB',url:'http://127.0.0.1/api',apiKey:'dummy'},jwt));
    assert.equal(one.status,201);assert.equal(two.status,201);
    assert.equal(one.json.url,'http://127.0.0.1/api');
    assert.equal((await req(ix+'/IndexA',jsonReq('PUT',{timeout:10,timeoutEnabled:true},jwt))).status,200);
    assert.equal((await req(ix+'/reorder',jsonReq('POST',{indexers:[two.json,one.json]},jwt))).status,200);
    assert.equal(indexers[0].name,'IndexB');
    assert.equal((await req(ix+'/IndexA',{method:'DELETE'})).status,204);
    assert.equal(indexers.length,1);
    const caps=await req(ix+'/caps',jsonReq('POST',{url:'http://127.0.0.1',apiKey:'dummy'},jwt));
    assert.equal(caps.status,200);
    record('A4-INDEXER-006','pass',{created:2,normalizedUrl:one.json.url,reordered:true,deleted:1,caps:200},'Original manual indexer router, injected caps and proxy callbacks; not a sync integration test');
  }finally{await s.close();}
}catch(e){record('A4-PROVIDER-INDEXER','fail',{error:String(e)},'Synthetic CRUD fixture did not satisfy original route contract');}

fs.writeFileSync(process.env.A4_RESULTS,JSON.stringify(report,null,2)+'\n',{mode:0o600});
console.log('A4 SYNTHETIC SUMMARY',JSON.stringify({passed:report.cases.filter(x=>x.status==='pass').length,failed:failures}));
process.exit(failures ? 1 : 0);
