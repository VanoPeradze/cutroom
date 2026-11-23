const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../web/timeline.js'), 'utf8').replace(/^export /gm, '');
const plain = value => JSON.parse(JSON.stringify(value));
const tick = async () => { await Promise.resolve(); await Promise.resolve(); };

function fixture(kind = 'video') {
  const listeners = {}, requests = [], writes = [], captures = new Set(), selected = [];
  const canvas = {style:{},attrs:{},title:'Timeline',getContext:()=>({}),
    setAttribute(key,value){this.attrs[key]=value;},addEventListener(key,fn){listeners[key]=fn;},focus(){},
    getBoundingClientRect:()=>({left:10,top:20,width:600}),
    setPointerCapture:id=>captures.add(id),hasPointerCapture:id=>captures.has(id),releasePointerCapture:id=>captures.delete(id)};
  const scroll = {clientWidth:600,clientHeight:300,scrollLeft:0,scrollTop:0,closest:()=>null,addEventListener(){}};
  const context = vm.createContext({window:{devicePixelRatio:1},ResizeObserver:class{observe(){}},requestAnimationFrame:()=>1,cancelAnimationFrame(){}});
  vm.runInContext(source+'\nglobalThis.TimelineView=TimelineView;',context);
  const isText=['title','caption'].includes(kind),clip={id:isText?'text_one':'media_one',asset_id:'asset',start:2,end:6,source_start:2,video_source_start:.75,speed:.5,enabled:false,...(isText?{kind,text:'Title'}:{})};
  const project={id:'synthetic',revision:1,settings:{fps:30},sources:{A:{duration:12}},draft:{keep_ranges:[{start:0,end:12}]},
    assets:{asset:{kind,status:'ready',duration:20}},manual:{sequence:{duration:12},source_tracks:{A:[{id:'a',start:0,end:12,source_start:0}],B:[]},media_clips:isText?[]:[clip],text_clips:isText?[clip]:[]}};
  const timeline=new context.TimelineView(canvas,scroll,()=>{throw Error('Host owns navigation');},null,()=>writes.push('source'),{
    getTrackClips:(p,slot)=>p.manual.source_tracks[slot],
    mediaSourceIssue:()=>'',onMediaSourceOpen:async(id,time)=>{requests.push({id,time});return true;},
    onMediaSelect:id=>selected.push(id),onMediaAction:(action,detail)=>writes.push({action,...detail}),
    onMediaEdit:(id,patch)=>writes.push({id,patch}),onMediaPreview(){},
  });
  timeline.project=project;timeline.mediaSelection=clip.id;timeline.playhead=1.2;timeline.fit=()=>timeline.fitCount=(timeline.fitCount||0)+1;
  const point=(time=3.1234567,extra={})=>({button:0,pointerId:1,clientX:10+time*timeline.geometry().px,
    clientY:20+timeline.mediaRows()[0].top+24,preventDefault(){this.prevented=true;},stopPropagation(){this.stopped=true;},...extra});
  return{timeline,canvas,scroll,listeners,project,clip,requests,writes,selected,point};
}

for(const tool of ['select','move'])test(`${tool} double-click delegates exact clicked video time with no edit/fit/clock approximation`,async()=>{
  const h=fixture(),before=JSON.stringify(h.project);h.timeline.tool=tool;const e=h.point();h.listeners.dblclick(e);await tick();
  assert.equal(h.requests.length,1);assert.equal(h.requests[0].id,h.clip.id);assert.ok(Math.abs(h.requests[0].time-3.1234567)<1e-12);
  assert.equal(e.prevented,true);assert.equal(e.stopped,true);assert.equal(h.timeline.fitCount,undefined);assert.equal(h.timeline.editPending,false);
  assert.equal(h.timeline.playhead,1.2,'host, not timeline, owns the edited seek');assert.equal(JSON.stringify(h.project),before);assert.deepEqual(h.writes,[]);
});

test('disabled/covered video still delegates read-only original source when host permits',async()=>{
  const h=fixture();h.project.manual.media_clips.push({...h.clip,id:'cover'});await h.timeline.openMediaSourceAt(h.clip.id,3);
  assert.deepEqual(h.requests,[{id:h.clip.id,time:3}]);assert.equal(h.clip.enabled,false);assert.equal(h.project.manual.media_clips.length,2);assert.deepEqual(h.writes,[]);
});

for(const issue of ['Wait for pending edits.','Switch to Edited video.','Picture is past source duration.','Source is not ready.'])test(`blocked video double-click reports reason, never silently falls through to Fit: ${issue}`,async()=>{
  const h=fixture();h.timeline.mediaSourceIssue=()=>issue;h.listeners.dblclick(h.point());await tick();
  assert.deepEqual(h.requests,[]);assert.equal(h.canvas.title,issue);assert.equal(h.timeline.fitCount,undefined);assert.deepEqual(h.writes,[]);
});

for(const missing of ['mediaSourceIssue','onMediaSourceOpen'])test(`legacy host without ${missing} retains existing Fit behavior`,async()=>{
  const h=fixture();h.timeline[missing]=null;h.listeners.dblclick(h.point());await tick();assert.equal(h.timeline.fitCount,1);assert.deepEqual(h.requests,[]);
});

for(const tool of ['blade','remove_between','slip','range'])test(`${tool} retains its previous double-click behavior, not source matching`,async()=>{
  const h=fixture();h.timeline.tool=tool;h.listeners.dblclick(h.point());await tick();assert.deepEqual(h.requests,[]);assert.equal(h.timeline.fitCount,tool==='range'?1:undefined);
});

for(const kind of ['audio','image','title','caption'])test(`${kind} never redirects into a video source or source A/B`,async()=>{
  const h=fixture(kind);h.listeners.dblclick(h.point());await tick();assert.equal(h.timeline.fitCount,1);assert.deepEqual(h.requests,[]);assert.deepEqual(h.writes,[]);
});

test('automatic caption double-click still opens its own caption inspector',async()=>{
  const h=fixture(),opened=[];h.timeline.captionAtEvent=()=>({item:{id:'automatic'}});h.timeline.onCaptionOpen=id=>opened.push(id);
  h.listeners.dblclick(h.point());await tick();assert.deepEqual(opened,['automatic']);assert.deepEqual(h.requests,[]);assert.equal(h.timeline.fitCount,undefined);
});

for(const modifier of ['altKey','ctrlKey','metaKey','shiftKey'])test(`${modifier} is not stolen by the new plain double-click action`,async()=>{
  const h=fixture();h.listeners.dblclick(h.point(3,{[modifier]:true}));await tick();assert.equal(h.timeline.fitCount,1);assert.deepEqual(h.requests,[]);
});

for(const guard of ['editPending','gesture','canEdit'])test(`${guard} blocks a video source-open without starting a different interaction`,async()=>{
  const h=fixture();if(guard==='canEdit')h.timeline.canEdit=()=>false;else h.timeline[guard]=guard==='gesture'?{kind:'media'}:true;
  h.listeners.dblclick(h.point());await tick();assert.deepEqual(h.requests,[]);assert.equal(h.timeline.fitCount,undefined);assert.match(h.canvas.title,/current edit/);
});

test('absent clip, nonfinite/outside time and source-review timeline fail closed',async()=>{
  const h=fixture();for(const [id,time]of [['gone',3],[h.clip.id,NaN],[h.clip.id,1.99],[h.clip.id,6]])assert.equal(await h.timeline.openMediaSourceAt(id,time),false);
  h.timeline.sourceReview=true;assert.equal(await h.timeline.openMediaSourceAt(h.clip.id,3),false);assert.deepEqual(h.requests,[]);
});

test('malformed or throwing readiness never opens or fits a supported video',async()=>{
  for(const mode of ['null','throw']){const h=fixture();h.timeline.mediaSourceIssue=()=>{if(mode==='throw')throw Error('stale');return null;};h.listeners.dblclick(h.point());await tick();assert.equal(h.requests.length,0);assert.equal(h.timeline.fitCount,undefined);assert.match(h.canvas.title,/could not be confirmed/);}
});

test('independent pending guard prevents duplicate open without self-blocking host editPending',async()=>{
  const h=fixture();let finish;h.timeline.onMediaSourceOpen=(id,time)=>{assert.equal(h.timeline.editPending,false);h.requests.push({id,time});return new Promise(resolve=>finish=resolve);};
  const pending=h.timeline.openMediaSourceAt(h.clip.id,3);assert.equal(await h.timeline.openMediaSourceAt(h.clip.id,3.5),false);assert.equal(h.requests.length,1);
  finish(true);assert.equal(await pending,true);assert.equal(h.timeline.mediaSourceOpening,null);h.timeline.onMediaSourceOpen=async()=>true;assert.equal(await h.timeline.openMediaSourceAt(h.clip.id,4),true);
});

test('rejected/false source opens restore readiness and do not trigger an edit fallback',async()=>{
  const h=fixture();h.timeline.onMediaSourceOpen=async()=>{throw Error('Synthetic source unavailable');};assert.equal(await h.timeline.openMediaSourceAt(h.clip.id,3),false);
  assert.equal(h.canvas.title,'Synthetic source unavailable');assert.equal(h.timeline.mediaSourceOpening,null);assert.equal(h.timeline.editPending,false);
  h.timeline.onMediaSourceOpen=async()=>false;assert.equal(await h.timeline.openMediaSourceAt(h.clip.id,3),false);assert.match(h.canvas.title,/did not open/);assert.deepEqual(h.writes,[]);
});

test('late failure cannot replace feedback for a newer project/selection/tool',async()=>{
  for(const change of ['project','selection','tool']){const h=fixture();let fail;h.timeline.onMediaSourceOpen=()=>new Promise((_,reject)=>fail=reject);const pending=h.timeline.openMediaSourceAt(h.clip.id,3);
    if(change==='project')h.project.id='new';if(change==='selection')h.timeline.mediaSelection='other';if(change==='tool')h.timeline.tool='range';h.canvas.title='New context';fail(Error('Old error'));
    assert.equal(await pending,false);assert.equal(h.canvas.title,'New context');assert.equal(h.timeline.mediaSourceOpening,null);
  }
});

test('two ordinary clicks do not move/trim and double-click opens the clicked occurrence once',async()=>{
  const h=fixture();h.timeline.mediaMovePreview=(id,start)=>({issue:'',patch:{start,end:start+4}});
  for(let i=0;i<2;i++){h.timeline.pointerDown(h.point(3));h.timeline.pointerUp(h.point(3));}
  h.listeners.dblclick(h.point(3));await tick();assert.equal(h.requests.length,1);assert.deepEqual(h.writes,[]);assert.equal(h.timeline.mediaSelection,h.clip.id);
});

test('source double-click is discoverable on video bodies without replacing edge-trim hints',()=>{
  const h=fixture();h.timeline.mediaMovePreview=()=>({issue:'',patch:{}});h.timeline.mediaTrimPreview=()=>({issue:'',patch:{}});
  h.timeline.updatePointerCursor(h.point(3),3);assert.match(h.canvas.title,/Double-click to open the original source/);
  h.timeline.updatePointerCursor(h.point(2.001),2.001);assert.match(h.canvas.title,/trim/);assert.doesNotMatch(h.canvas.title,/Double-click/);
  const image=fixture('image');image.timeline.updatePointerCursor(image.point(3),3);assert.doesNotMatch(image.canvas.title,/Double-click/);
});

test('empty timeline space keeps Fit rather than guessing a selected video/source',async()=>{
  const h=fixture();const event=h.point(9);h.listeners.dblclick(event);await tick();assert.equal(h.timeline.fitCount,1);assert.equal(h.requests.length,0);
});

test('contextual source controls stay hidden for unsupported kinds and origin copy can wrap in RTL/mobile',()=>{
  const css=fs.readFileSync(path.join(__dirname,'../web/studio-workbench.css'),'utf8');
  assert.match(css,/\.media-source-match\[hidden\]\s*\{\s*display:none/);
  assert.match(css,/\.media-source-match \[data-match-source\]\s*\{[^}]*width:100%;[^}]*min-height:34px/);
  assert.match(css,/\.library-shot-match-origin\s*\{[^}]*border-inline-start:[^}]*overflow-wrap:anywhere;[^}]*unicode-bidi:plaintext/);
});

test('source readiness safely skips null retained rows without guessing a different occurrence',async()=>{
  const h=fixture();h.project.manual.media_clips.unshift(null);assert.equal(await h.timeline.openMediaSourceAt(h.clip.id,3),true);
  assert.equal(h.requests.length,1);assert.equal(h.requests[0].id,h.clip.id);assert.equal(await h.timeline.openMediaSourceAt('missing',3),false);assert.equal(h.requests.length,1);
});
