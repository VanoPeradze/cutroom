// Opt-in browser qualification. Use an already-installed Playwright and Chromium.
// PLAYWRIGHT_MODULE may point to an installed package; CHROME_PATH and CAPTURE_DIR are optional.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {createServer} from 'node:http';
import {readFile, writeFile} from 'node:fs/promises';
import {dirname, extname, resolve, sep} from 'node:path';
import {fileURLToPath} from 'node:url';
const require = createRequire(import.meta.url);
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const site = resolve(dirname(fileURLToPath(import.meta.url)),'public');
const types = {'.css':'text/css','.js':'text/javascript','.svg':'image/svg+xml','.html':'text/html; charset=utf-8','.png':'image/png','.ttf':'font/ttf'};
const server = createServer(async(req,res) => {
  try {
    const name = decodeURIComponent(new URL(req.url,'http://localhost').pathname);
    const target = resolve(site,'.'+(name === '/' ? '/index.html' : name));
    if (!target.startsWith(site+sep) || !types[extname(target)]) {res.writeHead(404).end();return;}
    res.setHeader('Content-Type',types[extname(target)]);res.end(await readFile(target));
  } catch {res.writeHead(404).end();}
});
await new Promise((ok,fail) => {server.once('error',fail);server.listen(0,'127.0.0.1',ok);});
const base='http://127.0.0.1:'+server.address().port;
let browser;
const report={cases:[],errors:[],externalRequests:[]};
async function capture(page,name) {
  if(process.env.CAPTURE_DIR) await page.screenshot({path:resolve(process.env.CAPTURE_DIR,'cutroom-night-drive-'+name+'.png'),animations:'disabled'});
}
try {
  browser=await chromium.launch({headless:true,...(process.env.CHROME_PATH?{executablePath:process.env.CHROME_PATH}:{})});
  for (const size of [[1440,900],[1024,768],[768,1024],[390,844],[320,740]]) for (const lang of ['en','he']) {
    const [width,height]=size;
    const p=await browser.newPage({viewport:{width,height},reducedMotion:'reduce'});
    p.on('pageerror',e=>report.errors.push(String(e)));
    p.on('console',m=>{if(m.type()==='error')report.errors.push(m.text());});
    p.on('request',r=>{if(!r.url().startsWith(base))report.externalRequests.push(r.url());});
    await p.goto(base+'/?lang='+lang,{waitUntil:'networkidle'});
    await p.evaluate(()=>document.fonts.ready);
    const $=s=>p.locator(s), prop=(s,k)=>$(s).getAttribute(k), visible=(s)=>$(s).isVisible();
    assert.equal(await prop('html','lang'),lang);
    assert.equal(await prop('html','dir'),lang==='he'?'rtl':'ltr');
    assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'horizontal overflow');
    assert.match(await prop('#downloadButton','href'),/hebrew1\/CUTROOM-1.3-Beta-Windows-ba67003.zip$/);
    assert.match(await prop('#macDownloadButton','href'),/hebrew1\/CUTROOM-1.3-Beta-combined-ba67003.zip$/);
    assert.equal(await visible('.reel-tools'),true);
    assert.equal(await $('.reel-still:visible').count(),1);
    assert.equal(await $('.reel-still:visible').evaluate(i=>i.complete && i.naturalWidth>0),true);
    assert.equal(await prop('#night-drive','data-playing'),'false');
    assert.ok((await $('#reel-title').innerText()).includes(lang==='he'?'נסיעת לילה':'Night Drive'));
    assert.ok(await p.evaluate(()=>{
      const a=document.querySelector('.reel').getBoundingClientRect(),b=document.querySelector('.hero-title').getBoundingClientRect();
      return b.bottom<=a.top+1||a.right<=b.left+1||b.right<=a.left+1;
    }),'title intersects poster');
    assert.ok(await p.evaluate(()=>{
      const a=document.querySelector('.reel-tally').getBoundingClientRect(),b=document.querySelector('#reel-title').getBoundingClientRect();
      return a.right<=b.left+1||b.right<=a.left+1||a.bottom<=b.top+1||b.bottom<=a.top+1;
    }),'shot number overlaps poster title');
    if(width===1440||width===390) await capture(p,lang+'-'+width);
    await $('[data-mode="flashback"]').click();
    assert.equal(await prop('#night-drive','data-shot'),'lake');
    assert.equal(await prop('[data-mode="flashback"]','aria-pressed'),'true');
    await $('.reel-track button').nth(1).click();
    assert.equal(await $('#reel-seek').inputValue(),'2');
    assert.match(await $('.reel-still:visible').getAttribute('alt'),lang==='he'?/כביש/:/road/);
    await $('#reel-seek').focus(); await p.keyboard.press('End');
    assert.equal(await $('#reel-seek').inputValue(),'8'); assert.equal(await prop('#night-drive','data-shot'),'crossing');
    await p.keyboard.press('Home'); await p.keyboard.press('ArrowRight');
    assert.equal(await $('#reel-seek').inputValue(),'0.1');
    await $('#reel-play').click();
    await p.waitForFunction(()=>Number(document.getElementById('reel-seek').value)>=.3);
    await $('#reel-play').click();
    assert.equal(await prop('#night-drive','data-playing'),'false');
    const held=await $('#reel-seek').inputValue(); await p.waitForTimeout(160);
    assert.equal(await $('#reel-seek').inputValue(),held);
    // Language changes do not replace the reel's player, reset time, or switch the cut.
    if(width<768) {await $('#mobileNavToggle').click();await $('#mobileLanguageSwitch').click();}
    else await $('#languageSwitch').click();
    assert.equal(await $('#reel-seek').inputValue(),held);assert.equal(await prop('#night-drive','data-cut'),'flashback');
    assert.match(await prop('#reel-seek','aria-valuetext'),lang==='he'?/seconds/:/שניות/);
    await $('[data-mode="journey"]').click();await $('.reel-track button').nth(2).click();
    assert.equal(await $('#reel-seek').inputValue(),'5');assert.equal(await prop('#night-drive','data-shot'),'lake');
    assert.equal(await prop('html','data-motion'),'paused');
    assert.equal(await $('.reel-still:visible').evaluate(i=>getComputedStyle(i).transform),'none');
    if(width===1440&&lang==='en') {
      await $('#reel-play').click();await $('#workspaces').scrollIntoViewIfNeeded();await p.waitForFunction(()=>document.querySelector('.reel').dataset.playing==='false');
      await $('#tab-edit').click();await $('#panel-edit .workspace-image-link').click();assert.ok(await visible('#imageDialog'));await p.keyboard.press('Escape');assert.ok(!await visible('#imageDialog'));
      await $('#reel-seek').focus();await p.keyboard.press('End');await p.keyboard.press('ArrowLeft');await $('#reel-play').click();
      await p.waitForFunction(()=>document.querySelector('.reel').dataset.playing==='false'&&document.getElementById('reel-seek').value==='8');
      await $('#reel-play').click();await p.waitForFunction(()=>Number(document.getElementById('reel-seek').value)<1);await $('#reel-play').click();
      // The motion-enabled illustration actually pans at different times in the same shot.
      await p.emulateMedia({reducedMotion:'no-preference'});
      if(await prop('html','data-motion')==='paused') await $('#heroMotionToggle').click();
      await $('.reel-track button').first().click();
      const t0=await $('.reel-still:visible').evaluate(i=>getComputedStyle(i).transform);
      await $('#reel-seek').focus();for(let i=0;i<12;i++)await p.keyboard.press('ArrowRight');
      const t1=await $('.reel-still:visible').evaluate(i=>getComputedStyle(i).transform);assert.notEqual(t0,t1);
      await $('#reel-play').click();await $('#heroMotionToggle').click();assert.equal(await prop('#night-drive','data-playing'),'false');
    }
    report.cases.push({width,height,lang});await p.close();
  }
  const fallback=await browser.newPage({javaScriptEnabled:false,viewport:{width:390,height:844}});
  await fallback.goto(base);
  assert.equal(await fallback.locator('.reel-tools').isVisible(),false);assert.equal(await fallback.locator('.reel-still:visible').count(),1);
  assert.ok(await fallback.locator('#downloadButton').isVisible());assert.ok(await fallback.locator('#panel-media').isVisible());
  await fallback.close();
  assert.deepEqual(report.errors,[]);assert.deepEqual(report.externalRequests,[]);
  console.log('PASS: '+report.cases.length+' viewport/language combinations; playback, seek, recut, reduced motion, bilingual switch, exact downloads, no-script fallback.');
  if(process.env.CAPTURE_DIR) await writeFile(resolve(process.env.CAPTURE_DIR,'cutroom-night-drive-site-report.json'),JSON.stringify(report,null,2)+'\n');
} finally {if(browser)await browser.close(); await new Promise(ok=>server.close(ok));}
