const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const sourcePath = process.env.CUTROOM_TIMELINE_SOURCE ||
  path.join(__dirname, '../web/timeline.js');
const source = fs.readFileSync(sourcePath, 'utf8').replace(/^export /gm, '');

function fixture() {
  const images = [];
  class FakeImage {
    set src(value) { this.url = value; images.push(this); }
  }
  const scope = vm.createContext({
    Image: FakeImage,
    window: {devicePixelRatio:1},
    ResizeObserver: class {observe() {}},
    requestAnimationFrame: () => 1,
    cancelAnimationFrame() {},
  });
  vm.runInContext(source + '\nglobalThis.TimelineView = TimelineView;', scope);
  const canvas = {style:{},getContext:()=>({}),addEventListener(){},setAttribute(){}};
  const scroll = {clientWidth:600,scrollLeft:0,addEventListener(){},closest:()=>null};
  const timeline = new scope.TimelineView(canvas, scroll, () => {});
  const project = (id, url) => ({id,sources:{A:{duration:120,thumbnail_urls:[url]}}});
  return {timeline,images,project};
}

test('a late thumbnail load cannot overwrite a newer snapshot of the same project', async () => {
  const {timeline,images,project} = fixture();
  timeline.project = project('same-project','/old.jpg');
  const oldLoad = timeline.loadImages();
  timeline.project = project('same-project','/new.jpg');
  const newLoad = timeline.loadImages();
  images.find(image => image.url === '/new.jpg').onload();
  await newLoad;
  images.find(image => image.url === '/old.jpg').onload();
  await oldLoad;
  assert.equal(timeline.images[0]?.url, '/new.jpg');
});

test('switching projects clears the previous project thumbnails immediately', async () => {
  const {timeline,images,project} = fixture();
  timeline.project = project('first','/first.jpg');
  const first = timeline.loadImages();
  images[0].onload();
  await first;
  timeline.setProject(project('second','/second.jpg'));
  assert.equal(timeline.images.length, 0);
});

test('changing thumbnail URLs in the same project clears the old source while loading', async () => {
  const {timeline,images,project} = fixture();
  timeline.setProject(project('same','/old.jpg'));
  images[0].onload();
  await Promise.resolve();
  await Promise.resolve();
  assert.equal(timeline.images[0]?.url, '/old.jpg');
  timeline.setProject(project('same','/new.jpg'));
  assert.equal(timeline.images.length, 0);
});

test('reopening the same thumbnail source does not blank it while it reloads', async () => {
  const {timeline,images,project} = fixture();
  timeline.setProject(project('same','/same.jpg'));
  images[0].onload();
  await Promise.resolve();
  await Promise.resolve();
  timeline.setProject(project('same','/same.jpg'));
  assert.equal(timeline.images[0]?.url, '/same.jpg');
});

test('secondary thumbnails can load while source A thumbnails are still pending', async () => {
  const {timeline,images,project} = fixture();
  const p = project('same','/a.jpg');
  p.sources.B = {thumbnail_urls:['/b.jpg']};
  timeline.project = p;
  const pending = timeline.loadImages();
  const b = images.find(image => image.url === '/b.jpg');
  assert.ok(b, 'source B should not wait for source A');
  b.onload();
  assert.equal(timeline.mediaImages.get('/b.jpg'), b);
  images.find(image => image.url === '/a.jpg').onload();
  await pending;
});

test('a secondary thumbnail from the previous project cannot enter the new cache', async () => {
  const {timeline,images,project} = fixture();
  const first = project('first','/a.jpg');
  first.sources.B = {thumbnail_urls:['/old-b.jpg']};
  timeline.setProject(first);
  const oldB = images.find(image => image.url === '/old-b.jpg');
  assert.ok(oldB);
  timeline.setProject(project('second','/new-a.jpg'));
  oldB.onload();
  assert.equal(timeline.mediaImages.has('/old-b.jpg'), false);
});
