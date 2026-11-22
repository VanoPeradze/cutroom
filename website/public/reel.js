/* Original stills and deliberately different cuts. No real footage, upload or sound. */
(() => {
  const reel = document.getElementById('night-drive');
  if (!reel) return;
  const root = document.documentElement;
  const cuts = {
    journey: [{id:'pass', length:3}, {id:'crossing', length:2}, {id:'lake', length:3}],
    flashback: [{id:'lake', length:2}, {id:'pass', length:4.5}, {id:'crossing', length:1.5}],
  };
  const names = {
    en: {pass:'The pass', crossing:'The bridge', lake:'First light', play:'Play', pause:'Pause', shot:'Shot', of:'of', time:'seconds', jump:'Jump to'},
    he: {pass:'מעבר ההרים', crossing:'הגשר', lake:'אור ראשון', play:'ניגון', pause:'השהיה', shot:'שוט', of:'מתוך', time:'שניות', jump:'מעבר אל'},
  };
  const duration = 8;
  const tools = reel.querySelector('.reel-tools');
  const track = reel.querySelector('.reel-track');
  const modes = [...reel.querySelectorAll('[data-mode]')];
  const images = [...reel.querySelectorAll('[data-still]')];
  const play = document.getElementById('reel-play');
  const playLabel = document.getElementById('reel-play-label');
  const slider = document.getElementById('reel-seek');
  const clock = document.getElementById('reel-time');
  const serial = document.getElementById('shot-number');
  const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
  // Tie the illustration pan to sequence time, including manual scrubbing.
  // The underlying artwork stays a native, descriptive image without this API.
  const pans = images.map((img,i) => {
    const moves = [
      [{transform:'scale(1.025) translateX(.6%)'},{transform:'scale(1.105) translateX(-1.5%)'}],
      [{transform:'scale(1.08) translateY(.5%)'},{transform:'scale(1.025) translateY(-.3%)'}],
      [{transform:'scale(1.075) translateX(1.4%)'},{transform:'scale(1.025) translateX(-.4%)'}],
    ];
    return typeof Animation !== 'undefined' && typeof KeyframeEffect !== 'undefined' ? new Animation(new KeyframeEffect(img,moves[i],{duration:1000,fill:'both'}),document.timeline) : null;
  });
  const buttons = [];
  let mode = 'journey', position = 0, active = -1, animation = 0, origin = 0;
  let playing = false, lastTenth = -1;
  const copy = () => names[root.lang] || names.en;
  const starts = () => cuts[mode].map((_,i,a) => a.slice(0,i).reduce((sum,c) => sum+c.length, 0));

  function draw(force = false) {
    const text = copy();
    const decisecond = Math.min(80, Math.floor(position * 10 + 0.00001));
    if (!force && decisecond === lastTenth) return;
    lastTenth = decisecond;
    const cut = cuts[mode], slots = starts();
    const index = position < slots[1] ? 0 : position < slots[2] ? 1 : 2;
    if (index !== active || force) {
      active = index;
      reel.dataset.shot = cut[index].id;
      serial.textContent = String(index + 1).padStart(2, '0');
      images.forEach(img => { img.hidden = img.dataset.still !== cut[index].id; });
      buttons.forEach((b,i) => {
        if (i === index) b.setAttribute('aria-current','step'); else b.removeAttribute('aria-current');
        b.dataset.clip = cut[i].id;
        b.querySelector('.reel-shot-name').textContent = text[cut[i].id];
        b.setAttribute('aria-label',text.jump+' '+text[cut[i].id]+', '+slots[i]+' '+text.time);
      });
    }
    const pan = pans[images.findIndex(img => img.dataset.still === cut[index].id)];
    if (pan) {
      if (preference.matches || root.dataset.motion === 'paused') pan.cancel();
      else pan.currentTime = Math.min(1000, (position-slots[index])/cut[index].length*1000);
    }
    const seconds = decisecond / 10;
    slider.value = String(seconds);
    slider.setAttribute('aria-valuetext',seconds+' '+text.of+' '+duration+' '+text.time+', '+text[cut[index].id]);
    clock.textContent = '0:'+String(Math.floor(seconds)).padStart(2,'0');
    playLabel.textContent = playing ? text.pause : text.play;
    reel.dataset.playing = String(playing);
  }

  function pause() {
    playing = false;
    if (animation) cancelAnimationFrame(animation);
    animation = 0;
    draw(true);
  }
  function advance(now) {
    if (!playing) return;
    position = Math.min((now - origin) / 1000, duration);
    if (position >= duration) { pause(); return; }
    draw();
    animation = requestAnimationFrame(advance);
  }
  function seek(value) {
    if (!Number.isFinite(value)) return;
    position = Math.max(0,Math.min(value,duration));
    pause();
  }
  // Keep the same focusable nodes while switching edits or languages.
  cuts.journey.forEach((_,i) => {
    const button = document.createElement('button');
    button.type = 'button';
    const counter = document.createElement('span'), name = document.createElement('span');
    counter.className = 'reel-shot-no'; counter.setAttribute('aria-hidden','true');
    counter.textContent = String(i+1).padStart(2,'0'); name.className = 'reel-shot-name';
    button.append(counter,name); track.append(button); buttons.push(button);
    button.addEventListener('click',() => seek(starts()[i]));
  });
  slider.addEventListener('input',() => seek(Number(slider.value)));
  play.addEventListener('click',() => {
    if (playing) { pause(); return; }
    if (position >= duration) position = 0;
    origin = performance.now() - position * 1000;
    playing = true; draw(true);
    animation = requestAnimationFrame(advance);
  });
  modes.forEach(button => button.addEventListener('click',() => {
    const next = button.dataset.mode;
    if (!Object.hasOwn(cuts,next) || next === mode) return;
    mode = next; reel.dataset.cut = mode;
    modes.forEach(b => b.setAttribute('aria-pressed',String(b === button)));
    seek(0);
  }));
  // A reader who leaves the study must not come back to a different shot.
  if ('IntersectionObserver' in window) new IntersectionObserver(entries => {
    if (playing && !entries.some(e => e.isIntersecting)) pause();
  }).observe(reel);
  document.addEventListener('visibilitychange',() => { if (document.hidden && playing) pause(); });
  window.addEventListener('pagehide',pause);
  preference.addEventListener('change',() => draw(true));
  new MutationObserver(changes => {
    if (changes.some(m => m.attributeName === 'data-motion' && m.oldValue !== 'paused' && root.dataset.motion === 'paused') && playing) pause();
    else draw(true);
  }).observe(root,{attributes:true,attributeOldValue:true,attributeFilter:['lang','data-motion']});
  draw(true);
  tools.hidden = false;
})();
