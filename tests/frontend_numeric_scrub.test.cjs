const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const scope=vm.createContext({});
vm.runInContext(fs.readFileSync('web/numeric-scrub.js','utf8').replace(/^export /gm,'')+'\nthis.api={initNumericScrub,steppedValue};',scope);
function fixture(type='number',value='50',step='1',min='0',max='100') {
  const events=new Map(),windowEvents=new Map(),timers=new Map(),calls=[];let id=0,revision=1,busy=false,captured=null;
  const attach=map=>({addEventListener:(key,fn)=>map.set(key,[...(map.get(key)||[]),fn]),removeEventListener:(key,fn)=>map.set(key,(map.get(key)||[]).filter(x=>x!==fn))});
  const doc={...attach(events),documentElement:{dir:'ltr',classList:{add(){},remove(){}}},hidden:false};
  const win={...attach(windowEvents),Event:class{constructor(type){this.type=type;}},setTimeout:fn=>{timers.set(++id,fn);return id;},clearTimeout:key=>timers.delete(key)};
  const label={querySelector:selector=>selector==='output'?output:field};
  const field={type,value,step,min,max,isConnected:true,disabled:false,readOnly:false,
    matches:selector=>selector===':disabled'?false:selector.includes('input[type='+type+']'),
    closest:selector=>selector==='label'?label:null,getAttribute:()=>null,
    getBoundingClientRect:()=>({left:0,right:150}),focus(){doc.activeElement=this;},
    setPointerCapture:key=>captured=key,hasPointerCapture:key=>captured===key,releasePointerCapture:()=>captured=null,
    dispatchEvent:event=>calls.push({type:event.type,value:field.value})};
  const output={textContent:value+'%',matches:s=>s==='output',closest:()=>label};
  const controller=scope.api.initNumericScrub({document:doc,window:win,context:()=>revision,canEdit:()=>!busy});
  const emit=(type,extra={},map=events)=>{
    const e={target:field,button:0,pointerId:1,clientX:40,clientY:100,preventDefault(){this.prevented=true;},stopImmediatePropagation(){this.stopped=true;},...extra};
    for(const fn of map.get(type)||[])fn(e);return e;
  };
  const flush=()=>{for(const [key,fn] of [...timers]){timers.delete(key);fn();}};
  return {doc,win,field,output,calls,controller,emit,flush,windowEvents,captured:()=>captured,revision:()=>revision++,busy:()=>busy=true};
}
test('vertical drag respects step and bounds, emits one edit only on release, and repeats cleanly',()=>{
  const f=fixture();f.doc.activeElement=f.field;f.emit('pointerdown');
  f.emit('pointermove',{clientY:80});assert.equal(f.field.value,'55');assert.equal(f.calls.length,0);assert.equal(f.captured(),1);
  f.emit('pointermove',{clientY:60});f.emit('pointerup',{clientY:60});
  assert.deepEqual(f.calls,[{type:'input',value:'60'},{type:'change',value:'60'}]);assert.equal(f.captured(),null);
  f.emit('pointerdown');f.emit('pointermove',{clientY:800});f.emit('pointerup');assert.equal(f.field.value,'0');
});
test('a click preserves typing, decimal steps are exact, and Shift slows dragging without invalid fractional steps',()=>{
  const f=fixture('number','1.2','0.1','0','2');f.emit('pointerdown');f.emit('pointerup');assert.equal(f.calls.length,0);
  f.emit('pointerdown');f.emit('pointermove',{clientY:60,shiftKey:true});f.emit('pointerup');assert.equal(f.field.value,'1.3');
  assert.equal(scope.api.steppedValue(f.field,1.3,100),'2');
});
for(const reason of ['Escape','pointercancel','lostpointercapture','focusout','blur'])test(reason+' cancels an in-flight drag without a save or stuck capture',()=>{
  const f=fixture();f.emit('pointerdown');f.emit('pointermove',{clientY:60});
  if(reason==='Escape')f.emit('keydown',{key:'Escape'});else f.emit(reason,{},reason==='blur'?f.windowEvents:undefined);
  assert.equal(f.field.value,'50');assert.equal(f.calls.length,0);assert.equal(f.captured(),null);
  f.emit('pointerup');assert.equal(f.calls.length,0);
});
test('wheel only intercepts an intentionally focused numeric field and coalesces a burst',()=>{
  const f=fixture();assert.equal(f.emit('wheel',{deltaY:-100}).prevented,undefined);assert.equal(f.field.value,'50');
  f.doc.activeElement=f.field;f.emit('wheel',{deltaY:-100});f.emit('wheel',{deltaY:-100});assert.equal(f.field.value,'52');assert.equal(f.calls.length,0);
  f.flush();assert.equal(f.calls.length,2);assert.equal(f.calls[1].value,'52');
  assert.equal(f.emit('wheel',{deltaY:-100,ctrlKey:true}).prevented,undefined);
  assert.equal(f.emit('wheel',{target:{matches:()=>false},deltaY:-100}).prevented,undefined);
});
test('wheel blur commits once, Escape cancels, and context changes cannot commit into another clip',()=>{
  const f=fixture();f.doc.activeElement=f.field;f.emit('wheel',{deltaY:100});f.emit('focusout');f.flush();assert.equal(f.calls.length,2);
  f.emit('wheel',{deltaY:100});f.emit('keydown',{key:'Escape'});f.flush();assert.equal(f.field.value,'49');assert.equal(f.calls.length,2);
  f.emit('pointerdown');f.emit('pointermove',{clientY:60});f.revision();f.emit('pointerup');assert.equal(f.calls.length,2);
});
test('disabled, readonly, busy controls and native number steppers remain untouched',()=>{
  for(const prop of ['disabled','readOnly']){const f=fixture();f.field[prop]=true;f.emit('pointerdown');f.emit('pointermove',{clientY:40});f.emit('pointerup');assert.equal(f.field.value,'50');}
  const f=fixture();f.busy();f.doc.activeElement=f.field;assert.equal(f.emit('wheel',{deltaY:100}).prevented,undefined);
  const g=fixture();g.emit('pointerdown',{clientX:145});g.emit('pointermove',{clientY:40});g.emit('pointerup');assert.equal(g.field.value,'50');
});
test('range value output supports vertical drag, preserves units, and leaves the native slider alone',()=>{
  const f=fixture('range','.12','.01','.01','1');f.output.textContent='12%';
  f.emit('pointerdown');f.emit('pointermove',{clientY:80});f.emit('pointerup');assert.equal(f.field.value,'.12');
  f.emit('pointerdown',{target:f.output});f.emit('pointermove',{clientY:92});assert.equal(f.output.textContent,'14%');
  f.emit('pointerup');assert.equal(f.calls.length,2);assert.equal(f.field.value,'0.14');
});
