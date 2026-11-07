#!/usr/bin/env node
'use strict';
// Source-only AST analyzer: parses original files, never imports or starts app.
const fs=require('fs'),path=require('path'),cp=require('child_process'),crypto=require('crypto');
const ROOT=path.resolve(__dirname,'../..'),OUT=path.resolve(process.argv[2]||'/tmp/kaijuflow-a3-ast');
const ts=require(path.join(ROOT,'ui/node_modules/typescript'));
const BASE='c83a3c733b6394eb140a1c0a1dc500010a9f22e5';
function git(...args){return cp.execFileSync('git',['-C',ROOT,...args],{encoding:'utf8'}).trim()}
git('cat-file','-e',BASE+'^{commit}');
const changed=git('diff','--name-only',BASE,'HEAD','--','src','ui/src').split('\n').filter(Boolean);
if(changed.length)throw Error('Original source was modified: '+changed.join(','));
function files(dir){return fs.readdirSync(path.join(ROOT,dir),{withFileTypes:true}).flatMap(e=>e.isDirectory()?files(path.join(dir,e.name)):/\.tsx?$/.test(e.name)&&!e.name.endsWith('.d.ts')?[path.join(dir,e.name).replace(/\\/g,'/')]:[]).sort()}
const uifiles=files('ui/src'),serverfiles=files('src');
const rows={files:[],functions:[],jsx:[],calls:[],effects:[],network:[],routes:[],mounts:[],sdk:[],writes:[],parseErrors:[]};
const add=(name,v)=>rows[name].push(v);
const print=n=>n?n.getText(n.getSourceFile()).replace(/\s+/g,' ').slice(0,210):'';
const literal=n=>n&&(ts.isStringLiteral(n)||ts.isNoSubstitutionTemplateLiteral(n))?n.text:null;
const methods=new Set(['get','post','put','patch','delete','head','options','all']);
const writes=new Set(['writeFile','writeFileSync','appendFile','appendFileSync','unlink','unlinkSync','rm','rmSync','rmdir','rmdirSync','rename','renameSync','mkdir','mkdirSync','saveConfig','saveToDisk','persist','flush']);
const genericWrites=new Set(['save','delete','del','clear','update','insert','commit','run','exec','set']);
function owner(n){for(let x=n;x;x=x.parent){if(ts.isFunctionDeclaration(x)&&x.name)return x.name.text;if(ts.isMethodDeclaration(x))return print(x.name);if((ts.isArrowFunction(x)||ts.isFunctionExpression(x))&&x.parent){let p=x.parent;if(ts.isVariableDeclaration(p))return print(p.name);if(ts.isPropertyAssignment(p))return print(p.name);if(ts.isCallExpression(p)&&ts.isVariableDeclaration(p.parent))return print(p.parent.name);if(ts.isJsxExpression(p)&&ts.isJsxAttribute(p.parent))return 'inline@'+print(p.parent.name)}}return '<module>'}
function method(arg){if(arg&&ts.isObjectLiteralExpression(arg))for(const p of arg.properties)if(ts.isPropertyAssignment(p)&&print(p.name).replace(/['"]/g,'')==='method')return literal(p.initializer)||print(p.initializer);return 'GET(default)'}
for(const file of [...uifiles,...serverfiles]){
 const isUI=file.startsWith('ui/');
 const code=fs.readFileSync(path.join(ROOT,file),'utf8');
 const sf=ts.createSourceFile(file,code,ts.ScriptTarget.Latest,true,file.endsWith('.tsx')?ts.ScriptKind.TSX:ts.ScriptKind.TS);
 const line=n=>sf.getLineAndCharacterOfPosition(n.getStart(sf)).line+1;
 const base=n=>({file,line:line(n),owner:owner(n)});
 if(sf.parseDiagnostics.length)add('parseErrors',{file,count:sf.parseDiagnostics.length});
 if(isUI)add('files',{file,lines:code.split('\n').length,sha256:crypto.createHash('sha256').update(code).digest('hex')});
 function visit(n){
  if(isUI&&ts.isFunctionDeclaration(n)&&n.name)add('functions',{...base(n),name:n.name.text,kind:'declaration'});
  if(isUI&&ts.isVariableDeclaration(n)&&n.initializer){let i=n.initializer;if(ts.isArrowFunction(i)||ts.isFunctionExpression(i)||ts.isCallExpression(i)&&/^(useCallback|useMemo)$/.test(print(i.expression)))add('functions',{...base(n),name:print(n.name),kind:ts.isCallExpression(i)?'hook-wrapped':'function-expression'})}
  if(isUI&&ts.isJsxAttribute(n)&&/^on[A-Z]/.test(print(n.name))){const x=n.initializer&&ts.isJsxExpression(n.initializer)?n.initializer.expression:n.initializer;add('jsx',{...base(n),tag:n.parent&&n.parent.parent&&n.parent.parent.tagName?print(n.parent.parent.tagName):'<unknown>',event:print(n.name),target:print(x),inline:!!x&&(ts.isArrowFunction(x)||ts.isFunctionExpression(x))})}
  if(ts.isCallExpression(n)){
   const c=print(n.expression);
   if(isUI){
    if(['apiFetch','fetch','window.fetch'].includes(c)){const p=n.arguments[0];add('network',{...base(n),kind:'http',callee:c,path:literal(p)||print(p),literal:literal(p)!==null,method:method(n.arguments[1])})}
    if(['useEffect','useLayoutEffect'].includes(c))add('effects',{...base(n),callback:print(n.arguments[0]),deps:print(n.arguments[1])});
    if(/(?:^|\.)localStorage\.(?:setItem|removeItem|clear)$/.test(c)||/(?:^|\.)sessionStorage\.(?:setItem|removeItem|clear)$/.test(c))add('writes',{...base(n),kind:'browser-storage',callee:c});
    if(!['apiFetch','fetch','window.fetch'].includes(c))add('calls',{...base(n),callee:c,firstArg:print(n.arguments[0])});
   }else{
    if(ts.isPropertyAccessExpression(n.expression)){
     const recv=print(n.expression.expression),m=n.expression.name.text;
     if(methods.has(m)&&/^(app|router|[A-Za-z_]*Router)$/.test(recv)&&literal(n.arguments[0])!==null)add('routes',{...base(n),receiver:recv,method:m.toUpperCase(),path:literal(n.arguments[0]),handlers:n.arguments.slice(1).map(print)});
     if(m==='use'&&/^(app|router|[A-Za-z_]*Router)$/.test(recv))add('mounts',{...base(n),receiver:recv,args:n.arguments.map(print)});
     if(writes.has(m)||genericWrites.has(m)&&/(?:db|database|cache|store|config|settings)/i.test(recv))add('writes',{...base(n),kind:writes.has(m)?'operation-name':'heuristic',callee:c,expression:print(n)});
    }
    if(c==='getRouter'||/^builder\.define\w+Handler$/.test(c))add('sdk',{...base(n),callee:c,args:n.arguments.map(print)});
   }
  }
  if(isUI&&ts.isNewExpression(n)&&['EventSource','WebSocket','XMLHttpRequest'].includes(print(n.expression))){const p=n.arguments?.[0];add('network',{...base(n),kind:print(n.expression),callee:'new '+print(n.expression),path:literal(p)||print(p),literal:literal(p)!==null,method:'GET-or-protocol'})}
  ts.forEachChild(n,visit);
 }
 visit(sf);
}
const summary={baseline:BASE,typescriptVersion:ts.version,uiFiles:uifiles.length,backendFiles:serverfiles.length,uiFunctions:rows.functions.length,jsxEventBindings:rows.jsx.length,jsxInlineHandlers:rows.jsx.filter(x=>x.inline).length,uiCallSites:rows.calls.length,uiNetworkSites:rows.network.length,dynamicNetworkSites:rows.network.filter(x=>!x.literal).length,hookEffects:rows.effects.length,backendDeclaredRoutes:rows.routes.length,backendMounts:rows.mounts.length,sdkReferences:rows.sdk.length,writeCandidates:rows.writes.length,parseErrors:rows.parseErrors.length,modifiedSourcePaths:changed};
fs.mkdirSync(OUT,{recursive:true});
fs.writeFileSync(path.join(OUT,'ast-edges.json'),JSON.stringify({summary,rows},null,2)+'\n');
const T=String.fromCharCode(96);
const md=['# A3-ROUTE-002 — TypeScript AST extraction','',
 'Immutable source '+T+BASE+T+'. TypeScript '+ts.version+'. Source AST only: not runtime or complete semantic symbol resolution.','',
 '## Counts',''];
for(const [key,val] of Object.entries(summary))if(typeof val==='number')md.push('- '+key+': '+val);
md.push('','## UI network calls','','| Source | Owner | Method | Path expression | Static URL |','| --- | --- | --- | --- | --- |');
for(const x of rows.network)md.push('| '+T+x.file+':'+x.line+T+' | '+x.owner+' | '+x.method+' | '+T+String(x.path).replace(/\|/g,'\\|')+T+' | '+(x.literal?'yes':'no')+' |');
md.push('','## Explicit backend route declarations','','| Source | Method | Path |','| --- | --- | --- |');
for(const x of rows.routes)md.push('| '+T+x.file+':'+x.line+T+' | '+x.method+' | '+T+x.path+T+' |');
md.push('','## SDK and mounted routers');
for(const x of rows.sdk)md.push('- '+x.file+':'+x.line+' '+x.callee);
for(const x of rows.mounts)md.push('- '+x.file+':'+x.line+' '+x.receiver+'.use('+x.args.join(', ').slice(0,140)+')');
md.push('','## Mutation candidates');
for(const x of rows.writes)md.push('- '+x.file+':'+x.line+' '+x.kind+': '+x.callee);
md.push('','## Limitations','- JSX prop aliasing, dynamic URLs, cross-module symbol references, dependencies, and persistent store targets require additional resolution.','- SDK-generated Stremio routes are not explicitly declared in app AST.','- Heuristic mutation methods are candidates, not proven durable sinks.','- No application, credentials, NNTP, NzbDAV, or production access.');
fs.writeFileSync(path.join(OUT,'AST_SUMMARY.md'),md.join('\n')+'\n');
console.log('KAJUIFLOW_AST_SUMMARY '+JSON.stringify(summary));
rows.network.forEach(x=>console.log('AST_NETWORK '+JSON.stringify(x)));
console.log('KAJUIFLOW_AST_WRITTEN '+OUT);
