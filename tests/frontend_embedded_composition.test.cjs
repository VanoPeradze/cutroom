const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');

const source = fs.readFileSync(path.join(__dirname, '../web/app.js'), 'utf8')
  .replace(/^import .*;\r?\n/gm, '')
  .replace(/\nboot\(\)\.catch\(\(error\) => \{[\s\S]*?\n\}\);/, '');

function element() {
  const classes = new Set();
  return {
    value: '', dataset: {}, src: '', currentTime: 0, paused: true, hidden: false,
    style: {setProperty(key, value) { this[key] = value; }},
    classList: {add(...items) {items.forEach(item => classes.add(item));}, remove(...items) {items.forEach(item => classes.delete(item));}, contains: item => classes.has(item)},
    querySelector: () => ({}), addEventListener() {}, load() {},
    pause() {this.paused = true;}, play() {this.paused = false; return Promise.resolve();},
    removeAttribute(key) {this[key] = '';},
  };
}

function app() {
  const scope = vm.createContext({console, dictionaries: {en: {}}, document: {}, window: {}, setTimeout, clearTimeout, element,
    formatTime: value => `${value.toFixed(2)}s`});
  const run = code => vm.runInContext(code, scope);
  run(fs.readFileSync(path.join(__dirname, '../web/source-tracks.js'), 'utf8').replace(/^export /gm, ''));
  run(fs.readFileSync(path.join(__dirname, '../web/timeline.js'), 'utf8').replace(/^export /gm, ''));
  run(source);
  run(`
    for (const id of ['previewA','previewB','previewPaneA','previewPaneB','previewStage','cameraBadge',
      'cropSourceSelect','cropX','cropY','cropZoom','cropVideo','cropPreview','aspectSelect','resetCrop','embeddedCropHelp',
      'embeddedCameraW','embeddedCameraH','embeddedCameraX','embeddedCameraY','embeddedContentX','embeddedContentY',
      'embeddedCameraSeek','embeddedCameraSeekOut','embeddedCameraVideo']) elements[id] = element();
    elements.previewStage.dataset.aspect = elements.aspectSelect.value = '9:16';
    elements.cropSourceSelect.value = 'A';
    state.project = {id:'embedded-test', sources:{A:{url:'/a.mp4',duration:20,width:1920,height:1080,has_audio:true}}, settings:{aspect:'9:16'},
      manual:{embedded_camera:{x:0,y:0,w:1,h:.3,content_focus:{x:.5,y:.5}}},
      draft:{layout:'embedded_stack',embedded_layout_confirmed:true,camera_plan:[{start:0,end:20,camera:'embedded_stack'}]}};
  `);
  return {run, scope};
}

const plain = value => JSON.parse(JSON.stringify(value));

function twoSourceComposition() {
  const harness = app();
  harness.run(`
    for (const id of ['sourceCompositionCanvas','sourceCompositionA','sourceCompositionB',
      'sourceCompositionRoleA','sourceCompositionRoleB','sourceCompositionNameA','sourceCompositionNameB',
      'sourceCompositionMode','firstSlotName']) elements[id] = element();
    globalThis.compositionSlots = {A:element(), B:element()};
    elements.sourceCompositionCanvas.querySelector = selector => compositionSlots[selector.includes('"A"') ? 'A' : 'B'];
    state.project.sources.B = {url:'/b.mp4',duration:20,width:1920,height:1080,has_audio:true,name:'Camera B'};
    state.project.manual = {source_mixer:{screen_slot:'A',camera_slot:'B',first_slot:'B',primary_role:'screen',stack_fit:'cover'},
      crop:{A:{x:.1,y:.2,zoom:1.8},B:{x:.9,y:.8,zoom:1.4}}};
    state.sourceMixerLayout = 'stacked';
    state.sourceMixerPreviewLayout = 'stacked';
  `);
  return harness;
}

test('source-order composition uses the output ratio and preserves the 30/70 creator stack', () => {
  const {run} = twoSourceComposition();
  for (const [aspect, css, ratio] of [['9:16','9 / 16',9/16],['16:9','16 / 9',16/9],['1:1','1',1],['4:5','4 / 5',4/5]]) {
    run(`elements.aspectSelect.value=${JSON.stringify(aspect)}; renderSourceCompositionPreview(sourceMixerSettings());`);
    assert.equal(run('elements.sourceCompositionCanvas.style.aspectRatio'), css);
    assert.equal(run('Number(elements.sourceCompositionCanvas.style["--composition-ratio"])'), ratio);
    assert.equal(run('elements.sourceCompositionCanvas.style["--composition-first-share"]'), '30%');
    assert.match(run('elements.sourceCompositionCanvas.className'), /first-slot-b/);
    assert.match(run('elements.sourceCompositionMode.textContent'), /B on top 30%/);
  }
  run(`state.project.manual.source_mixer.first_slot='A'; renderSourceCompositionPreview(sourceMixerSettings());`);
  assert.equal(run('elements.sourceCompositionCanvas.style["--composition-first-share"]'), '70%');
  run(`state.project.manual.source_mixer.primary_role='camera'; renderSourceCompositionPreview(sourceMixerSettings());`);
  assert.equal(run('elements.sourceCompositionCanvas.style["--composition-first-share"]'), '30%');
});

test('stack fit is centred and uncropped in both previews, while Fill restores saved source framing', () => {
  const {run} = twoSourceComposition();
  const original = plain(run('state.project.manual.crop'));
  for (const fit of ['cover', 'contain', 'cover']) {
    run(`state.project.manual.source_mixer.stack_fit=${JSON.stringify(fit)};
      setupPreviewSources(); syncSecondaryPreview(5); renderSourceCompositionPreview(sourceMixerSettings());`);
    for (const slot of ['A','B']) {
      const zoom = fit === 'contain' ? 1 : original[slot].zoom;
      const position = fit === 'contain' ? '50% 50%' : `${original[slot].x*100}% ${original[slot].y*100}%`;
      for (const prefix of ['preview','sourceComposition']) {
        assert.equal(run(`elements.${prefix}${slot}.style.transform`), `scale(${zoom})`);
        assert.equal(run(`elements.${prefix}${slot}.style.objectPosition`), position);
      }
    }
  }
  assert.deepEqual(plain(run('state.project.manual.crop')), original, 'Fit must not erase the user framing');
});

test('changing output shape or crop updates the layout chooser immediately without saving or replaying media', () => {
  const {run} = twoSourceComposition();
  run(`elements.cropSourceSelect.value='B'; elements.cropX.value='0'; elements.cropY.value='100'; elements.cropZoom.value='180';
    elements.aspectSelect.value='4:5'; applyFramingPreview();`);
  assert.equal(run('elements.sourceCompositionCanvas.style.aspectRatio'), '4 / 5');
  assert.equal(run('elements.sourceCompositionB.style.objectPosition'), '0% 100%');
  assert.equal(run('elements.sourceCompositionB.style.transform'), 'scale(1.8)');
  assert.equal(run('elements.previewB.style.objectPosition'), '0% 100%');
  assert.equal(run('state.project.manual.crop.B.zoom'), 1.4);
  assert.equal(run('elements.sourceCompositionB.paused'), true);
});

test('fitted layouts ignore saved zoom while picture-in-picture crops only its primary source', () => {
  const {run} = twoSourceComposition();
  for (const layout of ['auto', 'side_by_side']) {
    for (const slot of ['A','B']) assert.deepEqual(plain(run(`previewCropForLayout('${slot}','${layout}',sourceMixerSettings())`)), {x:.5,y:.5,zoom:1});
  }
  assert.equal(run(`previewCropForLayout('A','pip',sourceMixerSettings()).zoom`), 1.8);
  assert.equal(run(`previewCropForLayout('B','pip',sourceMixerSettings()).zoom`), 1);
  run(`state.project.manual.source_mixer.primary_role='camera';`);
  assert.equal(run(`previewCropForLayout('A','pip',sourceMixerSettings()).zoom`), 1);
  assert.equal(run(`previewCropForLayout('B','pip',sourceMixerSettings()).zoom`), 1.4);
});

test('layout chooser hides the unused source in single-role layouts without losing routing', () => {
  const {run} = twoSourceComposition();
  for (const [layout, hiddenA, hiddenB] of [['screen',false,true],['camera',true,false],['stacked',false,false]]) {
    run(`state.sourceMixerLayout='${layout}'; renderSourceCompositionPreview(sourceMixerSettings());`);
    assert.equal(run('compositionSlots.A.hidden'), hiddenA);
    assert.equal(run('compositionSlots.B.hidden'), hiddenB);
  }
});

test('picture-in-picture preview uses the rendered overlay size and 32 output-pixel margins', () => {
  const {run} = twoSourceComposition();
  run(`elements.resolutionSelect=element(); state.sourceMixerLayout='pip'; state.sourceMixerPreviewLayout='pip';`);
  // Expected sizes are the even-pixel FFmpeg dimensions, not rounded percentages.
  for (const [aspect, resolution, width, height, insetWidth, insetHeight] of [
    ['9:16','1080',1080,1920,366,536], ['9:16','720',720,1280,244,358],
    ['16:9','1080',1920,1080,652,302], ['16:9','720',1280,720,434,200],
    ['1:1','1080',1080,1080,366,302], ['4:5','720',720,900,244,252],
  ]) {
    run(`elements.aspectSelect.value='${aspect}'; elements.resolutionSelect.value='${resolution}';
      renderSourceCompositionPreview(sourceMixerSettings()); syncSecondaryPreview(5);`);
    for (const id of ['sourceCompositionCanvas', 'previewStage']) {
      for (const [property, expected] of [['width',100*insetWidth/width], ['height',100*insetHeight/height],
        ['right',3200/width], ['bottom',3200/height]]) {
        assert.equal(parseFloat(run(`elements.${id}.style['--pip-${property}']`)), expected);
      }
    }
    assert.equal(run('elements.sourceCompositionA.style.transform'), 'scale(1.8)');
    assert.equal(run('elements.sourceCompositionB.style.transform'), 'scale(1)');
  }
  run(`elements.aspectSelect.value='source'; elements.resolutionSelect.value='1080';
    state.project.sources.A.width=2560; state.project.sources.A.height=1080;`);
  assert.deepEqual(plain(run('previewExportDimensions()')), [1920,810]);
  run(`state.project.sources.A.width=NaN; state.project.sources.A.height=0; applyPreviewPipGeometry(elements.previewStage);`);
  assert.ok(Number.isFinite(parseFloat(run(`elements.previewStage.style['--pip-width']`))));
});

test('draft layout hydration follows saved scenes instead of the next-build Creator default', () => {
  const {run} = twoSourceComposition();
  run(`state.project.manual.source_mixer.default_layout='stacked';
    state.project.draft.camera_plan=[{start:0,end:20,camera:'pip'}]; hydrateSourceMixerLayout();`);
  assert.equal(run('state.sourceMixerLayout'), 'pip');
  run(`state.project.draft.camera_plan=[{start:0,end:10,camera:'stacked'},{start:10,end:20,camera:'pip'}];
    state.manualSelection={start:11,end:19}; hydrateSourceMixerLayout();`);
  assert.equal(run('state.sourceMixerLayout'), 'pip');
  run(`state.manualSelection={start:0,end:8}; hydrateSourceMixerLayout();`);
  assert.equal(run('state.sourceMixerLayout'), 'stacked');
  run(`state.project.draft=null; hydrateSourceMixerLayout();`);
  assert.equal(run('state.sourceMixerLayout'), 'stacked', 'Pre-Director layout still uses its saved default');
});

test('rapid Fit/Fill saves followed by a layout click retain and commit that exact request once', async () => {
  const {run} = twoSourceComposition();
  run(`state.project.manual.source_mixer.default_layout='stacked';
    state.project.draft.camera_plan=[{start:0,end:20,camera:'stacked'}];
    globalThis.layoutCalls=[]; globalThis.mixerPending = new Promise(resolve => globalThis.finishMixerSave=resolve);
    state.sourceMixerSavePending=1; state.sourceMixerSaveTail=mixerPending;
    renderSourceMixer=()=>{globalThis.lastRenderedLayout=state.sourceMixerLayout;};
    syncSecondaryPreview=()=>{}; toast=()=>{};
    applyManualEdit=async (action, detail)=>{
      layoutCalls.push({action,...detail});
      if(foregroundBusy()) throw new Error('Layout was sent before the mixer save settled');
      state.project.draft.camera_plan=[{start:0,end:20,camera:detail.layout}];
      hydrateSourceMixerLayout(); return state.project;
    };
    state.sourceMixerLayout='pip';
    globalThis.layoutTask=applySourceLayout('all',{immediate:true});`);
  assert.equal(run('layoutCalls.length'), 0);
  assert.equal(run('sourceMixerControlBusy()'), true, 'Prevent a second operation while the layout is queued');
  run(`state.sourceMixerLayout='stacked'; state.sourceMixerSavePending=0; finishMixerSave();`);
  await run('layoutTask');
  assert.deepEqual(plain(run('layoutCalls')), [{action:'set_camera_layout',layout:'pip',start:0,end:20}]);
  assert.equal(run('state.sourceMixerLayout'), 'pip');
  assert.equal(run('lastRenderedLayout'), 'pip');
  assert.equal(run('state.sourceMixerLayoutRequest'), null);
  run('hydrateSourceMixerLayout();');
  assert.equal(run('state.sourceMixerLayout'), 'pip', 'Later edits or reload hydration must not bring Stacked back');
});

test('a queued layout cannot mutate a newly opened project and failed edits restore the saved chooser', async () => {
  const {run} = twoSourceComposition();
  run(`state.project.draft.camera_plan=[{start:0,end:20,camera:'stacked'}];
    renderSourceMixer=()=>{}; syncSecondaryPreview=()=>{}; toast=()=>{};
    globalThis.layoutCalls=[]; applyManualEdit=async (action, detail)=>{layoutCalls.push(detail); return null;};
    state.sourceMixerLayout='pip';`);
  await run(`applySourceLayout('all')`);
  assert.equal(run('state.sourceMixerLayout'), 'stacked');
  run(`state.sourceMixerSavePending=1;
    state.sourceMixerSaveTail=new Promise(resolve=>globalThis.finishMixerSave=resolve);
    state.sourceMixerLayout='pip'; globalThis.layoutTask=applySourceLayout('all');
    state.project={id:'other-project',sources:{A:{duration:20},B:{}},draft:{camera_plan:[]}};
    state.sourceMixerLayout='camera'; state.sourceMixerSavePending=0; finishMixerSave();`);
  await run('layoutTask');
  assert.equal(run('layoutCalls.length'), 1);
  assert.equal(run('state.sourceMixerLayout'), 'camera');
  assert.equal(run('state.sourceMixerLayoutRequest'), null);
});

test('optimistic Fit and Fill changes are retained when another mixer response is pending', () => {
  const {run} = twoSourceComposition();
  run(`const payload={screen_slot:'A',camera_slot:'B',primary_role:'screen',audio_slot:'A',first_slot:'B',stack_fit:'contain'};
    applyOptimisticSourceMixer(payload);`);
  assert.equal(run('state.project.manual.source_mixer.stack_fit'), 'contain');
  run(`applyOptimisticSourceMixer({...payload,stack_fit:'cover'});`);
  assert.equal(run('state.project.manual.source_mixer.stack_fit'), 'cover');
});

test('embedded preview scales preserve native source proportions in every output shape', () => {
  const {run} = app();
  for (const sourceRatio of [16/9, 4/3, 9/16]) for (const frameRatio of [16/9, 9/16, 1, 4/5]) {
    for (const share of [.3, .7]) {
      const panelRatio = frameRatio / share;
      const geometry = run(`embeddedFacePreviewGeometry({x:.1,y:.1,w:.5,h:.3},${sourceRatio},${panelRatio})`);
      assert.ok(Math.abs(geometry.width / geometry.height * panelRatio - sourceRatio) < 1e-9,
        'CSS percentage geometry must scale width and height uniformly, not squash faces');
    }
  }
});

test('camera-free content region handles a full-width top band, side-by-side and corner cameras', () => {
  const {run} = app();
  for (const [camera, expected] of [
    [{x:0,y:0,w:1,h:.3}, {x:0,y:.3,w:1,h:.7}],
    [{x:0,y:0,w:.5,h:1}, {x:.5,y:0,w:.5,h:1}],
    [{x:.75,y:0,w:.25,h:.3}, {x:0,y:0,w:.75,h:1}],
    [{x:.4,y:.4,w:.2,h:.2,content_focus:{x:1,y:.5}}, {x:.6,y:0,w:.4,h:1}],
  ]) assert.deepEqual(plain(run(`normalizedEmbeddedGeometry(${JSON.stringify(camera)}).content_region`)), expected);
  assert.equal(run('normalizedEmbeddedGeometry({x:0,y:0,w:1,h:1})'), null);
  assert.deepEqual(plain(run('normalizedEmbeddedGeometry({x:0,y:0,w:1,h:.3,content_region:{x:0,y:0,w:1,h:1}}).content_region')), {x:0,y:.3,w:1,h:.7});
});

test('embedded controls accept the whole top band and exact edge focus without NaN', () => {
  const {run} = app();
  run(`elements.embeddedCameraW.value='100'; elements.embeddedCameraH.value='30';
    elements.embeddedCameraX.value='0'; elements.embeddedCameraY.value='0';
    elements.embeddedContentX.value='0'; elements.embeddedContentY.value='100';`);
  assert.deepEqual(plain(run('embeddedEditorGeometryFromControls()')), {x:0,y:0,w:1,h:.3,content_focus:{x:0,y:1}});
  run("elements.embeddedCameraW.value='invalid'; elements.embeddedContentY.value='invalid';");
  assert.equal(run('embeddedEditorGeometryFromControls().w'), .25);
  assert.equal(run('embeddedEditorGeometryFromControls().content_focus.y'), .5);
});

test('30/70 embedded preview crops both panes and never repeats the camera in the lower pane', () => {
  const {run} = app();
  run('setupPreviewSources(); syncSecondaryPreview(5);');
  assert.equal(run('elements.previewB.src'), '/a.mp4');
  assert.equal(run('elements.previewStage.classList.contains("layout-embedded_stack")'), true);
  assert.equal(run('elements.previewA.style.objectFit'), 'fill');
  assert.equal(run('elements.previewB.style.objectFit'), 'fill');
  const a = plain(run('elements.previewA.style'));
  const topOfGame = parseFloat(a.top) + parseFloat(a.height) * .3;
  assert.ok(Math.abs(topOfGame) < .001, 'Only source pixels below the selected top camera appear in the game pane');
  assert.equal(run('elements.previewB.muted'), true);
  assert.equal(run('elements.previewA.muted'), false);
});

test('a second actual source invalidates stale embedded settings and does not load A into B', () => {
  const {run} = app();
  run(`state.project.sources.B={url:'/b.mp4',duration:20,has_audio:true}; setupPreviewSources(); syncSecondaryPreview(5);`);
  assert.equal(run('embeddedCameraCandidate()'), null);
  assert.equal(run('embeddedLayoutConfirmed()'), false);
  assert.equal(run('cameraAt(5)'), 'A');
  assert.equal(run('elements.previewB.src'), '/b.mp4');
  assert.equal(run('elements.previewB.hidden'), true);
});

test('full-source browsing preserves a confirmed embedded composition across removed gaps but respects explicit A scenes', () => {
  const {run} = app();
  run("state.project.draft.camera_plan=[{start:0,end:4,camera:'embedded_stack'},{start:8,end:10,camera:'A'}];");
  assert.equal(run('cameraAt(5)'), 'embedded_stack');
  assert.equal(run('cameraAt(9)'), 'A');
  run('state.project.draft.embedded_layout_confirmed=false;');
  assert.equal(run('cameraAt(5)'), 'A');
});

test('unconfirmed suggestions never duplicate source playback and stale B audio settings cannot mute A', () => {
  const {run} = app();
  run(`state.project.draft.embedded_layout_confirmed=false;
    state.project.manual.source_mixer={audio_slot:'B'}; setupPreviewSources(); syncSecondaryPreview(5);`);
  assert.equal(run('elements.previewB.src'), '');
  assert.equal(run('elements.previewB.hidden'), true);
  assert.equal(run('elements.previewA.muted'), false);
  assert.equal(run('elements.previewB.muted'), true);
});

test('disabling an embedded layout clears crop geometry from both sources', () => {
  const {run} = app();
  run(`setupPreviewSources(); syncSecondaryPreview(2);
    state.project.draft.layout='A'; state.project.draft.camera_plan=[{start:0,end:20,camera:'A'}];
    setupPreviewSources(); syncSecondaryPreview(2);`);
  for (const slot of ['A','B']) for (const property of ['width','height','left','top','objectFit'])
    assert.equal(run(`elements.preview${slot}.style.${property}`), '');
  assert.equal(run('elements.previewB.hidden'), true);
});

test('generic framing changes do not corrupt either embedded pane while paused', () => {
  const {run} = app();
  run('setupPreviewSources(); syncSecondaryPreview(2);');
  const original = plain(run('elements.previewA.style'));
  run(`elements.cropZoom.value='180'; elements.cropX.value='0'; elements.cropY.value='100'; applyFramingPreview();`);
  assert.equal(run('elements.previewA.style.transform'), 'none');
  assert.equal(run('elements.previewA.style.top'), original.top);
  assert.equal(run('elements.previewA.style.width'), original.width);
});

test('generic crop controls explain embedded ownership and re-enable for A scenes or a new B source', () => {
  const {run} = app();
  run('setupPreviewSources(); syncSecondaryPreview(2);');
  for (const id of ['cropX','cropY','cropZoom','resetCrop','cropSourceSelect']) assert.equal(run(`elements.${id}.disabled`), true);
  assert.equal(run('elements.embeddedCropHelp.hidden'), false);
  run(`state.project.draft.camera_plan.push({start:20,end:25,camera:'A'});
    elements.previewA.currentTime=21; syncSecondaryPreview(21);`);
  for (const id of ['cropX','cropY','cropZoom','resetCrop','cropSourceSelect']) assert.equal(run(`elements.${id}.disabled`), false);
  assert.equal(run('elements.embeddedCropHelp.hidden'), true);
  run("elements.cropZoom.value='180'; applyFramingPreview();");
  assert.equal(run('elements.previewA.style.transform'), 'scale(1.8)');
  run(`elements.previewA.currentTime=2; syncSecondaryPreview(2);
    state.project.sources.B={url:'/b.mp4',duration:20,has_audio:true}; setupPreviewSources(); syncSecondaryPreview(2);`);
  assert.equal(run('elements.cropZoom.disabled'), false);
  assert.equal(run('elements.embeddedCropHelp.hidden'), true);
});

test('content focus pans only inside the clear region at both extremes', () => {
  const {run} = app();
  for (const focus of [0,1]) {
    const geometry = run(`embeddedFacePreviewGeometry({x:.5,y:0,w:.5,h:1},16/9,(9/16)/.7,{x:${focus},y:${focus}})`);
    assert.ok(geometry.left + geometry.width * .5 <= .001);
    assert.ok(geometry.left + geometry.width >= 99.999);
    assert.ok(geometry.top <= .001);
    assert.ok(geometry.top + geometry.height >= 99.999);
  }
});

test('camera marking can seek to a later source frame without starting playback', () => {
  const {run} = app();
  run(`elements.embeddedCameraSeek.value='750'; elements.embeddedCameraVideo.paused=false; seekEmbeddedCameraFrame();`);
  assert.equal(run('elements.embeddedCameraVideo.currentTime'), 15);
  assert.equal(run('elements.embeddedCameraVideo.paused'), true);
  assert.equal(run('elements.embeddedCameraSeekOut.textContent'), '00:15.0');
});
