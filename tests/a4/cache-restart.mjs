// Separate-process cache persistence/corruption fixture. Executed only inside sealed A4 netns.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { spawnSync } from 'node:child_process';
const root=process.env.A4_APP_ROOT, output=process.env.A4_CACHE_RESULTS;
if(!root||!output||!fs.existsSync(path.join(path.dirname(root),'app-import.started'))) throw Error('FAIL CLOSED: isolation gate missing');
assert.deepEqual(Object.keys(os.networkInterfaces()),['lo']);
assert.match(root,/kaijuflow-a4-[^/]+\/positive\/work$/);
const childScript=`
import {pathToFileURL} from 'node:url';
import path from 'node:path';
const root=process.env.A4_APP_ROOT;
const sc=await import(pathToFileURL(path.join(root,'dist/nzbdav/streamCache.js')).href);
const u='https://127.0.0.1/cache-restart-A4.nzb', title='A4 Restart Fixture';
const bad='https://127.0.0.1/cache-restart-dead-A4.nzb';
if(process.env.A4_CACHE_STAGE==='write'){
  sc.setReadyCacheEntry(sc.getCacheKey(u,title),{videoPath:'/synthetic/a4.mp4',videoSize:4096},'Synthetic');
  sc.addDeadNzbByUrl(bad,'A4 Unavailable','Synthetic',123);
}
const state={ready:sc.isStreamCached(u,title),dead:sc.isDeadNzbByUrl(bad),readyCount:sc.getCacheStats().ready,deadCount:sc.getCacheStats().failed};
console.log('CACHE_METRIC '+JSON.stringify(state));
process.exit(0);
`;
const run=stage=>{
 const p=spawnSync(process.execPath,['--input-type=module','-e',childScript],{cwd:root,env:{...process.env,A4_CACHE_STAGE:stage},encoding:'utf8',timeout:12000,maxBuffer:200000});
 assert.equal(p.status,0,'child '+stage+' failed: '+p.stderr+' '+p.stdout);
 const line=p.stdout.split('\n').find(x=>x.startsWith('CACHE_METRIC '));
 assert.ok(line,'missing metric for '+stage+': '+p.stdout);
 return JSON.parse(line.slice('CACHE_METRIC '.length));
};
const cases=[];
const test=(id,fn)=>{try{const metrics=fn();cases.push({id,status:'pass',metrics});console.log('A4 CACHE CASE',id,'pass',JSON.stringify(metrics))}catch(e){cases.push({id,status:'fail',error:String(e)});console.log('A4 CACHE CASE',id,'fail',String(e))}};
test('A4-CACHE-RESTART-021',()=>{
 const writer=run('write'),reloaded=run('reload');
 assert.ok(writer.ready&&writer.dead);
 assert.ok(reloaded.ready&&reloaded.dead);
 return {writer,reloaded};
});
test('A4-CACHE-CORRUPT-022',()=>{
 for(const name of ['healthy-nzbs.json','dead-nzbs.json']) fs.writeFileSync(path.join(root,'config',name),'{invalid fixture json');
 const loaded=run('corrupt');
 assert.equal(loaded.ready,false);assert.equal(loaded.dead,false);
 return {loaded,survived:true};
});
fs.writeFileSync(output,JSON.stringify({source_commit:'c83a3c733b6394eb140a1c0a1dc500010a9f22e5',gate:'A4-ISO-000',cases},null,2));
console.log('A4 CACHE SUMMARY',JSON.stringify({passed:cases.filter(c=>c.status==='pass').length,failed:cases.filter(c=>c.status==='fail').length}));
process.exit(cases.some(c=>c.status==='fail')?1:0);
