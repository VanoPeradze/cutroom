const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const test=require('node:test');
const source=fs.readFileSync('web/app.js','utf8').replace(/^import .*;\r?\n/gm,'').replace(/\nboot\(\)\.catch\(\(error\) => \{[\s\S]*?\n\}\);/,'');
const plain=value=>JSON.parse(JSON.stringify(value));
function fixture(){
  const scope=vm.createContext({console,setTimeout,clearTimeout,window:{addEventListener(){},scrollTo(){}},document:{},dictionaries:{en:{saved:'Saved'}},localStorage:{getItem(){return null;},removeItem(){}}});
  const run=code=>vm.runInContext(code,scope);run(source);
  run(`globalThis.calls=[];globalThis.toasts=[];state.project={id:'p',revision:4,name:'Edit',settings:{},manual:{},draft:{}};
    state.dictionary={saved:'Saved'};elements.saveState={textContent:'',dataset:{},attrs:{},setAttribute(k,v){this.attrs[k]=v;}};
    liveEmbeddedCameraRequest=()=>null;toast=message=>toasts.push(message);pauseAllMedia=()=>{};
    globalThis.realReveal=revealPendingSave;revealPendingSave=status=>calls.push(['reveal',status.target,status.slot]);
    saveTranscriptBuffers=async()=>{calls.push('transcript');return true;};
    flushPendingSourceSync=async id=>calls.push(['sync',id]);flushEmbeddedCameraSave=async id=>{calls.push(['camera',id]);return true;};
    loadProjects=async()=>{};state.textStudio={projectId:'p',pending:new Map(),flush:async()=>{calls.push('text');return true;}};
    state.mediaStudio={projectId:'p',pending:new Map(),flush:async()=>{calls.push('media');return true;}};
    api=async(url,options)=>{calls.push([options?.method||'GET',url]);return {project:{...state.project,revision:state.project.revision+1}};};
    showWelcome=()=>calls.push('home');setAdvanced=()=>{};showWorkspace=hydrateProject=()=>{};recoverActiveJobs=async()=>{};
    workflowSettings=()=>({});
  `);
  return {run,scope,status:()=>plain(run('projectSaveStatus()')),node:()=>run('elements.saveState')};
}

test('aggregate Saved is truthful and persisted AI preferences are not unsaved edits',()=>{
 const f=fixture();assert.equal(f.status().kind,'saved');f.run('state.draftDirtyReasons.add("language");renderProjectSaveState()');
 assert.equal(f.node().textContent,'Saved');assert.equal(f.node().disabled,true);assert.equal(f.run('hasUnsavedProjectWork()'),false);
 assert.match(f.node().attrs['aria-label'],/All current project changes/);
});

test('all Chroma targets participate even while another clean target is selected',()=>{
 const f=fixture();f.run(`state.chromaStudio={projectId:'p',source:{value:'A'},pendingDrafts:()=>[{slot:'B',label:'Second video',issue:''}]};renderProjectSaveState();`);
 assert.equal(f.status().kind,'unsaved');assert.equal(f.status().slot,'B');assert.equal(f.node().disabled,false);assert.equal(f.run('hasUnsavedProjectWork()'),true);
});

test('a settings success cannot announce Saved over explicit Chroma or caption changes',async()=>{
 const f=fixture();f.run(`state.captionDirty=true;saveQueueFor('p',4).pending={name:'New name'};`);
 await f.run(`flushProjectSaves('p')`);assert.equal(f.node().textContent,'Unsaved changes');assert.equal(f.status().target,'caption');
 f.run(`state.captionDirty=false;state.chromaStudio={projectId:'p',pendingDrafts:()=>[{slot:'A',issue:'Source changed. Draft retained.'}]};setSaveState('p','Saved');`);
 assert.equal(f.node().dataset.saveState,'unsaved');assert.match(f.node().title,/Draft retained/);
});

test('queued settings have Saving state until the actual request finishes',async()=>{
 const f=fixture();f.run(`saveQueueFor('p',4).pending={name:'New name'};api=()=>new Promise(resolve=>globalThis.release=resolve);`);
 const task=f.run(`flushProjectSaves('p')`);assert.equal(f.status().kind,'saving');assert.equal(f.run('hasUnsavedProjectWork()'),true);
 f.run(`release({project:{...state.project,revision:5}})`);await task;assert.equal(f.status().kind,'saved');assert.equal(f.run('hasUnsavedProjectWork()'),false);
});

test('failed settings save is retained and header retries only that existing queue',async()=>{
 const f=fixture();f.run(`saveQueueFor('p',4).pending={name:'New name'};api=async()=>{throw Error('Offline');};`);
 await assert.rejects(f.run(`flushProjectSaves('p')`),/Offline/);assert.equal(f.status().kind,'error');assert.match(f.node().title,/Offline/);
 f.run(`api=async(url,options)=>{calls.push(['retry',JSON.parse(options.body)]);return {project:{...state.project,revision:5,name:'New name'}};};`);
 await f.run('activateSaveStatus()');assert.equal(f.status().kind,'saved');assert.equal(f.run('state.project.name'),'New name');
 assert.equal(f.run('calls.some(row=>row==="text"||row==="media")'),false);
});

for(const [field,value] of [['manualEditBusy','true'],['manualEditPromise','Promise.resolve()'],['captionContextSave','Promise.resolve()'],['transcriptSaving','true'],['sourceMixerSavePending','1'],['sourceSyncPending','{}']])test(`in-flight ${field} prevents a Saved claim and browser exit`,()=>{
 const f=fixture();f.run(`state.${field}=${value};`);assert.equal(f.status().kind,'saving');assert.equal(f.run('hasUnsavedProjectWork()'),true);
});

for(const name of ['mediaStudio','textStudio','chromaStudio'])test(`${name} in-flight save stays visible even after its pending map drains`,()=>{
 const f=fixture();f.run(`state.${name}={projectId:'p',pending:new Map(),saving:Promise.resolve()${name==='textStudio'?',dirty(){return Boolean(this.saving);}':''}};`);
 assert.equal(f.status().kind,'saving');assert.equal(f.run('hasUnsavedProjectWork()'),true);
});

test('unsaved work in a background project queue still prevents browser exit',()=>{
 const f=fixture();f.run(`saveQueueFor('other',1).pending={name:'Other edit'};`);assert.equal(f.status().kind,'saved');assert.equal(f.run('hasUnsavedProjectWork()'),true);
});

for(const kind of ['caption','chroma'])for(const action of ['goHome()','createProject()','openProject("other")'])test(`${kind} draft blocks ${action} without writes or clearing the editor`,async()=>{
 const f=fixture();f.run(kind==='caption'?'state.captionDirty=true;':`state.chromaStudio={projectId:'p',pendingDrafts:()=>[{slot:'B',issue:''}]};`);
 const old=f.run('state.project');await f.run(action);assert.equal(f.run('state.project'),old);assert.equal(f.run('state.projectViewToken'),0);
 assert.deepEqual(plain(f.run('calls')).map(row=>row[0]),['reveal']);assert.match(f.run('toasts[0]'),/Save|Apply/);
});

test('resolved explicit drafts restore the existing autosave then Home workflow',async()=>{
 const f=fixture();await f.run('goHome()');assert.equal(f.run('state.projectViewToken'),1);assert.equal(f.run('calls.at(-1)'),'home');
 assert.deepEqual(plain(f.run('calls.slice(0,4)')),['text','media','transcript',['sync','p']]);
});

for(const phase of ['text','media','transcript','sync','camera'])test(`flush stops if project or view changes during ${phase}, without flushing a replacement`,async()=>{
 const f=fixture();
 const setter={text:'state.textStudio.flush',media:'state.mediaStudio.flush',transcript:'saveTranscriptBuffers',sync:'flushPendingSourceSync',camera:'flushEmbeddedCameraSave'}[phase];
 f.run(`${setter}=async()=>{state.projectViewToken++;state.project={id:'other',revision:1};return true;};`);
 assert.equal(await f.run('flushCurrentProjectSaves()'),false);assert.equal(f.run('state.project.id'),'other');
 assert.equal(f.run('calls.some(row=>Array.isArray(row)&&row[1]==="other")'),false);
});

test('new explicit input during a held autosave aborts leaving and keeps that draft',async()=>{
 const f=fixture();f.run('state.textStudio.flush=()=>new Promise(resolve=>globalThis.release=resolve);');
 const task=f.run('flushCurrentProjectSaves()');f.run('state.captionDirty=true;release(true)');assert.equal(await task,false);
 assert.equal(f.run('state.captionDirty'),true);assert.equal(f.run('calls.some(row=>row==="media")'),false);
});

test('failed auto-save prevents navigation and keeps the failure visible',async()=>{
 const f=fixture();f.run(`state.textStudio.flush=async()=>{state.textStudio.saveError='Invalid timing';return false;};`);
 assert.equal(await f.run('flushCurrentProjectSaves()'),false);assert.equal(f.status().kind,'error');assert.equal(f.status().target,'text');assert.equal(f.node().textContent,'Save failed');
});

test('clicking an unapplied status only reveals its editor and never saves',async()=>{
 const f=fixture();f.run(`state.chromaStudio={projectId:'p',pendingDrafts:()=>[{slot:'B',issue:''}]};`);await f.run('activateSaveStatus()');
 assert.deepEqual(plain(f.run('calls')),[['reveal','chroma','B']]);
});

test('stale project module error cannot leak into a new project Saved status',()=>{
 const f=fixture();f.run(`state.mediaStudio={projectId:'other',saveError:'Old failure'};state.textStudio={projectId:'other',saveError:'Old failure'};`);assert.equal(f.status().kind,'saved');
});

test('header button semantics are native and translations cannot overwrite live save state',()=>{
 const html=fs.readFileSync('web/index.html','utf8');const tag=html.match(/<button[^>]*id="saveState"[^>]*>/)?.[0];
 assert.ok(tag);assert.match(tag,/type="button"/);assert.match(tag,/aria-live="polite"/);assert.doesNotMatch(tag,/data-i18n|role="status"/);
 assert.match(source,/beforeunload[\s\S]*?hasUnsavedProjectWork\(\)/);
});


test('runUiAction returns actual success and false after an API failure for awaited navigation',async()=>{
 const f=fixture();assert.equal(await f.run('runUiAction(async()=>42)'),42);
 f.run('console={error(){}};');assert.equal(await f.run('runUiAction(async()=>{throw Error("Offline")})'),false);
 assert.match(f.run('toasts.at(-1)'),/Offline/);
});

test('failed camera save remains actionable rather than falsely reporting Saving forever',()=>{
 const f=fixture();f.run(`state.embeddedEditor={projectId:'p',dirty:true,error:true};liveEmbeddedCameraRequest=()=>({projectId:'p'});renderProjectSaveState();`);
 assert.equal(f.status().kind,'error');assert.equal(f.status().target,'framing');assert.equal(f.status().actionable,true);
 assert.equal(f.run('hasUnsavedProjectWork()'),true);assert.match(f.node().title,/Retry save/);
});

test('reveal closes only the project picker before focusing an existing pending inspector',()=>{
 const f=fixture();f.run(`elements.projectsDialog={open:true,close(){this.open=false;calls.push('picker closed');}};
    openStudioTab=tab=>calls.push(tab);elements.captionItemEditor={scrollIntoView(){calls.push('reveal caption');}};
    elements.captionItemText={focus(){calls.push('focus caption');}};realReveal({target:'caption'});`);
 assert.deepEqual(plain(f.run('calls')),['picker closed','transcript','reveal caption','focus caption']);
});


test('unapplied Chroma blocks opening or starting a new export before any flush or render request',async()=>{
 const f=fixture();f.run(`document.getElementById=()=>null;showExportLayoutWarning=()=>{};
   state.chromaStudio={projectId:'p',pendingDrafts:()=>[{slot:'A',issue:''}]};openExportDialog();`);
 assert.deepEqual(plain(f.run('calls')),[['reveal','chroma','A']]);f.run('calls.length=0;');await f.run('startExport()');
 assert.deepEqual(plain(f.run('calls')),[['reveal','chroma','A']]);
});

test('a late explicit draft during export preflush stops rather than rendering the wrong saved state',async()=>{
 const f=fixture();f.run('state.textStudio.flush=async()=>{state.captionDirty=true;return true;};');
 await f.run('startExport()');assert.deepEqual(plain(f.run('calls')),[['reveal','caption',null]]);
});

test('a project switch during export preflush never starts an export for the replacement',async()=>{
 const f=fixture();f.run('state.textStudio.flush=async()=>{state.project={id:"other",draft:{}};state.projectViewToken++;return true;};');
 await f.run('startExport()');assert.equal(f.run('calls.length'),0);
});


test('failed media save forces the existing rollback into focused native fields without blurring',async()=>{
 const code=fs.readFileSync('web/media-studio.js','utf8').replace(/^export /gm,'');
 const volume={dataset:{media:'volume_db'},type:'range',value:'-2'}, x={dataset:{media:'x'},type:'number',value:'12.345'};
 const document={activeElement:volume};const scope=vm.createContext({console,document,window:{},clearTimeout(){},setTimeout(){}});
 vm.runInContext(code+'\nthis.MediaStudio=MediaStudio;',scope);const studio=Object.create(scope.MediaStudio.prototype);
 const project={id:'one',manual:{media_clips:[{id:'clip',volume_db:0,x:.2}]}};const paints=[];
 Object.assign(studio,{projectId:'one',selected:'clip',pending:new Map([['clip',{volume_db:-2}]]),overrides:new Map([['clip',{volume_db:-2}]]),
   root:{querySelectorAll:()=>[volume,x]},status:{textContent:''},options:{project:()=>project,edit:async()=>{throw Error('Offline');},preview(){}},
   render(force){paints.push(force);this.syncInspectorInputs(project.manual.media_clips[0],force);},updateImportAvailability(){}});
 studio.syncInspectorInputs(project.manual.media_clips[0]);assert.equal(volume.value,'-2','ordinary render preserves active typing');assert.equal(x.value,'20');
 assert.equal(await studio.flush(),false);assert.equal(volume.value,0);assert.equal(document.activeElement,volume,'no forced blur');
 assert.deepEqual(paints,[true]);assert.match(studio.saveError,/Previous settings restored/);
});

test('failure-only mixer sync also restores a focused typed dB value',()=>{
 const code=fs.readFileSync('web/media-studio.js','utf8').replace(/^export /gm,'');
 const input={dataset:{mixNumber:'source_db'},value:'-2'},document={activeElement:input};
 const scope=vm.createContext({document,console,window:{}});vm.runInContext(code+'\nthis.MediaStudio=MediaStudio;',scope);
 const studio=Object.create(scope.MediaStudio.prototype);const ducking={};
 Object.assign(studio,{options:{},mixer:()=>({source_db:0}),project:()=>({}),root:{querySelector:s=>s==='[data-ducking]'?ducking:null,querySelectorAll:s=>s==='[data-mix-number]'?[input]:[]},renderNormalization(){},renderClipAudio(){}});
 studio.renderMixer();assert.equal(input.value,'-2');studio.renderMixer(true);assert.equal(input.value,'0.0');assert.equal(document.activeElement,input);
});


test('transcript recovery opens its collapsed disclosure and restores the actual pending line without seeking',()=>{
 const f=fixture();f.run(`globalThis.details={open:false,parentElement:null};globalThis.field={focus(){calls.push('focus');}};
   state.project.analysis={transcript:{segments:[{id:'dirty',start:1,end:2,text:'Saved line'}]}};
   state.transcriptActive={projectId:'p',id:'clean'};state.transcriptBuffers.set('p:dirty',{projectId:'p',id:'dirty',base:'Saved line',text:'Retained text',start:1,end:2,provenance:transcriptBufferProvenance()});
   elements.transcriptEditForm={closest:()=>details,scrollIntoView(){calls.push(['scroll',details.open]);}};elements.transcriptEditText=field;
   openStudioTab=tab=>calls.push(tab);renderTranscriptDetail=()=>calls.push(['render',state.transcriptActive.id]);
   seekSourcePreview=()=>{throw Error('Header must not seek');};realReveal({target:'transcript'});`);
 assert.equal(f.run('details.open'),true);assert.equal(f.run('state.transcriptActive.id'),'dirty');
 assert.deepEqual(plain(f.run('calls')),['transcript',['render','dirty'],['scroll',true],'focus']);
 assert.equal(f.run('state.transcriptBuffers.get("p:dirty").text'),'Retained text');
});
