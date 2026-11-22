const assert=require("node:assert/strict"),fs=require("node:fs"),path=require("node:path"),vm=require("node:vm"),test=require("node:test");
const source=fs.readFileSync(path.join(__dirname,"../web/app.js"),"utf8").replace(/^import .*;\r?\n/gm,"").replace(/\nboot\(\)\.catch\(\(error\) => \{[\s\S]*?\n\}\);/,"");
const plain=value=>JSON.parse(JSON.stringify(value));
function node(id = "") {
  const children = new Map();
  return {
    id, dataset: {}, style: { setProperty() {} }, listeners: {}, hidden: false,
    children: [], parentElement: null,
    classList: { add() {}, remove() {}, toggle() {} },
    querySelector(key) { if (!children.has(key)) children.set(key, node(key)); return children.get(key); },
    querySelectorAll() { return []; },
    addEventListener(type, callback) { this.listeners[type] = callback; },
    setAttribute() {}, removeAttribute() {}, append() {}, replaceChildren() {},
    appendChild(child) { return this.insertBefore(child, null); },
    insertBefore(child, before) {
      if (before && before.parentElement !== this) throw new Error("NotFoundError: reference node is in another dock");
      if (child.parentElement) child.parentElement.children = child.parentElement.children.filter((item) => item !== child);
      const index = before ? this.children.indexOf(before) : this.children.length;
      this.children.splice(index, 0, child);
      child.parentElement = this;
      return child;
    },
  };
}

function app() {
  const nodes = new Map();
  const selectors = new Map();
  const document = {
    getElementById(id) { if (!nodes.has(id)) nodes.set(id, node(id)); return nodes.get(id); },
    querySelectorAll(selector) { return selectors.get(selector) || []; },
    querySelector(selector) { return this.querySelectorAll(selector)[0] || null; },
    createElement: node, addEventListener() {},
  };
  const context = vm.createContext({ document, console, dictionaries: { en: {} }, setTimeout, clearTimeout, window: {addEventListener() {}}, requestAnimationFrame: (callback) => callback(),
    // These workflow tests simulate explicit request-review confirmation. The
    // actual review dialog/check/cancel contract has its own dedicated suite.
    reviewEditingRequest: async ({settings}) => settings });
  const run = (code) => vm.runInContext(code, context);
  run(fs.readFileSync(path.join(__dirname, "../web/keyboard.js"), "utf8").replace(/^export /gm, ""));
  run(fs.readFileSync(path.join(__dirname, "../web/source-tracks.js"), "utf8").replace(/^export /gm, ""));
  run(fs.readFileSync(path.join(__dirname, "../web/timeline.js"), "utf8").replace(/^export /gm, ""));
  run(fs.readFileSync(path.join(__dirname, "../web/caption-alternatives.js"), "utf8").replace(/^export /gm, ""));
  run(source);
  run(`cacheElements();
    state.project = { id: "p", sources: { A: { duration: 100 } }, settings: { goal: "short" }, draft: { goal: "short", keep_ranges: [{ start: 0, end: 10 }] } };
    globalThis.messages = [];
    toast = (message, type) => messages.push({ message, type });
  `);
  return { context, run, nodes, selectors };
}

function settingsApp() {
  const fixture = app();
  const { run, nodes } = fixture;
  for (const [id, values] of Object.entries({
    goalChoices: ["short", "youtube", "podcast", "clean"],
    paceChoices: ["balanced", "gentle", "dynamic"],
    audioPresetChoices: ["clean", "natural", "tight"],
  })) {
    const buttons = values.map((value) => {
      const button = node();
      button.dataset.value = value;
      button.classList.toggle = (_class, active) => { button.active = active; };
      return button;
    });
    nodes.get(id).querySelectorAll = () => buttons;
    nodes.get(id).querySelector = () => buttons.find((button) => button.active) || null;
  }
  for (const [id, values] of Object.entries({
    layoutSelect: ["auto", "A", "embedded_stack"], aspectSelect: ["source", "16:9", "9:16", "1:1", "4:5"],
    resolutionSelect: ["720", "1080", "2160"], qualitySelect: ["fast", "balanced", "quality"],
    captionStyleSelect: ["clean", "bold", "boxed"], captionPositionSelect: ["bottom", "top", "auto"],
    spokenLanguageSelect: ["auto", "en", "he"], performanceModeSelect: ["auto", "lite", "quality"], visualAiSelect: ["auto", "on", "off"],
  })) nodes.get(id).options = values.map((value) => ({ value }));
  nodes.get("layoutSelect").closest = () => null;
  run(`
    renderEditStyleChoices = renderCaptionControls = renderLanguageDetectionStatus = loadCropControls = () => {};
    state.project.sources.A.duration = 500;
    state.project.settings = { goal: "short", aspect: "9:16", target_duration: 75, edit_style: "smart", pace: "gentle" };
    state.system = { edit_styles: [
      { id: "smart", defaults: { goal: "short", aspect: "9:16", target_duration: 60, pace: "balanced" } },
      { id: "reaction_burst", defaults: { goal: "short", aspect: "9:16", target_duration: 45, pace: "dynamic", layout: "A", resolution: "1080", quality: "balanced", editorial_effects: true, audio_cleanup: { preset: "tight" } } },
      { id: "clean_vod", defaults: { goal: "youtube", aspect: "16:9", target_duration: 180, pace: "gentle", layout: "A", editorial_effects: false, audio_cleanup: { preset: "natural" } } },
    ] };
    hydrateSettings();
  `);
  return fixture;
}

const audio={preset:"clean",silence_action:"shorten",silence_min_seconds:.75125,silence_threshold_dbfs:null,silence_keep_seconds:.3025,max_remove_ratio:.283333,quiet_action:"boost",quiet_gain_db:2.375,loud_action:"lower",loud_gain_db:-3.625,normalize:true,target_lufs:-18.75};
function fixture(){
 const f=settingsApp();f.run(`state.project.revision=7;state.project.settings={...state.project.settings,target_duration:75.125,caption_scale:103,caption_words_per_line:6,spoken_language:'he',quality:'quality',audio_cleanup:${JSON.stringify(audio)}};hydrateSettings();
 globalThis.patches=[];globalThis.rebuilds=[];globalThis.realSchedulePatch=schedulePatch;
 schedulePatch=patch=>patches.push(patch);markDraftRebuild=reason=>rebuilds.push(reason);
 renderReadiness=applyFramingPreview=syncSecondaryPreview=renderLanguageDetectionStatus=renderAudioCalibration=()=>{};
 updatePreviewCaption=()=>{};previewPlaybackTime=()=>0;
 bindEvents();`);
 f.saved=plain(f.run('state.project.settings'));
 f.patch=()=>plain(f.run('patches.at(-1)'));
 f.fire=(id,type='change')=>f.nodes.get(id).listeners[type]({target:f.nodes.get(id)});
 return f;
}
function assertScope(f,expected){
 assert.deepEqual(f.patch(),{settings:expected});
 const applied=plain(f.run('applyPatchToProject(state.project,patches.at(-1)).settings'));
 const wanted={...f.saved,...expected};if(expected.audio_cleanup)wanted.audio_cleanup={...f.saved.audio_cleanup,...expected.audio_cleanup};
 assert.deepEqual(applied,wanted);
}
for(const [id,property,value,field] of [
 ['resolutionSelect','value','720','resolution'],['qualitySelect','value','fast','quality'],['fpsSelect','value','60','fps'],['exportFpsSelect','value','24','fps'],
 ['autoReframe','checked',false,'auto_reframe'],['effectsToggle','checked',false,'editorial_effects'],['captionsToggle','checked',false,'captions'],['layoutSelect','value','A','layout'],
 ['burnCaptionsToggle','checked',false,'burn_captions'],['studioBurnCaptionsToggle','checked',false,'burn_captions'],
 ['captionStyleSelect','value','boxed','caption_style'],['captionPositionSelect','value','top','caption_position'],['captionScale','value','125','caption_scale'],['captionWordsPerLine','value','4','caption_words_per_line'],
 ['spokenLanguageSelect','value','en','spoken_language'],['performanceModeSelect','value','lite','performance_mode'],['visualAiSelect','value','off','visual_ai'],
 ['durationMode','value','target','duration_mode'],['targetDuration','value','80.125','target_duration'],['allowExtractiveRoughCut','checked',true,'allow_extractive_rough_cut'],
])test(`actual ${id} handler saves only ${field}`,()=>{
 const f=fixture();f.nodes.get(id)[property]=value;f.fire(id);
 assertScope(f,{[field]:['fps','caption_scale','caption_words_per_line','target_duration'].includes(field)?Number(value):value});
});
for(const [id,property,value,field,expected] of [
 ['silenceAction','value','keep','silence_action','keep'],['quietAction','value','keep','quiet_action','keep'],['loudAction','value','keep','loud_action','keep'],['normalizeAudio','checked',false,'normalize',false],
 ['silenceMin','value','1.125','silence_min_seconds',1.125],['silenceKeep','value','.25','silence_keep_seconds',.25],['maxRemoveRatio','value','35','max_remove_ratio',.35],
 ['quietGain','value','4.125','quiet_gain_db',4.125],['loudGain','value','1.375','loud_gain_db',-1.375],['silenceThreshold','value','-39','silence_threshold_dbfs',-39],
 ['preSilenceMin','value','1.875','silence_min_seconds',1.875],['preSilenceKeep','value','.325','silence_keep_seconds',.325],
])test(`actual ${id} audio handler preserves all other cleanup leaves`,()=>{
 const f=fixture();f.nodes.get(id)[property]=value;f.fire(id);assertScope(f,{audio_cleanup:{[field]:expected}});
});
test('recommended threshold is an explicit one-field audio change',()=>{
 const f=fixture();f.run('preAudioProfile=()=>({summary:{recommended_silence_threshold_dbfs:-37.6}})');f.fire('useRecommendedThreshold','click');
 assertScope(f,{audio_cleanup:{silence_threshold_dbfs:-38}});
});
test('brief remains scoped outside Studio as well as in the AI pane',()=>{
 const f=fixture();f.nodes.get('directorInstruction').value='  Exact brief  ';f.fire('directorInstruction','input');assertScope(f,{instruction:'Exact brief'});
});
test('pace changes only pace without committing hidden audio/caption rounding',()=>{
 const f=fixture();const choice=f.nodes.get('paceChoices').querySelectorAll().find(n=>n.dataset.value==='dynamic');
 f.nodes.get('paceChoices').listeners.click({target:{closest:()=>choice}});assertScope(f,{pace:'dynamic'});
});
test('audio preset writes its defined bundle, not automatic threshold or hidden target LUFS',()=>{
 const f=fixture();const choice=f.nodes.get('audioPresetChoices').querySelectorAll().find(n=>n.dataset.value==='tight');
 f.nodes.get('audioPresetChoices').listeners.click({target:{closest:()=>choice}});
 const expected={...plain(f.run('AUDIO_PRESETS.tight')),preset:'tight'};assertScope(f,{audio_cleanup:expected});
 assert.equal(Object.hasOwn(expected,'silence_threshold_dbfs'),false);assert.equal(Object.hasOwn(expected,'target_lufs'),false);
});
for(const touched of [false,true])test(`goal bundle keeps unrelated settings and burn-caption ownership (${touched})`,()=>{
 const f=fixture();if(touched)f.nodes.get('burnCaptionsToggle').dataset.touched='1';
 const choice=f.nodes.get('goalChoices').querySelectorAll().find(n=>n.dataset.value==='youtube');f.nodes.get('goalChoices').listeners.click({target:{closest:()=>choice}});
 assertScope(f,{goal:'youtube',aspect:'16:9',layout:'A',pace:'gentle',audio_cleanup:{...plain(f.run('AUDIO_PRESETS.clean')),preset:'clean'},auto_reframe:false,editorial_effects:false,...(!touched?{burn_captions:false}:{})});
});
test('style applies canonical declared audio values and preserves explicit format/brief fields',()=>{
 const f=fixture();f.run(`state.system.edit_styles.push({id:'scoped',defaults:{pace:'dynamic',layout:'A',auto_reframe:false,editorial_effects:true,captions:true,burn_captions:false,performance_mode:'quality',audio_cleanup:{preset:'natural',max_remove_ratio:.173333,silence_threshold_dbfs:null,target_lufs:-20.25}}});`);
 f.run(`chooseEditStyle('scoped')`);
 assertScope(f,{edit_style:'scoped',pace:'dynamic',layout:'A',auto_reframe:false,editorial_effects:true,captions:true,burn_captions:false,performance_mode:'quality',audio_cleanup:{...plain(f.run('AUDIO_PRESETS.natural')),preset:'natural',max_remove_ratio:.173333,silence_threshold_dbfs:null,target_lufs:-20.25}});
});
test('style without audio defaults cannot persist unrelated displayed cleanup fields',()=>{
 const f=fixture();f.run(`chooseEditStyle('smart')`);const patch=f.patch().settings;
 assert.equal(Object.hasOwn(patch,'audio_cleanup'),false);assert.equal(Object.hasOwn(patch,'aspect'),false);assert.equal(Object.hasOwn(patch,'target_duration'),false);
 assert.equal(Object.hasOwn(patch,'caption_scale'),false);assertScope(f,patch);
});
test('ambiguous or missing scope fails closed instead of saving the whole form',()=>{
 const f=fixture();f.run('console={error(){}}');for(const reason of ['settings','output','audio','captions','framing'])assert.equal(f.run(`scheduleSettingsPatch({reason:'${reason}',requiresRebuild:true})`),false);
 assert.equal(f.run('patches.length'),0);assert.equal(f.run('rebuilds.length'),0);
});
test('rapid settings changes coalesce only the intended leaves',async()=>{
 const f=fixture();f.run('schedulePatch=realSchedulePatch;renderProjectSaveState=()=>{};');
 f.nodes.get('normalizeAudio').checked=false;f.fire('normalizeAudio');f.nodes.get('captionStyleSelect').value='boxed';f.fire('captionStyleSelect');f.nodes.get('quietGain').value='4.125';f.fire('quietGain');
 const queue=plain(f.run(`state.saveQueues.get('p').pending`));assert.deepEqual(queue,{settings:{audio_cleanup:{normalize:false,quiet_gain_db:4.125},caption_style:'boxed'}});
 f.run(`clearTimeout(state.saveQueues.get('p').timer);state.saveQueues.get('p').timer=null;`);
});
test('revision retry rebases exact top-level and audio leaves without overwriting concurrent siblings',async()=>{
 const f=fixture();f.run(`schedulePatch=realSchedulePatch;renderProjectSaveState=()=>{};loadProjects=async()=>{};globalThis.requests=[];globalThis.latest=JSON.parse(JSON.stringify(state.project));latest.revision=8;latest.settings.quality='fast';latest.settings.audio_cleanup.target_lufs=-21.25;latest.settings.audio_cleanup.quiet_gain_db=7.125;
 api=async(url,options)=>{if(!options)return {project:latest};const body=JSON.parse(options.body);requests.push(body);if(requests.length===1){const error=new Error('conflict');error.status=409;error.code='revision_conflict';error.payload={error:'revision_conflict'};throw error;}return {project:{...applyPatchToProject(latest,body),revision:9}};};`);
 f.nodes.get('normalizeAudio').checked=false;f.fire('normalizeAudio');f.nodes.get('captionPositionSelect').value='top';f.fire('captionPositionSelect');await f.run(`flushProjectSaves('p')`);
 const requests=plain(f.run('requests'));assert.equal(requests.length,2);
 assert.deepEqual(requests.map(p=>p.settings),[{audio_cleanup:{normalize:false},caption_position:'top'},{audio_cleanup:{normalize:false},caption_position:'top'}]);
 assert.equal(requests[1].expected_revision,8);const saved=plain(f.run('state.project.settings'));assert.equal(saved.quality,'fast');assert.equal(saved.audio_cleanup.target_lufs,-21.25);assert.equal(saved.audio_cleanup.quiet_gain_db,7.125);assert.equal(saved.audio_cleanup.normalize,false);
});
test('failed save retains only its exact patch and later explicit retry uses it',async()=>{
 const f=fixture();f.run(`schedulePatch=realSchedulePatch;renderProjectSaveState=()=>{};loadProjects=async()=>{};api=async()=>{throw new Error('offline')};`);
 f.nodes.get('fpsSelect').value='60';f.fire('fpsSelect');await assert.rejects(f.run(`flushProjectSaves('p')`),/offline/);
 assert.deepEqual(plain(f.run(`state.saveQueues.get('p').pending`)),{settings:{fps:60}});
 f.run(`api=async(url,options)=>({project:{...applyPatchToProject(state.project,JSON.parse(options.body)),revision:8}})`);await f.run(`flushProjectSaves('p')`);
 assert.deepEqual(plain(f.run('state.project.settings')),{...f.saved,fps:60});
});

for(const id of ['resolutionSelect','qualitySelect','fpsSelect','exportFpsSelect','autoReframe','effectsToggle','captionsToggle','layoutSelect'])test(`${id} does not stage source framing or seek the editor`,()=>{
 const f=fixture();f.run(`state.framingDraft={untouched:'existing candidate'};applyFramingPreview=pausePreview=seekSourcePreview=()=>{throw new Error('unrelated source framing action');};`);
 f.fire(id);assert.deepEqual(plain(f.run('state.framingDraft')),{untouched:'existing candidate'});
});
test('caption scale accepts every persisted integer percentage rather than snapping to five',()=>{
 const html=fs.readFileSync(path.join(__dirname,'../web/index.html'),'utf8');assert.match(html,/id="captionScale"[^>]*min="75"[^>]*max="150"[^>]*step="1"/);
 const f=fixture();assert.equal(Number(f.nodes.get('captionScale').value),103);assert.equal(f.run('captionSettingsFromControls().scale'),103);
});
test('export dispatch uses flushed saved settings rather than hidden form overrides',async()=>{
 const f=fixture();f.run(`globalThis.calls=[];requireResolvedExplicitDrafts=requireSavedTranscript=hasTimelineFootage=()=>true;state.project.settings.fps=60;state.project.settings.quality='quality';elements.qualitySelect.value='fast';elements.fpsSelect.value='24';
 pauseAllMedia=showExportLayoutWarning=assertJobStartNotCancelled=()=>{};liveEmbeddedCameraRequest=exportRequiresDraftRebuild=()=>false;
 acquireJobStartLock=()=>1;releaseJobStartLock=()=>{};flushProjectSaves=async()=>calls.push('flushed');
 api=async(url,options)=>{calls.push(JSON.parse(options.body));return {job:{id:'test'},storage_estimate:null}};setActiveJob=()=>{};pollExportJob=async()=>({});completeExportJob=async()=>{};`);
 await f.run('startExport()');assert.deepEqual(plain(f.run('calls')),['flushed',{}]);
 assert.equal(f.run('state.project.settings.fps'),60);assert.equal(f.run('state.project.settings.quality'),'quality');
});

test('legacy Setup request review reads accepted exact settings too, without changing rebuild policy',()=>{
 const f=fixture();f.run(`state.studio.open=false;state.project.settings.workflow='ai';elements.targetDuration.value='75';elements.maxRemoveRatio.value='28';elements.silenceThreshold.value='-42';elements.qualitySelect.value='fast';`);
 const request=plain(f.run('directorRequestSettings()'));
 assert.equal(request.target_duration,75.125);assert.equal(request.quality,'quality');assert.deepEqual(request.audio_cleanup,audio);
 assert.equal(f.run('editorAiRequestContext()'),false);
});
test('legacy request fallback reads controls only for fields missing from accepted settings',()=>{
 const f=fixture();f.run(`delete state.project.settings.visual_ai;elements.visualAiSelect.value='off';`);
 const request=plain(f.run('directorRequestSettings()'));assert.equal(request.visual_ai,'off');assert.deepEqual(request.audio_cleanup,audio);
});
