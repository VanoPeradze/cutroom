/* Explicit real-browser regression; intentionally excluded from frontend*.test.cjs.
 * Requires Node 22+, an existing Chrome/Chromium and an already-running isolated
 * Cutroom server with a synthetic manual project. No downloads or installations.
 * node tests/browser_edit_inspector_layout.cjs <loopback-origin> <project-id> <chrome> <output-dir>
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
async function geometry(label) {
  return cdp.eval(`(()=>{const form=document.getElementById('timelineRangeForm'),status=document.getElementById('timelineRangeStatus'),pane=document.getElementById('studioPanelTimeline');const style=getComputedStyle(form),statusStyle=getComputedStyle(status),range=document.createRange();range.selectNodeContents(status);const rect=e=>e.getBoundingClientRect().toJSON();return{label:${JSON.stringify(label)},viewport:innerWidth,form:rect(form),contentWidth:form.clientWidth-parseFloat(style.paddingLeft)-parseFloat(style.paddingRight),columns:style.gridTemplateColumns,status:rect(status),statusFont:parseFloat(statusStyle.fontSize),statusLines:[...range.getClientRects()].map(b=>b.toJSON()),children:[...form.children].filter(e=>e.getClientRects().length).map(e=>({tag:e.tagName,id:e.id,rect:rect(e)})),inputWidths:['timelineRangeStart','timelineRangeEnd'].map(id=>rect(document.getElementById(id)).width),button:rect(document.getElementById('timelineRangeSubmit')),formClientWidth:form.clientWidth,formScrollWidth:form.scrollWidth,paneClientWidth:pane.clientWidth,paneScrollWidth:pane.scrollWidth,hidden:form.hidden}})()`);
}
function assertReadable(row) {
  assert.equal(row.hidden,false,'Range must remain open');
  assert.ok(row.contentWidth>=200,`Inspector range content must be usable: ${row.contentWidth}px`);
  assert.ok(row.status.width>=row.contentWidth-2,`Status must span inspector width; got ${row.status.width}px for ${row.contentWidth}px content`);
  assert.ok(row.statusFont>=11,'Status typography must remain readable');
  assert.ok(row.statusLines.length>0 && row.statusLines.length<=4,`Status must not wrap one character per line: ${row.statusLines.length} fragments`);
  assert.ok(Math.max(...row.statusLines.map(line=>line.width))>=100,'Status needs a normal text line');
  assert.ok(row.inputWidths.every(width=>width>=90),'Both range inputs need usable width');
  assert.ok(row.button.width>=100,'Range action needs usable width');
  assert.ok(row.formScrollWidth<=row.formClientWidth+1,'Range must not overflow horizontally');
  assert.ok(row.paneScrollWidth<=row.paneClientWidth+1,'Inspector must not overflow horizontally');
  for(const child of row.children) assert.ok(child.rect.left>=row.form.left-1&&child.rect.right<=row.form.right+1,`${child.id||child.tag} must fit inside the range form`);
}
(async()=>{
  try {
    const portFile=path.join(profile,'DevToolsActivePort');await wait(()=>fs.existsSync(portFile));
    const port=Number(fs.readFileSync(portFile,'utf8').split(/\r?\n/)[0]);
    const version=await(await fetch(`http://127.0.0.1:${port}/json/version`)).json();evidence.browser=version.Browser;
    const pages=await(await fetch(`http://127.0.0.1:${port}/json/list`)).json();cdp=new CDP(pages.find(page=>page.type==='page').webSocketDebuggerUrl);await cdp.open();
    for(const method of ['Page.enable','Runtime.enable','Log.enable','Network.enable'])await cdp.send(method);
    await cdp.send('Network.setCacheDisabled',{cacheDisabled:true});await cdp.send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
    await cdp.send('Page.navigate',{url:origin});await wait(()=>cdp.eval(`!!document.querySelector('[data-project-id="${projectId}"] [data-project-action="open"]')`));
    await cdp.eval(`document.querySelector('[data-project-id="${projectId}"] [data-project-action="open"]').click()`);await wait(()=>cdp.eval(`!document.body.classList.contains('welcome-mode')&&!document.getElementById('advancedButton').disabled`));
    await cdp.eval(`if(document.getElementById('advancedPanel').hidden)document.getElementById('advancedButton').click()`);await wait(()=>cdp.eval(`!document.getElementById('advancedPanel').hidden&&document.getElementById('timelineCanvas').width>0`));await pause(500);
    for(const width of [961,1100,1440]) {
      await cdp.send('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:false});await pause(150);
      await cdp.eval(`document.getElementById('studioTabTimeline').click();if(!document.getElementById('editorMoreTools').open)document.querySelector('#editorMoreTools>summary').click();if(document.getElementById('timelineRangeForm').hidden)document.getElementById('manualRange').click()`);
      await wait(()=>cdp.eval(`!document.getElementById('timelineRangeForm').hidden`));await pause(120);
      let row=await geometry(`edit-range-${width}`);evidence.rows.push(row);await screenshot(`edit-range-${width}`);assertReadable(row);
      await cdp.eval(`document.getElementById('studioTabAudio').click();document.getElementById('studioTabTimeline').click()`);await pause(100);
      row=await geometry(`audio-return-edit-${width}`);evidence.rows.push(row);assertReadable(row);
    }
    evidence.errors=cdp.events.filter(item=>item.method==='Runtime.exceptionThrown'||(item.method==='Runtime.consoleAPICalled'&&item.params.type==='error')||(item.method==='Log.entryAdded'&&item.params.entry.level==='error')||(item.method==='Network.loadingFailed'&&!item.params.canceled));
    assert.equal(evidence.errors.length,0,'Actual browser must have no unexpected JS/console/network errors');
    evidence.status='PASS';
  } catch(error) {evidence.status='FAIL';evidence.failure=error.stack;process.exitCode=1;if(cdp)evidence.debug=await cdp.eval(`({activeTab:document.querySelector('[data-tab][aria-selected=true]')?.dataset.tab,rangeForm:document.getElementById('timelineRangeForm')?.outerHTML,rangeButton:document.getElementById('manualRange')?.outerHTML,bodyClass:document.body.className})`).catch(()=>null);}
  finally {evidence.finished=new Date().toISOString();fs.writeFileSync(path.join(output,'browser-edit-inspector-layout.json'),JSON.stringify(evidence,null,2));if(cdp){try{await cdp.send('Browser.close');}catch{}cdp.close();}if(browser.exitCode===null)browser.kill();fs.writeFileSync(path.join(output,'chrome-stderr.txt'),stderr);}
  console.log(JSON.stringify({status:evidence.status,rows:evidence.rows.length,failure:evidence.failure,output},null,2));
})();
