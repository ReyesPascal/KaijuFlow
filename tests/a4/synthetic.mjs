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
    const metrics={invalidDeletes:0,headResponse:head.status,headRemoteDeletes:afterHEAD,replayRemoteDeletes:afterReplay,failedFirst:failCount1,failedReplay:failCount2};
    const violations=[];
    if(afterHEAD!==0) violations.push('HEAD initiated WebDAV DELETE');
    if(afterReplay!==1) violations.push('dedup/replay count differs from one');
    if(failCount2!==2) violations.push('failed DELETE is deduped instead of retried');
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

fs.writeFileSync(process.env.A4_RESULTS,JSON.stringify(report,null,2)+'\n',{mode:0o600});
console.log('A4 SYNTHETIC SUMMARY',JSON.stringify({passed:report.cases.filter(x=>x.status==='pass').length,failed:failures}));
process.exit(failures ? 1 : 0);
