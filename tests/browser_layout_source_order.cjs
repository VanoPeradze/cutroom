/* Focused real-browser regression. Uses disposable projects on a running isolated
 * server; fresh fixtures need a ready source A, manual workflow and no draft.
 * node tests/browser_layout_source_order.cjs <loopback-origin> <fixtures.json> <chrome> <output>
 * Fixtures: [{id:'project_...', direction:'ltr'|'rtl', phase:'fresh'|'drafted'}].
 * RTL emulates direction with Hebrew project names; the shipped editor is English-only.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {spawn} = require('node:child_process');
const {setTimeout:pause} = require('node:timers/promises');
const [origin, fixturesFile, chrome, outputArg] = process.argv.slice(2);
assert.match(origin || '', /^http:\/\/127\.0\.0\.1:\d+$/);
const fixtures = JSON.parse(fs.readFileSync(fixturesFile, 'utf8'));
const output = path.resolve(outputArg); fs.mkdirSync(output, {recursive:true});
const profile = path.join(output, 'chrome-' + Date.now());
const browser = spawn(chrome, ['--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check','--disable-background-networking','--disable-component-update','--disable-sync','--disable-extensions','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'], {windowsHide:true,stdio:['ignore','ignore','pipe']});
let cdp, stderr = ''; browser.stderr.on('data', data => stderr += data);
const report = {rows:[], localeCoverage:'English UI; Hebrew project names with emulated RTL. No translated Hebrew editor exists.'};
async function wait(check) {
  const start = Date.now();
  while (Date.now()-start < 25000) {
    try { if (await check()) return; } catch (error) { if (!/context|object.*id|Cannot find/i.test(error.message)) throw error; }
    await pause(80);
  }
  throw Error('Timed out waiting for Layout workflow');
}
class CDP {
  constructor(url) {
    this.id=0; this.pending=new Map(); this.events=[]; this.ws=new WebSocket(url);
    this.ws.onmessage=e=>{const v=JSON.parse(e.data);if(!v.id){this.events.push(v);return;}const p=this.pending.get(v.id);if(!p)return;this.pending.delete(v.id);v.error?p.reject(Error(JSON.stringify(v.error))):p.resolve(v.result);};
  }
  open() {return new Promise((resolve,reject)=>{this.ws.onopen=resolve;this.ws.onerror=reject;});}
  send(method,params={}) {return new Promise((resolve,reject)=>{const id=++this.id;this.pending.set(id,{resolve,reject});this.ws.send(JSON.stringify({id,method,params}));});}
  async call(fn,...args) {
    const root=await this.send('Runtime.evaluate',{expression:'globalThis'});
    try {const result=await this.send('Runtime.callFunctionOn',{objectId:root.result.objectId,functionDeclaration:fn.toString(),arguments:args.map(value=>({value})),returnByValue:true,awaitPromise:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value;}
    finally {await this.send('Runtime.releaseObject',{objectId:root.result.objectId}).catch(()=>{});}
  }
}
const click = id => cdp.call(id=>document.getElementById(id).click(), id);
async function project(id) {const response=await fetch(origin+'/api/projects/'+encodeURIComponent(id));assert.equal(response.status,200);return (await response.json()).project;}
async function open(row) {
  await wait(()=>cdp.call(id=>!!document.querySelector('[data-project-id="'+CSS.escape(id)+'"] [data-project-action="open"]'),row.id));
  await cdp.call(id=>document.querySelector('[data-project-id="'+CSS.escape(id)+'"] [data-project-action="open"]').click(),row.id);
  await wait(()=>cdp.call(()=>!document.body.classList.contains('welcome-mode')));
  await cdp.call(direction=>{document.documentElement.dir=direction;document.documentElement.lang=direction==='rtl'?'he':'en';},row.direction);
}
async function screenshot(name) {const shot=await cdp.send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});fs.writeFileSync(path.join(output,name+'.png'),Buffer.from(shot.data,'base64'));}
async function checkLayout(row, stage) {
  await wait(()=>cdp.call(()=>!document.getElementById('advancedButton').disabled));
  await cdp.call(()=>{if(document.getElementById('advancedPanel').hidden)document.getElementById('advancedButton').click();});
  await click('studioTabFraming');
  await wait(()=>cdp.call(()=>document.querySelector('#previewStage video')?.readyState>=2));
  const geometry=await cdp.call(()=>{
    const panel=document.getElementById('studioPanelFraming'), frame=panel.querySelector('.framing-layout'), mixer=document.getElementById('sourceMixer');
    const rect=el=>{const r=el.getBoundingClientRect();return{x:r.x,y:r.y,w:r.width,h:r.height};};
    return {children:[...panel.children].map(el=>el.id||el.className), frame:rect(frame),mixer:rect(mixer),preview:rect(document.getElementById('previewStage')),timeline:rect(document.getElementById('studioTimelineDock')),inspector:rect(document.getElementById('studioInspector')),inPanel:mixer.parentElement.id==='studioShelfLayout',count:document.querySelectorAll('#sourceMixer').length,dockHidden:document.getElementById('setupSourceMixerDock').hidden,sameControls:!globalThis.originalLayoutMixer||globalThis.originalLayoutMixer===mixer,dir:document.documentElement.dir,pageWidth:document.documentElement.scrollWidth,viewport:innerWidth};
  });
  assert.ok(geometry.inPanel); assert.equal(geometry.count,1); assert.ok(geometry.dockHidden); assert.ok(geometry.sameControls);
  assert.ok(geometry.frame.h>0 && geometry.mixer.h>0);
  if(row.direction==='rtl') {
    assert.ok(geometry.mixer.x>=geometry.preview.x+geometry.preview.w,'Composition controls occupy the inline-start shelf in RTL');
    assert.ok(geometry.frame.x+geometry.frame.w<=geometry.preview.x,'Clip framing occupies the inline-end inspector in RTL');
  } else {
    assert.ok(geometry.mixer.x+geometry.mixer.w<=geometry.preview.x,'Composition controls occupy the inline-start shelf in LTR');
    assert.ok(geometry.frame.x>=geometry.preview.x+geometry.preview.w,'Clip framing occupies the inline-end inspector in LTR');
  }
  assert.equal(geometry.dir,row.direction); assert.ok(geometry.pageWidth<=geometry.viewport+1);
  assert.ok(geometry.preview.h>=300,'Retain preview-first layout'); assert.equal(geometry.timeline.w,1366); assert.ok(geometry.inspector.w<=420);
  // Disclosure controls remain interactive after their sibling is reparented.
  assert.equal(await cdp.call(()=>{const el=document.querySelector('#studioPanelFraming .framing-layout');const before=el.open;el.querySelector('summary').click();const toggled=el.open!==before;el.querySelector('summary').click();return toggled&&el.open===before;}),true);
  report.rows.push({id:row.id,direction:row.direction,stage,...geometry});
  await screenshot(row.direction+'-'+stage);
}
(async()=>{try {
  await wait(()=>fs.existsSync(path.join(profile,'DevToolsActivePort')));
  const port=Number(fs.readFileSync(path.join(profile,'DevToolsActivePort'),'utf8').split(/\r?\n/)[0]);
  const tabs=await(await fetch('http://127.0.0.1:'+port+'/json/list')).json();
  cdp=new CDP(tabs.find(tab=>tab.type==='page').webSocketDebuggerUrl);await cdp.open();
  for(const method of ['Page.enable','Runtime.enable','Log.enable','Network.enable'])await cdp.send(method);
  await cdp.send('Network.setCacheDisabled',{cacheDisabled:true});
  await cdp.send('Emulation.setDeviceMetricsOverride',{width:1366,height:768,deviceScaleFactor:1,mobile:false});
  await cdp.send('Page.navigate',{url:origin});
  for(const row of fixtures) {
    assert.match(row.id,/^project_[a-zA-Z0-9_]+$/);
    const before=await project(row.id);
    assert.equal(Boolean(before.draft),row.phase==='drafted','Use fresh isolated fixtures for each run');
    await open(row);
    if(row.phase==='fresh') {
      await wait(()=>cdp.call(()=>document.getElementById('sourceMixer').parentElement.id==='setupSourceMixerDock'&&!document.getElementById('generateButton').disabled));
      await cdp.call(()=>{globalThis.originalLayoutMixer=document.getElementById('sourceMixer');});
      await click('generateButton');
      await wait(async()=>Boolean((await project(row.id)).draft));
      await wait(()=>cdp.call(()=>document.getElementById('sourceMixer').parentElement.id==='studioShelfLayout'));
      await checkLayout(row,'fresh-to-draft');
      const drafted=await project(row.id);assert.ok(drafted.draft);assert.deepEqual(drafted.sources,before.sources);
      await click('homeButton');
      await open(row);await checkLayout(row,'reopened-draft');
      assert.deepEqual(await project(row.id),drafted,'Display and reopen must preserve the saved draft');
    } else {
      await checkLayout(row,'existing-draft');
      assert.deepEqual(await project(row.id),before,'Existing draft display must not mutate the project');
    }
    await click('homeButton');
  }
  report.errors=cdp.events.filter(e=>e.method==='Runtime.exceptionThrown'||e.method==='Log.entryAdded'&&e.params.entry.level==='error');
  assert.equal(report.errors.length,0,JSON.stringify(report.errors));report.status='PASS';
} catch(error) {report.status='FAIL';report.failure=error.stack;process.exitCode=1;if(cdp)await screenshot('failure').catch(()=>{});}
finally {fs.writeFileSync(path.join(output,'results.json'),JSON.stringify(report,null,2));if(cdp){await cdp.send('Browser.close').catch(()=>{});cdp.ws.close();}if(browser.exitCode===null)browser.kill();fs.writeFileSync(path.join(output,'browser.stderr'),stderr);}
console.log(JSON.stringify({status:report.status,failure:report.failure,rows:report.rows.length,output}));})();
