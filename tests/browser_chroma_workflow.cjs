/* Explicit real-browser regression; intentionally excluded from frontend*.test.cjs.
 * Requires Node 22+, an existing Chrome/Chromium and an already-running isolated
 * Cutroom server with an isolated authorized manual project and Media video.
 * Mutates only that disposable project; evidence stays local. No installations.
 * node tests/browser_chroma_workflow.cjs <loopback-origin> <project-id> <chrome> <output-dir>
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {spawn} = require('node:child_process');
const {setTimeout: pause} = require('node:timers/promises');
const [origin, projectId, chrome, outputArg] = process.argv.slice(2);
if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(origin || '') || !/^project_[a-zA-Z0-9_-]+$/.test(projectId || '') || !chrome || !outputArg) {
  throw new Error('Provide an isolated loopback origin, synthetic project ID, existing Chrome path and output directory');
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
async function screenshot(name) {const result=await cdp.send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});const file=path.join(output,`${name}.png`);fs.writeFileSync(file,Buffer.from(result.data,'base64'));evidence.screenshots.push(file);}
async function project() {return (await (await fetch(`${origin}/api/projects/${projectId}`)).json()).project;}
async function click(selector) {await cdp.eval(`document.querySelector(${JSON.stringify(selector)}).click()`);}
async function field(selector,value) {await cdp.eval(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});e.value=${JSON.stringify(value)};e.dispatchEvent(new Event('input',{bubbles:true}));})()`);}
async function keyedFrame() {
  return cdp.eval(`(()=>{const c=document.querySelector('.media-overlay .chroma-live:not([hidden])');if(!c)return null;const p=c.getContext('2d').getImageData(0,0,c.width,c.height).data;return{width:c.width,height:c.height,corner:[...p.slice((16*c.width+16)*4,(16*c.width+16)*4+4)],center:[...p.slice((Math.floor(c.height/2)*c.width+Math.floor(c.width/2))*4,(Math.floor(c.height/2)*c.width+Math.floor(c.width/2))*4+4)]};})()`);
}
(async()=>{
 try {
  await wait(()=>fs.existsSync(path.join(profile,'DevToolsActivePort')));
  const port=Number(fs.readFileSync(path.join(profile,'DevToolsActivePort'),'utf8').split(/\r?\n/)[0]);
  const pages=await(await fetch(`http://127.0.0.1:${port}/json/list`)).json();cdp=new CDP(pages.find(p=>p.type==='page').webSocketDebuggerUrl);await cdp.open();
  for(const method of ['Page.enable','Runtime.enable','Log.enable','Network.enable'])await cdp.send(method);
  await cdp.send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await cdp.send('Page.navigate',{url:origin});
  await wait(()=>cdp.eval(`!!document.querySelector('[data-project-id="${projectId}"] [data-project-action="open"]')`));
  await click(`[data-project-id="${projectId}"] [data-project-action="open"]`);
  await wait(()=>cdp.eval(`!document.body.classList.contains('welcome-mode')&&!document.getElementById('advancedButton').disabled`));
  await cdp.eval(`if(document.getElementById('advancedPanel').hidden)document.getElementById('advancedButton').click()`);
  await click('#studioTabFraming');
  const initial=await project();const asset=Object.values(initial.assets).find(a=>a.kind==='video');assert.ok(asset);
  await wait(()=>cdp.eval(`!!document.querySelector('[data-chroma-target="${asset.id}"]')&&!document.querySelector('[data-chroma-target="${asset.id}"]').disabled`));
  await click(`[data-chroma-target="${asset.id}"]`);
  if (initial.manual?.chroma_key?.[asset.id]?.enabled) {
    const beforeReset=initial.revision;await click('[data-chroma-reset]');
    await wait(async()=>(await project()).revision>beforeReset);await pause(200);
  }
  await field('#previewSeek','450');await pause(300);
  await screenshot('ui-before');
  await click('[data-chroma-defaults]');
  assert.equal(await cdp.eval(`document.querySelector('[data-chroma="background_mode"]').value`),'transparent');
  await click('[data-chroma-apply]');
  await wait(async()=> (await project()).manual.chroma_key?.[asset.id]?.background_mode==='transparent');
  await wait(()=>cdp.eval(`!!document.querySelector('[data-chroma-frame]').src&&!document.querySelector('[data-chroma-frame]').parentElement.hidden`));
  await wait(async()=>Boolean(await keyedFrame()));
  evidence.rows.push({stage:'saved-layer-preview',...(await keyedFrame())});assert.equal(evidence.rows.at(-1).corner[3],0);assert.ok(evidence.rows.at(-1).center[3]>240);
  await screenshot('ui-keyed-paused');
  const revision=(await project()).revision;
  await click('#manualUndo');await wait(async()=>(await project()).revision>revision);
  await wait(()=>cdp.eval(`!document.querySelector('.media-overlay .chroma-live:not([hidden])')`));
  const undone=(await project()).revision;await click('#manualRedo');await wait(async()=>(await project()).revision>undone);
  await wait(async()=>Boolean(await keyedFrame()));
  await click('#playButton');await pause(600);await click('#playButton');
  evidence.rows.push({stage:'playback',...(await keyedFrame())});assert.equal(evidence.rows.at(-1).corner[3],0);
  await field('[data-chroma="tolerance"]','1');
  assert.equal(await cdp.eval(`document.querySelector('[data-chroma-warning]').hidden`),false);
  await click('[data-chroma-defaults]');
  await cdp.send('Page.navigate',{url:'about:blank'});await wait(()=>cdp.eval(`location.href==='about:blank'`));
  await cdp.send('Page.navigate',{url:origin});
  await wait(()=>cdp.eval(`!!document.querySelector('[data-project-id="${projectId}"] [data-project-action="open"]')`));
  await click(`[data-project-id="${projectId}"] [data-project-action="open"]`);
  await wait(()=>cdp.eval(`!document.body.classList.contains('welcome-mode')&&!document.getElementById('advancedButton').disabled`));
  await cdp.eval(`if(document.getElementById('advancedPanel').hidden)document.getElementById('advancedButton').click()`);await click('#studioTabFraming');
  await wait(()=>cdp.eval(`document.querySelector('[data-chroma-source]').value===${JSON.stringify(asset.id)}`));
  assert.equal(await cdp.eval(`document.querySelector('[data-chroma="background_mode"]').value`),'transparent');
  assert.equal(await cdp.eval(`document.querySelector('[data-chroma="tolerance"]').value`),'0.12');
  await field('#previewSeek','450');await wait(async()=>Boolean(await keyedFrame()));await screenshot('ui-reopened');
  // A/B use replacement backgrounds; exercise the main source player as well
  // as Media and confirm Original mode intentionally bypasses the saved key.
  await click('[data-chroma-target="A"]');
  await cdp.eval(`(()=>{const e=document.querySelector('[data-chroma="enabled"]');if(!e.checked)e.click();})()`);
  await field('[data-chroma="tolerance"]','1');await field('[data-chroma="background_color"]','#0000ff');
  const beforeMain=(await project()).revision;await click('[data-chroma-apply]');await wait(async()=>(await project()).revision>beforeMain);
  await wait(()=>cdp.eval(`!!document.querySelector('#previewPaneA .chroma-live:not([hidden])')`));
  const mainPixel=await cdp.eval(`[...document.querySelector('#previewPaneA .chroma-live').getContext('2d').getImageData(16,16,1,1).data]`);
  assert.deepEqual(mainPixel,[0,0,255,255]);evidence.rows.push({stage:'main-source-preview',pixel:mainPixel});
  await cdp.eval(`(()=>{const e=document.getElementById('previewMode');e.value='source';e.dispatchEvent(new Event('change'));})()`);
  await wait(()=>cdp.eval(`!document.querySelector('#previewPaneA .chroma-live:not([hidden])')`));
  await cdp.eval(`(()=>{const e=document.getElementById('previewMode');e.value='edit';e.dispatchEvent(new Event('change'));})()`);
  await wait(()=>cdp.eval(`!!document.querySelector('#previewPaneA .chroma-live:not([hidden])')`));
  const mainRevision=(await project()).revision;await click('#manualUndo');await wait(async()=>(await project()).revision>mainRevision);
  await wait(()=>cdp.eval(`!document.querySelector('#previewPaneA .chroma-live:not([hidden])')`));
  await click(`[data-chroma-target="${asset.id}"]`);
  const start=Date.now();await click('#renderButton');await wait(()=>cdp.eval(`document.getElementById('exportDialog').open`));await click('#confirmExport');
  await wait(()=>cdp.eval(`!document.getElementById('downloadExport').hidden&&!!document.getElementById('downloadExport').href`),120000);
  evidence.exportUrl=await cdp.eval(`document.getElementById('downloadExport').href`);evidence.exportSeconds=(Date.now()-start)/1000;
  const exported=await fetch(evidence.exportUrl);assert.equal(exported.status,200);fs.writeFileSync(path.join(output,'ui-export.mp4'),Buffer.from(await exported.arrayBuffer()));
  evidence.errors=cdp.events.filter(e=>e.method==='Runtime.exceptionThrown'||e.method==='Log.entryAdded'&&e.params.entry.level==='error');
  assert.equal(evidence.errors.length,0,'No browser errors');evidence.status='PASS';await screenshot('ui-exported');
 } catch(error) {
  evidence.status='FAIL';evidence.failure=error.stack;process.exitCode=1;
  if(cdp){await screenshot('ui-failure').catch(()=>{});evidence.debug=await cdp.eval(`({body:document.body.innerText.slice(-9000),chroma:document.querySelector('#chromaKeyTool')?.innerText,canvases:[...document.querySelectorAll('.chroma-live')].map(c=>({hidden:c.hidden,width:c.width,height:c.height}))})`).catch(()=>null);}
 } finally {
  evidence.finished=new Date().toISOString();fs.writeFileSync(path.join(output,'browser-chroma-workflow.json'),JSON.stringify(evidence,null,2));
  if(cdp){try{await cdp.send('Browser.close');}catch{}cdp.close();}if(browser.exitCode===null)browser.kill();fs.writeFileSync(path.join(output,'chrome-stderr.txt'),stderr);
 }
 console.log(JSON.stringify({status:evidence.status,rows:evidence.rows,failure:evidence.failure,output},null,2));
})();
