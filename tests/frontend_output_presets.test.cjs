const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../web/studio-screens.js'),'utf8');
function harness(dir='ltr'){
  const document={readyState:'loading',documentElement:{dir},addEventListener(){}};
  const scope=vm.createContext({document,window:{addEventListener(){}},setInterval(){}});
  vm.runInContext(source.replace('  // A select shown as a row of buttons.','  globalThis.radioKeydown=radioKeydown;\n  // A select shown as a row of buttons.'),scope);
  const buttons=Array.from({length:5},(_,index)=>({index,disabled:false,closest(){return this;},click(){this.clicked=true;},focus(){this.focused=true;}}));
  function key(key,index,extra={}){let prevented=false;scope.radioKeydown({key,target:buttons[index],preventDefault(){prevented=true;},...extra},buttons);return prevented;}
  return {scope,buttons,key};
}
test('output radios use arrow, Home and End keys and move focus to the chosen option',()=>{
  for(const [key,index,expected] of [['ArrowRight',0,1],['ArrowLeft',0,4],['ArrowDown',4,0],['ArrowUp',0,4],['Home',3,0],['End',1,4]]){
    const h=harness();assert.equal(h.key(key,index),true);assert.equal(h.buttons[expected].clicked,true);assert.equal(h.buttons[expected].focused,true);
  }
});
test('output radios skip disabled options and leave modified or unrelated keys alone',()=>{
  const h=harness();h.buttons[1].disabled=true;assert.equal(h.key('ArrowRight',0),true);assert.equal(h.buttons[2].clicked,true);
  const idle=harness();for(const extra of [{ctrlKey:true},{altKey:true},{metaKey:true}])assert.equal(idle.key('ArrowRight',0,extra),false);
  assert.equal(idle.key('Tab',0),false);assert.ok(idle.buttons.every(button=>!button.clicked));
  idle.buttons.forEach(button=>button.disabled=true);assert.equal(idle.key('ArrowRight',0),false);
});
test('output radios follow reading direction for horizontal keys only',()=>{
  const h=harness('rtl');h.key('ArrowRight',0);assert.equal(h.buttons[4].clicked,true);
  const vertical=harness('rtl');vertical.key('ArrowDown',0);assert.equal(vertical.buttons[1].clicked,true);
});

test('Layout decorates the real framing controls once without creating duplicate composition buttons',()=>{
  const framing={dataset:{},open:false};
  const inputs=new Map(['cropX','cropY','cropZoom'].map(id=>[id,{id}]));
  const decorated=[];const syncers=new Set();
  const context=vm.createContext({
    $:selector=>selector==='#studioPanelFraming .framing-layout'?framing:inputs.get(selector.slice(1)),
    syncers,rangeValue:(input,format)=>decorated.push({input,format}),
  });
  const start=source.indexOf('  function initLayout()');
  const end=source.indexOf('  // ---------- Captions ----------',start);
  vm.runInContext(source.slice(start,end)+'\ninitLayout();initLayout();',context);
  assert.equal(framing.open,true);
  assert.deepEqual(decorated.map(row=>row.input.id),['cropX','cropY','cropZoom']);
  assert.equal(decorated[0].format(42),'42%');
  assert.equal(decorated[2].format(1.5,{max:3}),'150%');
  assert.equal(decorated[2].format(150,{max:300}),'150%');
  assert.equal(syncers.size,1);
  framing.open=false;for(const sync of syncers)sync();assert.equal(framing.open,true);
});
