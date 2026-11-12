/* CUTROOM film field. Original geometric artwork, not simulated editor footage. */
(() => {
  const canvas = document.getElementById('filmField');
  if (!canvas) return;
  const context = canvas.getContext('2d', {alpha:true});
  if (!context) return;
  const field = canvas.closest('.film-field'), root = document.documentElement;
  const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
  let width=0, height=0, frame=0, lastTime=0, elapsed=4, visible=true, mobile=false;
  const motionAllowed = () => !preference.matches && root.dataset.motion !== 'paused' && !document.hidden && visible;
  function project(x,y,z,angle,yaw,cx,cy) {
    const tx=x*Math.cos(yaw), tz=z-x*Math.sin(yaw);
    const focal=Math.min(width,1500)*0.85, scale=focal/(focal+tz);
    const c=Math.cos(angle), s=Math.sin(angle);
    return [cx+(tx*c-y*s)*scale,cy+(tx*s+y*c)*scale];
  }
  function polygon(points) {
    context.moveTo(points[0][0],points[0][1]);
    points.slice(1).forEach(point=>context.lineTo(point[0],point[1]));
    context.closePath();
  }
  function draw() {
    if (!width || !height) return;
    context.clearRect(0,0,width,height);
    const sceneScale=mobile?0.73:Math.min(1.16,width/1150);
    const centerX=width*(mobile?1.0:0.84), centerY=height*0.38, phase=elapsed*0.16;
    const count=mobile?17:25;
    for(let index=count-1;index>=0;index--) {
      const depth=index*42+140, angle=-0.36+index*0.019+Math.sin(phase+index*0.07)*0.09;
      const yaw=0.60+Math.sin(phase*0.73)*0.12, x=500*sceneScale, y=350*sceneScale;
      const thickness=(index%6===0?18:10)*sceneScale;
      const cx=centerX+Math.sin(index*0.10+phase)*26, cy=centerY+Math.cos(index*0.12+phase)*24;
      const corners=(xx,yy)=>[[-xx,-yy],[xx,-yy],[xx,yy],[-xx,yy]].map(([a,b])=>project(a,b,depth,angle,yaw,cx,cy));
      const outer=corners(x,y),inner=corners(x-thickness,y-thickness);
      const color=index%8<5?[112,217,224]:[183,166,222], opacity=Math.max(0.08,0.42-index*0.011);
      const material=context.createLinearGradient(outer[0][0],outer[0][1],outer[2][0],outer[2][1]);
      material.addColorStop(0,`rgba(${color.join(',')},${opacity*0.13})`);
      material.addColorStop(0.37,`rgba(${color.join(',')},${opacity})`);
      material.addColorStop(0.7,`rgba(${color.join(',')},${opacity*0.36})`);
      material.addColorStop(1,`rgba(${color.join(',')},${opacity*0.12})`);
      context.beginPath();polygon(outer);polygon(inner);context.fillStyle=material;context.fill('evenodd');
      context.beginPath();polygon(outer);context.lineWidth=index%6===0?1:0.6;
      context.strokeStyle=`rgba(${color.join(',')},${opacity+0.05})`;context.stroke();
      if(index%6===0) {
        context.beginPath();
        for(let corner=0;corner<4;corner++) {
          const a=outer[corner],b=outer[(corner+1)%4];context.moveTo(a[0],a[1]);
          context.lineTo(a[0]+(b[0]-a[0])*0.06,a[1]+(b[1]-a[1])*0.06);
        }
        context.strokeStyle=`rgba(213,225,250,${opacity+0.14})`;context.lineWidth=1.3;context.stroke();
      }
    }
  }
  function tick(now) {
    frame=0;if(!motionAllowed()){lastTime=0;return;}
    const interval=mobile?1000/24:1000/30;
    if(!lastTime||now-lastTime>=interval){elapsed+=lastTime?Math.min((now-lastTime)/1000,0.1):0;lastTime=now;draw();}
    frame=requestAnimationFrame(tick);
  }
  function synchronize() {
    if(frame)cancelAnimationFrame(frame);frame=0;lastTime=0;
    if(motionAllowed())frame=requestAnimationFrame(tick);else draw();
  }
  function resize() {
    const box=field.getBoundingClientRect();width=Math.round(box.width);height=Math.round(box.height);mobile=width<768;
    const ratio=Math.min(window.devicePixelRatio||1,mobile?1.25:1.5);
    canvas.width=Math.round(width*ratio);canvas.height=Math.round(height*ratio);
    context.setTransform(ratio,0,0,ratio,0,0);draw();synchronize();
  }
  if('IntersectionObserver' in window)new IntersectionObserver(entries=>{visible=entries.some(e=>e.isIntersecting);synchronize();},{rootMargin:'80px 0px',threshold:0}).observe(field);
  if('ResizeObserver' in window)new ResizeObserver(resize).observe(field);
  else window.addEventListener('resize',resize,{passive:true});
  new MutationObserver(synchronize).observe(root,{attributes:true,attributeFilter:['data-motion']});
  document.addEventListener('visibilitychange',synchronize);preference.addEventListener('change',synchronize);
  field.classList.add('is-rendered');resize();
})();
