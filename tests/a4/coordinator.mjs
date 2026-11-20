// A4 additional coordinator integration smoke tests; imported only after fail-closed gate.
// All candidate health statuses are synthetic/pre-existing; no external NNTP or Backend calls.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { pathToFileURL } from 'node:url';
const root = process.env.A4_APP_ROOT;
const output = process.env.A4_COORD_RESULTS;
if (!root || !output || !fs.existsSync(path.join(path.dirname(root), 'app-import.started'))) throw Error('FAIL CLOSED: isolation sentinel missing');
assert.deepEqual(Object.keys(os.networkInterfaces()), ['lo']);
assert.match(root, /kaijuflow-a4-[^/]+\/positive\/work$/);
const load = x => import(pathToFileURL(path.join(root,'dist',x)).href);
const {configData} = await load('config/index.js');
const {coordinateHealthChecks} = await load('addon/healthCheckCoordinator.js');
const original = { healthChecks:structuredClone(configData.healthChecks), streamingMode:configData.streamingMode, indexManager:configData.indexManager, easynewsHealthCheck:configData.easynewsHealthCheck };
const results=[];
const run=async(id,fn)=>{try{const measurements=await fn();results.push({id,status:'pass',measurements});console.log('A4 COORD CASE',id,'pass',JSON.stringify(measurements));}catch(e){results.push({id,status:'fail',error:String(e),stack:e.stack});console.log('A4 COORD CASE',id,'fail',String(e));}};
const items=()=>[
  {link:'https://127.0.0.1/fixture-a.nzb',title:'A4 Coordinator A',indexerName:'Synthetic'},
  {link:'https://127.0.0.1/fixture-b.nzb',title:'A4 Coordinator B',indexerName:'Synthetic'},
  {link:'https://127.0.0.1/fixture-c.nzb',title:'A4 Coordinator C',indexerName:'Synthetic',zyclopsVerified:true}
];
const pre=arr=>new Map(arr.slice(0,2).map(r=>[r.link,{status:'verified',message:'Synthetic cached result',playable:true}]));
try{
  configData.streamingMode='none'; configData.indexManager='manual'; configData.easynewsHealthCheck=false;
  configData.healthChecks={...configData.healthChecks,enabled:true,providers:[{host:'127.0.0.1',port:119,enabled:true,username:'fixture',password:'fixture'}],inspectionMethod:'smart',smartBatchSize:2,smartAdditionalRuns:2,smartMinHealthy:1,hideBlocked:false};
  await run('A4-COORD-SMART-018',async()=>{
    const arr=items(), r=await coordinateHealthChecks({allResults:arr,type:'movie',preExistingHealth:pre(arr)});
    assert.equal(r.healthResults.get(arr[0].link)?.status,'verified');
    assert.equal(r.healthResults.get(arr[2].link)?.message,'Zyclops');
    assert.equal(r.filteredResults.length,3);
    return {verified:r.healthResults.size,retained:r.filteredResults.length};
  });
  await run('A4-COORD-FIXED-019',async()=>{
    configData.healthChecks.inspectionMethod='fixed';configData.healthChecks.nzbsToInspect=2;
    const arr=items(),r=await coordinateHealthChecks({allResults:arr,type:'movie',preExistingHealth:pre(arr)});
    assert.equal(r.healthResults.get(arr[1].link)?.status,'verified');
    assert.equal(r.healthResults.get(arr[2].link)?.message,'Zyclops');
    assert.equal(r.filteredResults.length,3);
    return {topN:2,verified:r.healthResults.size,retained:r.filteredResults.length};
  });
  await run('A4-COORD-DISABLED-020',async()=>{
    configData.healthChecks.enabled=false;
    const arr=items(),r=await coordinateHealthChecks({allResults:arr,type:'movie',preExistingHealth:pre(arr)});
    assert.equal(r.healthResults.get(arr[2].link)?.message,'Zyclops');
    assert.equal(r.filteredResults.length,3);
    return {autoMarked:true,retained:r.filteredResults.length};
  });
} finally {
  configData.healthChecks=original.healthChecks;configData.streamingMode=original.streamingMode;configData.indexManager=original.indexManager;configData.easynewsHealthCheck=original.easynewsHealthCheck;
}
fs.writeFileSync(output,JSON.stringify({source_commit:'c83a3c733b6394eb140a1c0a1dc500010a9f22e5',gate:'A4-ISO-000',cases:results},null,2));
console.log('A4 COORD SUMMARY',JSON.stringify({passed:results.filter(x=>x.status==='pass').length,failed:results.filter(x=>x.status!=='pass').length}));
process.exit(results.some(x=>x.status!=='pass') ? 1 : 0);
