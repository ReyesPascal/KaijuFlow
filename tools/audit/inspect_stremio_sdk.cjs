#!/usr/bin/env node
'use strict';
// Bounded read-only SDK route inspection. NEVER imports SDK or runs the server.
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const ROOT=path.resolve(__dirname,'../..');
const sdk=path.join(ROOT,'node_modules','stremio-addon-sdk');
const ts=require(path.join(ROOT,'ui','node_modules','typescript'));
const out=path.resolve(process.argv[2]||'/tmp/kf-stremio-sdk');
const pkg=JSON.parse(fs.readFileSync(path.join(sdk,'package.json'),'utf8'));
if(pkg.version!=='1.6.10')throw Error('Locked SDK expected 1.6.10, found '+pkg.version);
const relevant=['get','post','put','patch','head','options','delete','all','use','route'];
const rows={sdkFiles:[],routerDeclarations:[],getRouterFunctions:[],resourceDispatch:[],errors:[]};
function walk(d){return fs.readdirSync(d,{withFileTypes:true}).flatMap(e=>e.isDirectory()?e.name==='node_modules'?[]:walk(path.join(d,e.name)):/\.m?js$/.test(e.name)?[path.join(d,e.name)]:[])}
for(const file of walk(sdk)){
 const rel=path.relative(sdk,file).replace(/\\/g,'/');
 const content=fs.readFileSync(file,'utf8');
 const sf=ts.createSourceFile(rel,content,ts.ScriptTarget.Latest,true,ts.ScriptKind.JS);
 const line=n=>sf.getLineAndCharacterOfPosition(n.getStart(sf)).line+1;
 const code=n=>n.getText(sf).replace(/\s+/g,' ').slice(0,240);
 const label=n=>({file:rel,line:line(n)});
 rows.sdkFiles.push({...label(sf),sha256:crypto.createHash('sha256').update(content).digest('hex')});
 if(sf.parseDiagnostics.length)rows.errors.push({...label(sf),parseErrors:sf.parseDiagnostics.length});
 function visit(n) {
  if(ts.isCallExpression(n)){
   const callee=code(n.expression),a=n.arguments[0];
   if(ts.isPropertyAccessExpression(n.expression) && relevant.includes(n.expression.name.text)){
    const receiver=code(n.expression.expression),m=n.expression.name.text;
    if(/route|router|app|express|server/i.test(receiver)||m==='route')
     rows.routerDeclarations.push({...label(n),method:m,receiver,pattern:a?code(a):'',staticPath:!!a&&ts.isStringLiteral(a)?a.text:null,expression:code(n).slice(0,260)});
   }
   if(/(\.get|\.defineStreamHandler|\.getInterface)$/.test(callee)||/resource|manifest|stream/i.test(callee))
    rows.resourceDispatch.push({...label(n),callee,arg:a?code(a):'',expression:code(n).slice(0,220)});
  }
  if(ts.isFunctionDeclaration(n) && /getRouter/i.test(n.name?.text||''))rows.getRouterFunctions.push({...label(n),kind:'function',expression:code(n).slice(0,220)});
  if(ts.isVariableDeclaration(n) && /getRouter/i.test(code(n.name)))rows.getRouterFunctions.push({...label(n),kind:'variable',expression:code(n).slice(0,220)});
  ts.forEachChild(n,visit);
 }
 visit(sf);
}
fs.mkdirSync(out,{recursive:true});
const result={package:pkg.name,version:pkg.version,typescriptParser:ts.version,rootManifestVersion:'1.6.10',summary:{files:rows.sdkFiles.length,routerDeclarations:rows.routerDeclarations.length,getRouterReferences:rows.getRouterFunctions.length,resourceDispatchCandidates:rows.resourceDispatch.length,parseErrors:rows.errors.length},rows};
fs.writeFileSync(path.join(out,'sdk-routes.json'),JSON.stringify(result,null,2)+'\n');
console.log('SDK_ROUTE_SUMMARY '+JSON.stringify(result.summary));
for(const x of rows.routerDeclarations)console.log('SDK_ROUTE '+JSON.stringify(x));
for(const x of rows.getRouterFunctions)console.log('SDK_GETROUTER '+JSON.stringify(x));
for(const x of rows.errors)console.log('SDK_PARSE_ERROR '+JSON.stringify(x));
