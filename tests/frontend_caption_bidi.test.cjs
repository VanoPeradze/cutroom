const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const css = fs.readFileSync(path.join(__dirname, '../web/styles.css'), 'utf8');
const html = fs.readFileSync(path.join(__dirname, '../web/index.html'), 'utf8');
const rules = [...css.matchAll(/\.preview-caption\s*\{([^}]+)\}/g)].map(match => match[1]).join(';');
test('caption preview retains authored line breaks without changing source text', () => {
  assert.match(rules, /white-space\s*:\s*pre-line\s*;/);
  assert.match(rules, /unicode-bidi\s*:\s*plaintext\s*;/);
  assert.match(html, /<div\b[^>]*id="previewCaption"[^>]*dir="auto"/);
});
test('all four caption styles keep paragraph direction and line breaks inherited', () => {
  for (const style of ['clean','bold','boxed','highlight']) {
    const selector = `.preview-caption[data-caption-style="${style}"]`;
    const at = css.indexOf(selector); assert.ok(at >= 0);
    const body = css.slice(at + selector.length, css.indexOf('}', at));
    assert.doesNotMatch(body, /white-space\s*:\s*(normal|nowrap)|unicode-bidi\s*:\s*(normal|bidi-override)/);
  }
});
