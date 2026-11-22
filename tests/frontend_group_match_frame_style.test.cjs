const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.join(__dirname,'..');
const all=fs.readFileSync(path.join(root,'web/studio-workbench.css'),'utf8');
const start=all.indexOf('/* Match framing:');
const end=all.indexOf('/* End Match framing. */',start);
const css=all.slice(start,end);

test('match framing is one bounded existing-group style section',()=>{
  assert.ok(start>=0 && end>start && css.length>500);
  for(const line of css.split('\n').filter(line=>line.includes('{')&&!line.startsWith('@')))
    assert.match(line,/#studioInspector \.layer-group-controls .*layer-group-frame-controls/);
  assert.doesNotMatch(css,/#timelineCanvas|\.timeline-scroll|\.preview-stage|\.media-frame-editor|position:\s*fixed|!important/);
});

test('native details disclosure is not forced open or replaced with a custom display mode',()=>{
  const details=css.match(/details\.layer-group-frame-controls \{([^}]*)\}/)?.[1];
  assert.ok(details);
  assert.doesNotMatch(details,/display:|height:|overflow:hidden/);
  assert.match(css,/> summary \{[^}]*min-height:36px;[^}]*overflow-wrap:anywhere;[^}]*cursor:pointer/);
  assert.doesNotMatch(css,/::marker|list-style:none|\[open\]/);
});

test('reference picker stays within a narrow inspector and uses native selection',()=>{
  assert.match(css,/\[data-group-frame-reference\] \{[^}]*box-sizing:border-box; width:100%; min-width:0; max-width:100%/);
  assert.match(css,/\[data-group-frame-reference\] \{[^}]*text-overflow:ellipsis/);
  assert.doesNotMatch(css,/appearance:none|direction:ltr|direction:rtl/);
});

test('saved-frame and changed-count text wrap instead of clipping long occurrence labels',()=>{
  assert.match(css,/label \{[^}]*display:grid;[^}]*min-width:0;[^}]*overflow-wrap:anywhere/);
  assert.match(css,/:is\(\[data-group-frame-summary\],\[data-group-frame-status\]\) \{[^}]*min-width:0;[^}]*white-space:normal; overflow-wrap:anywhere/);
});

test('apply action has a full-width bounded layout and wraps its target count',()=>{
  assert.match(css,/\[data-group-frame-apply\] \{[^}]*box-sizing:border-box; width:calc\(100% - 16px\); min-width:0; min-height:36px/);
  assert.match(css,/\[data-group-frame-apply\] \{[^}]*white-space:normal; overflow-wrap:anywhere/);
});

test('mobile disclosure, source picker and apply button have scoped 44px targets',()=>{
  assert.match(css,/@media \(max-width:899px\) \{\s*#advancedPanel #studioInspector \.layer-group-controls details\.layer-group-frame-controls :is\(summary,\[data-group-frame-reference\],\[data-group-frame-apply\]\) \{[^}]*min-height:44px/);
});

test('focus and disabled treatments remain visible for keyboard operation',()=>{
  assert.match(css,/:is\(summary,\[data-group-frame-reference\],\[data-group-frame-apply\]\):focus-visible \{ outline:2px solid var\(--focus-ring\); outline-offset:2px/);
  assert.match(css,/:is\(\[data-group-frame-reference\],\[data-group-frame-apply\]\):disabled \{ opacity:\.5; cursor:not-allowed/);
  assert.match(css,/@media \(forced-colors:active\)[\s\S]*outline-color:Highlight/);
});

test('host hidden state is retained without affecting other inspector controls',()=>{
  assert.match(css,/\.layer-group-frame-controls\[hidden\], #studioInspector \.layer-group-controls \.layer-group-frame-controls \[hidden\] \{ display:none/);
  assert.equal((css.match(/display:none/g)||[]).length,1);
});

test('theme surface and focus tokens already exist in shipped styles',()=>{
  const definitions=fs.readdirSync(path.join(root,'web')).filter(n=>n.endsWith('.css')).map(n=>fs.readFileSync(path.join(root,'web',n),'utf8')).join('\n');
  for(const token of new Set([...css.matchAll(/var\((--[\w-]+)\)/g)].map(m=>m[1])))
    assert.match(definitions,new RegExp(`${token}\\s*:`),token);
  assert.doesNotMatch(css,/var\(--bg\)/);
});

test('style-only work introduces no animation, rendering transform or text corruption',()=>{
  assert.doesNotMatch(css,/@keyframes|animation:|transition:|transform:|z-index:|[\u0000-\u0008\u000b\u000c\u000e-\u001f\ufffd]/);
});
