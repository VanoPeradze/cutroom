const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),{pathToFileURL}=require('node:url');
const mod=n=>import(pathToFileURL(path.resolve(__dirname,'../web',n)).href);
const module9=mod('source-view.js'),studio9=mod('media-studio.js'),id='asset_'+'a'.repeat(32),other='asset_'+'b'.repeat(32),pid='project_9c0e00000001';
for(const [name,d,asset,want] of [
 ['video',{reviewShot:id},id,'video'],['audio',{reviewAudio:id},id,'audio'],['foreign',{reviewShot:other},id,''],
 ['two owners',{reviewShot:id,reviewAudio:id},id,''],['wrong case',{reviewShot:id.toUpperCase()},id.toUpperCase(),''],
 ['short',{reviewShot:'asset_aa'},'asset_aa',''],['no id',{},undefined,''],['coercible input',{reviewShot:id},[id],''],['no owner',null,id,''],['prefix',{reviewShot:id+' '},id,'']]){
 test('Pool source identity: '+name,async()=>{const {poolSourceKind}=await module9;assert.equal(poolSourceKind(d,asset),want);});
}
for(const [name,older,newer,media,playing,want] of [
 ['same project',{focused:true,project:pid},{project:pid,video:true},true,false,true],['initial',null,{project:pid,video:true},true,false,false],
 ['split',{focused:false,project:pid},{project:pid,video:true},true,false,false],['switched',{focused:true,project:pid},{project:'project_other',video:true},true,false,false],
 ['empty',{focused:true,project:''},{project:'',video:true},true,false,false],['switch to audio',{focused:true,project:pid},{project:pid,video:false},true,false,false],
 ['project closed',{focused:true,project:pid},null,true,false,false],['AI or other room',{focused:true,project:pid},{project:pid,video:true},false,false,false],
 ['Program playing',{focused:true,project:pid},{project:pid,video:true},true,true,false],['closed room / playing',{focused:true,project:pid},{project:pid,video:true},false,true,false]]){
 test('Focus continuation: '+name,async()=>{const {sourceFocusContinuation}=await module9;assert.equal(sourceFocusContinuation(older,newer,media,playing),want);});
}
async function subject(){const {MediaStudio}=await studio9,counts={pause:0,flush:0,host:0,open:0};const s=Object.create(MediaStudio.prototype);const asset={id,kind:'video',status:'ready',url:'/prepared/owned.mp4',duration:8},p={id:pid,draft:{output_duration:8},assets:{[id]:asset}};
const monitor={token:()=>1,poolIssue:()=>{counts.host++;return '';},open:()=>{counts.open++;return false;}};s.project=()=>p;s.options={busy:()=>false,pause:()=>{counts.pause++},time:()=>0,sourceMonitor:monitor};s.flush=async()=>{counts.flush++;return false;};s.status={textContent:''};return {s,counts,p,asset,monitor};}
for(const [name,change] of [
 ['no committed edit',({p})=>{delete p.draft}],['orphan asset',({p})=>{delete p.assets[id]}],['mismatched identity',({asset})=>{asset.id=other}],
 ['image',({asset})=>{asset.kind='image'}],['preparing file',({asset})=>{asset.status='preparing'}],['missing preview',({asset})=>{delete asset.url}],
 ['no installed guard',({monitor})=>{delete monitor.poolIssue}],['host busy',({s})=>{s.options.busy=()=>true}],
 ['upload in progress',({s})=>{s.uploading=true}],['import queue running',({s})=>{s.importQueue={running:true}}],
 ['placing',({s})=>{s.placing=true}],['pending draft',({s})=>{s.pending=new Set(['m'])}],['saving',({s})=>{s.saving=true}],
 ['pending frame editor',({s})=>{s.frameEditor={pending:true}}],['frame drag',({s})=>{s.frameEditorState={dragging:true}}],['open source committing',({s})=>{s.shotReview={pending:true}}],
 ['dirty host editor',({monitor})=>{monitor.poolIssue=()=>'Finish the existing caption draft.'}]]){
 test('Direct source does not flush, pause or navigate with '+name,async()=>{const ctx=await subject();change(ctx);const result=await ctx.s.reviewShot(id,{browse:true});assert.equal(result,false);assert(ctx.s.status.textContent);assert.equal(ctx.counts.flush,0);assert.equal(ctx.counts.pause,0);assert.equal(ctx.counts.open,0);});
}
async function withDoc(fn){const old=global.document;global.document={activeElement:null};try{await fn();}finally{if(old===undefined)delete global.document;else global.document=old;}}
test('Clean direct source checks guards twice without flushing or committing',async()=>withDoc(async()=>{const {s,counts}=await subject();await s.reviewShot(id,{browse:true});assert.deepEqual(counts,{pause:1,flush:0,host:2,open:1});}));
test('Direct source rejects a host change at second admission',async()=>withDoc(async()=>{const {s,counts,monitor}=await subject();monitor.poolIssue=()=>++counts.host===1?'':'A local edit started.';assert.equal(await s.reviewShot(id,{browse:true}),false);assert.deepEqual(counts,{pause:1,flush:0,host:2,open:0});}));
test('Legacy unpromoted action still follows original save preflight',async()=>withDoc(async()=>{const {s,counts}=await subject();await s.reviewShot(id);assert.deepEqual(counts,{pause:1,flush:1,host:0,open:0});}));
test('Library readiness checks reuse the supplied dirty-state sample',async()=>{const {s,counts}=await subject();assert.equal(s.poolSourceIssue(id,'Shared editing guard'),'Shared editing guard');assert.equal(s.poolSourceIssue(id,''),'');assert.equal(counts.host,0);});
test('No DOM or incomplete console: initialization safely returns null',async()=>{const {initSourceView}=await module9;assert.equal(initSourceView(null,null),null);assert.equal(initSourceView({getElementById:()=>null},{}),null);});
