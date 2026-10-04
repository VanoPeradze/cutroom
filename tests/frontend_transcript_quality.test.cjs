const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');

const source = fs.readFileSync(path.join(__dirname, '../web/app.js'), 'utf8');
function shippedFunction(name) {
  const start = source.indexOf(`function ${name}(`);
  assert.ok(start >= 0);
  const end = source.indexOf('\nfunction ', start + 1);
  return source.slice(start, end);
}

class Element {
  constructor(tag = 'div') {
    this.tag = tag; this.children = []; this.dataset = {}; this.attributes = {}; this.events = {};
    this.textContent = ''; this.value = ''; this.hidden = false; this.scrollTop = 0;
    this.classList = {toggle() {}};
  }
  set innerHTML(value) {
    this.children = [];
    if (value.includes('transcript-seek')) {
      const seek = new Element('button'); seek.className = 'transcript-seek';
      const time = new Element('time'), text = new Element('span'), status = new Element('b');
      text.className = 'transcript-text'; seek.append(time, text, status);
      const edit = new Element('button'); edit.className = 'transcript-edit';
      this.append(seek, edit);
    }
  }
  append(...children) { for (const child of children) { child.parentElement = this; this.children.push(child); } }
  insertBefore(child, before) {
    const index = this.children.indexOf(before); assert.ok(index >= 0);
    child.parentElement = this; this.children.splice(index, 0, child);
  }
  querySelector(selector) {
    for (const child of this.children) {
      if (selector.startsWith('.') ? child.className?.split(' ').includes(selector.slice(1)) : child.tag === selector) return child;
      const match = child.querySelector(selector); if (match) return match;
    }
    return null;
  }
  setAttribute(name, value) { this.attributes[name] = value; }
  addEventListener(name, callback) { this.events[name] = callback; }
}

function app({count = 1, flagged = [{segment_id:'weak', reasons:['low_word_confidence']}]} = {}) {
  const elements = Object.fromEntries([
    'transcriptEditForm','transcriptEditText','transcriptEditTime','transcriptEditStatus',
    'transcriptSave','transcriptDiscard','transcriptSaveAll','transcriptPrevious','transcriptNext',
    'transcriptList','transcriptSearch','transcriptFilter','transcriptLanguage','transcriptResults',
  ].map(id => [id, new Element(id)]));
  const card = new Element(); card.append(elements.transcriptList);
  elements.transcriptEditForm.append(elements.transcriptEditText);
  elements.transcriptFilter.value = 'all';
  const segments = [
    {id:'weak',start:1,end:3,text:'אני בודק OpenAI'},
    {id:'clear',start:4,end:6,text:'A clear sentence'},
  ];
  const state = {project:{id:'project',analysis:{transcript:{segments},
    transcript_quality:{review_segments:flagged,review_segment_count:count}}},
    transcriptBuffers:new Map(),transcriptSaving:false,manualEditBusy:false};
  const scope = vm.createContext({state,elements, document:{createElement:tag => new Element(tag)},
    selectedTranscriptSegment:() => state.project.analysis.transcript.segments[0],
    transcriptBufferKey:id => id, foregroundBusy:() => false,
    transcriptMappingLabel:segment => `Source ${segment.start}–${segment.end}`,
    transcriptTimelineMapping:(start,end) => ({ranges:[{start,end}],independent:false}),
    pendingTranscriptBuffers:() => [...state.transcriptBuffers.values()],
    renderLanguageDetectionStatus() {}, highlightTranscriptSelection() {}, rangeMostlyRemoved:() => false,
    formatTime:time => String(time), languageName:() => 'Hebrew', uiCopy:(_he,en) => en,
    $:(selector,root) => root.querySelector(selector),
    selectTranscriptLine:segment => {scope.selectedLine = segment.id;}, beginTranscriptEdit() {},
  });
  vm.runInContext(shippedFunction('renderTranscriptDetail') + '\n' + shippedFunction('renderTranscript'), scope);
  return {state,elements,card,scope,run:code => vm.runInContext(code, scope)};
}

test('ASR review metadata adds a visible row badge and honest summary without changing seeking', () => {
  const {run,card,elements,scope} = app();
  run('renderTranscript()');
  assert.match(card.querySelector('.transcript-quality-note').textContent, /1 line was flagged/);
  assert.match(card.querySelector('.transcript-quality-note').textContent, /not measured accuracy/);
  assert.equal(elements.transcriptList.children.length, 2);
  const weak = elements.transcriptList.children[0], clear = elements.transcriptList.children[1];
  assert.equal(weak.querySelector('.transcript-review-badge').textContent, 'Review');
  assert.equal(clear.querySelector('.transcript-review-badge'), null);
  assert.equal(weak.querySelector('.transcript-text').textContent, 'אני בודק OpenAI');
  weak.querySelector('.transcript-seek').events.click({shiftKey:false});
  assert.equal(scope.selectedLine, 'weak');
  assert.equal(weak.querySelector('b').textContent, 'In edit');
});

test('selected-line warning describes original AI confidence and preserves unsaved text', () => {
  const {run,elements,state} = app();
  run('renderTranscriptDetail()');
  const note = elements.transcriptEditForm.querySelector('.transcript-line-review');
  assert.match(note.textContent, /Original AI confidence/);
  assert.match(note.textContent, /Saving text does not recheck/);
  elements.transcriptEditText.value = 'My correction';
  state.transcriptBuffers.set('weak',{text:'My correction'});
  run('renderTranscriptDetail(false)');
  assert.equal(elements.transcriptEditText.value, 'My correction');
  assert.match(elements.transcriptEditStatus.textContent, /Unsaved/);
  assert.equal(elements.transcriptSave.disabled, false);
});

test('switching to a transcript without confidence metadata clears old review indicators', () => {
  const {run,state,card,elements} = app();
  run('renderTranscript()');
  delete state.project.analysis.transcript_quality;
  run('renderTranscript()');
  assert.equal(card.querySelector('.transcript-quality-note').hidden, true);
  assert.equal(elements.transcriptEditForm.querySelector('.transcript-line-review').hidden, true);
  assert.equal(elements.transcriptList.querySelector('.transcript-review-badge'), null);
});

test('capped review metadata discloses partial markers and search preserves the total warning', () => {
  const {run,card,elements} = app({count:2});
  elements.transcriptSearch.value = 'clear';
  run('renderTranscript()');
  const note = card.querySelector('.transcript-quality-note');
  assert.match(note.textContent, /2 lines were flagged/);
  assert.match(note.textContent, /Only 1 flag has line markers; search and filters may hide them/);
  assert.equal(elements.transcriptList.children.length, 1);
  assert.equal(elements.transcriptList.querySelector('.transcript-review-badge'), null);
});
