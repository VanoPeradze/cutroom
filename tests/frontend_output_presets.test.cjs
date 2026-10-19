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
