// Interactive RGB preview of the saved FFmpeg chroma settings. The native-size
// processed frame remains the edge-quality reference; browser decoding/resizing
// can differ from FFmpeg's subsampled YUV neighbourhoods.
export function keyPixels(pixels, width, height, settings) {
  const rgb = settings.color.slice(1).match(/../g).map(value => parseInt(value, 16));
  const uv = (r,g,b) => [(-.148223*r-.290993*g+.439216*b)/255, (.439216*r-.367788*g-.071427*b)/255];
  const [ku,kv] = uv(...rgb), distances = new Float32Array(width*height);
  for (let p=0,i=0;p<distances.length;p++,i+=4) {
    const [u,v] = uv(pixels[i],pixels[i+1],pixels[i+2]);
    distances[p] = Math.hypot(u-ku,v-kv)/Math.SQRT2;
  }
  for (let y=0;y<height;y++) for (let x=0;x<width;x++) {
    let distance=0;
    for (let dy=-1;dy<=1;dy++) for (let dx=-1;dx<=1;dx++) {
      distance += distances[Math.max(0,Math.min(height-1,y+dy))*width+Math.max(0,Math.min(width-1,x+dx))];
    }
    distance = distance/9-settings.tolerance;
    const alpha = settings.edge_softness > .0001 ? Math.max(0,Math.min(1,distance/settings.edge_softness)) : Number(distance>0);
    pixels[(y*width+x)*4+3] = Math.floor(pixels[(y*width+x)*4+3]*alpha);
  }
  return pixels;
}

export class ChromaPreview {
  constructor(video) {
    this.video=video; this.canvas=document.createElement('canvas'); this.canvas.className='chroma-live';
    this.canvas.hidden=true; this.canvas.setAttribute('aria-label','Chroma-key playback preview');
    video.parentElement.append(this.canvas);
    this.context=this.canvas.getContext('2d',{willReadFrequently:true});
    this.notice=document.createElement('span'); this.notice.className='chroma-live-error'; this.notice.hidden=true;
    this.notice.textContent='Chroma preview unavailable. Check the processed frame.'; video.parentElement.append(this.notice);
    this.listener=()=>{this.draw(true);this.schedule();};
    for (const name of ['loadeddata','seeked','play','pause','emptied']) video.addEventListener(name,this.listener);
  }
  update(settings, backgroundUrl) {
    const signature=JSON.stringify([settings,backgroundUrl,this.video.currentSrc||this.video.src]);
    const changed=signature!==this.signature; this.signature=signature; this.settings=settings;
    if (backgroundUrl!==this.backgroundUrl) {
      this.backgroundUrl=backgroundUrl; this.image=null;
      if (backgroundUrl) {
        const picture=new Image(); this.image=picture;
        picture.onload=()=>{if(this.image===picture)this.draw(true);};
        picture.onerror=()=>{if(this.image===picture)this.fail();}; picture.src=backgroundUrl;
      }
    }
    if (!settings?.enabled) {this.hide();return;}
    // Mirror framing, crop, fit and motion without touching the media clock.
    const style=getComputedStyle(this.video);
    for (const key of ['width','height','left','top','right','bottom','transform','transformOrigin','objectFit','objectPosition','clipPath']) this.canvas.style[key]=style[key];
    this.draw(changed); this.schedule();
  }
  draw(force=false) {
    const video=this.video, config=this.settings;
    if (!config?.enabled) return;
    if (video.readyState<2 || !video.videoWidth) {this.hide(false);return;}
    if (!force && this.time===video.currentTime) return;
    if (config.background_mode!=='transparent' && config.background_asset_id && (!this.image?.complete || !this.image?.naturalWidth)) {
      this.fail();return;
    }
    try {
      const factor=Math.min(1,640/video.videoWidth), width=Math.max(2,Math.round(video.videoWidth*factor)), height=Math.max(2,Math.round(video.videoHeight*factor));
      if(this.canvas.width!==width||this.canvas.height!==height){this.canvas.width=width;this.canvas.height=height;}
      const ctx=this.context; ctx.globalCompositeOperation='source-over'; ctx.clearRect(0,0,width,height);ctx.drawImage(video,0,0,width,height);
      const frame=ctx.getImageData(0,0,width,height);keyPixels(frame.data,width,height,config);ctx.putImageData(frame,0,0);
      if(config.background_mode!=='transparent') {
        ctx.globalCompositeOperation='destination-over';
        if(config.background_asset_id) {
          const scale=Math.max(width/this.image.naturalWidth,height/this.image.naturalHeight), w=this.image.naturalWidth*scale,h=this.image.naturalHeight*scale;
          ctx.drawImage(this.image,(width-w)/2,(height-h)/2,w,h);
        } else {ctx.fillStyle=config.background_color;ctx.fillRect(0,0,width,height);}
        ctx.globalCompositeOperation='source-over';
      }
      this.time=video.currentTime;this.canvas.hidden=false;this.notice.hidden=true;video.style.opacity='0';
    } catch {this.fail();}
  }
  schedule() {
    if(this.frame!=null||!this.settings?.enabled||this.video.paused||this.video.ended)return;
    this.frame=requestAnimationFrame(()=>{this.frame=null;this.draw();this.schedule();});
  }
  hide(cancel=true) {this.canvas.hidden=true;this.notice.hidden=true;this.video.style.opacity='';this.time=null;if(cancel&&this.frame!=null){cancelAnimationFrame(this.frame);this.frame=null;}}
  fail() {this.hide();this.notice.hidden=false;}
  dispose() {
    this.hide(); for(const name of ['loadeddata','seeked','play','pause','emptied'])this.video.removeEventListener(name,this.listener);
    if(this.image){this.image.onload=null;this.image.onerror=null;}this.canvas.remove();this.notice.remove();
  }
}
