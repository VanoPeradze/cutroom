const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.join(__dirname, '..');
const css = fs.readFileSync(path.join(root, 'web/studio-finish.css'), 'utf8');
const html = fs.readFileSync(path.join(root, 'web/index.html'), 'utf8');
const packageSource = fs.readFileSync(path.join(root, 'scripts/build_test_package.py'), 'utf8');
const luminance = hex => hex.slice(1).match(/../g).map(x => parseInt(x,16)/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4).reduce((s,v,i)=>s+v*[.2126,.7152,.0722][i],0);
const ratio = (a,b) => { const l=[luminance(a),luminance(b)].sort((a,b)=>a-b); return (l[1]+.05)/(l[0]+.05); };
const tokens = block => Object.fromEntries([...block.matchAll(/--([\w-]+):(#[\da-f]{6})/g)].map(m=>[m[1],m[2]]));
const themeTokens = fs.readFileSync(path.join(root, 'web/tokens.css'), 'utf8');
const dark = tokens(themeTokens.match(/:root\s*\{([^}]+)\}/)[1]);
const light = tokens(themeTokens.match(/html\[data-theme=light\]\s*\{([^}]+)\}/)[1]);
test('workbench ships its own licensed proportional fonts, independent of the marketing site',()=>{
  for(const name of ['Geist.ttf','Geist-OFL.txt','NotoSansHebrew.ttf','NotoSansHebrew-OFL.txt']) {
    assert.ok(fs.statSync(path.join(root,'web/fonts',name)).size>100);
    assert.ok(packageSource.includes(`"web/fonts/${name}"`),`${name} must be included by source packages`);
  }
  assert.match(themeTokens,/--mono:var\(--font\)/);
  assert.doesNotMatch(css,/ui-monospace|font-family:[^;}]*monospace|url\(['"]?https?:/);
  assert.match(css,/font-display:swap/);
  assert.match(html,/studio-finish.css\?v=20261112-workbench1/);
});
test('both themes give readable controls, accents and timeline surfaces',()=>{
  for(const [name,t] of [['dark',dark],['light',light]]) {
    for(const fg of ['paper','paper-dim','muted']) for(const bg of ['ink','ink-2','ink-3','ink-4','surface-panel','surface-inset','surface-chrome','surface-raised','surface-hover'])
      assert.ok(ratio(t[fg],t[bg])>=4.5,`${name} ${fg}/${bg}`);
    assert.ok(ratio(t['cyan-text'],t['surface-selected'])>=4.5);
    for(const bg of ['timeline-bg','timeline-ruler','timeline-lane','timeline-lane-alt'])
      assert.ok(ratio(t['timeline-text'],t[bg])>=4.5,`${name} timeline text/${bg}`);
    assert.ok(ratio(t['timeline-label'],t['timeline-clip'])>=4.5,`${name} source labels`);
  }
  assert.ok(ratio('#271c16',dark['primary-fill'])>=4.5);
  assert.ok(ratio('#ffffff',light['primary-fill'])>=4.5);
});
test('new finish preserves workspace geometry, keyboard focus and accessible motion alternatives',()=>{
  assert.doesNotMatch(css,/#previewStage|preview-viewport|--workspace-inspector-width|--workspace-timeline-height/);
  assert.match(css,/:focus-visible/);
  assert.match(css,/prefers-reduced-motion:reduce/);
  assert.match(css,/forced-colors:active/);
  assert.match(css,/\.eyebrow[^\n]+display:none/);
  assert.match(css,/@media\(max-width:899px\)/);
  assert.match(css,/\[dir=rtl\]/);
});
