const assert = require('node:assert/strict');
const test = require('node:test');
const {browserElementBox, readBrowserElementBox} = require('./browser_dom_box.cjs');

function dom(overrides = {}) {
  const seen = {selectors: [], scrolls: [], points: []};
  const element = {
    disabled: false,
    closest: () => null,
    scrollIntoView: options => seen.scrolls.push(options),
    getBoundingClientRect: () => ({x: 10, y: 20, width: 80, height: 40}),
    contains: () => false,
    ...overrides,
  };
  const document = {
    querySelector: selector => { seen.selectors.push(selector); return element; },
    elementFromPoint: (x, y) => { seen.points.push([x, y]); return element; },
  };
  return {seen, element, document};
}

test('CDP sends adversarial selectors as argument data with fixed executable source', async () => {
  const values = [
    '#safe-control',
    "#x');globalThis.injected=true;//",
    '` ${globalThis.injected=true} \\ "',
    'line\nbreak\rcontrol',
    'line\u2028separator\u2029control',
    '</script><script>globalThis.injected=true</script>',
  ];
  const declaration = readBrowserElementBox.toString();
  for (const selector of values) {
    const fixture = dom();
    const calls = [];
    const cdp = {async send(method, params) {
      // Model CDP's JSON wire boundary without evaluating generated source.
      params = JSON.parse(JSON.stringify(params));
      calls.push({method, params});
      if (method === 'Runtime.evaluate') {
        assert.deepEqual(params, {expression: 'globalThis', returnByValue: false});
        return {result: {objectId: 'owned-global'}};
      }
      if (method === 'Runtime.callFunctionOn') {
        assert.equal(params.objectId, 'owned-global');
        assert.equal(params.functionDeclaration, declaration);
        assert.equal(params.functionDeclaration.includes(selector), false);
        assert.deepEqual(params.arguments, [{value: selector}]);
        return {result: {value: readBrowserElementBox.call({document: fixture.document}, params.arguments[0].value)}};
      }
      assert.equal(method, 'Runtime.releaseObject');
      assert.deepEqual(params, {objectId: 'owned-global'});
      return {};
    }};
    assert.deepEqual(await browserElementBox(cdp, selector), {x: 10, y: 20, width: 80, height: 40});
    assert.deepEqual(fixture.seen.selectors, [selector]);
    assert.deepEqual(calls.map(call => call.method), ['Runtime.evaluate', 'Runtime.callFunctionOn', 'Runtime.releaseObject']);
  }
});

test('box rejects missing, disabled and inert controls before scrolling', () => {
  for (const overrides of [{disabled: true}, {closest: () => ({inert: true})}]) {
    const fixture = dom(overrides);
    assert.throws(() => readBrowserElementBox.call({document: fixture.document}, '#control'), /Unavailable or inert/);
    assert.deepEqual(fixture.seen.scrolls, []);
  }
  const fixture = dom();
  fixture.document.querySelector = () => null;
  assert.throws(() => readBrowserElementBox.call({document: fixture.document}, '#missing'), /Unavailable or inert/);
});

test('box retains hidden and covered control checks', () => {
  for (const rect of [{x: 1, y: 2, width: 0, height: 40}, {x: 1, y: 2, width: 80, height: 0}]) {
    const fixture = dom({getBoundingClientRect: () => rect});
    assert.throws(() => readBrowserElementBox.call({document: fixture.document}, '#hidden'), /Hidden UI control/);
  }
  for (const hit of [null, {}]) {
    const fixture = dom();
    fixture.document.elementFromPoint = () => hit;
    assert.throws(() => readBrowserElementBox.call({document: fixture.document}, '#covered'), /UI control is covered/);
  }
});

test('box scrolls to center and permits a descendant hit', () => {
  const child = {};
  const fixture = dom({contains: hit => hit === child});
  fixture.document.elementFromPoint = (x, y) => { fixture.seen.points.push([x, y]); return child; };
  assert.deepEqual(readBrowserElementBox.call({document: fixture.document}, '#control'), {x: 10, y: 20, width: 80, height: 40});
  assert.deepEqual(fixture.seen.scrolls, [{block: 'center'}]);
  assert.deepEqual(fixture.seen.points, [[50, 40]]);
});

test('CDP releases its handle when the browser function throws', async () => {
  const calls = [];
  const cdp = {async send(method, params) {
    calls.push({method, params});
    if (method === 'Runtime.evaluate') return {result: {objectId: 'owned-global'}};
    if (method === 'Runtime.callFunctionOn') return {exceptionDetails: {text: 'Unavailable or inert UI control'}};
    return {};
  }};
  await assert.rejects(browserElementBox(cdp, '#disabled'), /Unavailable or inert/);
  assert.equal(calls.at(-1).method, 'Runtime.releaseObject');
});

test('CDP refuses a missing global handle without invoking browser code', async () => {
  const methods = [];
  const cdp = {async send(method) { methods.push(method); return {result: {value: null}}; }};
  await assert.rejects(browserElementBox(cdp, '#control'), /Browser global object unavailable/);
  assert.deepEqual(methods, ['Runtime.evaluate']);
});
