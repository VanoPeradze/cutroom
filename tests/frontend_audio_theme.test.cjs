const test=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const vm=require('node:vm');const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../web/audio-meter.js'),'utf8');
function harness(extra={}) { return vm.runInNewContext(source.replaceAll('export ','')+'\n({AudioThresholdView,audioThresholdPaint})',extra); }
test('audio plot uses semantic canvas colors and proportional fonts with no DOM dependency',()=>{
 const {audioThresholdPaint}=harness();const p=audioThresholdPaint({});
 assert.equal(p.background,'#191b1f');assert.equal(p.marker,'#efb28d');assert.match(p.font,/Geist/);assert.doesNotMatch(source,/monospace|Consolas/);
});
test('audio plot resolves the live light theme instead of painting a dark rectangle',()=>{
 const values={'--timeline-bg':'#b5b9bf','--timeline-text':'#333c48','--timeline-selected':'#82462a','--timeline-danger':'#902e3c'};
 const {audioThresholdPaint}=harness({getComputedStyle:()=>({getPropertyValue:k=>values[k]||''})});const p=audioThresholdPaint({});
 assert.equal(p.background,values['--timeline-bg']);assert.equal(p.text,values['--timeline-text']);assert.equal(p.marker,values['--timeline-selected']);assert.equal(p.danger,values['--timeline-danger']);
});
test('theme and font readiness repaint only appearance while measurements remain unchanged',()=>{
 let changed,ready,observed,draws=0;const root={};
 const {AudioThresholdView}=harness({window:{devicePixelRatio:1},ResizeObserver:class{observe(){}},MutationObserver:class{constructor(fn){changed=fn}observe(node,options){observed={node,options}}},document:{documentElement:root,fonts:{ready:{then(fn){ready=fn}}}}});
 AudioThresholdView.prototype.draw=function(){draws++};
 const view=new AudioThresholdView({getContext:()=>({}),addEventListener(){}});
 view.setProfile({duration:3,waveform:[{start:0,end:1,rms_dbfs:-60},{start:1,end:2,rms_dbfs:-55},{start:2,end:3,rms_dbfs:-20}]});
 const before=JSON.stringify(view.estimate());const threshold=view.threshold;const profile=view.profile;
 changed([{attributeName:'data-theme'}]);ready();
 assert.equal(draws,3);assert.equal(observed.node,root);assert.deepEqual([...observed.options.attributeFilter],['data-theme']);
 assert.equal(JSON.stringify(view.estimate()),before);assert.equal(view.threshold,threshold);assert.equal(view.profile,profile);
});
