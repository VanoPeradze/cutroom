const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const css=fs.readFileSync('web/studio-workbench.css','utf8');
const section=css.slice(css.indexOf('/* Imported preview verification'),css.indexOf('/* End imported preview verification. */'));
test('repair is a full-width asset-owned secondary row, not permanent chrome',()=>{
  assert.match(section,/\.media-library \.media-asset > \.media-preview-repair \{[^}]*grid-column:1 \/ -1/);
  assert.match(section,/\[data-repair-preview\] \{ flex-basis:100%/);
  assert.doesNotMatch(section,/position:fixed|z-index|\.editor-toolbar/);
});
test('repair status wraps and preserves native hidden actions',()=>{
  assert.match(section,/\.media-preview-repair-status \{[^}]*overflow-wrap:anywhere/);
  assert.match(section,/\.media-preview-repair > \[hidden\] \{ display:none/);
});
test('repair controls retain visible focus and disabled affordance',()=>{
  assert.match(section,/> button:disabled \{ opacity:\.5; cursor:not-allowed/);
  assert.match(section,/:focus-visible \{ outline:2px solid var\(--focus-ring\)/);
  assert.match(section,/@media \(forced-colors:active\)/);
});
test('mobile repair actions and Source link use scoped 44px targets',()=>{
  assert.match(section,/@media \(max-width:899px\)/);
  assert.match(section,/#advancedPanel \.media-library \.media-preview-repair > button, #studioInspector \.library-source-monitor \.library-preview-repair-link \{ min-height:44px/);
});
test('source repair link stays in its source context and uses logical text alignment',()=>{
  assert.match(section,/#studioInspector \.library-source-monitor \.library-preview-repair-link \{[^}]*text-align:start/);
  assert.doesNotMatch(section,/text-align:left|float:left/);
});
test('repair surfaces use existing theme tokens without animation',()=>{
  assert.match(section,/background:var\(--surface-inset\)/);
  assert.doesNotMatch(section,/var\(--bg\)|animation:|transition:all|!important/);
  assert.ok(css.indexOf('/* Imported preview verification')<css.indexOf('/* Named-track levels'));
});
