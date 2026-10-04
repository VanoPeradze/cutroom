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
async function screenshot(name) {await cdp.send('Input.dispatchMouseEvent',{type:'mouseMoved',x:850,y:75});await pause(120);const result=await cdp.send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});const file=path.join(output,`${name}.png`);fs.writeFileSync(file,Buffer.from(result.data,'base64'));evidence.screenshots.push(file);}
async function project() {return (await (await fetch(`${origin}/api/projects/${projectId}`)).json()).project;}
// Values embedded in evaluated code are JSON literals with script-breaking characters escaped.
const UNSAFE_IN_SCRIPT = new RegExp(`[<>/${String.fromCharCode(0x2028, 0x2029)}]`, 'g');
const literal = value => JSON.stringify(value).replace(UNSAFE_IN_SCRIPT, character => String.fromCharCode(92) + 'u' + character.charCodeAt(0).toString(16).padStart(4,'0'));
async function click(selector) {await cdp.eval(`document.querySelector(${literal(selector)}).click()`);}
async function field(selector,value) {await cdp.eval(`(()=>{const e=document.querySelector(${literal(selector)});e.value=${literal(value)};e.dispatchEvent(new Event('input',{bubbles:true}));})()`);}
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

 await cdp.send('Emulation.setDeviceMetricsOverride',{width:1600,height:900,deviceScaleFactor:1,mobile:false});
 await cdp.send('Page.navigate',{url:origin});
 await wait(()=>cdp.eval(`!!document.querySelector(${literal(`[data-project-id="${projectId}"] [data-project-action="open"]`)})`));
 await click('[data-project-id="'+projectId+'"] [data-project-action="open"]');
 await wait(()=>cdp.eval("!document.getElementById('advancedPanel').hidden"));
 await wait(()=>cdp.eval("document.querySelector('#previewStage video')?.readyState>=2"));
 const original=await project();
 const revision=()=>project().then(p=>p.revision);
 const tab=async name=>{await click('#studioTab'+name[0].toUpperCase()+name.slice(1));await pause(100);};
 // All surfaces stay within the viewport. Overflow belongs to the shelf/inspector.
 for(const [width,height] of [[1366,768],[1600,900],[1920,1080]]) {
   await cdp.send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});
   for(const name of ['media','timeline','framing','audio','transcript','settings']) {
     await tab(name);
     const row=await cdp.eval(`(()=>{const r=s=>{const e=document.querySelector(s),b=e.getBoundingClientRect();return{x:b.x,y:b.y,w:b.width,h:b.height,right:b.right,bottom:b.bottom,scrollWidth:e.scrollWidth,clientWidth:e.clientWidth}};return{body:{w:document.documentElement.scrollWidth,h:document.documentElement.scrollHeight},shelf:r('#studioShelf'),preview:r('#previewStage'),inspector:r('#studioInspector'),timeline:r('#studioTimelineDock'),nav:r('.advanced-tabs'),panels:[...document.querySelectorAll('.tab-panel')].filter(e=>!e.hidden).length,shelves:[...document.querySelectorAll('[data-shelf]')].filter(e=>!e.hidden).length}})()`);
     assert.equal(row.panels,1);assert.equal(row.shelves,1);
     assert.ok(row.body.w<=width+1&&row.body.h<=height+1,'No page overflow');
     assert.ok(row.shelf.right<=row.preview.x&&row.preview.right<=row.inspector.x,'No column overlap');
     assert.ok(row.preview.bottom<=row.timeline.y,'Monitor stays above the timeline');
     assert.ok(row.nav.bottom<=height+1&&row.nav.y>=row.timeline.bottom-1,'Bottom navigation remains stable');
     assert.ok(row.inspector.scrollWidth<=row.inspector.clientWidth+1,'No clipped horizontal inspector controls');
     evidence.rows.push({stage:'geometry',width,height,tab:name,...row});
   }
 }
 await cdp.send('Emulation.setDeviceMetricsOverride',{width:1600,height:900,deviceScaleFactor:1,mobile:false});
 await tab('framing');assert.equal(await cdp.eval("document.querySelector('#sourceMixer').parentElement.id"),'studioShelfLayout');
 await cdp.eval("document.querySelector('#sourceSetupDisclosure').open=true");
 assert.equal(await cdp.eval("document.querySelector('#audioSourceSelect').disabled"),false);
 await screenshot('layout-two-real-sources');
 // Keyboard-tab navigation and focus remain in the tablist.
 await cdp.eval("document.querySelector('#studioTabMedia').focus()");
 await cdp.send('Input.dispatchKeyEvent',{type:'keyDown',key:'ArrowRight',code:'ArrowRight'});
 await cdp.send('Input.dispatchKeyEvent',{type:'keyUp',key:'ArrowRight',code:'ArrowRight'});
 assert.equal(await cdp.eval("document.activeElement.id"),'studioTabTimeline');
 await tab('audio');await field('#previewSeek','50');await click('#playButton');await pause(700);
 const meter=await cdp.eval("document.querySelector('[data-channel=source] meter').value");assert.ok(meter>0,'Live original audio meter measures the generated tone');
 await screenshot('audio-real-playback');await click('#playButton');
 await field('[data-mix=music_db]','-12');await wait(async()=>(await project()).manual.audio_mixer?.music_db===-12);
 await cdp.eval("document.querySelector('[data-mix=music_db]').focus()");
 await cdp.send('Input.dispatchKeyEvent',{type:'keyDown',key:'ArrowUp',code:'ArrowUp'});
 await cdp.send('Input.dispatchKeyEvent',{type:'keyUp',key:'ArrowUp',code:'ArrowUp'});
 await wait(async()=>(await project()).manual.audio_mixer.music_db===-11);
 await click('[data-mute=music]');await wait(async()=>(await project()).manual.audio_mixer.music_muted===true);
 let rev=await revision();await click('[data-solo=source]');await pause(700);assert.equal(await revision(),rev,'Solo remains preview-only');await click('[data-solo=source]');
 evidence.rows.push({stage:'audio',livePeak:meter,keyboardVolume:-11,muteSaved:true,soloPersisted:false});
 // Added media still imports and adds through the relocated, delegated library.
 await tab('media');
 const doc=await cdp.send('DOM.getDocument');
 const fileNode=await cdp.send('DOM.querySelector',{nodeId:doc.root.nodeId,selector:'#studioPanelMedia input[type=file]'});
 await cdp.send('DOM.setFileInputFiles',{nodeId:fileNode.nodeId,files:[path.resolve('validation-work/chroma-current/data/projects/'+projectId+'/media/source-B.mp4')]});
 await wait(async()=>Object.values((await project()).assets||{}).some(a=>a.status==='ready'),60000);
 await wait(()=>cdp.eval("!!document.querySelector('#studioShelfMedia [data-asset]:not(:disabled)')"));
 await click('#studioShelfMedia [data-asset]');await wait(async()=>((await project()).manual.media_clips||[]).length>0);
 assert.equal(await cdp.eval("document.querySelector('.media-inspector').hidden"),false);
 await field('[data-media=volume_db]','-4');await wait(async()=>(await project()).manual.media_clips[0].volume_db===-4);
 await screenshot('media-import-and-inspector');
 // Text is added from the shelf and edited by the original inspector and save queue.
 await tab('transcript');const count=(await project()).manual.text_clips.length;
 await click('#studioShelfCaptions [data-add=title]');
 await wait(async()=>(await project()).manual.text_clips.length===count+1);
 await field('[data-text=text]','Verified in the redesigned editor');
 await wait(async()=>(await project()).manual.text_clips.some(c=>c.text==='Verified in the redesigned editor'));
 await field('#studioShelfCaptions [data-search]','Verified');
 assert.equal(await cdp.eval("document.querySelectorAll('#studioShelfCaptions [data-text-id]').length"),1);
 await click('#studioShelfCaptions [data-text-id]');await screenshot('captions-saved');
 rev=await revision();await click('#manualUndo');await wait(async()=>(await revision())>rev);
 assert.ok(!(await project()).manual.text_clips.some(c=>c.text==='Verified in the redesigned editor'));
 rev=await revision();await click('#manualRedo');await wait(async()=>(await revision())>rev);
 assert.ok((await project()).manual.text_clips.some(c=>c.text==='Verified in the redesigned editor'));
 // Source trim uses the actual canvas hit target; undo restores its exact data.
 await tab('timeline');await click('#editToolClip');await cdp.eval("document.getElementById('timelineScroll').scrollTop=0");
 await cdp.eval("(()=>{const e=document.getElementById('timelineTarget');e.value='A';e.dispatchEvent(new Event('change',{bubbles:true}))})()");
 const point=await cdp.eval("(()=>{const r=document.getElementById('timelineCanvas').getBoundingClientRect();return{x:r.x+100,y:r.y+60}})()");
 await cdp.send('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...point});await cdp.send('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...point});
 await wait(()=>cdp.eval("!document.querySelector('#clipTrimForm').hidden"));
 const oldOut=Number(await cdp.eval("document.querySelector('#clipTrimOut').value"));const oldManual=(await project()).manual;
 await field('#clipTrimOut',String(oldOut-.15));rev=await revision();await click('#clipTrimApply');await wait(async()=>(await revision())>rev);
 rev=await revision();await click('#manualUndo');await wait(async()=>(await revision())>rev);
 const restored=(await project()).manual;
 const {history:oldHistory,...oldEdit}=oldManual;const {history:newHistory,...restoredEdit}=restored;
 assert.deepEqual(restoredEdit,oldEdit);assert.equal(newHistory.redo_count,oldHistory.redo_count+1);
 // Single aspect field moved to Output still drives the real frame and export settings.
 await tab('settings');await cdp.eval("(()=>{const e=document.getElementById('aspectSelect');e.value='9:16';e.dispatchEvent(new Event('change',{bubbles:true}))})()");
 await wait(async()=>(await project()).settings.aspect==='9:16');await pause(250);
 const ratio=await cdp.eval("(()=>{const r=document.getElementById('previewStage').getBoundingClientRect();return r.width/r.height})()");assert.ok(Math.abs(ratio-9/16)<.02);
 await screenshot('portrait-real-aspect');
 await cdp.eval("(()=>{const e=document.getElementById('aspectSelect');e.value='16:9';e.dispatchEvent(new Event('change',{bubbles:true}))})()");
 await wait(async()=>(await project()).settings.aspect==='16:9');
 // Dialogs open and cancel repeatedly without stale focus or project mutations.
 for(let i=0;i<2;i++){
   await click('#projectsButton');await click('#closeProjectsDialog');
   await click('#renderButton');await click('#cancelExport');
   await click('#studioTabMedia');await click('#studioShelfMedia .source-library-card');await wait(()=>cdp.eval("document.getElementById('sourceReviewDialog').open"));await click('[data-review=close]');
 }
 await click('#projectsButton');
 await click('#dialogProjects [data-project-id="'+projectId+'"] [data-project-action=rename]');await screenshot('dialog-rename');await cdp.eval("document.querySelector('#projectRenameDialog').close()");
 await click('#dialogProjects [data-project-id="'+projectId+'"] [data-project-action=delete]');await screenshot('dialog-delete');await cdp.eval("document.querySelector('#projectDeleteDialog').close()");await click('#closeProjectsDialog');
 // Reopen, assert persistence, and export through the visible dialog.
 await cdp.send('Page.navigate',{url:'about:blank'});await pause(150);await cdp.send('Page.navigate',{url:origin});
 await wait(()=>cdp.eval(`!!document.querySelector(${literal(`[data-project-id="${projectId}"] [data-project-action="open"]`)})`));
 await click('[data-project-id="'+projectId+'"] [data-project-action="open"]');await wait(()=>cdp.eval("!document.getElementById('advancedPanel').hidden"));
 await tab('audio');assert.equal(await cdp.eval("document.querySelector('[data-mix=music_db]').value"),'-11');assert.equal(await cdp.eval("document.querySelector('[data-mute=music]').getAttribute('aria-pressed')"),'true');
 assert.equal(await cdp.eval("document.querySelector('[data-solo=source]').getAttribute('aria-pressed')"),'false');
 await click('#renderButton');await screenshot('export-ready');await click('#confirmExport');await pause(200);await screenshot('export-processing');
 await wait(()=>cdp.eval("!document.getElementById('downloadExport').hidden&&!!document.getElementById('downloadExport').href"),120000);
 const url=await cdp.eval("document.getElementById('downloadExport').href");const exported=await fetch(url);assert.equal(exported.status,200);
 fs.writeFileSync(path.join(output,'workflow-export.mp4'),Buffer.from(await exported.arrayBuffer()));await screenshot('export-complete');
 evidence.rows.push({stage:'workflow',mediaImported:true,captionSavedUndoRedo:true,sourceTrimUndo:true,portraitRatio:ratio,reopened:true,exportUrl:url});
 evidence.errors=cdp.events.filter(e=>e.method==='Runtime.exceptionThrown'||e.method==='Log.entryAdded'&&e.params.entry.level==='error');assert.equal(evidence.errors.length,0);evidence.status='PASS';
}catch(error){evidence.status='FAIL';evidence.failure=error.stack;process.exitCode=1;if(cdp)await screenshot('layout-failure').catch(()=>{});}
finally{fs.writeFileSync(path.join(output,'studio-design.json'),JSON.stringify(evidence,null,2));if(cdp){try{await cdp.send('Browser.close');}catch{}cdp.close();}if(browser.exitCode===null)browser.kill();}
console.log(JSON.stringify({status:evidence.status,failure:evidence.failure,rows:evidence.rows,output},null,2));
})();


