/* Real installed Chromium, real local app/API and synthetic media only.
 * node tests/browser_reel_proposals.cjs <isolated-origin> <project-id> <chrome> <output>
 * Test-only fixture server supplies /__qa/state and /__qa/change; never production.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {spawn} = require('node:child_process');
const {setTimeout: pause} = require('node:timers/promises');
const {browserElementBox} = require('./browser_dom_box.cjs');
const [origin,pid,chrome,out] = process.argv.slice(2);
if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(origin||'') || !/^project_[\w-]+$/.test(pid||'') || !out || !chrome) throw Error('Use an isolated local QA project');
fs.mkdirSync(out,{recursive:true});
const profile=path.join(out,`chromium-${Date.now()}`);
const evidence={started:new Date().toISOString(),origin,projectId:pid,realBrowser:true,headless:true,rows:[],screenshots:[]};
const browser=spawn(chrome,['--headless=new','--disable-gpu','--mute-audio','--no-first-run','--no-default-browser-check','--disable-background-networking','--disable-component-update','--disable-sync','--disable-extensions','--remote-debugging-port=0',`--user-data-dir=${profile}`,'about:blank'],{windowsHide:true,stdio:['ignore','ignore','pipe']});
let stderr='',launchError,cdp;browser.stderr.on('data',d=>stderr+=d);browser.on('error',e=>launchError=e);
class CDP {
  constructor(url){this.id=0;this.pending=new Map();this.events=[];this.ws=new WebSocket(url);this.ws.addEventListener('message',e=>{const r=JSON.parse(e.data);if(!r.id){this.events.push(r);return;}const p=this.pending.get(r.id);if(!p)return;clearTimeout(p.timer);this.pending.delete(r.id);r.error?p.reject(Error(JSON.stringify(r.error))):p.resolve(r.result);});}
  async open(){await new Promise((yes,no)=>{this.ws.addEventListener('open',yes,{once:true});this.ws.addEventListener('error',no,{once:true});});}
  send(method,params={}){return new Promise((resolve,reject)=>{const id=++this.id;const timer=setTimeout(()=>{this.pending.delete(id);reject(Error(`CDP timeout ${method}`));},15000);this.pending.set(id,{resolve,reject,timer});this.ws.send(JSON.stringify({id,method,params}));});}
  async eval(expression){const r=await this.send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value;}
  close(){for(const p of this.pending.values())clearTimeout(p.timer);this.ws.close();}
}
async function wait(check,label,timeout=15000){const start=Date.now();while(Date.now()-start<timeout){if(launchError)throw launchError;if(await check())return;await pause(80);}throw Error(`Timed out: ${label}`);}
async function box(selector){return browserElementBox(cdp,selector);}
async function mouseClick(x,y,count=1){await cdp.send('Input.dispatchMouseEvent',{type:'mouseMoved',x,y});await cdp.send('Input.dispatchMouseEvent',{type:'mousePressed',x,y,button:'left',clickCount:count});await cdp.send('Input.dispatchMouseEvent',{type:'mouseReleased',x,y,button:'left',clickCount:count});}
async function click(selector){const r=await box(selector);await mouseClick(r.x+r.width/2,r.y+r.height/2);}
async function state(){return (await(await fetch(`${origin}/__qa/state`)).json());}
async function project(){return (await(await fetch(`${origin}/api/projects/${pid}`)).json()).project;}
async function screenshot(name){const r=await cdp.send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});const file=path.join(out,`${name}.png`);fs.writeFileSync(file,Buffer.from(r.data,'base64'));evidence.screenshots.push(file);}
const dialog='dialog[aria-labelledby="reelReviewTitle"]';
async function openReview(){if(await cdp.eval(`document.body.classList.contains('studio-open')`))await click('#closeAdvanced');await click('button[data-candidate-id="qa-alternative"]');await wait(()=>cdp.eval(`!!document.querySelector('${dialog}')?.open && !!document.querySelector('${dialog} video')?.getAttribute('src')`),'proposal loaded');}
async function play(){await wait(()=>cdp.eval(`document.querySelector('${dialog} video').readyState>=2`),'source decoded');const r=await box(`${dialog} video`);await mouseClick(r.x+26,r.y+r.height-49);await wait(()=>cdp.eval(`!document.querySelector('${dialog} .primary').disabled`),'native Play before accept');}
async function reload(){await cdp.eval(`window.__reelQAOldDocument=true`);await cdp.send('Page.reload',{ignoreCache:true});await wait(()=>cdp.eval(`!window.__reelQAOldDocument&&document.readyState==='complete'&&!!document.body&&!!document.querySelector('[data-project-id="${pid}"] [data-project-action="open"]')`),'new document and saved project');if(await cdp.eval(`document.body.classList.contains('welcome-mode')`))await click(`[data-project-id="${pid}"] [data-project-action="open"]`);await wait(()=>cdp.eval(`!!document.querySelector('button[data-candidate-id="qa-alternative"]')&&!document.querySelector('button[data-candidate-id="qa-alternative"]').disabled`),'reopened alternative');}
function row(stage,detail={}){evidence.rows.push({stage,...detail});console.log(JSON.stringify(evidence.rows.at(-1)));}
(async()=>{
 try {
  await wait(()=>fs.existsSync(path.join(profile,'DevToolsActivePort')),'owned Chromium startup');
  const port=Number(fs.readFileSync(path.join(profile,'DevToolsActivePort'),'utf8').split(/\r?\n/)[0]);
  const pages=await(await fetch(`http://127.0.0.1:${port}/json/list`)).json();cdp=new CDP(pages.find(p=>p.type==='page').webSocketDebuggerUrl);await cdp.open();
  evidence.browser=await cdp.send('Browser.getVersion');
  for(const method of ['Page.enable','Runtime.enable','Log.enable','Network.enable'])await cdp.send(method);
  await cdp.send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await cdp.send('Page.navigate',{url:origin});
  await wait(()=>cdp.eval(`!!document.querySelector('[data-project-id="${pid}"] [data-project-action="open"]')`),'project card');
  await click(`[data-project-id="${pid}"] [data-project-action="open"]`);
  await wait(()=>cdp.eval(`!!document.querySelector('button[data-candidate-id="qa-alternative"]')&&!document.querySelector('button[data-candidate-id="qa-alternative"]').disabled`),'normal Reel controls');
  const before=await state();await openReview();
  const preview=await cdp.eval(`(()=>{const d=document.querySelector('${dialog}');return{copy:d.innerText,duration:d.querySelector('video').duration,disabled:d.querySelector('.primary').disabled};})()`);
  assert.equal(preview.disabled,true);assert.match(preview.copy,/0:01.*0:02.*0:04.*0:07.*0:04/s);
  assert.match(preview.copy,/still needs review/);await play();
  await wait(()=>cdp.eval(`document.querySelector('${dialog} video').currentTime>4.05`),'source gap skip',7000);
  const playback=await cdp.eval(`(()=>{const v=document.querySelector('${dialog} video');return{time:v.currentTime,frames:v.getVideoPlaybackQuality().totalVideoFrames,ready:v.readyState,audio:v.audioTracks?.length??null};})()`);
  assert.ok(playback.frames>0);await screenshot('proposal-preview');
  await click(`${dialog} .ghost`);await wait(()=>cdp.eval(`!document.querySelector('${dialog}')`),'Keep current closed');
  assert.equal((await state()).projectSha256,before.projectSha256);row('preview-and-keep',{preview,playback,bytePreserved:true});
  await openReview();await cdp.send('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});await cdp.send('Input.dispatchKeyEvent',{type:'keyUp',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
  await wait(()=>cdp.eval(`!document.querySelector('${dialog}')`),'Escape dismissed');assert.equal((await state()).projectSha256,before.projectSha256);row('escape-dismiss',{bytePreserved:true});
  // Delay only this synthetic read-only response to exercise real cancellation,
  // then release it normally; no global browser/network settings are changed.
  await cdp.send('Fetch.enable',{patterns:[{urlPattern:'*/reel-proposal',requestStage:'Response'}]});
  const eventStart=cdp.events.length;await click('button[data-candidate-id="qa-alternative"]');
  await wait(()=>cdp.events.slice(eventStart).some(e=>e.method==='Fetch.requestPaused'),'pending proposal response');
  assert.equal(await cdp.eval(`document.querySelector('${dialog} .primary').disabled`),true);
  await click(`${dialog} .ghost`);await cdp.send('Fetch.disable');
  await wait(()=>cdp.eval(`!document.querySelector('${dialog}')`),'pending review cancelled');
  assert.equal((await state()).projectSha256,before.projectSha256);row('cancel-pending-review',{bytePreserved:true,delayedResponse:true});
  await openReview();await play();
  const reviewed=await cdp.eval(`(()=>{const d=document.querySelector('${dialog}');return d.innerText;})()`);
  const applyBox=await box(`${dialog} .primary`);await mouseClick(applyBox.x+applyBox.width/2,applyBox.y+applyBox.height/2);await mouseClick(applyBox.x+applyBox.width/2,applyBox.y+applyBox.height/2,2);
  await wait(async()=>(await project()).draft.active_reel_candidate==='qa-alternative','applied alternative');
  await wait(()=>cdp.eval(`!document.querySelector('${dialog}')`),'accepted closed');
  const applied=await project();assert.equal(applied.draft.output_duration,4);assert.deepEqual(applied.draft.keep_ranges,[{start:1,end:2},{start:4,end:7}]);assert.equal(applied.manual.history.undo_count,1);assert.equal(applied.draft.status,'requires_review');
  row('apply-and-double-click',{ranges:applied.draft.keep_ranges,duration:applied.draft.output_duration,history:applied.manual.history,reviewed});
  if(await cdp.eval(`document.getElementById('advancedPanel').hidden`))await click('[data-open-studio-tab="timeline"]');
  await wait(()=>cdp.eval(`!document.getElementById('manualUndo').disabled`),'Undo available');await click('#manualUndo');
  await wait(async()=>(await project()).draft.active_reel_candidate==='director_pick','Undo restored');const undone=await project();assert.equal(undone.draft.output_duration,8);assert.deepEqual(undone.draft.keep_ranges,[{start:0,end:8}]);row('undo',{duration:undone.draft.output_duration});
  await wait(()=>cdp.eval(`!document.getElementById('manualRedo').disabled`),'Redo available');await click('#manualRedo');await wait(async()=>(await project()).draft.active_reel_candidate==='qa-alternative','Redo restored');row('redo',{duration:(await project()).draft.output_duration});
  await click('#manualUndo');await wait(async()=>(await project()).draft.active_reel_candidate==='director_pick','Undo for stale tests');
  for(const kind of ['manual','source']){
    await reload();await openReview();await play();
    if(kind==='source'){
      const exact=await cdp.eval(`document.querySelector('${dialog}').innerText`);
      assert.match(exact,/00:01\.000–00:01\.500.*00:01\.750–00:02\.000.*00:04\.000–00:07\.000.*00:03\.750/s);
      row('fractional-source-labels',{exact});
    }
    const change=await fetch(`${origin}/__qa/change`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind})});assert.equal(change.status,200);
    const saved=await state();await click(`${dialog} .primary`);
    await wait(()=>cdp.eval(`document.querySelector('${dialog}')?.innerText.includes('not applied')`),'stale rejection');
    assert.equal((await state()).projectSha256,saved.projectSha256);
    await screenshot(`stale-${kind}`);await click(`${dialog} .ghost`);row(`stale-after-${kind}`,{bytePreserved:true,revision:saved.revision});
  }
  evidence.runtimeErrors=cdp.events.filter(e=>e.method==='Runtime.exceptionThrown');assert.equal(evidence.runtimeErrors.length,0);
  evidence.status='PASS';
 }catch(error){evidence.status='FAIL';evidence.failure=error.stack;process.exitCode=1;if(cdp){await screenshot('failure').catch(()=>{});evidence.debug=await cdp.eval(`({text:document.body.innerText.slice(-10000),dialogs:[...document.querySelectorAll('dialog[open]')].map(e=>e.innerText)})`).catch(()=>null);}}
 finally{
  if(cdp){try{await cdp.send('Browser.close');}catch{}cdp.close();}
  if(browser.exitCode===null){await Promise.race([new Promise(done=>browser.once('exit',done)),pause(3000)]);if(browser.exitCode===null){browser.kill();evidence.ownedBrowserForcedStop=true;}}
  evidence.finished=new Date().toISOString();evidence.browserExitCode=browser.exitCode;
  fs.writeFileSync(path.join(out,'browser-reel-proposals.json'),JSON.stringify(evidence,null,2));fs.writeFileSync(path.join(out,'chromium-stderr.txt'),stderr);
  console.log(JSON.stringify({status:evidence.status,failure:evidence.failure,stages:evidence.rows.length,out}));
 }
})();
