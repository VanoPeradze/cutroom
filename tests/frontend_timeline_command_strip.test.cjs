const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'..'),read=n=>fs.readFileSync(path.join(root,n),'utf8'),js=read('web/timeline-command-strip.js'),css=read('web/timeline-command-strip.css');
const mod=import('data:text/javascript;base64,'+Buffer.from(js).toString('base64'));
for(const [width,expected] of [[0,'wide'],[320,'small'],[390,'small'],[599,'small'],[600,'medium'],[768,'medium'],[899,'medium'],[900,'wide'],[1440,'wide']]){
  test('native toolbar mode at '+width,async()=>assert.equal((await mod).stripMode(width),expected));
}
const rows=[{top:31,height:60},{top:91,height:33},{top:124,height:45},{top:169,height:36},{top:205,height:50},{top:255,height:60}];
for(const height of [62,99,134,156,211,310,360]){
  for(const at of [-4,0,4.5,33,117,999]){
    test('track page clamps, counts true partially visible lanes and advances '+height+' / '+at,async()=>{
      const {trackWindow}=await mod,max=Math.max(0,315-height),pos=Math.max(0,Math.min(at,max));
      const g=trackWindow([rows[4],rows[1],{top:NaN,height:33},rows[5],rows[3],{top:0,height:-2},rows[0],rows[2]],at,height,315);
      assert.equal(g.total,6);assert.equal(g.at,pos);assert.equal(g.max,max);
      const a=rows.map((r,i)=>r.top+r.height>pos+.5&&r.top<pos+height-.5?i+1:0).filter(Boolean);
      assert.equal(g.first,a[0]||0);assert.equal(g.last,a.at(-1)||0);
      assert(g.up>=0&&g.down<=max&&g.up<=pos&&g.down>=pos);
      if(pos>1)assert(g.up<pos);if(pos<max-1)assert(g.down>pos);
    });
  }
}
for(const [name,patch,want] of [
 ['native wheel',{deltaY:18},43],['line wheel',{deltaY:2,deltaMode:1},57],['page wheel',{deltaY:1,deltaMode:2},125],
 ['up through top',{deltaY:-1000},0],['down through bottom',{deltaY:4000},205],['no vertical intent',{deltaY:0},null],
 ['horizontal',{deltaY:8,deltaX:9},null],['equal diagonal',{deltaY:8,deltaX:-8},null],['shift',{shiftKey:true},null],
 ['zoom',{ctrlKey:true},null],['pinch/meta',{metaKey:true},null],['alternate',{altKey:true},null],['prior owner',{defaultPrevented:true},null],['invalid',{deltaY:NaN},null]
])test('track label wheel: '+name,async()=>assert.equal((await mod).railWheel({deltaX:0,deltaY:1,...patch},{scrollTop:25,clientHeight:100,scrollHeight:305}),want));
test('let a parent scroll once the rail has no more rows',async()=>{const {railWheel}=await mod;for(const [scrollTop,deltaY] of [[0,-15],[205,50]])assert.equal(railWheel({deltaY},{scrollTop,clientHeight:100,scrollHeight:305}),null);});
test('empty lanes never claim a visible track',async()=>{const {trackWindow}=await mod;assert.equal(trackWindow([],0,100,100).last,0);assert.equal(trackWindow([{top:180,height:20}],0,80,240).first,0);});
test('module and stylesheet are last independent console refinements',()=>{const html=read('web/index.html');for(const ext of ['css','js'])assert(html.indexOf('/assets/timeline-command-strip.'+ext)>html.indexOf('/assets/studio-console.'+ext));});
test('existing controls are moved/replaced at exact home anchors, never simulated',()=>{for(const id of ['timelineTargetField','manualDelete','reviewSourceButton','closeTimelineGaps','editorMoreButton'])assert(js.includes("'"+id+"'"));assert.match(js,/toolbar\.insertBefore\(node,mark\)/);assert.match(js,/createComment/);assert.match(js,/move\)parent\.append\(node\)/);assert.doesNotMatch(js,/\bfetch\s*\(|XMLHttpRequest|localStorage|sessionStorage|innerHTML|cloneNode|\.click\s*\(|\.play\s*\(|\.pause\s*\(|applyManualEdit/);});
test('native modal, name, visible trigger, language/focus routes, cleanup',()=>{for(const text of ['aria-controls','aria-haspopup','aria-expanded','aria-labelledby','dialog.showModal()','groups.actions.body.contains(b)','preventScroll:true','frame!==null','--timeline-command-min-height','timelineStripController','בקרי ציר הזמן'])assert(js.includes(text));assert.match(css,/forced-colors:active/);assert.match(css,/\.track-pager-count[\s\S]*?unicode-bidi:isolate/);});
test('screen width controls are effective only on the full editor; no source-review canvas resizing',()=>{assert.match(css,/#studioTimelineDock \{ --compact-track-rail/);assert.doesNotMatch(css,/canvas\s*\{|\.preview-|#previewStage|position:\s*absolute[^}]+track-header/);});
