const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');
const plain = value => JSON.parse(JSON.stringify(value));
const dataKey = key => key.slice(5).replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());

// Real constructor markup, selectors and input handlers run against this DOM
// double. Pixel/FFmpeg parity is checked by backend and actual browser tests.
class Element {
  constructor(tag = 'div') { this.tagName = tag; this.children = []; this.dataset = {}; this.attrs = {}; this.listeners = {}; this.parentElement = null; this.open = false; }
  setAttribute(key, value) { this.attrs[key] = String(value); if (key.startsWith('data-')) this.dataset[dataKey(key)] = String(value); else this[key] = String(value); }
  removeAttribute(key) { delete this.attrs[key]; delete this[key]; }
  append(...nodes) { for (const node of nodes) { if (node.parentElement) node.parentElement.children = node.parentElement.children.filter(item => item !== node); this.children.push(node); node.parentElement = this; } }
  appendChild(node) { this.append(node); }
  // A native select cannot retain a value until a matching option exists.
  get value() { return this.tagName === 'select' ? (this.children.find(n => n.value === this._value)?.value || '') : this._value; }
  set value(value) { this._value = this.tagName === 'select' && !this.children.some(n => n.value === String(value)) ? '' : String(value); }
  get firstChild() { return this.children[0]; }
  insertBefore(node, next) { this.append(node); this.children = this.children.filter(item => item !== node); const at = this.children.indexOf(next); this.children.splice(at < 0 ? 0 : at, 0, node); }
  matches(selector) {
    const tag = selector.match(/^[a-z]+/i)?.[0]; if (tag && tag !== this.tagName) return false;
    for (const [, name] of selector.matchAll(/\.([\w-]+)/g)) if (!(this.className || this.class || '').split(/\s+/).includes(name)) return false;
    for (const [, key, expected] of selector.matchAll(/\[([\w-]+)(?:="?([^\]"']+)"?)?\]/g)) {
      const value = key.startsWith('data-') ? this.dataset[dataKey(key)] : this[key];
      if (expected === undefined ? value === undefined : value !== expected) return false;
    }
    return true;
  }
  querySelectorAll(selector) { return this.children.flatMap(node => [...(node.matches(selector) ? [node] : []), ...node.querySelectorAll(selector)]); }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  addEventListener(type, callback) { (this.listeners[type] ||= []).push(callback); }
  dispatch(type, target) { for (const listener of this.listeners[type] || []) listener({target}); }
  showModal() { this.open = true; this.shown = (this.shown || 0) + 1; }
  close() { this.open = false; }
  set innerHTML(markup) {
    this.children = []; const stack = [this];
    for (const token of markup.matchAll(/<\/?([a-z][\w-]*)([^>]*)>/gi)) {
      if (token[0].startsWith('</')) { stack.pop(); continue; }
      const node = new Element(token[1]);
      for (const [, key, quoted, single, bare] of token[2].matchAll(/([\w-]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?/g)) node.setAttribute(key, quoted ?? single ?? bare ?? '');
      stack.at(-1).append(node);
      if (!['input','img','br','hr','meta','link'].includes(token[1])) stack.push(node);
    }
  }
}

async function chromaFixture() {
  let project = {id:'chroma-project',revision:7,draft:{engine:'manual'},sources:{A:{name:'green.mp4',width:640,height:360,duration:12},B:{name:'blue.mp4',width:640,height:360,duration:10}},manual:{chroma_key:{B:{enabled:true,color:'#0000FF',tolerance:.2,edge_softness:.1,background_color:'#FFFFFF'}}}};
  const calls = [], revoked = []; let paused = 0, busy = false;
  const root = new Element();
  const context = vm.createContext({document:{createElement:tag=>new Element(tag)}, AbortController,
    URL:{createObjectURL:blob=>`blob:${blob.id}`,revokeObjectURL:url=>revoked.push(url)}, console});
  const source = fs.readFileSync('web/chroma-studio.js','utf8').replace(/^export /gm,'');
  vm.runInContext(source+'\nthis.api={ChromaStudio,chromaSettings,CHROMA_DEFAULTS};',context);
  const studio = new context.api.ChromaStudio(root, {
    project:()=>project, busy:()=>busy, pause:()=>{paused++;}, sourceTime:()=>3, selectedTarget:()=> 'A',
    api:async()=>({available:true,supports:['solid','image'],mp4_alpha:false}),
    frame:async request=>{calls.push(['frame',plain(request)]);return {id:'frame'};},
    edit:async(action,detail,options)=>{
      calls.push([action,plain(detail)]); if (!options.isCurrent()) return null;
      project = {...project,revision:project.revision+1,manual:{...project.manual,chroma_key:{...project.manual.chroma_key,[detail.slot]:action==='reset_chroma_key'?plain(context.api.CHROMA_DEFAULTS):Object.fromEntries(Object.entries(detail).filter(([key])=>key!=='slot'))}}};
      return project;
    },
  });
  await studio.ready;
  const input = (key,value) => { const node=studio.node.querySelector(`[data-chroma="${key}"]`); if (node.type==='checkbox') node.checked=value; else node.value=value; studio.node.dispatch('input',node); };
  return {studio,calls,input,api:context.api,revoked,project:()=>project,paused:()=>paused,switchProject:value=>{project=value;studio.render();},busy:value=>{busy=value;studio.render();}};
}

test('chroma controls expose exact per-source saved settings and never change the project while adjusting',async()=>{
  const f=await chromaFixture(), {studio,input}=f;
  assert.equal(studio.source.value,'A'); assert.equal(studio.node.querySelector('[data-chroma="enabled"]').checked,false);
  const before=JSON.stringify(f.project()); input('enabled',true); input('tolerance','.25'); input('edge_softness','.15'); input('background_color','#345678');
  assert.equal(JSON.stringify(f.project()),before); assert.equal(f.calls.length,0); assert.ok(f.paused()>0);
  assert.equal(studio.apply.disabled,false); assert.equal(studio.refresh.disabled,true); assert.match(studio.status.textContent,/not saved/);
  studio.source.value='B'; studio.source.onchange(); assert.equal(studio.settings().color,'#0000FF');
  studio.source.value='A'; studio.source.onchange(); assert.equal(studio.settings().tolerance,.25);
  await studio.apply.onclick();
  assert.deepEqual(f.calls,[['set_chroma_key',{slot:'A',enabled:true,color:'#00FF00',tolerance:.25,edge_softness:.15,background_color:'#345678',background_asset_id:null,background_mode:'replace'}]]);
  assert.equal(f.project().manual.chroma_key.B.color,'#0000FF'); assert.equal(studio.dirty(),false); assert.match(studio.status.textContent,/Saved/);
});

test('reset uses the existing undoable source action and saved state is restored on reopen or history changes',async()=>{
  const f=await chromaFixture(), {studio}=f; studio.source.value='B';studio.source.onchange();
  assert.equal(studio.node.querySelector('[data-chroma="enabled"]').checked,true);
  await studio.reset.onclick(); assert.deepEqual(f.calls,[['reset_chroma_key',{slot:'B'}]]);
  assert.deepEqual(plain(studio.settings()),plain(f.api.CHROMA_DEFAULTS));
  f.switchProject({...f.project(),revision:9,manual:{chroma_key:{B:{enabled:true,color:'#0000FF',tolerance:.2,edge_softness:.1,background_color:'#FFFFFF'}}}});
  assert.equal(studio.node.querySelector('[data-chroma="color"]').value,'#0000FF');
  assert.equal(studio.node.querySelector('[data-chroma="enabled"]').checked,true);
});

test('saving one source preserves the other unsaved candidate through the actual app render while external history invalidates it',async()=>{
  const f=await chromaFixture(),edit=f.studio.options.edit;
  f.input('enabled',true);f.input('tolerance',.35);f.studio.source.value='B';f.studio.source.onchange();f.input('tolerance',.45);
  f.studio.source.value='A';f.studio.source.onchange();f.studio.options.edit=async(...args)=>{const result=await edit(...args);f.studio.render();return result;};
  await f.studio.apply.onclick();f.studio.source.value='B';f.studio.source.onchange();
  assert.equal(f.studio.settings().tolerance,.45);assert.equal(f.studio.dirty(),true);assert.equal(f.project().manual.chroma_key.B.tolerance,.2);assert.equal(f.calls.length,1);
  f.switchProject({...f.project(),revision:f.project().revision+1});assert.equal(f.studio.settings().tolerance,.2);assert.equal(f.studio.dirty(),false);
});

test('busy, protected and missing sources cannot submit chroma mutations',async()=>{
  const f=await chromaFixture(); f.input('enabled',true); f.busy(true); await f.studio.save(false); f.busy(false);
  f.switchProject({...f.project(),revision:8,manual:{track_locks:{A:true}}}); f.studio.drafts.set('A',{...f.api.CHROMA_DEFAULTS,enabled:true});f.studio.render();
  await f.studio.save(false); assert.match(f.studio.status.textContent,/protected/);
  f.switchProject({id:'empty',revision:1,sources:{},manual:{}}); await f.studio.save(true);
  assert.equal(f.calls.length,0); assert.equal(f.studio.apply.disabled,true);
});

test('failed save keeps an unsaved candidate and switching project during save cannot corrupt the new project',async()=>{
  const f=await chromaFixture();f.input('enabled',true); f.studio.options.edit=async()=>null;
  await f.studio.save(false);assert.equal(f.studio.dirty(),true);assert.match(f.studio.status.textContent,/not saved/);assert.equal(f.project().manual.chroma_key.A,undefined);
  let finish;f.studio.options.edit=()=>new Promise(resolve=>{finish=resolve;});const saving=f.studio.save(false);
  f.switchProject({id:'other',revision:1,sources:{A:{width:640,height:360,duration:2}},draft:{},manual:{}});finish({id:'chroma-project'});await saving;
  assert.equal(f.studio.projectId,'other');assert.equal(f.studio.dirty(),false);assert.equal(f.project().manual.chroma_key,undefined);
});

test('frame preview requests saved source-native time and revision, revokes old images and discards stale requests',async()=>{
  const f=await chromaFixture(); await f.studio.refresh.onclick();
  assert.deepEqual(f.calls,[['frame',{projectId:'chroma-project',slot:'A',time:3,revision:7}]]);
  assert.equal(f.studio.frame.src,'blob:frame');assert.equal(f.studio.frame.parentElement.hidden,false);
  f.input('enabled',true);assert.deepEqual(f.revoked,['blob:frame']);assert.equal(f.studio.frame.parentElement.hidden,true);
  await f.studio.refreshFrame();assert.equal(f.calls.length,1,'unsaved settings are never presented as export parity');
  await f.studio.save(false);let finish,signal;
  f.studio.options.frame=(_request,s)=>{signal=s;return new Promise(resolve=>{finish=resolve;});};const preview=f.studio.refreshFrame();
  f.studio.source.value='B';f.studio.source.onchange();finish({id:'old'});await preview;
  assert.equal(signal.aborted,true);assert.equal(f.studio.frame.src,undefined);assert.equal(f.studio.previewing,false);
});

test('missing local capability and frame errors are visible without fake processed footage',async()=>{
  const f=await chromaFixture(); f.studio.options.api=async()=>({available:false,message:'Chroma filter unavailable.'});await f.studio.checkCapability();
  assert.equal(f.studio.apply.disabled,true);assert.match(f.studio.status.textContent,/unavailable/);
  f.studio.capability={available:true};f.studio.options.frame=async()=>{throw new Error('This frame is stale. Refresh the project.');};
  await f.studio.refreshFrame();assert.equal(f.studio.frame.parentElement.hidden,true);assert.match(f.studio.previewStatus.textContent,/stale/);
});

test('missing filter still lets a saved enabled source be disabled or reset while preventing enable and color changes',async()=>{
  const f=await chromaFixture();f.studio.source.value='B';f.studio.source.onchange();
  f.studio.capability={available:false,message:'Chroma filter unavailable.'};f.studio.render();
  assert.equal(f.studio.node.querySelector('[data-chroma="enabled"]').disabled,false);
  assert.equal(f.studio.node.querySelector('[data-chroma="color"]').disabled,true);assert.equal(f.studio.refresh.disabled,true);assert.equal(f.studio.reset.disabled,false);
  f.input('color','#FF0000');assert.equal(f.studio.settings().color,'#0000FF');
  f.input('enabled',false);assert.equal(f.studio.apply.disabled,false);await f.studio.apply.onclick();
  assert.equal(f.project().manual.chroma_key.B.enabled,false);assert.equal(f.calls.length,1);
  f.input('enabled',true);assert.equal(f.studio.settings().enabled,false,'unsupported filter cannot be re-enabled');
  f.switchProject({...f.project(),revision:9,manual:{chroma_key:{B:{...f.project().manual.chroma_key.B,enabled:true}}}});
  await f.studio.reset.onclick();assert.deepEqual(f.calls[1],['reset_chroma_key',{slot:'B'}]);assert.equal(f.project().manual.chroma_key.B.enabled,false);
});

test('non-video source metadata cannot expose functional chroma mutation or preview controls',async()=>{
  for(const invalid of [{width:0},{height:0},{duration:0},{width:'unknown'}]){
    const f=await chromaFixture();f.switchProject({...f.project(),revision:8,sources:{A:{...f.project().sources.A,...invalid}}});
    f.input('enabled',true);await f.studio.save(false);await f.studio.save(true);await f.studio.refreshFrame();
    assert.equal(f.calls.length,0);assert.equal(f.studio.apply.disabled,true);assert.equal(f.studio.refresh.disabled,true);
  }
});

test('replacement images use only real ready project assets and save the chosen source independently through the existing action',async()=>{
  const f=await chromaFixture(),id='asset_'+'a'.repeat(32),bad='asset_'+'b'.repeat(32),pending='asset_'+'c'.repeat(32);
  f.switchProject({...f.project(),revision:8,assets:{[id]:{id,kind:'image',status:'ready',name:'Backdrop.png',width:640,height:360},[bad]:{id:bad,kind:'video',status:'ready',width:640,height:360},[pending]:{id:pending,kind:'image',status:'preparing',width:640,height:360}}});
  assert.deepEqual(plain(f.studio.images()).map(asset=>asset.id),[id]);
  f.input('background_asset_id',bad);assert.equal(f.studio.settings().background_asset_id,null);
  f.input('background_asset_id',id);f.input('enabled',true);assert.equal(f.studio.node.querySelector('[data-chroma-solid]').hidden,true);assert.equal(f.calls.length,0);
  await f.studio.apply.onclick();assert.equal(f.project().manual.chroma_key.A.background_asset_id,id);assert.equal(f.project().manual.chroma_key.B.background_asset_id,undefined);
  let opened=0;f.studio.options.openMedia=()=>opened++;f.studio.node.querySelector('[data-chroma-import]').onclick();assert.equal(opened,1);assert.equal(f.calls.length,1,'Media entry never starts an upload automatically');
  await f.studio.reset.onclick();assert.equal(f.project().manual.chroma_key.A.background_asset_id,null);assert.equal(f.studio.node.querySelector('[data-chroma-solid]').hidden,false);
});

test('a saved missing image stays explicit rather than silently changing to a solid replacement, and unsupported image capability blocks selection',async()=>{
  const f=await chromaFixture(),id='asset_'+'a'.repeat(32);
  f.switchProject({...f.project(),revision:8,manual:{chroma_key:{A:{...f.api.CHROMA_DEFAULTS,enabled:true,background_asset_id:id}}}});
  assert.equal(f.studio.background.value,id);assert.match(f.studio.background.querySelectorAll('option').at(-1).textContent,/Unavailable image/);assert.equal(f.studio.dirty(),false);
  await f.studio.reset.onclick();assert.equal(f.project().manual.chroma_key.A.background_asset_id,null);
  f.studio.capability={available:true,supports:['solid']};f.switchProject({...f.project(),revision:10,assets:{[id]:{id,kind:'image',status:'ready',width:640,height:360}}});
  f.input('background_asset_id',id);assert.equal(f.studio.settings().background_asset_id,null);assert.deepEqual(plain(f.studio.images()),[]);
});

function directorFixture() {
  const nodes=new Map(), get=id=>{if(!nodes.has(id)){const node=new Element();node.id=id;nodes.set(id,node);}return nodes.get(id);};
  get('aiDraftNotice').append(new Element('p'));get('aiDraftApplyDialog').open=false;
  const header=new Element();header.className='studio-header';get('advancedPanel').append(header);
  const calls=[],toasts=[],context=vm.createContext({console,document:{getElementById:get},window:{addEventListener(){}},dictionaries:{en:{aiDraftKept:'New draft ready; manual timeline kept',aiDraftApply:'Apply new AI draft',aiDraftApplied:'New draft applied; Undo available'}},setTimeout,clearTimeout});
  const app=fs.readFileSync('web/app.js','utf8').replace(/^import .*;\r?\n/gm,'').replace(/\nboot\(\)\.catch\(\(error\) => \{[\s\S]*?\n\}\);/,'');
  vm.runInContext(app+`\nforegroundBusy=()=>false;flushCurrentProjectSaves=async()=>true;toast=(...args)=>globalThis.toasts.push(args);
    applyManualEdit=async(action,detail,options)=>{globalThis.calls.push([action,detail,options.isCurrent()]);state.project={...state.project,revision:state.project.revision+1,manual:{}};return state.project;};
    this.ui={state,elements,rememberDirectorResult,currentAiDraftNotice,directorCompletionNotice,renderAiDraftNotice,openAiDraftConfirmation,confirmAiDraftApply,renderEditStyleNote,renderModelStatus,prepareLocalAI,renderDraftWarning,openSpeechReviewSettings,renderDurationReview};`,Object.assign(context,{calls,toasts}));
  const {ui}=context;ui.state.dictionary=context.dictionaries.en;
  ui.state.project={id:'current',revision:8,draft:{engine:'style',segments:[{start:0,end:10}]},manual:{sequence:{tracks:{A:[{id:'manual-kept'}]}}}};
  ui.elements.resultPanel=get('resultPanel');ui.elements.advancedPanel=get('advancedPanel');
  const job=()=>({project_id:'current',result:{project_id:'current',draft:plain(ui.state.project.draft),applied_to_timeline:false,timeline_preserved:true}});
  return {ui,job,get,calls,toasts,run:code=>vm.runInContext(code,context)};
}

test('new preset disposition is truthful for current manual timelines and guarded against unrelated, stale or unchanged results',()=>{
  const f=directorFixture(),{ui,job,get}=f;
  assert.equal(ui.rememberDirectorResult(job()),true);assert.equal(get('aiDraftNotice').hidden,false);assert.match(get('aiDraftNotice').querySelector('p').textContent,/manual timeline kept/);
  assert.equal(ui.rememberDirectorResult({...job(),project_id:'other'}),false);
  assert.equal(ui.rememberDirectorResult({...job(),result:{...job().result,variation_changed:false}}),false);assert.equal(get('aiDraftNotice').hidden,true);
  assert.equal(ui.rememberDirectorResult({...job(),result:{...job().result,draft:{engine:'old',segments:[]}}}),false);
  assert.equal(ui.rememberDirectorResult({...job(),result:{...job().result,applied_to_timeline:true,timeline_preserved:false}}),false);
  ui.state.project=null;assert.equal(ui.rememberDirectorResult({}),false);
});

test('draft notice keeps a single accessible action in overview and Studio and disappears after project or draft changes',()=>{
  const f=directorFixture();f.ui.rememberDirectorResult(f.job());
  assert.equal(f.get('aiDraftNotice').parentElement,f.get('resultPanel'));
  f.ui.state.studio.open=true;f.ui.renderAiDraftNotice();assert.equal(f.get('aiDraftNotice').parentElement,f.get('advancedPanel').children[0]);
  f.ui.state.project={...f.ui.state.project,draft:{engine:'newer'}};f.ui.renderAiDraftNotice();assert.equal(f.get('aiDraftNotice').hidden,true);
});

test('completion wording names a nonverbal or basic cleanup fallback instead of claiming a successful semantic preset',()=>{
  const f=directorFixture();Object.assign(f.ui.state.dictionary,{audioHighlightsReady:'Audio and scene highlights; speech could not be transcribed reliably.',basicCleanupReady:'Basic cleanup; Story AI did not produce a valid edit.',draftReady:'Your first edit is ready'});
  f.ui.state.project.draft={engine:'audio_visual_highlights'};
  assert.deepEqual(plain(f.ui.directorCompletionNotice(f.job())),{message:'Audio and scene highlights; speech could not be transcribed reliably.',kind:'info'});
  const kept=f.ui.directorCompletionNotice(f.job(),true);assert.match(kept.message,/manual timeline kept.*speech could not/);assert.equal(kept.kind,'info');
  f.ui.state.project.draft={engine:'deterministic',quality_review:{warnings:[{type:'story_ai_fallback',message:'Invalid model draft'}]}};
  assert.match(f.ui.directorCompletionNotice(f.job()).message,/Story AI did not produce a valid edit/);
  f.ui.state.project.draft={engine:'story_ai'};assert.equal(f.ui.directorCompletionNotice(f.job()).kind,'success');
  assert.equal(f.ui.directorCompletionNotice({...f.job(),project_id:'other'}).message,'Your first edit is ready','an unrelated job does not use the current project fallback');
});

test('saved transcript fallback is actionable and reviewing it expands the actual language controls without changing settings',()=>{
  const f=directorFixture();Object.assign(f.ui.state.dictionary,{transcriptFallbackActionable:'Requested speech style was not created. Choose exact language and Quality; CPU can be slower.',speechStyleFallbackReady:'Requested speech style was not created; review speech settings.'});
  f.ui.state.project={...f.ui.state.project,settings:{spoken_language:'auto',performance_mode:'auto'},analysis:{warnings:[{type:'transcript_fallback',reason:'low_transcript_confidence'}]},draft:{engine:'audio_visual_highlights'}};
  f.ui.elements.draftWarning=f.get('draftWarning');f.ui.elements.draftWarningText=f.get('draftWarningText');f.ui.renderDraftWarning();
  assert.equal(f.get('draftWarning').hidden,false);assert.match(f.get('draftWarningText').textContent,/not created.*Quality.*CPU/);assert.match(f.ui.directorCompletionNotice(f.job()).message,/not created/);
  const disclosure=new Element('details'),language=f.get('spokenLanguage');let focused=false,scrolled=false;
  language.closest=()=>disclosure;language.focus=()=>{focused=true;};language.scrollIntoView=()=>{scrolled=true;};f.ui.elements.spokenLanguageSelect=language;
  f.run(`openStudioTab=tab=>{globalThis.openedTab=tab;return true;};`);f.ui.openSpeechReviewSettings();
  assert.equal(f.run('openedTab'),'transcript');assert.equal(disclosure.open,true);assert.equal(focused,true);assert.equal(scrolled,true);
  assert.deepEqual(plain(f.ui.state.project.settings),{spoken_language:'auto',performance_mode:'auto'});assert.equal(f.calls.length,0);
});

test('Apply new AI draft requires explicit modal confirmation and delegates the existing undoable sequence reset',async()=>{
  const f=directorFixture();f.ui.rememberDirectorResult(f.job());await f.ui.openAiDraftConfirmation();
  assert.equal(f.get('aiDraftApplyDialog').open,true);assert.equal(f.calls.length,0);
  await f.ui.confirmAiDraftApply();assert.deepEqual(plain(f.calls),[['sequence_reset',{},true]]);assert.equal(f.get('aiDraftApplyDialog').open,false);assert.equal(f.get('aiDraftNotice').hidden,true);
  await f.ui.confirmAiDraftApply();assert.equal(f.calls.length,1);
});

test('cancelling or a revision/project change during confirmation preserves the manual timeline without any reset',async()=>{
  for(const change of ['cancel','revision','project']){
    const f=directorFixture();f.ui.rememberDirectorResult(f.job());await f.ui.openAiDraftConfirmation();
    if(change==='cancel')f.get('aiDraftApplyDialog').close();else if(change==='revision')f.ui.state.project.revision++;else f.ui.state.project={id:'other',revision:1,draft:{},manual:{}};
    await f.ui.confirmAiDraftApply();assert.equal(f.calls.length,0);
  }
});

test('Clean VOD explains an intentionally selected Short and full-length alternative without changing the user goal',()=>{
  const f=directorFixture();f.ui.state.dictionary.cleanVodShortNote='Clean VOD will still create a Short. Choose YouTube for a full-length cleanup.';
  f.ui.state.selectedEditStyle='clean_vod';f.ui.state.project.settings={goal:'short'};f.ui.elements.editStyleNote=f.get('styleNote');
  f.ui.renderEditStyleNote('short');assert.match(f.get('styleNote').textContent,/still create a Short.*YouTube/);assert.equal(f.ui.state.project.settings.goal,'short');
  f.ui.renderEditStyleNote('youtube');assert.doesNotMatch(f.get('styleNote').textContent,/still create a Short/);assert.equal(f.ui.state.project.settings.goal,'short');
});

test('local model status names the actual fallback, requested model and reason without claiming the requested model is installed',()=>{
  const f=directorFixture();const status=f.get('modelStatus');status.append(new Element('b'),new Element('small'));
  f.ui.elements.modelStatus=status;f.ui.elements.modelButton=f.get('modelButton');f.ui.elements.retryAIButton=f.get('retryAI');
  f.ui.state.system={runtime:{state:'ready',available:true},models:{story_ai_ready:true,selected_story_model:'gemma3:4b',editor_model:'gemma3:9b',ollama:{available:true},
    story_ai_selection:{selected_model:'gemma3:4b',requested_model:'gemma3:9b',requested_model_installed:false,using_fallback:true,fallback_reason:'requested_model_missing',message:'gemma3:9b is not installed. Using installed gemma3:4b.'}}};
  f.ui.renderModelStatus();assert.equal(status.dataset.state,'fallback-model');assert.match(status.querySelector('b').textContent,/fallback/);
  assert.match(status.querySelector('small').textContent,/gemma3:4b.*gemma3:9b is not installed/);assert.equal(f.get('modelButton').hidden,false);assert.match(f.get('modelButton').textContent,/requested/);assert.equal(f.calls.length,0);
  f.ui.state.system.models.story_ai_selection.using_fallback=false;f.ui.state.system.models.story_ai_selection.selected_model='gemma3:9b';f.ui.renderModelStatus();
  assert.equal(status.dataset.state,'ready');assert.doesNotMatch(status.querySelector('b').textContent,/fallback/);assert.equal(f.get('modelButton').hidden,true);
});

test('runtime preparation preserves full selection evidence and makes no automatic model download request',async()=>{
  const f=directorFixture();const status=f.get('modelStatus');status.append(new Element('b'),new Element('small'));
  f.ui.elements.modelStatus=status;f.ui.elements.modelButton=f.get('modelButton');f.ui.elements.retryAIButton=f.get('retryAI');
  f.run(`this.prepareCalls=[];api=async(path,options)=>{prepareCalls.push([path,JSON.parse(options.body)]);return {runtime:{state:'ready',available:true},story_ai:{ready:true,selected_model:'gemma3:4b',requested_model:'gemma3:9b',requested_model_installed:false,using_fallback:true,fallback_reason:'requested_model_missing',recommended_model:'gemma3:9b'}};};renderActiveJobBar=()=>{};scheduleRuntimeRefresh=()=>{};`);
  await f.ui.prepareLocalAI();assert.equal(f.ui.state.system.models.selected_story_model,'gemma3:4b');assert.equal(f.ui.state.system.models.recommended_story_model,'gemma3:9b');
  assert.equal(f.ui.state.system.models.story_ai_selection.requested_model_installed,false);assert.equal(f.ui.state.system.models.story_ai_selection.using_fallback,true);
  assert.deepEqual(plain(f.run('prepareCalls')),[['/api/runtime/prepare',{performance_mode:'auto'}]]);
});


// All-project video regressions: imported clips are independent native-time
// targets, including when they have the same display filename as A/B.
const importedVideo=(letter,extra={})=>({id:'asset_'+letter.repeat(32),kind:'video',status:'ready',name:'green.mp4',width:640,height:360,duration:8,thumbnail_url:'/api/thumbnail/'+letter,...extra});
test('green screen has a permanently visible labelled section and genuine all-video thumbnail choices',async()=>{
  const f=await chromaFixture(),a=importedVideo('a'),b=importedVideo('b');
  f.switchProject({...f.project(),revision:8,assets:{[a.id]:a,[b.id]:b}});
  assert.equal(f.studio.node.tagName,'section');
  assert.match(f.studio.node.querySelector('[data-chroma-copy="chromaTitle"]').textContent,/Green screen.*Chroma key/);
  assert.deepEqual(plain(f.studio.targets()).map(item=>item.id),['A','B',a.id,b.id]);
  const radios=f.studio.node.querySelectorAll('[data-chroma-target]');assert.equal(radios.length,4);
  assert.equal(radios[0].checked,true);assert.equal(radios[2].value,a.id);assert.equal(radios[2].disabled,false);
  assert.equal(f.studio.node.querySelectorAll('.chroma-source-thumb').length,2);
  const labels=f.studio.node.querySelectorAll('.chroma-source-caption');
  assert.match(labels[2].textContent,/aaaaaaaa/);assert.match(labels[3].textContent,/bbbbbbbb/);
  assert.notEqual(labels[2].textContent,labels[3].textContent);
});
test('imported video edits and reset use stable asset ID and never mutate another same-named video',async()=>{
  const f=await chromaFixture(),a=importedVideo('a'),b=importedVideo('b');
  f.switchProject({...f.project(),revision:8,assets:{[a.id]:a,[b.id]:b}});
  f.studio.source.value=a.id;f.studio.source.onchange();f.input('enabled',true);f.input('color','#AA1234');
  assert.equal(f.studio.apply.disabled,false);await f.studio.save(false);
  assert.equal(f.calls[0][1].slot,a.id);assert.equal(f.project().manual.chroma_key[a.id].color,'#AA1234');
  assert.equal(f.project().manual.chroma_key[b.id],undefined);assert.equal(f.project().manual.chroma_key.A,undefined);
  await f.studio.save(true);assert.deepEqual(f.calls[1],['reset_chroma_key',{slot:a.id}]);
});
test('native imported-video preview time is explicit, independent of the A/B playhead and bounded to the selected file',async()=>{
  const f=await chromaFixture(),a=importedVideo('a');f.switchProject({...f.project(),revision:8,assets:{[a.id]:a}});
  f.studio.source.value=a.id;f.studio.source.onchange();
  const time=f.studio.node.querySelector('[data-chroma-time]');assert.equal(time.disabled,false);time.value='6.125';time.oninput();
  await f.studio.refreshFrame();assert.equal(f.calls[0][1].time,6.125);assert.equal(f.calls[0][1].slot,a.id);
  assert.match(f.studio.node.querySelector('[data-chroma-frame-caption]').textContent,/green.mp4/);
  time.value='500';time.oninput();await f.studio.refreshFrame();assert.equal(f.calls[1][1].time,7.999);
  f.studio.source.value='B';f.studio.source.onchange();await f.studio.refreshFrame();assert.equal(f.calls[2][1].time,3);
  f.studio.source.value=a.id;f.studio.source.onchange();assert.equal(Number(time.value),7.999);
});
test('missing, failed and preparing video choices stay explicit; audio/images cannot become chroma targets',async()=>{
  const f=await chromaFixture(),ready=importedVideo('a'),pending=importedVideo('b',{status:'preparing'}),failed=importedVideo('c',{status:'failed'}),audio=importedVideo('d',{kind:'audio'}),image=importedVideo('e',{kind:'image'});
  f.switchProject({...f.project(),revision:8,assets:Object.fromEntries([ready,pending,failed,audio,image].map(item=>[item.id,item]))});
  assert.deepEqual(plain(f.studio.targets()).map(item=>item.id),['A','B',ready.id,pending.id,failed.id]);
  const radios=f.studio.node.querySelectorAll('[data-chroma-target]');assert.equal(radios[3].disabled,true);assert.equal(radios[4].disabled,true);
  f.studio.source.value=ready.id;f.studio.source.onchange();f.input('enabled',true);
  f.switchProject({...f.project(),revision:9,assets:{}});assert.equal(f.studio.source.value,ready.id);
  assert.equal(f.studio.apply.disabled,true);assert.equal(f.studio.refresh.disabled,true);assert.match(f.studio.status.textContent,/unavailable/i);
  await f.studio.save(false);await f.studio.refreshFrame();assert.equal(f.calls.length,0);
});
test('selected asset saved settings survive reopening and Undo; drafts are never copied into a replacement file',async()=>{
  const f=await chromaFixture(),a=importedVideo('a');f.switchProject({...f.project(),revision:8,assets:{[a.id]:a}});
  f.studio.source.value=a.id;f.studio.source.onchange();f.input('enabled',true);f.input('tolerance',.33);await f.studio.save(false);
  const saved=f.project();f.switchProject({id:'other-project',revision:1,sources:{},manual:{}});f.switchProject(saved);
  assert.equal(f.studio.source.value,a.id);assert.equal(f.studio.settings().tolerance,.33);
  f.switchProject({...saved,revision:10,manual:{...saved.manual,chroma_key:{}}});assert.equal(f.studio.settings().enabled,false);
  f.input('enabled',true);f.switchProject({...f.project(),assets:{[a.id]:{...a,name:'replacement.mp4',relative_path:'another.mp4'}}});
  assert.equal(f.studio.dirty(),false);assert.equal(f.studio.settings().enabled,false);
});
test('saving imported video preserves another target draft and stale target preview aborts on removal',async()=>{
  const f=await chromaFixture(),a=importedVideo('a'),b=importedVideo('b');f.switchProject({...f.project(),revision:8,assets:{[a.id]:a,[b.id]:b}});
  f.studio.source.value=a.id;f.studio.source.onchange();f.input('enabled',true);f.input('tolerance',.35);
  f.studio.source.value=b.id;f.studio.source.onchange();f.input('enabled',true);f.input('tolerance',.45);
  f.studio.source.value=a.id;f.studio.source.onchange();const edit=f.studio.options.edit;f.studio.options.edit=async(...args)=>{const result=await edit(...args);f.studio.render();return result;};
  await f.studio.save(false);f.studio.source.value=b.id;f.studio.source.onchange();assert.equal(f.studio.settings().tolerance,.45);assert.equal(f.studio.dirty(),true);
  await f.studio.save(false);let finish,signal;f.studio.options.frame=(_req,s)=>{signal=s;return new Promise(resolve=>{finish=resolve;});};const preview=f.studio.refreshFrame();
  f.switchProject({...f.project(),revision:11,assets:{[a.id]:a}});finish({id:'stale'});await preview;
  assert.equal(signal.aborted,true);assert.equal(f.studio.frame.src,undefined);assert.equal(f.studio.previewing,false);
});
test('manual project import entry is explicit, and source protection still applies only to its genuine A/B targets',async()=>{
  const f=await chromaFixture(),a=importedVideo('a');f.switchProject({...f.project(),revision:8,assets:{[a.id]:a},manual:{track_locks:{A:true,B:true}}});
  f.studio.source.value=a.id;f.studio.source.onchange();f.input('enabled',true);assert.equal(f.studio.apply.disabled,false);
  let opened=0;f.studio.options.openMedia=()=>opened++;f.studio.node.querySelector('[data-chroma-add-video]').onclick();assert.equal(opened,1);assert.equal(f.calls.length,0);
  assert.match(f.studio.node.querySelector('[data-chroma-copy="chromaPlayback"]').textContent,/Edited playback/);
});


test('short draft duration review is visible in overview and Studio with exact numbers and no automatic settings changes',()=>{
  const f=directorFixture(),{ui,get}=f, notice=get('durationReview');notice.append(new Element('p'));
  ui.state.dictionary={...ui.state.dictionary,durationDraftSummary:'AI draft: {selected}s / {requested}s maximum.',durationStyleLimit:'Style keeps {limit} moments.',durationSourceLimit:'Source: {available}s.',durationEvidenceLimit:'Review source ranges.',reviewDurationSettings:'Review style & length'};
  ui.state.project.draft.duration_review={reason:'style_moment_limit',requested_seconds:90,selected_seconds:12,available_source_seconds:360,style_moment_limit:1};
  const before=JSON.stringify(ui.state.project);ui.renderDurationReview();
  assert.equal(notice.hidden,false);assert.match(notice.querySelector('p').textContent,/12s \/ 90s maximum.*1 moments/);
  assert.equal(notice.parentElement,get('resultPanel'));ui.state.studio.open=true;ui.renderAiDraftNotice();
  assert.equal(notice.parentElement.className,'studio-header');assert.equal(JSON.stringify(ui.state.project),before);assert.equal(f.calls.length,0);
  ui.state.project.draft.duration_review={reason:'source_shorter',requested_seconds:90,selected_seconds:73.833,available_source_seconds:73.833};ui.renderDurationReview();assert.match(notice.querySelector('p').textContent,/73.8s/);
  ui.state.project.draft.duration_review.reason='near_target';ui.renderDurationReview();assert.equal(notice.hidden,true);
  ui.state.project=null;ui.renderDurationReview();assert.equal(notice.hidden,true);
});

test('reopening chooses a saved keyed Media video and green defaults recover excessive tolerance without silently saving',async()=>{
  const f=await chromaFixture(), asset=importedVideo('c');f.studio.options.selectedTarget=()=>null;
  const project={...f.project(),id:'reopen-layer',revision:19,assets:{[asset.id]:asset},manual:{chroma_key:{[asset.id]:{...f.api.CHROMA_DEFAULTS,enabled:true,tolerance:1,edge_softness:.61}}}};
  f.switchProject(project);assert.equal(f.studio.source.value,asset.id);assert.equal(f.studio.node.querySelector('[data-chroma-warning]').hidden,false);
  f.studio.node.querySelector('[data-chroma-defaults]').onclick();
  assert.equal(f.studio.settings().tolerance,.12);assert.equal(f.studio.settings().background_mode,'transparent');assert.equal(project.manual.chroma_key[asset.id].tolerance,1);
  f.studio.options.autoPreview=true;await f.studio.save(false);
  assert.equal(f.project().manual.chroma_key[asset.id].background_mode,'transparent');assert.equal(f.calls.at(-1)[0],'frame');assert.equal(f.calls.at(-1)[1].slot,asset.id);
  assert.equal(f.studio.frame.parentElement.hidden,false);
});

test('new imported video enables a layer while A/B rejects the unavailable layer mode',async()=>{
  const f=await chromaFixture(),asset=importedVideo('d');f.input('background_mode','transparent');assert.equal(f.studio.settings().background_mode,'replace');
  f.switchProject({...f.project(),revision:8,assets:{[asset.id]:asset}});f.studio.source.value=asset.id;f.studio.source.onchange();f.input('enabled',true);
  assert.equal(f.studio.settings().background_mode,'transparent');assert.equal(f.project().manual.chroma_key[asset.id],undefined);
});
