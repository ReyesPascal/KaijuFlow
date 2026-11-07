// Actual original useAppConfig hook, compiled without source edits by esbuild before isolation.
// Runs ONLY inside A4 fail-closed network namespace with disposable React dependencies.
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
assert(process.env.A4_APP_ROOT && process.env.A4_UI_RESULTS, 'FAIL CLOSED: no disposable root/results');
assert(fs.existsSync(path.join(path.dirname(process.env.A4_APP_ROOT),'app-import.started')), 'FAIL CLOSED: gate sentinel missing');
assert.deepEqual(Object.keys(os.networkInterfaces()), ['lo']);
assert.match(process.env.A4_APP_ROOT, /kaijuflow-a4-[^/]+\/positive\/work$/);
const React = require('react');
const renderer = require('react-test-renderer');
const {act} = renderer;
const {useAppConfig} = require('./hook.cjs');
const observed = [];
let state;
let clock = 0, serial = 0;
const timers = new Map();
const nativeSetTimeout = global.setTimeout, nativeClearTimeout = global.clearTimeout;
global.setTimeout = (fn, delay = 0, ...args) => {
  const id=++serial;
  timers.set(id,{at:clock+Number(delay),fn:()=>fn(...args)});
  return id;
};
global.clearTimeout = id => timers.delete(id);
const flush = async () => {await Promise.resolve();await Promise.resolve();await Promise.resolve();};
async function advance(ms) {
  const end=clock+ms;
  while(true) {
    const next=[...timers].sort((a,b)=>a[1].at-b[1].at || a[0]-b[0]).find(([,t])=>t.at<=end);
    if(!next) break;
    clock=next[1].at;timers.delete(next[0]);
    await act(async()=>{next[1].fn();await flush();});
  }
  clock=end;
}
const requests=[];
const apiFetch=(url,opts={})=>{
  if(url==='/api/config') return Promise.resolve({ok:true,json:async()=>({
    indexers:[], cacheTTL:9000, streamingMode:'stremio', addonEnabled:true,
    autoPlay:{enabled:false,method:'firstFile',attributes:['resolution','quality','edition']}
  })});
  if(url==='/api/settings' && opts.method==='PUT') {
    const body=JSON.parse(opts.body);
    return new Promise((resolve,reject)=>requests.push({body,resolve,reject}));
  }
  return Promise.resolve({ok:true,json:async()=>({}),status:200});
};
const cases=[];
function report(id,pass,metrics,notes) {
 cases.push({id,status:pass?'pass':'fail',measurements:metrics,notes});
 console.log('A4 REACT CASE',id,pass?'pass':'fail',JSON.stringify(metrics));
}
let root;
const errors=[];
const originalError=console.error;
console.error=(...args)=>errors.push(args.map(String).join(' '));
function Test(){state=useAppConfig(apiFetch,'authenticated');return null;}
async function putChange(set,value,ms=500) {
  const n=requests.length;
  await act(async()=>{set(value)});
  await advance(ms-1);
  assert.equal(requests.length,n,'save fired before debounce');
  await advance(1);
  assert(requests.length>n,'save did not fire after debounce');
  return requests.find((_,i)=>i>=n && (ms===300 ? Object.hasOwn(requests[i].body,'addonEnabled') : requests[i].body.cacheTTL===value));
}
const respond=(req,value)=>req.resolve({ok:true,status:200,json:async()=>({indexers:[],cacheTTL:value})});
(async()=>{
 try {
   await act(async()=>{root=renderer.create(React.createElement(Test));await flush();});
   await act(async()=>{await state.fetchConfig();await flush();});
   await advance(0); // allow initial-load sentinel without a real wall clock
   assert.equal(state.loading,false);
   assert.equal(requests.length,0,'initial hydration must not auto-save');
   const flag=await putChange(state.setAddonEnabled,false,300);
   assert(flag,'300ms addonEnabled request missing');
   report('A4-REACT-300',true,{delayMs:300,addonEnabled:flag.body.addonEnabled},'Original hook mounted; 299ms quiet, PUT at 300ms');
   await act(async()=>{respond(flag,9000);await flush();});
   const first=await putChange(state.setCacheTTL,9300);
   assert(first,'first TTL PUT missing');
   const second=await putChange(state.setCacheTTL,9400);
   assert(second,'second TTL PUT missing');
   assert.equal(state.cacheTTL,9400);
   await act(async()=>{respond(second,9400);await flush();});
   assert.equal(state.config.cacheTTL,9400,'newer response missing');
   await act(async()=>{respond(first,9300);await flush();});
   const stale=state.config.cacheTTL!==state.cacheTTL;
   report('A4-REACT-ORDER',!stale,{localTTL:state.cacheTTL,configTTL:state.config.cacheTTL,olderResponseLast:true},stale?'Out-of-order prior success overwrote newer config state':'Late success did not overwrite newer state');
   const failing=await putChange(state.setCacheTTL,9500);
   assert(failing);
   await act(async()=>{failing.resolve({ok:false,status:500,statusText:'Synthetic Error'});await flush();});
   report('A4-REACT-500',state.cacheTTL===9500,{localTTL:state.cacheTTL,errorLogged:errors.some(x=>x.includes('HTTP 500'))},'500 leaves local edit; error logged, no automatic retry asserted');
   const rejected=await putChange(state.setCacheTTL,9600);
   assert(rejected);
   await act(async()=>{rejected.reject(new Error('synthetic transport fault'));await flush();});
   report('A4-REACT-TRANSPORT',state.cacheTTL===9600,{localTTL:state.cacheTTL,errorLogged:errors.some(x=>x.includes('synthetic transport fault'))},'Transport rejection leaves local edit; later edit required for retry');
   await act(async()=>{root.unmount();await flush();});
 }catch(e) {
   report('A4-REACT-HARNESS',false,{error:String(e),stack:String(e.stack).slice(0,1600)},'Fixture failure, not evidence of a product defect');
 }finally {
   global.setTimeout=nativeSetTimeout;global.clearTimeout=nativeClearTimeout;
   console.error=originalError;
   fs.writeFileSync(process.env.A4_UI_RESULTS,JSON.stringify({schema_version:1,gate:'A4-ISO-000',source:'actual bundled original useAppConfig.ts',cases},null,2)+'\n');
   console.log('A4 REACT SUMMARY',JSON.stringify({passed:cases.filter(x=>x.status==='pass').length,failed:cases.filter(x=>x.status==='fail').length}));
   process.exitCode=cases.some(x=>x.status==='fail')?1:0;
 }
})();
