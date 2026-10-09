/* Explicit real-browser regression; intentionally excluded from frontend*.test.cjs.
 * Requires Node 22+, an existing Chrome/Chromium and an already-running isolated
 * Cutroom server with an isolated setup project with a prepared source A.
 * Mutates only that disposable project; evidence stays local. No installations.
 * node tests/browser_camera_layout.cjs <loopback-origin> <project-id> <chrome> <output-dir>
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {spawn} = require('node:child_process');
const {setTimeout: pause} = require('node:timers/promises');
const [origin, projectId, chrome, outputArg] = process.argv.slice(2);
if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(origin || '') || !/^project_[a-zA-Z0-9_-]+$/.test(projectId || '') || !chrome || !outputArg) {
  throw new Error('Provide an isolated loopback origin, isolated project ID, existing Chrome path and output directory');
}
const output = path.resolve(outputArg);
fs.mkdirSync(output, {recursive:true});
const profile = path.join(output, `chrome-profile-${Date.now()}`);
const browser = spawn(chrome, ['--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check','--disable-background-networking','--disable-component-update','--disable-sync','--disable-default-apps','--disable-extensions','--remote-debugging-port=0',`--user-data-dir=${profile}`,'about:blank'], {windowsHide:true,stdio:['ignore','ignore','pipe']});
let stderr = ''; browser.stderr.on('data', data => stderr += data.toString());
const evidence = {origin,projectId,platform:process.platform,rows:[],screenshots:[],started:new Date().toISOString()};
class CDP {
  constructor(url) {
    this.id=0; this.pending=new Map(); this.events=[]; this.ws=new WebSocket(url);
    this.ws.addEventListener('message', event => {
      const item=JSON.parse(event.data);
      if (!item.id) { this.events.push(item); return; }
      const entry=this.pending.get(item.id); if (!entry) return;
      this.pending.delete(item.id); clearTimeout(entry.timer);
      item.error ? entry.reject(new Error(JSON.stringify(item.error))) : entry.resolve(item.result);
    });
  }
  async open() { await new Promise((resolve,reject) => {this.ws.addEventListener('open',resolve,{once:true});this.ws.addEventListener('error',reject,{once:true});}); }
  send(method,params={}) { return new Promise((resolve,reject) => {const id=++this.id;const timer=setTimeout(()=>{this.pending.delete(id);reject(new Error(`CDP timeout: ${method}`));},20000);this.pending.set(id,{resolve,reject,timer});this.ws.send(JSON.stringify({id,method,params}));}); }
  async eval(expression) {const result=await this.send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(result.exceptionDetails)throw new Error(JSON.stringify(result.exceptionDetails));return result.result.value;}
  close() {for(const entry of this.pending.values())clearTimeout(entry.timer);this.pending.clear();this.ws.close();}
}
async function wait(check,timeout=25000) {const start=Date.now();while(Date.now()-start<timeout){if(await check())return;await pause(80);}throw new Error('Timed out waiting for the actual editor');}
let cdp;
async function screenshot(name) {await cdp.send('Input.dispatchMouseEvent',{type:'mouseMoved',x:850,y:75});await pause(120);const result=await cdp.send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});const file=path.join(output,`${name}.png`);fs.writeFileSync(file,Buffer.from(result.data,'base64'));evidence.screenshots.push(file);}
async function project() {return (await (await fetch(`${origin}/api/projects/${projectId}`)).json()).project;}
// Values embedded in evaluated code are JSON literals with script-breaking characters escaped.
const UNSAFE_IN_SCRIPT = new RegExp(`[<>/${String.fromCharCode(0x2028, 0x2029)}]`, 'g');
const literal = value => JSON.stringify(value).replace(UNSAFE_IN_SCRIPT, character => String.fromCharCode(92) + 'u' + character.charCodeAt(0).toString(16).padStart(4,'0'));
async function click(selector) {await cdp.eval(`document.querySelector(${literal(selector)}).click()`);}
async function pointerClick(selector) {
 await cdp.eval(`document.querySelector(${literal(selector)}).scrollIntoView({block:'center',inline:'nearest',behavior:'instant'})`);await pause(80);
 const point=await cdp.eval(`(()=>{const e=document.querySelector(${literal(selector)});e.scrollIntoView({block:'center',inline:'nearest'});const r=e.getBoundingClientRect();const x=r.x+r.width/2,y=r.y+r.height/2;const hit=document.elementFromPoint(x,y);return {x,y,visible:r.width>0&&r.height>0,reachable:hit===e||e.contains(hit),hit:hit?.id||hit?.className};})()`);
 assert.ok(point.visible&&point.reachable,`${selector} must be reachable: ${JSON.stringify(point)}`);
 await cdp.send('Input.dispatchMouseEvent',{type:'mousePressed',x:point.x,y:point.y,button:'left',clickCount:1});
 await cdp.send('Input.dispatchMouseEvent',{type:'mouseReleased',x:point.x,y:point.y,button:'left',clickCount:1});
}
(async()=>{try{
 await wait(()=>fs.existsSync(path.join(profile,'DevToolsActivePort')));
 const port=Number(fs.readFileSync(path.join(profile,'DevToolsActivePort'),'utf8').split(/\r?\n/)[0]);
 const pages=await(await fetch('http://127.0.0.1:'+port+'/json/list')).json();cdp=new CDP(pages.find(p=>p.type==='page').webSocketDebuggerUrl);await cdp.open();
 await cdp.send('Page.enable');await cdp.send('Runtime.enable');await cdp.send('Log.enable');
 await cdp.send('Emulation.setDeviceMetricsOverride',{width:2048,height:1152,deviceScaleFactor:1,mobile:false});
 const open=async()=>{await cdp.send('Page.navigate',{url:origin});await wait(()=>cdp.eval('!!document.querySelector('+literal('[data-project-id="'+projectId+'"] [data-project-action="open"]')+')'));await click('[data-project-id="'+projectId+'"] [data-project-action="open"]');await wait(()=>cdp.eval('document.querySelector("#embeddedCameraEditor").getBoundingClientRect().width>100'));};
 await open();
 for(const w of [2048,1440,1024,900,800,699,500,430,375]) {
  await cdp.send('Emulation.setDeviceMetricsOverride',{width:w,height:900,deviceScaleFactor:1,mobile:false});
  await cdp.eval(`document.querySelector('#embeddedCameraEditor').open=false`);
  await pointerClick('#embeddedCameraEditor > summary');
  assert.equal(await cdp.eval(`document.querySelector('#embeddedCameraEditor').open`),true);
  await cdp.eval(`document.querySelector('#preciseEmbeddedPosition').open=true;document.querySelector('.embedded-content-focus').open=true`);
  const geometry=await cdp.eval(`(()=>{const p=document.querySelector('#embeddedCameraEditor').getBoundingClientRect();return {panel:p.toJSON(),document:{scroll:document.documentElement.scrollWidth,client:document.documentElement.clientWidth},controls:[...document.querySelectorAll('#embeddedCameraEditor button,#embeddedCameraEditor input,#embeddedCameraEditor output')].filter(e=>e.getClientRects().length).map(e=>({id:e.id||e.dataset.embeddedPreset,rect:e.getBoundingClientRect().toJSON()}))};})()`);
  assert.ok(geometry.document.scroll<=geometry.document.client+1,`No page overflow at ${w}`);
  for(const c of geometry.controls) assert.ok(c.rect.x>=geometry.panel.x-1&&c.rect.right<=geometry.panel.right+1,`${c.id} must stay inside camera panel at ${w}`);
  const selectors=await cdp.eval(`([...document.querySelectorAll('#embeddedCameraEditor button,#embeddedCameraEditor input')].filter(e=>e.getClientRects().length&&!e.disabled).map(e=>e.id?'#'+e.id:'[data-embedded-preset="'+e.dataset.embeddedPreset+'"]'))`);
  const targets=[];
  for(const selector of selectors){
   await cdp.eval(`document.querySelector(${literal(selector)}).scrollIntoView({block:'center',inline:'nearest',behavior:'instant'})`);await pause(80);
   targets.push(await cdp.eval(`(()=>{const e=document.querySelector(${literal(selector)});const r=e.getBoundingClientRect();const h=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);return {id:e.id||e.dataset.embeddedPreset,rect:r.toJSON(),reachable:h===e||e.contains(h),hit:h?.outerHTML?.slice(0,700)};})()`));
  }
  for(const t of targets) assert.ok(t.reachable,`${t.id} hit target occluded at ${w}: ${JSON.stringify(t)}`);
  await pointerClick('#embeddedCameraEditor > summary');assert.equal(await cdp.eval(`document.querySelector('#embeddedCameraEditor').open`),false);
  evidence.rows.push({stage:'layout',w,geometry,targets,collapsed:true});
 }
 await cdp.send('Emulation.setDeviceMetricsOverride',{width:1440,height:900,deviceScaleFactor:1,mobile:false});
 await pointerClick('#embeddedCameraEditor > summary');
 let revision=(await project()).revision;await pointerClick('[data-embedded-preset="bottom-left"]');await wait(async()=>(await project()).revision>revision);
 const saved=(await project()).manual.source_mixer;assert.ok(saved);await screenshot('camera-preset-saved');
 await open();await cdp.eval(`document.querySelector('#embeddedCameraEditor').open=true`);assert.deepEqual((await project()).manual.source_mixer,saved);
 await pointerClick('#embeddedCameraSeek');const value=await cdp.eval(`document.querySelector('#embeddedCameraSeek').value`);
 await cdp.send('Input.dispatchKeyEvent',{type:'keyDown',key:'ArrowRight',code:'ArrowRight',windowsVirtualKeyCode:39});await cdp.send('Input.dispatchKeyEvent',{type:'keyUp',key:'ArrowRight',code:'ArrowRight',windowsVirtualKeyCode:39});
 assert.notEqual(await cdp.eval(`document.querySelector('#embeddedCameraSeek').value`),value);
 evidence.rows.push({stage:'camera-function',presetSavedAndReopened:true,keyboardSeek:true,sourceMixer:saved});await screenshot('camera-reopened-keyboard-seek');
 evidence.errors=cdp.events.filter(e=>e.method==='Runtime.exceptionThrown');assert.equal(evidence.errors.length,0);evidence.status='PASS';
}catch(e){evidence.status='FAIL';evidence.failure=e.stack;process.exitCode=1;if(cdp)await screenshot('failure').catch(()=>{});}
finally{fs.writeFileSync(path.join(output,'camera-regression.json'),JSON.stringify(evidence,null,2));if(cdp){try{await cdp.send('Browser.close');}catch{}cdp.close();}if(browser.exitCode===null)browser.kill();}
console.log(JSON.stringify({status:evidence.status,failure:evidence.failure,rows:evidence.rows.map(r=>({stage:r.stage,w:r.w,presetSavedAndReopened:r.presetSavedAndReopened,keyboardSeek:r.keyboardSeek})),output},null,2));})();
