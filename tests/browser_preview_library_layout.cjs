// Isolated DOM regression using the shipped styles and UI modules, no project,
// server, media files or user state. Requires an existing Chromium + Playwright.
// node tests/browser_preview_library_layout.cjs /usr/bin/chromium
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');
const root = path.resolve(__dirname, '..');
const html = fs.readFileSync(path.join(root,'web/index.html'),'utf8');
const styles = [...html.matchAll(/href="\/assets\/([^"?]+\.css)/g)].map(m => fs.readFileSync(path.join(root,'web',m[1]),'utf8')).join('\n');
(async () => {
 const browser = await chromium.launch({executablePath:process.argv[2] || '/usr/bin/chromium',headless:true,args:['--no-sandbox']});
 try {
  const page = await browser.newPage();
  await page.setContent(`<style>${styles}</style><div id="advancedPanel" class="studio-workspace"><div id="studioPreviewDock" class="studio-preview-dock"><div id="previewColumn" class="preview-column"><div id="previewStage" class="preview-stage" data-aspect="9:16"><video id="previewA"></video></div><div class="preview-controls"><input id="previewSeek" type="range"><button id="playButton">Play</button><span id="previewTime">00:01 / 01:30</span></div><div id="notice" style="height:90px">Missing B footage</div></div></div><section id="studioShelfMedia" class="studio-shelf"><header class="shelf-heading"><h3>Media</h3></header><div class="source-library"><button class="source-library-card" data-kind="video"><span class="library-thumb"></span><span>Gameplay recording with a long file name.mp4</span><small>A · 38:06</small></button><button class="source-library-card" data-kind="video"><span class="library-thumb"></span><span>Camera B.mp4</span><small>B · 38:06</small></button></div><div class="media-library"><div class="media-asset" data-kind="audio"><span class="library-thumb"></span><span>Music.wav</span><small>02:00</small><button>Add</button><button>Review</button></div></div></section></div>`);
  await page.addScriptTag({type:'module',content:fs.readFileSync(path.join(root,'web/workspace.js'),'utf8')+'\nwindow.viewportTest = initPreviewViewport({document,preview:document.getElementById("previewColumn")});'});
  await page.waitForFunction(() => window.viewportTest);
  await page.addScriptTag({content:fs.readFileSync(path.join(root,'web/studio-screens.js'),'utf8')});
  await page.addStyleTag({content:'#advancedPanel {display:block !important;} #studioPreviewDock {width:var(--test-width);height:var(--test-height);padding:0 !important;} #studioShelfMedia {width:240px;padding:0;}'});
  for (const [width,height] of [[1080,430],[540,300],[320,380]]) {
   for (const aspect of ['16:9','9:16','1:1','4:5']) {
    for (const notice of [false,true]) {
     await page.evaluate(({width,height,aspect,notice}) => {
      document.documentElement.style.setProperty('--test-width',width+'px');document.documentElement.style.setProperty('--test-height',height+'px');
      document.querySelector('#previewStage').dataset.aspect=aspect;document.querySelector('#notice').hidden=!notice;
     },{width,height,aspect,notice});
     const boxes=await page.evaluate(()=>Object.fromEntries(['previewStage','previewColumn','previewSeek'].map(id=>{const r=document.getElementById(id).getBoundingClientRect();return[id,{x:r.x,y:r.y,w:r.width,h:r.height,b:r.bottom}]})));
     const [a,b]=aspect.split(':').map(Number);
     assert.ok(boxes.previewStage.h>20,JSON.stringify({width,height,aspect,notice,boxes}));
     assert.ok(Math.abs(boxes.previewStage.w/boxes.previewStage.h-a/b)<.02,'Preserve composition aspect ratio');
     assert.ok(boxes.previewStage.b<=boxes.previewSeek.y+1,'Picture never overlaps seek/transport');
     assert.ok(boxes.previewStage.b<=boxes.previewColumn.b+1,'Picture remains inside monitor');
    }
   }
  }
  await page.evaluate(()=>{window.originalCard=document.querySelector('.source-library-card');window.cardClicks=0;originalCard.addEventListener('click',()=>window.cardClicks++);window.originalVideo=document.querySelector('#previewA');originalVideo.dataset.playhead='13.5';});
  for(const view of ['grid','list','grid','list']) {
   await page.locator('.library-view [data-view="'+view+'"]').click();
   assert.equal(await page.locator('#studioShelfMedia').getAttribute('data-library-view'),view);
   assert.equal(await page.locator('.library-view [data-view="'+view+'"]').getAttribute('aria-pressed'),'true');
  }
  await page.locator('.library-search').fill('Camera B');
  assert.equal(await page.locator('.source-library-card:visible').count(),1);
  await page.locator('.library-search').fill('');
  await page.locator('.library-filter button[data-value="audio"]').click();
  assert.equal(await page.locator('.source-library-card:visible').count(),0);
  assert.equal(await page.locator('.media-asset:visible').count(),1);
  await page.locator('.library-filter button[data-value="all"]').click();
  await page.locator('.source-library-card').first().click();
  assert.equal(await page.evaluate(()=>window.cardClicks),1);
  assert.equal(await page.evaluate(()=>originalCard===document.querySelector('.source-library-card')&&originalVideo===document.querySelector('#previewA')&&originalVideo.dataset.playhead==='13.5'),true);
  const card=await page.locator('.source-library-card').first().boundingBox();
  assert.ok(card.height<110,'Compact list retains readable metadata');
  const actions=await page.locator('.media-asset > button').evaluateAll(buttons=>buttons.map(b=>b.getBoundingClientRect().y));
  assert.ok(actions[1]>actions[0],'Imported asset actions do not overlap');
  await page.evaluate(()=>document.querySelector('#previewColumn').classList.add('video-expanded'));
  assert.ok(await page.evaluate(()=>document.querySelector('#previewStage').getBoundingClientRect().bottom<=document.querySelector('.preview-controls').getBoundingClientRect().top+1),'Fullscreen transport remains outside picture');
  await page.evaluate(()=>{document.querySelector('#previewColumn').classList.remove('video-expanded');window.viewportTest.restore();});
  assert.equal(await page.locator('#previewColumn > #previewStage').count(),1);
  console.log('PASS: 24 geometry cases; repeated grid/list, filtering, retained nodes/actions, compact cards, fullscreen and restore.');
 } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
