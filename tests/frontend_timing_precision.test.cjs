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

function timing(value='1.123456789',min='0',max='10'){const f=fixture('number',value,'any',min,max);f.field.dataset={scrubStep:'0.01'};f.doc.activeElement=f.field;return f;}
test('explicit timing scrub adds hundredths without snapping fractional frame origin',()=>{
 const f=timing();f.emit('pointerdown');f.emit('pointermove',{clientY:92});assert.equal(f.field.value,'1.143456789');assert.equal(f.calls.length,0);f.emit('pointerup');assert.deepEqual(f.calls,[{type:'input',value:'1.143456789'},{type:'change',value:'1.143456789'}]);
});
test('explicit timing ArrowUp/Down preserves fractional anchor and emits native-style changes',()=>{
 const f=timing();assert.equal(f.emit('keydown',{key:'ArrowUp'}).prevented,true);assert.equal(f.field.value,'1.133456789');assert.equal(f.emit('keydown',{key:'ArrowDown'}).prevented,true);assert.equal(f.field.value,'1.123456789');assert.equal(f.calls.length,4);
});
test('timing step keeps bounds and no-op boundary arrow does not create an edit',()=>{
 const f=timing('0');assert.equal(f.emit('keydown',{key:'ArrowDown'}).prevented,true);assert.equal(f.calls.length,0);assert.equal(scope.api.steppedValue(f.field,0,-50),'0');const g=timing('10');g.emit('keydown',{key:'ArrowUp'});assert.equal(g.calls.length,0);assert.equal(scope.api.steppedValue(g.field,9.999,5),'10');
});
test('timing wheel coalesces hundredths and Shift fine scrub keeps existing slowdown',()=>{
 const f=timing();f.emit('wheel',{deltaY:-100});f.emit('wheel',{deltaY:-100});assert.equal(f.field.value,'1.143456789');assert.equal(f.calls.length,0);f.flush();assert.equal(f.calls.length,2);
 const g=timing();g.emit('pointerdown');g.emit('pointermove',{clientY:60,shiftKey:true});g.emit('pointerup');assert.equal(g.field.value,'1.133456789');
});
test('Escape restores exact fractional timing without writes, including whole-width numeric drag',()=>{
 const f=timing();f.emit('pointerdown',{clientX:145});f.emit('pointermove',{clientY:60});assert.notEqual(f.field.value,'1.123456789');f.emit('keydown',{key:'Escape'});assert.equal(f.field.value,'1.123456789');assert.equal(f.calls.length,0);f.emit('pointerup');assert.equal(f.calls.length,0);
});
test('precision timing modifiers, readonly, disabled, busy and unfocused fields are not hijacked',()=>{
 for(const props of [{ctrlKey:true},{altKey:true},{metaKey:true}]){const f=timing();assert.equal(f.emit('keydown',{key:'ArrowUp',...props}).prevented,undefined);assert.equal(f.calls.length,0);}
 for(const prop of ['disabled','readOnly']){const f=timing();f.field[prop]=true;assert.equal(f.emit('keydown',{key:'ArrowUp'}).prevented,undefined);assert.equal(f.calls.length,0);}
 const b=timing();b.busy();assert.equal(b.emit('keydown',{key:'ArrowUp'}).prevented,undefined);const u=timing();u.doc.activeElement=null;assert.equal(u.emit('keydown',{key:'ArrowUp'}).prevented,undefined);
});
test('ordinary number inputs, Source in any, native steppers and invalid overrides stay unchanged',()=>{
 for(const step of ['any','0.1']){const f=fixture('number','1.2',step,'0','10');f.doc.activeElement=f.field;assert.equal(f.emit('keydown',{key:'ArrowUp'}).prevented,undefined);f.emit('pointerdown',{clientX:145});f.emit('pointermove',{clientY:60});f.emit('pointerup');assert.equal(f.calls.length,0);}
 for(const override of ['0','-1','garbage']){const f=timing();f.field.dataset.scrubStep=override;assert.equal(f.emit('keydown',{key:'ArrowUp'}).prevented,undefined);assert.equal(scope.api.steppedValue(f.field,1.123,1),'2');}
 const normal=fixture('number','1.2','.1','0','10');normal.field.dataset={scrubStep:'0.01'};assert.equal(scope.api.steppedValue(normal.field,1.2,1),'1.3');
});
test('context switch still prevents committing a staged fractional timing edit into another selection',()=>{
 const f=timing();f.emit('pointerdown');f.emit('pointermove',{clientY:60});f.revision();f.emit('pointerup');assert.equal(f.calls.length,0);
});
test('all four media/text timing inputs accept saved frame precision and opt into hundredth input steps',()=>{
 for(const [file,kind] of [['media-studio.js','media'],['text-studio.js','text']]){const source=fs.readFileSync('web/'+file,'utf8');for(const key of ['start','end'])assert.match(source,new RegExp('<input[^>]*data-'+kind+'="'+key+'"[^>]*step="any"[^>]*data-scrub-step="0.01"'));}
});
