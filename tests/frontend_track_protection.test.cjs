const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const source = fs.readFileSync(path.join(__dirname,'../web/track-protection.js'),'utf8').replace(/^export /gm,'');
function fixture() {
  const nodes=new Map();
  const document={getElementById(id){if(!nodes.has(id))nodes.set(id,{id,attrs:{},listeners:{},setAttribute(k,v){this.attrs[k]=v;},addEventListener(k,v){this.listeners[k]=v;}});return nodes.get(id);}};
  const ctx=vm.createContext({});vm.runInContext(source+'\nglobalThis.init=initTrackProtection;',ctx);
  const h={project:{id:'p',draft:{},sources:{A:{},B:{}},manual:{}},busy:false,calls:[],nodes};
  h.change=async(slot,locked)=>{h.calls.push({slot,locked});h.project.manual.track_locks={...h.project.manual.track_locks,[slot]:locked};return h.project;};
  h.view=ctx.init({document,getProject:()=>h.project,busy:()=>h.busy,change:(...a)=>h.change(...a)});
  h.click=slot=>nodes.get('trackLock'+slot).listeners.click();return h;
}
test('legacy projects are unlocked and an absent B has no lock control',()=>{
  const h=fixture();assert.equal(h.nodes.get('trackProtectionSummary').textContent,'Unlocked');
  delete h.project.sources.B;h.view.render();assert.equal(h.nodes.get('trackLockB').hidden,true);
});
test('lock state comes from the saved project, without optimistic changes',async()=>{
  const h=fixture();let finish;
  h.change=()=>new Promise(resolve=>finish=resolve);
  const pending=h.click('A');assert.equal(h.nodes.get('trackLockA').disabled,true);
  assert.equal(h.nodes.get('trackLockA').attrs['aria-pressed'],'false');
  await h.click('A');assert.equal(h.nodes.get('trackProtectionStatus').textContent,'Saving protection…');
  h.project.manual.track_locks={A:true};finish(h.project);await pending;
  assert.equal(h.nodes.get('trackLockA').textContent,'Unlock A');
  assert.equal(h.view.lockedNames('B').length,0);assert.equal(h.view.lockedNames('edit')[0],'A');
});
test('failed save leaves protection unchanged and supports retry',async()=>{
  const h=fixture();h.change=async()=>null;await h.click('A');
  assert.equal(h.nodes.get('trackLockA').attrs['aria-pressed'],'false');
  assert.match(h.nodes.get('trackProtectionStatus').textContent,/not changed/);
  assert.equal(h.nodes.get('trackLockA').disabled,false);
});
test('late completion cannot describe the old project as locked',async()=>{
  const h=fixture();let finish;h.change=()=>new Promise(resolve=>finish=resolve);
  const pending=h.click('A');h.project={id:'next',draft:{},sources:{A:{}},manual:{}};
  finish(null);await pending;
  assert.equal(h.nodes.get('trackProtectionSummary').textContent,'Unlocked');
  assert.doesNotMatch(h.nodes.get('trackProtectionStatus').textContent,/not changed|Saving/);
});
test('busy edits cannot change protection and unlock explicitly sends false',async()=>{
  const h=fixture();h.busy=true;await h.click('A');assert.equal(h.calls.length,0);
  h.busy=false;h.project.manual.track_locks={A:true};await h.click('A');
  assert.deepEqual(h.calls,[{slot:'A',locked:false}]);
});
