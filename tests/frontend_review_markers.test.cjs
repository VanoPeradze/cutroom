const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const src=n=>fs.readFileSync(path.join(__dirname,'../web',n),'utf8');
const {markerFrame:frame,reviewMarkerRows:rows,markerNavigation:nav}=vm.runInNewContext(src('review-markers.js').replace(/^export /gm,'')+'\n;({markerFrame,reviewMarkerRows,markerNavigation})');
const m=(frame=0,i=1,over={})=>({id:'marker_'+String(i).padStart(12,'0'),frame,fps:30,label:'Voice check',note:'Two\nlines',color:'teal',...over});
const rg=(...items)=>({version:1,items});const normal=x=>JSON.parse(JSON.stringify(x));
for(const fps of [24,25,30,50,60])test(fps+' FPS: end/playhead means last displayed frame, outside note never snaps to cut',()=>{
 assert.equal(frame(0,3,fps,true),0);assert.equal(frame(3,3,fps,true),3*fps-1);
 assert.equal(frame(3,3,fps),null);assert.equal(frame(3.01,3,fps,true),null);
 assert.equal(frame(3-.1/fps,3,fps),3*fps-1);
});
for(const [time,duration,fps] of [[NaN,1,30],[1,0,30],[0,1,0],[Infinity,3,60],[-1,8,30],[0,.002,30],[.1,5,29.97]])
 test('invalid grid or time is not silently clamped '+JSON.stringify([time,duration,fps]),()=>assert.equal(frame(time,duration,fps,true),null));
for(const [label,x] of Object.entries({null:null,future:{version:2,items:[]},unknown:{version:1,x:1,items:[]},badId:rg(m(0,1,{id:'no'})),
  staleKind:rg(m(0,1,{level:9})),dupes:rg(m(),m()),color:rg(m(0,1,{color:'toString'})),fps:rg(m(1,1,{fps:29.97})),negative:rg(m(-1)),
  whitespaceName:rg(m(0,1,{label:' x '})),paragraphName:rg(m(0,1,{label:'a\nb'})),controlNote:rg(m(0,1,{note:'x\0y'})),length:rg(m(0,1,{note:'x'.repeat(321)}))}))
 test('opaque or malformed '+label+' marker collection remains unavailable, never interpreted as empty',()=>assert.equal(rows(x),null));
test('fresh projects are empty, marker lists sort without mutating storage or comparing HTML',()=>{
 assert.deepEqual(normal(rows(undefined)),[]);const reg=rg(m(75,2),m(0),m(24,3,{fps:24,label:'<M>',note:'שמע'}));
 assert.deepEqual(normal(rows(reg)).map(r=>r.frame),[0,24,75]);assert.deepEqual(reg.items.map(r=>r.frame),[75,0,24]);
});
test('FPS changes preserve rational time; previous and next skip same-frame entries and shortened-away notes',()=>{
 const set=rows(rg(m(0),m(37,2),m(74,3,{fps:60}),m(100,4),m(500,5)));
 const at=frame(37/30,4,24);assert.equal(at,30);
 const n=nav(set,4,24,at);assert.equal(n.before.id,set[0].id);assert.equal(n.after.id,set[3].id);
 assert.equal(nav(set,4,24,0).before,null);assert.equal(nav(set,4,24,90).after,null);
});
const app=src('app.js'),hostFns=app.slice(app.indexOf('function reviewMarkerSnapshot()'),app.indexOf('function rangeAuditionSnapshot()'));
function host(){
 const s={studio:{open:true},project:{id:'p',revision:9,editor_sequence:{sequence:{},duration:6},settings:{fps:30},sources:{A:{}},draft:{}},projectViewToken:4,
 timeline:{project:{id:'p',revision:9},playhead:1.25,selection:{start:.2,end:.8},scheduleDraw(){s.draws++;}},draws:0};
 const c=vm.createContext({state:s,reviewMarkerRows:rows,elements:{resultPanel:{hidden:false}},foregroundBusy:()=>false,previewUsesSourceTime:()=>false,
 requireResolvedExplicitDrafts:()=>true,requireSavedTranscript:()=>true,flushProjectSaves:async()=>{},editorProject:()=>({...s.project}),
 rememberProjectRevision:p=>{s.remembered=p.revision;}}),run=x=>vm.runInContext(x,c);
 vm.runInContext(hostFns,c);const owner=run('reviewMarkerSnapshot()'),calls=[];
 c.api=async(url,opts)=>{calls.push([url,JSON.parse(opts.body)]);return{project_id:'p',previous_revision:9,revision:10,review_markers:rg(m(37))};};
 return {c,s,run,owner,calls,write:()=>c.writeReviewMarker(owner,{action:'add',expected_revision:9,frame:37,fps:30,label:'Voice check',note:'Two\nlines',color:'teal'})};
}
test('only an accepted same-view marker receipt updates revision; playhead and selected range are not rehydrated',async()=>{
 const h=host(),sel=h.s.timeline.selection;assert(await h.write());
 assert.equal(h.calls.length,1);assert.equal(h.s.project.revision,10);assert.equal(h.s.timeline.project.revision,10);
 assert.equal(h.s.timeline.selection,sel);assert.equal(h.s.timeline.playhead,1.25);assert.equal(h.s.remembered,10);assert.equal(h.s.draws,1);
});
for(const [reason,change] of Object.entries({view:h=>h.s.projectViewToken++,revision:h=>h.s.project.revision++,
 fps:h=>h.s.project.settings.fps=60,shorter:h=>h.s.project.editor_sequence.duration=3,source:h=>h.c.previewUsesSourceTime=()=>true,busy:h=>h.c.foregroundBusy=()=>true}))
 test('a pending save cannot retarget marker after '+reason+' change',async()=>{
 const h=host();h.c.flushProjectSaves=async()=>change(h);await assert.rejects(h.write(),/changed/);assert.equal(h.calls.length,0);assert.equal(h.s.draws,0);
});
test('explicit unresolved text or transcript is not committed as a side effect of a marker',async()=>{
 for(const key of ['requireResolvedExplicitDrafts','requireSavedTranscript']){const h=host();h.c[key]=()=>false;await assert.rejects(h.write(),/pending edits/);assert.equal(h.calls.length,0);}
});
for(const [name,patch] of Object.entries({otherProject:{project_id:'q'},future:{revision:12},prior:{previous_revision:8},unknown:{review_markers:{version:2,items:[]}},corrupt:{review_markers:rg({id:'bad'})}}))
 test('refuses unrelated '+name+' response without overwriting visible project',async()=>{
 const h=host();h.c.api=async()=>({project_id:'p',previous_revision:9,revision:10,review_markers:rg(),...patch});
 assert.equal(await h.write(),false);assert.equal(h.s.project.revision,9);assert.equal(h.s.draws,0);
});
test('project switch after dispatch never attaches an old marker to a new project',async()=>{
 const h=host();h.c.api=async()=>{h.s.project={...h.s.project,id:'q'};h.s.projectViewToken++;return{project_id:'p',previous_revision:9,revision:10,review_markers:rg(m())}};
 assert.equal(await h.write(),false);assert.equal(h.s.project.review_markers,undefined);assert.equal(h.s.draws,0);
});
