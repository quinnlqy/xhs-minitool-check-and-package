// Run against a fresh ZIP extraction. Requires the TARGET project's Playwright.
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import crypto from 'node:crypto';
import {createRequire} from 'node:module';
import {parseArgs} from 'node:util';
import assert from 'node:assert/strict';

const {values:a}=parseArgs({options:{root:{type:'string'},project:{type:'string'},config:{type:'string'},out:{type:'string'},channel:{type:'string'},'package-report':{type:'string'},zip:{type:'string'}}});
for(const key of ['root','project','config','out'])if(!a[key])throw Error('--'+key+' required');
const root=fs.realpathSync(a.root),out=path.resolve(a.out),config=JSON.parse(fs.readFileSync(a.config,'utf8').replace(/^\uFEFF/,''));
if(out===root||out.startsWith(root+path.sep))throw Error('Evidence directory must be outside extracted package');
if(fs.existsSync(out))throw Error('Use a new evidence directory');
const hash=file=>crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
let artifactBinding={verified:false,reason:'Directory-only run; no package report supplied'};
if(a.zip&&!a['package-report'])throw Error('--zip requires --package-report');
if(a['package-report']){
 const metadataPath=path.resolve(a['package-report']);
 const metadata=JSON.parse(fs.readFileSync(metadataPath,'utf8').replace(/^\uFEFF/,''));
 assert.ok(Array.isArray(metadata.files)&&metadata.files.length,'Package fingerprint: missing file manifest');
 const zip=path.resolve(a.zip||metadata.zip),sha256=metadata.zipSha256||metadata.sha256;
 assert.match(sha256||'',/^[a-f0-9]{64}$/i,'Package fingerprint: invalid ZIP hash');
 assert.equal(hash(zip),sha256,'Package fingerprint: ZIP hash mismatch');
 const expected=[];
 for(const entry of metadata.files){
  assert.equal(typeof entry.path,'string','Package fingerprint: invalid path');
  assert.ok(!entry.path.includes('\\')&&!entry.path.startsWith('/')&&!entry.path.split('/').includes('..'),'Package fingerprint: unsafe path');
  const file=path.resolve(root,entry.path);
  assert.ok(file.startsWith(root+path.sep),'Package fingerprint: path outside root');
  assert.equal(hash(file),entry.sha256,'Package fingerprint: extracted file changed: '+entry.path);
  expected.push(entry.path);
 }
 assert.equal(new Set(expected).size,expected.length,'Package fingerprint: duplicate paths');
 function list(folder){return fs.readdirSync(folder,{withFileTypes:true}).flatMap(entry=>{
  const file=path.join(folder,entry.name),real=fs.realpathSync(file);
  assert.ok(!entry.isSymbolicLink()&&real===file,'Package fingerprint: symlink/junction');
  return entry.isDirectory()?list(file):[path.relative(root,file).split(path.sep).join('/')];
 });}
 assert.deepEqual(list(root).sort(),expected.sort(),'Package fingerprint: missing/extra files');
 artifactBinding={verified:true,packageReport:metadataPath,zip,sha256,files:expected.length};
}
const require=createRequire(path.join(path.resolve(a.project),'package.json'));
let chromium;
try{({chromium}=require('@playwright/test'));}catch{({chromium}=require('playwright'));}
const ready=config.ready;
if(!ready||['body','html','*'].includes(ready.trim()))throw Error('Configure a real application ready selector');
const scenarios=config.scenarios||[{name:'normal'},{name:'cssom-unreadable',inject:'cssom'},{name:'crypto-unavailable',inject:'crypto'}];
const views=config.viewports||[{width:390,height:844},{width:360,height:640},{width:844,height:390}];
assert.ok(scenarios.length&&views.length,'Need at least one scenario and viewport');
const prefix='/nested/tool/';
const mime={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.svg':'image/svg+xml','.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.webp':'image/webp','.gif':'image/gif','.woff':'font/woff','.woff2':'font/woff2','.json':'application/json'};
const csp="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; media-src 'none'; connect-src 'none'; frame-src 'none'; worker-src 'none'; object-src 'none'";
const served=new Map();
const server=http.createServer((req,res)=>{
  let url;
  try{url=decodeURIComponent(new URL(req.url,'http://localhost').pathname);}catch{res.writeHead(400).end();return;}
  if(!url.startsWith(prefix)){res.writeHead(404).end();return;}
  const file=path.resolve(root,url.slice(prefix.length)+(url.endsWith('/')?'index.html':''));
  if(!file.startsWith(root+path.sep)||!fs.existsSync(file)||!fs.statSync(file).isFile()){res.writeHead(404).end();return;}
  const real=fs.realpathSync(file);
  if(!real.startsWith(root+path.sep)){res.writeHead(403).end();return;}
  const bytes=fs.readFileSync(real);
  served.set(path.relative(root,real).split(path.sep).join('/'),crypto.createHash('sha256').update(bytes).digest('hex'));
  res.writeHead(200,{'Content-Type':mime[path.extname(real)]||'application/octet-stream','Content-Security-Policy':csp,'Cache-Control':'no-store'}).end(bytes);
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const origin='http://127.0.0.1:'+server.address().port;
const report={scope:'Local browser emulation on extracted files; NOT XHS simulator/device/review acceptance',root,prefix,csp,artifactBinding,scenarios:[]};
fs.mkdirSync(out,{recursive:true});
let browser;
try{
 browser=await chromium.launch({headless:true,...(a.channel?{channel:a.channel}:{})});
 for(const [si,s] of scenarios.entries())for(const [vi,v] of views.entries()){
  const result={name:s.name,viewport:v,passed:false,errors:[],pageErrors:[],failedRequests:[],badResponses:[],externalRequests:[],consoleErrors:[]};
  report.scenarios.push(result);
  const context=await browser.newContext({viewport:{width:v.width,height:v.height},hasTouch:true,isMobile:true,serviceWorkers:'block'});
  const p=await context.newPage();p.setDefaultTimeout(config.timeoutMs||15000);
  try{
   p.on('pageerror',e=>result.pageErrors.push(e.message));
   p.on('console',m=>{if(m.type()==='error')result.consoleErrors.push(m.text());});
   p.on('requestfailed',r=>result.failedRequests.push({url:r.url(),error:r.failure()?.errorText}));
   p.on('response',r=>{if(r.status()>=400)result.badResponses.push({url:r.url(),status:r.status()});});
   await p.route('**/*',async route=>{
    const req=route.request(),url=new URL(req.url());
    if(url.protocol==='http:'||url.protocol==='https:'){
     if(url.origin!==origin){result.externalRequests.push(req.url());await route.abort();return;}
    }
    if((s.abort||[]).some(pattern=>req.url().includes(pattern))){await route.abort();return;}
    const replacement=Object.entries(s.replace||{}).find(([pattern])=>req.url().includes(pattern));
    if(replacement){await route.fulfill({contentType:'application/javascript',body:replacement[1]});return;}
    await route.continue();
   });
   await p.addInitScript(({inject,safe,nav})=>{
    window.__releaseCsp=[];
    document.addEventListener('securitypolicyviolation',e=>window.__releaseCsp.push({directive:e.effectiveDirective,blocked:e.blockedURI}));
    const modes=Array.isArray(inject)?inject:[inject];
    if(modes.includes('cssom'))Object.defineProperty(HTMLLinkElement.prototype,'sheet',{configurable:true,get(){return null;}});
    if(modes.includes('crypto'))Object.defineProperty(window,'crypto',{configurable:true,value:undefined});
    if(modes.includes('storage'))for(const key of ['localStorage','sessionStorage'])Object.defineProperty(window,key,{configurable:true,get(){throw Error('Injected storage access denial');}});
    if(modes.includes('webgl')){const original=HTMLCanvasElement.prototype.getContext;HTMLCanvasElement.prototype.getContext=function(type,...rest){return /webgl/.test(type)?null:original.call(this,type,...rest);};}
    function setSafe(){if(document.documentElement)for(const [key,value]of Object.entries(safe))document.documentElement.style.setProperty('--safe-area-inset-'+key,value+'px');}
    setSafe();document.addEventListener('readystatechange',setSafe);
    document.addEventListener('DOMContentLoaded',()=>{
     setSafe();
     for(const [i,rect]of nav.entries()){
      const el=document.createElement('button');el.className='release-native-nav';el.textContent='原生占位'+i;
      Object.assign(el.style,{position:'fixed',zIndex:'2147483647',pointerEvents:'auto',margin:'0',padding:'0',background:'#dedede',border:'1px solid #777'});
      for(const [key,value]of Object.entries(rect))el.style[key]=typeof value==='number'?value+'px':value;
      el.addEventListener('click',e=>{e.stopPropagation();});document.body.appendChild(el);
     }
    });
   },{inject:s.inject,safe:v.safeArea||{},nav:v.nativeButtons||config.nativeButtons||[]});
   await p.goto(origin+prefix,{waitUntil:'load'});
   await p.locator(s.ready||ready).waitFor({state:'visible'});
   async function visible(selector){await p.locator(selector).waitFor({state:'visible'});}
   for(const step of s.steps||config.steps||[]){
    if(step.tap){
     assert.ok(step.visible||step.hidden||step.text,'Each tap needs a resulting-state assertion');
     const target=p.locator(step.tap);await target.scrollIntoViewIfNeeded();
     const hit=await target.evaluate(el=>{
      const r=el.getBoundingClientRect(),x=r.x+r.width/2,y=r.y+r.height/2,node=document.elementFromPoint(x,y);
      const overlap=[...document.querySelectorAll('.release-native-nav')].some(n=>{const b=n.getBoundingClientRect();return r.left<b.right&&r.right>b.left&&r.top<b.bottom&&r.bottom>b.top;});
      return {own:!!node&&(el===node||el.contains(node)),overlap,hit:node?.outerHTML.slice(0,250)};
     });
     assert.ok(hit.own&&!hit.overlap,'Target blocked or overlaps native navigation: '+JSON.stringify(hit));
     await target.tap();
    }
    if(step.fill)await p.locator(step.fill.selector).fill(step.fill.value);
    if(step.reload)await p.reload({waitUntil:'load'});
    if(step.visible)await visible(step.visible);
    if(step.hidden)await p.locator(step.hidden).waitFor({state:'hidden'});
    if(step.text){await visible(step.text.selector);assert.ok((await p.locator(step.text.selector).innerText()).includes(step.text.contains),'Expected text missing');}
   }
   if(s.checkOverflow!==false)assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,'Horizontal overflow');
   result.cspViolations=await p.evaluate(()=>window.__releaseCsp);
   assert.deepEqual(result.externalRequests,[],'External requests');
   assert.deepEqual(result.badResponses,[],'Missing resources');
   assert.deepEqual(result.cspViolations,[],'CSP violations');
   const unexpected=result.pageErrors.filter(e=>!(s.expectedPageErrors||[]).some(pattern=>e.includes(pattern)));
   assert.deepEqual(unexpected,[],'Unexpected page errors');
   const failed=result.failedRequests.filter(r=>!(s.abort||[]).some(pattern=>r.url.includes(pattern)));
   assert.deepEqual(failed,[],'Unexpected failed requests');
   result.passed=true;
  }catch(e){result.errors.push(e.stack||String(e));}
  finally{await p.screenshot({path:path.join(out,si+'-'+vi+'.png'),fullPage:true}).catch(()=>{});await context.close();}
  console.log((result.passed?'PASS ':'FAIL ')+s.name+' '+v.width+'x'+v.height);
 }
}finally{
 await browser?.close();await new Promise(resolve=>server.close(resolve));
 report.servedFileSha256=Object.fromEntries(served);report.passed=report.scenarios.length>0&&report.scenarios.every(s=>s.passed);
 fs.writeFileSync(path.join(out,'report.json'),JSON.stringify(report,null,2));
}
if(!report.passed)process.exitCode=1;
