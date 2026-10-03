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
 const pages=await(await fetch('http://127.0.0.1:'+port+'/json/list')).json();
 cdp=new CDP(pages.find(p=>p.type==='page').webSocketDebuggerUrl);await cdp.open();
 await cdp.send('Page.enable');await cdp.send('Runtime.enable');await cdp.send('Log.enable');
 await cdp.send('Emulation.setDeviceMetricsOverride',{width:1440,height:900,deviceScaleFactor:1,mobile:false});
 await cdp.send('Page.navigate',{url:origin});
 await wait(()=>cdp.eval('!!document.querySelector(\'[data-project-id="'+projectId+'"] [data-project-action="open"]\')'));
 await click('[data-project-id="'+projectId+'"] [data-project-action="open"]');
 await wait(()=>cdp.eval("!document.body.classList.contains('welcome-mode')&&!document.getElementById('advancedButton').disabled"));
 await cdp.eval("if(document.getElementById('advancedPanel').hidden)document.getElementById('advancedButton').click()");
 const before=await project();
 const tabs=await cdp.eval("[...document.querySelectorAll('.advanced-tabs button')].map(e=>e.dataset.tab)");
 assert.deepEqual(tabs,['media','timeline','framing','audio','transcript','settings']);
 assert.equal(await cdp.eval("document.querySelectorAll('#chromaStudio').length"),1);
 assert.equal(await cdp.eval("!!document.querySelector('#studioPanelFraming #chromaStudio')"),false);
 for(const [width,height] of [[1440,900],[1280,720],[1280,640],[820,740],[390,844]]){
  await cdp.send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});
  for(const tab of ['timeline','effects','framing']){
   await click(tab==='framing'?'#studioTabFraming':'#studioTabTimeline');
   if(tab!=='framing')await click(tab==='effects'?'#editToolEffects':'#editToolClip');
   await pause(200);
   const geometry=await cdp.eval("(()=>{const ids=['advancedPanel','studioInspector','studioPreviewDock','studioTimelineDock','previewStage','editToolEffects'];const out={};for(const id of ids){const e=document.getElementById(id),r=e.getBoundingClientRect();out[id]={x:r.x,y:r.y,w:r.width,h:r.height,scrollWidth:e.scrollWidth,clientWidth:e.clientWidth,scrollHeight:e.scrollHeight,clientHeight:e.clientHeight};}const tabs=[...document.querySelectorAll('.advanced-tabs button')];out.tabs=tabs.map(e=>({tab:e.dataset.tab,x:e.getBoundingClientRect().x}));out.page={w:document.documentElement.scrollWidth,viewport:innerWidth};return out;})()");
   evidence.rows.push({width,height,tab,...geometry});
   if(width>=900&&height>600){
    assert.ok(geometry.previewStage.h>=Math.min(300,height-444)-1,'Preview keeps useful height with tools and timeline open');
    assert.ok(geometry.studioTimelineDock.h>=184);
    assert.equal(geometry.studioTimelineDock.x,0);
    assert.equal(geometry.studioTimelineDock.w,width,'Timeline spans the complete edit');
    assert.ok(geometry.studioTimelineDock.y+geometry.studioTimelineDock.h<=height-43);
    assert.ok(geometry.studioInspector.w<=420,'Tool panels preserve space for the monitor');
   }
   assert.ok(geometry.page.w<=width+1,'No page horizontal overflow');
   assert.ok(geometry.studioInspector.scrollWidth<=geometry.studioInspector.clientWidth+1,'No clipped tool controls');
   await screenshot('layout-'+width+'x'+height+'-'+tab);
  }
 }
 // Logical order also works with RTL and keyboard navigation.
 await cdp.send('Emulation.setDeviceMetricsOverride',{width:1440,height:900,deviceScaleFactor:1,mobile:false});
 await cdp.eval("document.documentElement.dir='rtl';document.getElementById('studioTabMedia').click();document.getElementById('studioTabMedia').focus()");
 await cdp.send('Input.dispatchKeyEvent',{type:'keyDown',key:'ArrowLeft',code:'ArrowLeft'});await cdp.send('Input.dispatchKeyEvent',{type:'keyUp',key:'ArrowLeft',code:'ArrowLeft'});
 assert.equal(await cdp.eval('document.activeElement.id'),'studioTabTimeline');
 await click('#editToolEffects');await pause(200);await screenshot('layout-rtl-effects');
 assert.equal((await project()).revision,before.revision,'Display changes preserve saved project');
 evidence.errors=cdp.events.filter(e=>e.method==='Runtime.exceptionThrown'||e.method==='Log.entryAdded'&&e.params.entry.level==='error');
 assert.equal(evidence.errors.length,0);evidence.status='PASS';
}catch(error){evidence.status='FAIL';evidence.failure=error.stack;process.exitCode=1;if(cdp)await screenshot('layout-failure').catch(()=>{});}
finally{fs.writeFileSync(path.join(output,'workspace-layout.json'),JSON.stringify(evidence,null,2));if(cdp){try{await cdp.send('Browser.close');}catch{}cdp.close();}if(browser.exitCode===null)browser.kill();}
console.log(JSON.stringify({status:evidence.status,failure:evidence.failure,rows:evidence.rows,output},null,2));
})();
