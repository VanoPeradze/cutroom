const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

function harness({horizontal=false, gain=-24, edit}={}) {
  const document={activeElement:null};
  const context=vm.createContext({window:{},document,performance:{now:()=>0},setTimeout:()=>1,clearTimeout(){}});
  const source=fs.readFileSync(path.join(__dirname,'../web/media-studio.js'),'utf8').replace(/^export /gm,'');
  vm.runInContext(source+'\nglobalThis.api={MediaStudio,faderGain,faderPointerGain};',context);
  let project={id:'one',manual:{audio_mixer:{source_db:gain,master_db:gain},media_clips:[]}},externalBusy=false;
  const control={states:new Set(),styles:new Map()};
  control.classList={add:name=>control.states.add(name),remove:name=>control.states.delete(name),toggle(name,on){if(on)control.states.add(name);else control.states.delete(name);}};
  control.style={setProperty:(name,value)=>control.styles.set(name,value)};
  const input={value:String(gain),dataset:{mix:horizontal?'master_db':'source_db',mixOrientation:horizontal?'horizontal':'vertical'},
    closest:()=>control,getBoundingClientRect:()=>({left:100,top:100,bottom:276,width:176,height:176}),
    focus(){document.activeElement=input;},setPointerCapture(id){this.captured=id;},hasPointerCapture(id){return this.captured===id;},releasePointerCapture(){this.captured=null;}};
  const studio=Object.create(context.api.MediaStudio.prototype);
  Object.assign(studio,{options:{project:()=>project,busy:()=>externalBusy,preview(){},edit:edit||(async()=>project)},
    pending:new Map(),overrides:new Map(),players:new Map(),status:{textContent:''},render(){},renderMixer(){}});
  const event=(changes={})=>({pointerId:7,button:0,clientX:188,clientY:188,shiftKey:false,preventDefault(){this.prevented=true;},...changes});
  return {studio,input,control,event,api:context.api,project:()=>project,activate:value=>project=value,busy:value=>externalBusy=value};
}

test('fader gain stays in the exported domain and fine pointer travel is ten times slower',()=>{
  const {api}=harness();
  assert.equal(api.faderGain(-100),-60);assert.equal(api.faderGain(100),12);
  assert.equal(api.faderGain(-7.26),-7.3);
  assert.equal(api.faderPointerGain(-24,22,154),-13.7);
  assert.equal(api.faderPointerGain(-24,22,154,true),-23);
  assert.equal(api.faderPointerGain(0,1000,154),12);
});

test('grabbing the cap preserves the grab point, captures the pointer and ignores other pointers',()=>{
  const {studio,input,control,event}=harness();
  studio.startFaderDrag(event({clientY:194}),input);
  assert.equal(input.value,'-24');assert.equal(studio.pending.size,0,'grabbing a cap must not jump');
  assert.equal(input.captured,7);assert.equal(control.states.has('is-dragging'),true);
  studio.moveFaderDrag(event({pointerId:8,clientY:172}));assert.equal(input.value,'-24');
  studio.moveFaderDrag(event({clientY:172}));assert.equal(input.value,'-13.7');
  assert.equal(studio.pending.get('mixer').source_db,-13.7);
  studio.endFaderDrag(event());assert.equal(input.captured,null);assert.equal(studio.faderDrag,null);
  assert.equal(control.states.has('is-dragging'),false);
});

test('rail clicks seek, Shift starts relative precision, and toggling Shift mid-drag does not jump',()=>{
  const normal=harness();normal.studio.startFaderDrag(normal.event({clientY:111}),normal.input);
  assert.equal(normal.input.value,'12');normal.studio.endFaderDrag();
  const fine=harness();fine.studio.startFaderDrag(fine.event({clientY:111,shiftKey:true}),fine.input);
  assert.equal(fine.input.value,'-24','Shift-click preserves the current level');
  fine.studio.moveFaderDrag(fine.event({clientY:89,shiftKey:true}));assert.equal(fine.input.value,'-23');
  const changed=harness();changed.studio.startFaderDrag(changed.event(),changed.input);
  changed.studio.moveFaderDrag(changed.event({clientY:166}));assert.equal(changed.input.value,'-13.7');
  changed.studio.moveFaderDrag(changed.event({clientY:144,shiftKey:true}));assert.equal(changed.input.value,'-12.7');
  changed.studio.moveFaderDrag(changed.event({clientY:122}));assert.equal(changed.input.value,'-2.4');
});

test('Master uses the same gain domain with horizontal pointer travel',()=>{
  const {studio,input,event,control}=harness({horizontal:true});
  studio.startFaderDrag(event(),input);studio.moveFaderDrag(event({clientX:210}));
  assert.equal(input.value,'-13.7');assert.equal(studio.pending.get('mixer').master_db,-13.7);
  assert.equal(control.styles.get('--fader-from-left'),`${(-13.7+60)/72*100}%`);
});

test('keyboard coarse/fine, page, endpoints and Escape preserve native focus and saved gain',()=>{
  const {studio,input,event}=harness({gain:0});
  const key=(name,shiftKey=false)=>{const item=event({key:name,shiftKey});studio.faderKeydown(item,input);assert.equal(item.prevented,true);};
  key('ArrowUp');assert.equal(input.value,'0.5');key('ArrowDown',true);assert.equal(input.value,'0.4');
  key('PageDown');assert.equal(input.value,'-5.6');key('Home');assert.equal(input.value,'-60');
  key('ArrowDown');assert.equal(input.value,'-60');key('End');assert.equal(input.value,'12');
  key('ArrowRight',true);assert.equal(input.value,'12');
  studio.setFaderGain(input,-24);studio.startFaderDrag(event(),input);
  studio.moveFaderDrag(event({clientY:166}));assert.equal(input.value,'-13.7');
  key('Escape');assert.equal(input.value,'-24');assert.equal(studio.faderDrag,null);
  assert.equal(studio.pending.get('mixer').source_db,-24);
});

test('external work blocks new gestures, stops active gestures and never writes into a new project',()=>{
  const h=harness();h.busy(true);h.studio.startFaderDrag(h.event(),h.input);
  assert.equal(h.studio.faderDrag,undefined);assert.equal(h.input.captured,undefined);
  h.studio.faderKeydown(h.event({key:'ArrowUp'}),h.input);assert.equal(h.studio.pending.size,0);
  h.busy(false);h.studio.startFaderDrag(h.event(),h.input);h.busy(true);
  h.studio.moveFaderDrag(h.event({clientY:166}));assert.equal(h.studio.pending.size,0);assert.equal(h.input.captured,null);
  h.busy(false);h.studio.startFaderDrag(h.event(),h.input);
  h.activate({id:'two',manual:{audio_mixer:{source_db:-24}}});
  h.studio.moveFaderDrag(h.event({clientY:166}));assert.equal(h.studio.pending.size,0);assert.equal(h.studio.faderDrag,null);
});

test('Escape during external work or after a project switch only releases the gesture',()=>{
  for(const switchProject of [false,true]) {
    const h=harness();h.studio.startFaderDrag(h.event(),h.input);
    h.studio.moveFaderDrag(h.event({clientY:166}));h.studio.pending.clear();
    if(switchProject)h.activate({id:'two',manual:{audio_mixer:{source_db:0}}});else h.busy(true);
    h.studio.faderKeydown(h.event({key:'Escape'}),h.input);
    assert.equal(h.studio.faderDrag,null);assert.equal(h.input.captured,null);
    assert.equal(h.studio.pending.size,0,'an interrupted drag cannot add rollback edits to locked/new work');
  }
});

test('revoked pointer capture cannot leave a stale drag or a partially applied rail click',()=>{
  const h=harness();h.input.setPointerCapture=()=>{throw new Error('Pointer is no longer active');};
  assert.doesNotThrow(()=>h.studio.startFaderDrag(h.event({clientY:111}),h.input));
  assert.equal(h.studio.faderDrag,null);assert.equal(h.studio.pending.size,0);
  assert.equal(h.control.states.has('is-dragging'),false);assert.equal(h.input.value,'-24');
});

test('a slow multi-move gesture survives its own async save and persists the final value on reopening',async()=>{
  let resolveFirst,manualBusy=false;const first=new Promise(resolve=>resolveFirst=resolve),calls=[];
  const h=harness({edit:async(action,patch)=>{
    manualBusy=true;calls.push({action,patch});if(calls.length===1)await first;
    const project=h.project();const saved={...project,manual:{...project.manual,audio_mixer:{...project.manual.audio_mixer,...patch}}};
    h.activate(saved);manualBusy=false;return saved;
  }});
  // Match the real app gate: its own mixer save is allowed, external jobs are not.
  h.studio.options.busy=()=>Boolean(manualBusy&&!h.studio.saving);
  h.studio.startFaderDrag(h.event(),h.input);h.studio.moveFaderDrag(h.event({clientY:166}));
  const saving=h.studio.flush();await Promise.resolve();await Promise.resolve();
  assert.equal(manualBusy,true);assert.equal(h.input.captured,7);
  h.studio.moveFaderDrag(h.event({clientY:144}));assert.equal(h.input.value,'-3.4');
  h.studio.moveFaderDrag(h.event({clientY:122,shiftKey:true}));assert.equal(h.input.value,'-2.4');
  resolveFirst();assert.equal(await saving,true);
  assert.equal(calls.length,2,'moves during a save coalesce into the next persisted patch');
  assert.equal(h.input.captured,7,'async rendering must not drop the drag');
  h.studio.endFaderDrag(h.event());assert.equal(h.input.captured,null);
  const reopened=harness({gain:h.project().manual.audio_mixer.source_db});
  assert.equal(reopened.input.value,'-2.4');assert.equal(h.studio.pending.size,0);
  assert.equal(calls[0].action,'set_audio_mixer');assert.equal(calls[1].patch.source_db,-2.4);
});
