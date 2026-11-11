const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const info = (engine='local', extra={}) => ({engine, cloud_ready:true, account_id:'a'.repeat(32), model:'@cf/openai/whisper-large-v3-turbo', consent_scope:'review-1', disclosure:'Provider privacy and pricing', ...extra});
function harness(overrides={}) {
  const nodes=new Map(), calls=[], updates=[];
  const node=id=>{
    if(!nodes.has(id)) nodes.set(id,{id,value:'',checked:false,hidden:false,disabled:false,open:false,dataset:{},events:{},
      addEventListener(type,handler){this.events[type]=handler;},
      async fire(type){let prevented=false;await this.events[type]?.({target:this,preventDefault(){prevented=true;}});return prevented;},
      showModal(){this.open=true;},close(){this.open=false;this.events.close?.();}});
    return nodes.get(id);
  };
  const document={getElementById:node}, scope=vm.createContext({});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/transcription-engine.js'),'utf8').replace(/^export /gm,''),scope);
  const controller=scope.initTranscriptionEngine({document,busy:()=>false,pause:()=>{},changed:async value=>updates.push(value),
    api:async(url,options)=>{calls.push({url,body:options?JSON.parse(options.body):null});return info(options?JSON.parse(options.body).engine:'local');},...overrides});
  controller.setStatus(info());
  const open=async()=>{controller.open();await new Promise(resolve=>setImmediate(resolve));};
  const choose=async value=>{node('transcriptionEngine').value=value;await node('transcriptionEngine').fire('change');};
  return {node,calls,updates,controller,open,choose,summary:scope.processingSummary};
}
test('explicit local speech summary stays local with cloud Story AI',()=>{
  const h=harness(), summary=h.summary(info('local'),{mode:'own',provider:'groq'});
  assert.equal(summary.cloudSpeech,false);assert.equal(summary.speech,'this computer');assert.equal(summary.story,'Groq');
  h.controller.setStoryConnection({mode:'own',provider:'groq'});
  assert.match(h.node('homePrivacyNote').textContent,/Transcription: this computer. Story AI: Groq/);
});
test('opening and choosing cloud is not consent, save or an upload',async()=>{
  const h=harness();await h.open();await h.choose('cloud');
  assert.equal(h.node('transcriptionConsent').checked,false);assert.equal(h.node('saveTranscription').disabled,true);
  await h.node('transcriptionForm').fire('submit');
  assert.equal(h.calls.filter(row=>row.body).length,0);assert.equal(h.updates.length,0);
});
test('explicit scoped cloud consent saves locally and clears checkbox',async()=>{
  const h=harness();await h.open();await h.choose('auto');
  h.node('transcriptionConsent').checked=true;await h.node('transcriptionConsent').fire('change');
  await h.node('transcriptionForm').fire('submit');
  assert.deepEqual(h.calls.at(-1).body,{engine:'auto',consent:true,consent_scope:'review-1'});
  assert.equal(h.calls.at(-1).url,'/api/transcription/engine');assert.equal(h.updates.length,1);
  assert.equal(h.node('transcriptionDialog').open,false);assert.equal(h.node('transcriptionConsent').checked,false);
  assert.equal(JSON.stringify(h.calls).includes('API_TOKEN'),false);
});
test('destination refresh and engine changes clear pending consent',async()=>{
  let current=info();const h=harness({api:async()=>current});await h.open();await h.choose('cloud');
  h.node('transcriptionConsent').checked=true;
  h.controller.setStatus(info('local',{consent_scope:'review-2',account_id:'b'.repeat(32)}));
  assert.equal(h.node('transcriptionConsent').checked,false);assert.match(h.node('transcriptionStatus').textContent,/destination changed/);
  h.node('transcriptionConsent').checked=true;await h.choose('auto');assert.equal(h.node('transcriptionConsent').checked,false);
});
test('missing credentials or failed refresh cannot enable cloud',async()=>{
  const h=harness({api:async()=>{throw Error('Offline');}});await h.open();await h.choose('cloud');
  h.node('transcriptionConsent').checked=true;await h.node('transcriptionForm').fire('submit');
  assert.equal(h.updates.length,0);assert.equal(h.node('saveTranscription').disabled,true);
});
test('local save has no cloud consent fields',async()=>{
  const h=harness();await h.open();await h.choose('local');await h.node('transcriptionForm').fire('submit');
  assert.deepEqual(h.calls.at(-1).body,{engine:'local'});
});
test('cancel and Escape clear consent without saving',async()=>{
  const h=harness();await h.open();await h.choose('cloud');h.node('transcriptionConsent').checked=true;
  await h.node('cancelTranscription').fire('click');assert.equal(h.node('transcriptionConsent').checked,false);
  assert.equal(h.calls.filter(row=>row.body).length,0);
  await h.open();h.node('transcriptionConsent').checked=true;h.node('transcriptionDialog').close();
  assert.equal(h.node('transcriptionConsent').checked,false);
});
test('active job blocks all engine changes',async()=>{
  const h=harness({busy:()=>true});await h.open();await h.node('transcriptionForm').fire('submit');
  assert.equal(h.calls.filter(row=>row.body).length,0);assert.match(h.node('transcriptionStatus').textContent,/Wait for active/);
});
test('double submit dispatches once; Escape cannot dismiss an unresolved save',async()=>{
  let resolve;const calls=[];const h=harness({api:async(url,options)=>{if(!options)return info();calls.push(options);return new Promise(done=>{resolve=done;});}});
  await h.open();const saving=h.node('transcriptionForm').fire('submit');await h.node('transcriptionForm').fire('submit');
  assert.equal(calls.length,1);assert.equal(await h.node('transcriptionDialog').fire('cancel'),true);
  await h.node('cancelTranscription').fire('click');assert.equal(h.node('transcriptionDialog').open,true);
  resolve(info());await saving;assert.equal(h.node('transcriptionDialog').open,false);
});
test('late refresh after dismissal cannot change saved state or announce success',async()=>{
  let resolve;const h=harness({api:()=>new Promise(done=>{resolve=done;})});h.controller.open();
  await h.node('cancelTranscription').fire('click');resolve(info('cloud'));await new Promise(done=>setImmediate(done));
  assert.equal(h.node('transcriptionDialog').open,false);assert.equal(h.updates.length,0);
  assert.match(h.node('transcriptionCurrent').textContent,/this computer/);
});
test('server route refreshed on reopen replaces stale draft selection',async()=>{
  const h=harness({api:async()=>info('auto')});await h.open();assert.equal(h.node('transcriptionEngine').value,'auto');
  assert.equal(h.node('transcriptionFallbackNote').hidden,false);assert.equal(h.node('transcriptionConsent').checked,false);
});
test('markup exposes explicit future-job consent, provider links, independent Story AI and no secret input',()=>{
  const html=fs.readFileSync(path.join(__dirname,'../web/index.html'),'utf8');
  const dialog=html.slice(html.indexOf('<dialog id="transcriptionDialog"'),html.indexOf('<dialog id="aiConnectionDialog"'));
  assert.match(dialog,/future transcription jobs until I change/);assert.match(dialog,/possible charges/);
  assert.match(dialog,/api\.cloudflare\.com/);assert.match(dialog,/Story AI has a separate connection/);
  assert.match(dialog,/Privacy and retention/);assert.match(dialog,/role="status"/);assert.doesNotMatch(dialog,/type="password"/);
});
