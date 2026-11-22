const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const src=fs.readFileSync('web/app.js','utf8').replace(/^import .*;\r?\n/gm,'').replace(/\nboot\(\)\.catch\(\(error\) => \{[\s\S]*?\n\}\);/,'');
const plain=v=>JSON.parse(JSON.stringify(v));
function fixture(){
 const nodes=new Map();const node=id=>{if(!nodes.has(id))nodes.set(id,{dataset:{},textContent:'',querySelector(){return null;}});return nodes.get(id);};
 const scope=vm.createContext({console,JSON,setTimeout,clearTimeout,window:{},document:{getElementById:node},localStorage:{getItem(){return null;},removeItem(){}},dictionaries:{en:{}}});
 const run=code=>vm.runInContext(code,scope);run(src);node('advancedPanel').dataset.aiRequestContext='editor';
 run(`globalThis.calls=[];globalThis.messages=[];state.studio.open=true;state.project={id:'p',revision:4,settings:{workflow:'manual',goal:'short',instruction:'My brief'},sources:{A:{duration:8}},manual:{},draft:{engine:'manual',keep_ranges:[{start:0,end:8}]},analysis:{}};
 state.projectViewToken=1;elements.directorInstruction={value:'My brief'};elements.analysisPanel={hidden:true};elements.generateButton={querySelector:()=>null};
 globalThis.realKeep=keepEditorAfterDirector;globalThis.realRemember=rememberDirectorResult;globalThis.realReconcile=reconcileDirectorOutcome;
 renderReadiness=()=>{};renderAiDraftNotice=()=>{};renderDirectorOutcomeNotice=()=>{};renderReelCandidates=()=>{};
 foregroundBusy=()=>false;requireResolvedExplicitDrafts=requireSavedTranscript=()=>true;liveEmbeddedCameraRequest=()=>false;
 flushCurrentProjectSaves=async()=>{calls.push('flush');return true;};flushProjectSaves=async()=>{};currentSettings=()=>({...state.project.settings});
 pauseAllMedia=()=>calls.push('pause');showAnalysis=options=>calls.push(['progress',options]);
 reviewEditingRequest=async options=>{calls.push(['review',options.preserveCurrentEdit,options.revision]);return {...options.settings,instruction:'Reviewed exact brief'};};
 acquireJobStartLock=()=>{calls.push('lock');return 'l';};releaseJobStartLock=()=>calls.push('release');
 ensureStoryAIReady=async()=>calls.push('provider');pollJob=async()=>{calls.push('poll');return {result:{}};};
 api=async(url,options)=>{calls.push(['post',url,JSON.parse(options.body),options.headers]);return {job:{id:'j'}};};
 toast=msg=>messages.push(msg);t=x=>x;openManualDraft=async()=>calls.push('manual');
 reconcileDirectorOutcome=async(id,error)=>calls.push(['error',error.message]);
 rememberProjectRevision=()=>{};loadDraftRebuildState=()=>{};state.timeline={setProject:()=>calls.push('timeline')};
 `);return{scope,run,node,calls:()=>plain(run('calls'))};
}
test('original manual Setup action stays manual but editor AI action invokes real request pipeline',async()=>{
 const f=fixture();f.node('advancedPanel').dataset.aiRequestContext='';await f.run('startDirectorAction()');assert.deepEqual(f.calls(),['manual']);
 f.node('advancedPanel').dataset.aiRequestContext='editor';f.run('calls=[]');await f.run('startDirectorAction()');
 assert.ok(f.calls().some(r=>r[0]==='review'));assert.equal(f.calls().includes('manual'),false);
 const post=f.calls().find(r=>r[0]==='post');assert.equal(post[1],'/api/projects/p/director');assert.equal(post[2].instruction,'Reviewed exact brief');
 assert.deepEqual(post[3],{'X-Cutroom-Reviewed-Revision':'4','X-Cutroom-Preserve-Edit':'1'});
 assert.equal(f.run('state.directorRequestPending'),false);assert.equal(f.run('state.editorDirectorSession'),null);
});
test('old non-sequence editor draft is protected without an artificial timeline edit',async()=>{
 const f=fixture();await f.run('generateDraft()');assert.equal(f.run('Boolean(state.project.manual.sequence)'),false);
 assert.deepEqual(f.calls().find(r=>r[0]==='review'),['review',true,4]);assert.deepEqual(f.calls().find(r=>r[0]==='progress'),['progress',{keepEditor:true}]);
});
test('legacy Setup without a manual sequence retains unprotected first-cut/rebuild route',async()=>{
 const f=fixture();f.node('advancedPanel').dataset.aiRequestContext='';f.run('state.project.settings.workflow="ai"');await f.run('generateDraft()');
 assert.deepEqual(f.calls().find(r=>r[0]==='post')[3],{'X-Cutroom-Reviewed-Revision':'4'});
 assert.equal(f.calls().find(r=>r[0]==='review')[1],false);
});
test('manual sequence is protected even when using existing Setup generation',async()=>{
 const f=fixture();f.node('advancedPanel').dataset.aiRequestContext='';f.run('state.project.manual.sequence={version:1,duration:8}');await f.run('generateDraft()');
 assert.equal(f.calls().find(r=>r[0]==='post')[3]['X-Cutroom-Preserve-Edit'],'1');
});
test('manual empty AI pane does not mistake manual-ready for a source to generate',async()=>{
 const f=fixture();f.run('state.project.sources={};state.project.draft=null');await f.run('generateDraft()');assert.deepEqual(f.calls(),['flush']);assert.equal(f.run('messages[0]'),'waitingForVideo');
});
test('explicit Chroma/caption draft blocks generation before preflush/provider or request',async()=>{
 const f=fixture();f.run('requireResolvedExplicitDrafts=()=>false');await f.run('generateDraft()');assert.deepEqual(f.calls(),[]);
});
test('repeat request during the first save cannot open two reviews or start two jobs',async()=>{
 const f=fixture();f.run('flushCurrentProjectSaves=()=>new Promise(resolve=>globalThis.finish=resolve)');const first=f.run('generateDraft()');assert.equal(f.run('state.directorRequestPending'),true);
 assert.equal(await f.run('generateDraft()'),false);f.run('finish(true)');await first;assert.equal(f.calls().filter(r=>r[0]==='post').length,1);
});
for(const action of ['generateDraft()','refineDraft("more_energy")'])test(`${action} pins project and view before waiting for a save`,async()=>{
 const f=fixture();f.run('flushCurrentProjectSaves=()=>new Promise(resolve=>globalThis.finish=resolve)');const op=f.run(action);
 f.run('state.project={...state.project,id:"other"};state.projectViewToken++;finish(true)');await op;assert.equal(f.calls().some(r=>r[0]==='post'||r[0]==='review'),false);
});
test('failed save never begins request checking or provider preparation',async()=>{
 const f=fixture();f.run('flushCurrentProjectSaves=async()=>false');await f.run('generateDraft()');assert.deepEqual(f.calls(),[]);
});
test('Keep/Cancel request review never prepares AI or creates a job and leaves editor open',async()=>{
 const f=fixture();f.run('reviewEditingRequest=async()=>null');await f.run('generateDraft()');assert.equal(f.calls().includes('provider'),false);assert.equal(f.calls().some(r=>r[0]==='post'),false);assert.equal(f.run('state.studio.open'),true);
});
test('pending explicit changes appearing during request review stop accepted request',async()=>{
 const f=fixture();f.run('reviewEditingRequest=async o=>{requireResolvedExplicitDrafts=()=>false;return o.settings;}');await f.run('generateDraft()');assert.equal(f.calls().includes('provider'),false);
});
test('project revision changed while provider preparation was pending cannot dispatch reviewed request',async()=>{
 const f=fixture();f.run('ensureStoryAIReady=async()=>{state.project.revision++}');await f.run('generateDraft()');assert.equal(f.calls().some(r=>r[0]==='post'),false);assert.match(f.calls().find(r=>r[0]==='error')[1],/changed after request review/);
});
test('provider refusal stays in editor and releases single request guard without success claim',async()=>{
 const f=fixture();f.run('ensureStoryAIReady=async()=>{throw Error("Provider is unavailable")}');await f.run('generateDraft()');assert.equal(f.calls().some(r=>r[0]==='post'),false);assert.equal(f.run('state.studio.open'),true);assert.equal(f.run('state.directorRequestPending'),false);assert.equal(f.run('state.editorDirectorSession'),null);
});
test('refinement sends exact protected revision and uses the same editor progress/Stop path',async()=>{
 const f=fixture();await f.run('refineDraft("more_energy")');const post=f.calls().find(r=>r[0]==='post');assert.equal(post[1],'/api/projects/p/director/refine');assert.deepEqual(post[2],{command:'more_energy'});assert.deepEqual(post[3],{'X-Cutroom-Reviewed-Revision':'4','X-Cutroom-Preserve-Edit':'1'});
 assert.deepEqual(f.calls().find(r=>r[0]==='progress'),['progress',{keepEditor:true}]);
});
test('isolated result refresh updates revision/provenance without teardown, seek or selection reset',()=>{
 const f=fixture();f.run('beginEditorDirectorSession("p",1);globalThis.old=state.project;globalThis.next={...state.project,revision:5,ai_draft_review:{version:1,available:true,isolated:true,origin_id:"new"}}');
 assert.equal(f.run('realKeep(next)'),true);assert.equal(f.run('state.project'),f.run('next'));assert.deepEqual(f.calls(),['timeline']);
});
for(const change of ['next.settings={...next.settings,aspect:"1:1"}','next.manual={crop:{A:{zoom:2}}}','next.analysis={transcript:{segments:[]}}','next.draft={engine:"other"}','state.projectViewToken++','state.studio.open=false'])test(`in-place refresh refuses changed render/navigation state: ${change}`,()=>{
 const f=fixture();f.run('beginEditorDirectorSession("p",1);globalThis.next={...state.project,revision:5}');f.run(change);assert.equal(f.run('realKeep(next)'),false);assert.deepEqual(f.calls(),[]);
});
test('isolated candidate has durable Review entry even when current manual draft has no sequence',()=>{
 const f=fixture();f.run('state.project.ai_draft_review={version:1,available:true,isolated:true,origin_id:"n"}');assert.equal(f.run('currentAiDraftNotice().originId'),'n');
 f.run('globalThis.job={project_id:"p",result:{project_id:"p",proposal_only:true,proposal_origin_id:"n",draft:{engine:"ai",keep_ranges:[]}}}');assert.equal(f.run('realRemember(job)'),true);
 f.run('state.project.ai_draft_review.available=false');assert.equal(f.run('currentAiDraftNotice()'),null);
});
test('synchronous original-node restore precedes closing Studio and any focus/visibility work',()=>{
 const start=src.indexOf('function setAdvanced(open)'),body=src.slice(start,src.indexOf('function exportRequiresDraftRebuild',start));assert.ok(body.indexOf('leaveEditor?.()')<body.indexOf('if (nextOpen === state.studio.open) return'));
});

for(const [reason,field,value] of [['brief','instruction','Exact only'],['duration','target_duration',25],['duration intent','duration_mode','target'],['rough-cut fallback','allow_extractive_rough_cut',true]])test(`AI pane ${reason} autosave writes only the actual changed request field`,()=>{
 const f=fixture();f.run(`elements.directorInstruction.value='Exact only';elements.targetDuration={value:'25'};elements.durationMode={value:'target'};elements.allowExtractiveRoughCut={checked:true};schedulePatch=p=>calls.push(p);markDraftRebuild=r=>calls.push(r);currentSettings=()=>{throw Error('Hidden output values must not be read');}`);
 f.run(`scheduleSettingsPatch({requiresRebuild:true,reason:${JSON.stringify(reason)}})`);assert.deepEqual(f.calls(),[reason,{settings:{[field]:value}}]);
});
test('every request uses saved fractional output/audio/length, never unrelated UI slider defaults',()=>{
 const f=fixture();f.run(`state.project.settings={instruction:'Saved brief',target_duration:8,aspect:'source',audio_cleanup:{silence_threshold_dbfs:null,gain:.123456}};currentSettings=()=>({instruction:'UI brief',target_duration:15,aspect:'9:16',audio_cleanup:{silence_threshold_dbfs:-42,gain:.12},goal:'short'});`);
 const output=plain(f.run('directorRequestSettings()'));assert.equal(output.target_duration,8);assert.equal(output.aspect,'source');assert.equal(output.audio_cleanup.silence_threshold_dbfs,null);assert.equal(output.audio_cleanup.gain,.123456);assert.equal(output.instruction,'Saved brief');assert.equal(output.goal,'short');
 f.run('state.studio.open=false');assert.equal(f.run('directorRequestSettings().target_duration'),8);
});
test('late completion GET cannot hydrate same project reopened in a new view',async()=>{
 const f=fixture();f.run(`loadProjects=async()=>{};hydrateProject=()=>calls.push('hydrate');api=()=>new Promise(r=>globalThis.finish=r);globalThis.response={project:{...state.project,revision:5}}`);
 const task=f.run('refreshProjectAfterDirector("p")');f.run('state.projectViewToken++;finish(response)');await task;assert.equal(f.run('state.project.revision'),4);assert.deepEqual(f.calls(),[]);
});
test('late completion GET cannot overwrite or hydrate a newer saved edit',async()=>{
 const f=fixture();f.run(`loadProjects=async()=>{};hydrateProject=()=>calls.push('hydrate');api=()=>new Promise(r=>globalThis.finish=r);globalThis.response={project:{...state.project,revision:5}}`);
 const task=f.run('refreshProjectAfterDirector("p")');f.run('state.project={...state.project,revision:6,name:"Newer save"};finish(response)');await task;assert.equal(f.run('state.project.name'),'Newer save');assert.deepEqual(f.calls(),[]);
});
for(const change of ['state.projectViewToken++','state.project={...state.project,revision:6,name:"Newer save"}'])test(`late failure refresh cannot install stale content: ${change}`,async()=>{
 const f=fixture();f.run(`hydrateProject=()=>calls.push('hydrate');api=()=>new Promise(r=>globalThis.finish=r);globalThis.response={project:{...state.project,revision:5}}`);
 const task=f.run('realReconcile("p",Error("Old job failed"))');f.run(`${change};finish(response)`);assert.equal(await task,false);assert.equal(f.run('state.project.revision'),change.includes('revision')?6:4);assert.deepEqual(f.calls(),[]);
});
test('older isolated receipt cannot announce a different currently saved candidate',()=>{
 const f=fixture();f.run(`state.project.ai_draft_review={version:1,available:true,isolated:true,origin_id:'new'};globalThis.job={project_id:'p',result:{project_id:'p',proposal_only:true,proposal_origin_id:'old',draft:{engine:'ai'}}};`);
 assert.equal(f.run('realRemember(job)'),false);assert.equal(f.run('state.aiDraftNotice'),null);assert.equal(f.run('currentAiDraftNotice().originId'),'new');
 assert.equal(f.run('directorCompletionNotice(job).kind'),'info');assert.match(f.run('directorCompletionNotice(job).message'),/earlier AI run/);
});
