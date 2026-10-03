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
async function click(selector) {await cdp.eval(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});e.focus();e.click();})()`);}
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

 const initial=await project(),asset=Object.values(initial.assets).find(a=>a.kind==='video');
 await click('#studioTabMedia');await click('[data-asset="'+asset.id+'"]');
 await wait(async()=>(await project()).revision>initial.revision);await pause(200);
 const clip=(await project()).manual.media_clips.at(-1);const width='[data-media="w"]';
 await cdp.eval("document.querySelector('.media-placement').open=true");
 const rect=async selector=>cdp.eval('(()=>{const e=document.querySelector('+JSON.stringify(selector)+');e.scrollIntoView({block:"center"});const r=e.getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2};})()');
 const pointer=async(type,p)=>cdp.send('Input.dispatchMouseEvent',{type,button:'left',buttons:type==='mouseReleased'?0:1,clickCount:1,...p});
 const value=async()=>Number(await cdp.eval('document.querySelector('+JSON.stringify(width)+').value'));
 const savedWidth=async()=> (await project()).manual.media_clips.find(c=>c.id===clip.id).w;
 let revision=(await project()).revision,p=await rect(width);
 await pointer('mousePressed',p);await pointer('mouseMoved',{x:p.x,y:p.y+40});await pause(700);
 assert.equal(await value(),90);assert.equal((await project()).revision,revision,'No autosave midway through a drag');
 await pointer('mouseReleased',{x:p.x,y:p.y+40});await wait(async()=>(await project()).revision>revision);
 assert.equal((await project()).revision,revision+1);assert.equal(await savedWidth(),.9);
 await click('#manualUndo');await wait(async()=>await savedWidth()===1);await click('#manualRedo');await wait(async()=>await savedWidth()===.9);
 evidence.rows.push({stage:'width-drag-single-undo',width:await savedWidth()});
 revision=(await project()).revision;p=await rect(width);await pointer('mousePressed',p);await pointer('mouseMoved',{x:p.x,y:p.y-24});
 await cdp.send('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape'});await pointer('mouseReleased',{x:p.x,y:p.y-24});await pause(500);
 assert.equal(await value(),90);assert.equal((await project()).revision,revision);
 p=await rect(width);await pointer('mousePressed',p);await pointer('mouseMoved',{x:p.x,y:p.y-24});await cdp.eval("window.dispatchEvent(new Event('blur'))");await pointer('mouseReleased',p);await pause(500);
 assert.equal(await value(),90);assert.equal((await project()).revision,revision);
 // Repeat a complete gesture and release outside the field.
 p=await rect(width);await pointer('mousePressed',p);await pointer('mouseMoved',{x:p.x,y:p.y-20});await pointer('mouseReleased',{x:1400,y:p.y-20});
 await wait(async()=>await savedWidth()===.95);assert.equal((await project()).revision,revision+1);
 revision=(await project()).revision;p=await rect(width);await cdp.eval('document.querySelector('+JSON.stringify(width)+').blur()');
 await cdp.send('Input.dispatchMouseEvent',{type:'mouseWheel',...p,deltaX:0,deltaY:100});await pause(500);assert.equal((await project()).revision,revision);
 p=await rect(width);await cdp.eval('document.querySelector('+JSON.stringify(width)+').focus()');
 for(let n=0;n<3;n++)await cdp.send('Input.dispatchMouseEvent',{type:'mouseWheel',...p,deltaX:0,deltaY:100});
 await wait(async()=>await savedWidth()===.92);assert.equal((await project()).revision,revision+1);
 await click('#manualUndo');await wait(async()=>await savedWidth()===.95);
 evidence.rows.push({stage:'focused-wheel-coalesced-and-undo',width:await savedWidth()});
 // Exact typing still follows the existing change handler.
 revision=(await project()).revision;await field(width,'75');await cdp.eval('document.querySelector('+JSON.stringify(width)+').dispatchEvent(new Event("change",{bubbles:true}))');
 await wait(async()=>await savedWidth()===.75);assert.equal((await project()).revision,revision+1);
 await click('#studioTabAudio');const volume='[data-mix="master_db"]',out='[data-mix-value="master_db"]';
 const originalVolume=(await project()).manual.audio_mixer?.master_db||0;
 revision=(await project()).revision;p=await rect(out);await pointer('mousePressed',p);await pointer('mouseMoved',{x:p.x,y:p.y-20});await pause(550);
 assert.equal((await project()).revision,revision);await pointer('mouseReleased',{x:p.x,y:p.y-20});
 await wait(async()=>(await project()).revision>revision);assert.equal((await project()).revision,revision+1);
 assert.equal(Number(await cdp.eval('document.querySelector('+JSON.stringify(volume)+').value')),originalVolume+5);
 await click('#manualUndo');await wait(async()=>Number(await cdp.eval('document.querySelector('+JSON.stringify(volume)+').value'))===originalVolume);
 evidence.rows.push({stage:'master-volume-output-drag-and-undo',volume:originalVolume});
 await cdp.send('Page.reload');await wait(()=>cdp.eval('!!document.querySelector(\'[data-project-id="'+projectId+'"] [data-project-action="open"]\')'));
 await click('[data-project-id="'+projectId+'"] [data-project-action="open"]');await wait(()=>cdp.eval("!document.body.classList.contains('welcome-mode')"));
 assert.equal(await savedWidth(),.75);evidence.rows.push({stage:'saved-width-survives-reopen',width:await savedWidth()});
 evidence.errors=cdp.events.filter(e=>e.method==='Runtime.exceptionThrown'||e.method==='Log.entryAdded'&&e.params.entry.level==='error');
 assert.equal(evidence.errors.length,0);evidence.status='PASS';
}catch(error){evidence.status='FAIL';evidence.failure=error.stack;process.exitCode=1;if(cdp)await screenshot('numeric-failure').catch(()=>{});}
finally{fs.writeFileSync(path.join(output,'numeric-scrub.json'),JSON.stringify(evidence,null,2));if(cdp){try{await cdp.send('Browser.close');}catch{}cdp.close();}if(browser.exitCode===null)browser.kill();}
console.log(JSON.stringify({status:evidence.status,failure:evidence.failure,rows:evidence.rows,output},null,2));
})();