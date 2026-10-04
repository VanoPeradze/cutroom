const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const test=require('node:test');
const context=vm.createContext({Float32Array,Math});
vm.runInContext(fs.readFileSync('web/chroma-preview.js','utf8').replace(/^export /gm,'')+'\nthis.keyPixels=keyPixels;',context);
const settings={color:'#00FF00',tolerance:.12,edge_softness:.08};
const frame=rgb=>new Uint8ClampedArray(Array.from({length:25},()=>[...rgb,255]).flat());
test('live preview preserves red/white/dark foreground and reveals underlying footage through green',()=>{
  const green=frame([0,255,0]);context.keyPixels(green,5,5,settings);assert.equal(green[51],0);
  for(const rgb of [[255,0,0],[220,220,220],[20,20,20]]) {
    const data=frame(rgb);context.keyPixels(data,5,5,settings);assert.equal(data[51],255);assert.deepEqual([...data.slice(48,51)],rgb);
  }
});
test('maximum saved tolerance removes the subject too; defaults recover without changing the input setting',()=>{
  const bad={...settings,tolerance:1,edge_softness:.61};const data=frame([255,0,0]);
  context.keyPixels(data,5,5,bad);assert.equal(data[51],0);
  const recovered=frame([255,0,0]);context.keyPixels(recovered,5,5,settings);assert.equal(recovered[51],255);assert.equal(bad.tolerance,1);
});
test('custom key colors and hard edges use the same saved threshold controls',()=>{
  const blue=frame([0,0,255]);context.keyPixels(blue,5,5,{...settings,color:'#0000FF',edge_softness:0});assert.equal(blue[51],0);
  const green=frame([0,255,0]);context.keyPixels(green,5,5,{...settings,color:'#0000FF',edge_softness:0});assert.equal(green[51],255);
});
