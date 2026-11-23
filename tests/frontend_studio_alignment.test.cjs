const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const root=path.join(__dirname,'..'),css=fs.readFileSync(path.join(root,'web/studio-workbench.css'),'utf8');
const start=css.indexOf('/* Workbench alignment:'),end=css.indexOf('/* End workbench alignment. */',start),section=css.slice(start,end);
test('alignment correction is bounded to the modern workbench, not a new editor surface',()=>{
 assert(start===0&&end>start);assert.doesNotMatch(section,/timelineCanvas|timeline-scroll|track-header|transform:|direction:|z-index:|position:\s*(?:fixed|absolute)|display:\s*none/);
 for(const line of section.split('\n').filter(x=>x.includes('{')&&!x.trimStart().startsWith('@')))assert.match(line,/#advancedPanel\.workbench-ready|body\.studio-open \.app-chrome :is\(#manualUndo,#manualRedo\)|#previewColumn:is\(\.video-expanded,:fullscreen\)/);
});
test('imported usage filter spans the existing full-width shelf grid',()=>assert.match(section,/#studioShelfMedia \.library-usage-label \{ grid-column:1\/-1; width:100%;/));
test('narrow media-pool heading keeps the existing Import control beside its title',()=>{
 assert.match(section,/#studioShelf \.shelf-heading \{ gap:6px; \}/);assert.match(section,/#studioShelf \.shelf-heading h3 \{ min-width:0; white-space:nowrap;/);
});
test('desktop pane header interiors share the existing 38px border-box baseline',()=>{
 assert.match(section,/@media \(min-width:900px\) and \(min-height:540px\)/);
 assert.match(section,/\.shelf-heading \{ box-sizing:border-box; height:38px; min-height:38px; padding-block:0;/);
 assert.match(section,/> \.workbench-inspector-switch \{ box-sizing:border-box; height:38px; min-height:38px;/);
 assert.match(section,/> \.workbench-inspector-switch button \{ box-sizing:border-box; height:100%; min-height:0;/);
});
test('only legacy transcript padding needs a modern bounded important override',()=>{
 const lines=section.split('\n').filter(x=>/!important;/.test(x)&&!x.includes('#previewColumn:is('));assert.equal(lines.length,2);
 for(const line of lines)assert.match(line,/\.workbench-ready\.studio-transcript > #studioInspector \{ padding:0 (?:16|12)px 16px !important; \}/);
});
test('embedded caption and output headings are content rather than negative-margin pane chrome',()=>assert.match(section,/:is\(#studioShelfCaptions,#studioShelfOutput\) > \.shelf-heading \{ min-height:0; margin:0 0 12px; padding:0; background:transparent; border:0;/));
test('narrow desktop transport removes only the already-hidden Restart grid track',()=>{
 assert.match(section,/@container studio-monitor \(max-width:540px\)/);
 assert.match(section,/grid-template-columns:minmax\(0,1fr\) 38px 120px 34px; grid-template-areas:"seek seek seek seek" "mode play time full"; gap:6px/);
 assert.doesNotMatch(section.slice(0,section.indexOf('/* Expanded transport')),/restart.*display:/);
});
test('mobile actions have equal 44px native targets and a matching monitor allowance',()=>{
 assert.match(section,/--monitor-controls-space:112px/);
 assert.match(section,/grid-template-columns:44px 44px minmax\(0,1fr\) 44px; grid-template-rows:8px 44px 44px/);
 assert.match(section,/width:44px; height:44px; min-height:44px/);
 for(const line of section.split('\n').filter(x=>x.includes('#studioPreviewDock')&&!x.includes(':has(')))assert.match(line,/#previewColumn:not\(\.video-expanded\):not\(:fullscreen\)/);
});
test('compact landscape allocation does not shrink portrait/square previews or timeline row height',()=>{
 assert.match(section,/:has\(#studioPreviewDock #previewStage\[data-aspect="16:9"\]\)/);
 assert.match(section,/clamp\(284px,calc\(56\.25vw \+ 108\.75px\),400px\) var\(--workspace-timeline-height,256px\) max-content max-content/);
 assert.doesNotMatch(section,/data-aspect="(?:9:16|1:1|4:5)"|--workspace-timeline-height:/);
});
test('alignment cache is independent from paused Match framing scripts',()=>{
 const html=fs.readFileSync(path.join(root,'web/index.html'),'utf8');assert.match(html,/studio-workbench\.css\?v=20261117-urgent-alignment2/);
 assert.doesNotMatch(section,/animation|transition|pointer-events/);
});

test('icon glyph centering preserves display and accessible labels without two-row drift',()=>{
 assert.match(section,/body\.studio-open \.app-chrome :is\(#manualUndo,#manualRedo\) \{ align-content:center; justify-content:center; gap:0;/);
 assert.match(section,/#advancedPanel\.workbench-ready \.timeline-tools button,/);
 assert.doesNotMatch(section,/content:\s*[\"']|font-size:0|display:inline-flex/);
});

test('expanded viewer has intrinsic transport height and explicit complete grid placement',()=>{
 const expanded=section.slice(section.indexOf('/* Expanded transport'));
 assert.match(expanded,/flex:0 0 auto; height:auto; min-height:0;/);
 assert.match(expanded,/grid-template-rows:8px 44px !important/);
 assert.match(expanded,/grid-template-rows:8px 44px 44px !important/);
 for(const area of ['seek','mode','restart','play','time','full'])assert.match(expanded,new RegExp('grid-area:'+area+' !important'));
 assert.doesNotMatch(expanded,/#advancedPanel|#studioPreviewDock|preview-stage|preview-viewport/);
});
test('expanded alignment keeps all native controls and contains only legacy-required important rules',()=>{
 const expanded=section.slice(section.indexOf('/* Expanded transport'));
 assert.match(expanded,/#restartPreview \{ grid-area:restart !important; display:inline-grid;/);
 assert.match(expanded,/#previewFullscreen \{ grid-area:full !important; position:static; inset:auto;/);
 assert.match(expanded,/width:44px; height:44px; min-height:44px/);
 for(const line of expanded.split('\n').filter(x=>x.includes('!important')))assert.match(line,/grid-template-|grid-area:/);
 assert.doesNotMatch(expanded,/display:none|overflow:hidden|height:100|fixed/);
});

test('fallback dialog seek input cannot inherit the generic 40px form height',()=>assert.match(section,/> #previewSeek \{ grid-area:seek !important; width:100%; height:8px; min-height:0; margin:0;/));
