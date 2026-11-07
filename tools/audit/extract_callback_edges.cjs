#!/usr/bin/env node
'use strict';
// A3-ROUTE-003: static compiler-API cross-file callback projection.
// No imports/exec of application modules; no production I/O.
const fs=require('fs'),path=require('path'),cp=require('child_process'),crypto=require('crypto');
const ROOT=path.resolve(__dirname,'../..'), SRC=path.join(ROOT,'ui/src'), OUT=path.resolve(process.argv[2]||'/tmp/kf-callbacks');
const BASE='c83a3c733b6394eb140a1c0a1dc500010a9f22e5';
const ts=require(path.join(ROOT,'ui/node_modules/typescript'));
const git=(...a)=>cp.execFileSync('git',['-C',ROOT,...a],{encoding:'utf8'}).trim();
git('cat-file','-e',BASE+'^{commit}');
const changed=git('diff','--name-only',BASE,'HEAD','--','src','ui/src').split('\n').filter(Boolean);
if(changed.length)throw Error('Immutable original application source modified: '+changed.join(','));
const conf=ts.readConfigFile(path.join(ROOT,'ui/tsconfig.json'),ts.sys.readFile);
if(conf.error)throw Error(ts.flattenDiagnosticMessageText(conf.error.messageText,' '));
const parsed=ts.parseJsonConfigFileContent(conf.config,ts.sys,path.join(ROOT,'ui'));
const program=ts.createProgram(parsed.fileNames,parsed.options), checker=program.getTypeChecker();
const files=program.getSourceFiles().filter(sf=>sf.fileName.startsWith(SRC+path.sep)&&/\.tsx?$/.test(sf.fileName)&&!sf.isDeclarationFile);
const errors=files.flatMap(sf=>sf.parseDiagnostics.map(d=>({file:sf.fileName,code:d.code})));
const visit=(n,f)=>{f(n);ts.forEachChild(n,x=>visit(x,f));};
const repr=n=>n?n.getText(n.getSourceFile()).replace(/\s+/g,' ').slice(0,180):'';
const loc=n=>path.relative(ROOT,n.getSourceFile().fileName).replace(/\\/g,'/')+':'+(n.getSourceFile().getLineAndCharacterOfPosition(n.getStart()).line+1);
const fn=n=>{
 if(ts.isFunctionDeclaration(n)||ts.isArrowFunction(n)||ts.isFunctionExpression(n))return n;
 if(ts.isVariableDeclaration(n)&&n.initializer){
  if(ts.isArrowFunction(n.initializer)||ts.isFunctionExpression(n.initializer))return n.initializer;
  if(ts.isCallExpression(n.initializer))for(const a of n.initializer.arguments)if(ts.isArrowFunction(a)||ts.isFunctionExpression(a))return a;
 }
 return null;
};
const symbols=new Map(), byName=new Map();
for(const sf of files)visit(sf,n=>{
 if(!(ts.isFunctionDeclaration(n)&&n.name||ts.isVariableDeclaration(n)&&ts.isIdentifier(n.name)))return;
 const body=fn(n);if(!body)return;
 const name=repr(n.name),d={name,body,location:loc(n)};
 const arr=byName.get(name)||[];arr.push(d);byName.set(name,arr);
 const sym=checker.getSymbolAtLocation(n.name);if(sym)symbols.set(sym,d);
});
function decl(expr){
 let sym=checker.getSymbolAtLocation(expr);
 if(sym&&sym.flags&ts.SymbolFlags.Alias){try{sym=checker.getAliasedSymbol(sym);}catch{}}
 if(sym&&symbols.has(sym))return symbols.get(sym);
 if(sym)for(const n of sym.declarations||[]){const body=fn(n);if(body)return {name:repr(expr),body,location:loc(n)};}
 const matches=byName.get(repr(expr));return matches&&matches.length===1?matches[0]:null;
}
function bindProps(d){
 const map=new Map(),param=d&&d.body.parameters&&d.body.parameters[0];
 if(param&&ts.isObjectBindingPattern(param.name))for(const e of param.name.elements){
  if(ts.isIdentifier(e.name))map.set(e.propertyName?repr(e.propertyName):e.name.text,e.name.text);
 }
 return map;
}
function uses(body,name){
 const r={calls:0,eventRefs:0,forwarded:0};
 visit(body,n=>{
  if(ts.isCallExpression(n)&&ts.isIdentifier(n.expression)&&n.expression.text===name)r.calls++;
  if(ts.isJsxAttribute(n)&&n.initializer&&ts.isJsxExpression(n.initializer)&&n.initializer.expression&&ts.isIdentifier(n.initializer.expression)&&n.initializer.expression.text===name){
   if(/^on[A-Z]/.test(repr(n.name)))r.eventRefs++;else r.forwarded++;
  }
 });
 return r;
}
function owner(n){for(let p=n.parent;p;p=p.parent){
 if(ts.isFunctionDeclaration(p)&&p.name)return p.name.text;
 if((ts.isArrowFunction(p)||ts.isFunctionExpression(p))&&ts.isVariableDeclaration(p.parent))return repr(p.parent.name);
 }return '<inline/module>';}
function returns(d){
 const result=new Map();if(!d)return result;
 visit(d.body,n=>{if(ts.isReturnStatement(n)&&n.expression&&ts.isObjectLiteralExpression(n.expression))for(const p of n.expression.properties){
  if(ts.isShorthandPropertyAssignment(p))result.set(repr(p.name),{source:repr(p.name),at:loc(p)});
  else if(ts.isPropertyAssignment(p))result.set(repr(p.name),{source:repr(p.initializer),at:loc(p)});
 }});return result;
}
const hooks=new Map();
for(const sf of files)visit(sf,n=>{
 if(!ts.isVariableDeclaration(n)||!ts.isIdentifier(n.name)||!n.initializer||!ts.isCallExpression(n.initializer))return;
 const d=decl(n.initializer.expression);
 if(d&&/^use[A-Z]/.test(d.name))hooks.set(sf.fileName+'#'+n.name.text,{definition:d.location,fields:returns(d)});
});
function origin(expr,sf){
 if(ts.isPropertyAccessExpression(expr)&&ts.isIdentifier(expr.expression)){
  const h=hooks.get(sf.fileName+'#'+expr.expression.text);
  if(h)return {kind:'hook-return',hook:h.definition,field:expr.name.text,source:h.fields.get(expr.name.text)||null};
 }
 const d=decl(expr);if(d)return {kind:'symbol',source:d.location};
 if(ts.isArrowFunction(expr)||ts.isFunctionExpression(expr))return {kind:'inline',source:loc(expr)};
 return {kind:'unresolved-expression'};
}
const edges=[],unresolvedComponents=new Set();
for(const sf of files)visit(sf,n=>{
 if(!ts.isJsxOpeningElement(n)&&!ts.isJsxSelfClosingElement(n))return;
 const childName=repr(n.tagName);if(!/^[A-Z]/.test(childName))return;
 const child=decl(n.tagName),props=bindProps(child);
 if(!child)unresolvedComponents.add(childName+' at '+loc(n));
 for(const a of n.attributes.properties){
  if(!ts.isJsxAttribute(a)||!a.initializer||!ts.isJsxExpression(a.initializer)||!a.initializer.expression)continue;
  const expr=a.initializer.expression, prop=repr(a.name);
  let callable=false;try{callable=checker.getTypeAtLocation(expr).getCallSignatures().length>0;}catch{}
  if(!callable&&!/^(apiFetch|on[A-Z]|set[A-Z]|handle[A-Z]|fetch[A-Z]|save[A-Z]|update[A-Z]|delete[A-Z]|check[A-Z]|send[A-Z])/.test(prop))continue;
  const binding=props.get(prop)||null;
  edges.push({at:loc(a),parent:owner(n),child:childName,childDefinition:child?child.location:null,prop,expression:repr(expr),callable,childBinding:binding,childUses:child&&binding?uses(child.body,binding):null,origin:origin(expr,sf),certainty:child&&binding?'syntactic-prop-binding':'unresolved'});
 }
});
const dynamic=[];
function pathTemplate(a){return ts.isTemplateExpression(a)?a.head.text+a.templateSpans.map(s=>'{'+repr(s.expression)+'}'+s.literal.text).join(''):repr(a);}
for(const sf of files)visit(sf,n=>{
 if(!ts.isCallExpression(n)&&!ts.isNewExpression(n))return;
 if(!['apiFetch','fetch','window.fetch','EventSource'].includes(repr(n.expression)))return;
 const a=n.arguments&&n.arguments[0];if(!a)return;
 if(!ts.isStringLiteral(a)&&!ts.isNoSubstitutionTemplateLiteral(a))dynamic.push({at:loc(n),owner:owner(n),urlExpression:pathTemplate(a),kind:'unevaluated-source-expression'});
});
const summary={sourceCommit:BASE,typescript:ts.version,uiFiles:files.length,parseErrors:errors.length,modifiedSourceFiles:changed.length,definedFunctions:[...byName.values()].reduce((n,a)=>n+a.length,0),hookBindings:hooks.size,callbackPropAssignments:edges.length,resolvedPropBindings:edges.filter(x=>x.certainty==='syntactic-prop-binding').length,hookReturnOrigins:edges.filter(x=>x.origin.kind==='hook-return').length,callableChildBindings:edges.filter(x=>x.childUses&&x.childUses.calls>0).length,forwardedOrEventChildBindings:edges.filter(x=>x.childUses&&(x.childUses.forwarded||x.childUses.eventRefs)).length,unresolvedPropBindings:edges.filter(x=>x.certainty==='unresolved').length,unresolvedComponents:unresolvedComponents.size,dynamicNetworkExpressions:dynamic.length};
fs.mkdirSync(OUT,{recursive:true});
const json=JSON.stringify({summary,edges,dynamic,unresolvedComponents:[...unresolvedComponents].sort(),errors},null,2)+'\n';
fs.writeFileSync(path.join(OUT,'callback-edges.json'),json);
const focus=/ProviderManager|HealthChecksOverlay|UltimateFallbackOverlay|StreamingOverlay|IndexManagerOverlay|InstallTab|AuthScreens|NzbDatabaseOverlay/;
const selected=edges.filter(x=>focus.test(x.child)||focus.test(x.parent));
const md=['# A3-ROUTE-003 — source-only typed callback projection','','Immutable source '+BASE+', TypeScript '+ts.version+'. No transitive runtime-reachability claim.','','## Counts','',...Object.entries(summary).map(([k,v])=>'- '+k+': '+v),'','## Selected cross-file JSX prop edges','',...selected.slice(0,150).map(x=>'- '+x.at+' '+x.parent+' -> '+x.child+' ('+x.childDefinition+').'+x.prop+' = '+x.expression+'; child '+JSON.stringify(x.childUses)+'; origin '+JSON.stringify(x.origin)),'','## Dynamic network URL expressions','',...dynamic.map(x=>'- '+x.at+' '+x.owner+': '+x.urlExpression),'','## Scope / uncertainty','- Uses TypeScript symbols for imported component declarations, hook function returns and direct prop bindings. Child uses are syntactic; no full closure, alias, state or runtime route resolution.','- Do not infer 603 complete event-to-network chains from prior AST enumeration.','- No source edit, app boot, production network, or live credentials.'];
fs.writeFileSync(path.join(OUT,'CALLBACK_SUMMARY.md'),md.join('\n')+'\n');
console.log(JSON.stringify(summary));
console.log('callback JSON SHA-256 '+crypto.createHash('sha256').update(json).digest('hex'));
for(const x of selected.slice(0,8))console.log(x.at+' '+x.child+'.'+x.prop+' <- '+x.expression+' ['+x.certainty+']');
if(errors.length)process.exitCode=2;
