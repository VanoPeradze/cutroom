export class AudioThresholdView {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d", { alpha: false });
    this.profile = null;
    this.threshold = -42;
    this.minimum = .75;
    this.keep = .30;
    this.dpr = Math.min(1.5, window.devicePixelRatio || 1);
    this.resizeObserver = new ResizeObserver(() => this.draw());
    this.resizeObserver.observe(canvas.parentElement || canvas);
    this.plot = null;
    canvas.addEventListener("pointerdown", (event) => {
      if (!this.plot || !this.profile) return;
      const rect = canvas.getBoundingClientRect();
      const x = event.clientX - rect.left;
      const { left, graphW, duration } = this.plot;
      if (x < left || x > left + graphW) return;
      const time = Math.max(0, Math.min(duration, (x - left) / graphW * duration));
      canvas.dispatchEvent(new CustomEvent("cutroom-audio-seek", { detail: { time }, bubbles: true }));
    });
  }

  setProfile(profile) {
    this.profile = profile || null;
    const recommended = Number(profile?.summary?.recommended_silence_threshold_dbfs ?? profile?.summary?.silence_threshold_dbfs);
    if (Number.isFinite(recommended)) this.threshold = recommended;
    this.draw();
  }

  setPolicy({ threshold, minimum, keep } = {}) {
    if (Number.isFinite(Number(threshold))) this.threshold = Number(threshold);
    if (Number.isFinite(Number(minimum))) this.minimum = Number(minimum);
    if (Number.isFinite(Number(keep))) this.keep = Number(keep);
    this.draw();
  }

  quietRanges() {
    const bins = this.profile?.waveform || [];
    const groups = [];
    let current = null;
    for (const bin of bins) {
      const start = Number(bin.start || 0), end = Number(bin.end || start);
      const quiet = Number(bin.rms_dbfs ?? -120) < this.threshold;
      if (quiet) {
        if (!current || start - current.end > .45) {
          if (current) groups.push(current);
          current = { start, end };
        } else current.end = end;
      } else if (current) {
        groups.push(current); current = null;
      }
    }
    if (current) groups.push(current);
    return groups.filter((item) => item.end - item.start >= this.minimum);
  }

  estimate() {
    const bins = this.profile?.waveform || [];
    if (!bins.length) return { ranges: 0, quietSeconds: 0, removedSeconds: 0 };
    const valid = this.quietRanges();
    const quietSeconds = valid.reduce((sum, item) => sum + item.end - item.start, 0);
    const removedSeconds = valid.reduce((sum, item) => sum + Math.max(0, item.end - item.start - this.keep), 0);
    return { ranges: valid.length, quietSeconds, removedSeconds };
  }

  draw() {
    const rect = this.canvas.getBoundingClientRect();
    const width = Math.max(320, Math.round(rect.width || 900));
    const height = 174;
    const dpr = this.dpr;
    this.canvas.width = Math.round(width * dpr);
    this.canvas.height = Math.round(height * dpr);
    this.canvas.style.height = `${height}px`;
    const ctx = this.ctx;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = "#081013"; ctx.fillRect(0, 0, width, height);
    const left = 42, right = 12, top = 12, bottom = 24;
    const graphW = width - left - right, graphH = height - top - bottom;
    const minDb = -72, maxDb = 0;
    const yForDb = (db) => top + (maxDb - Math.max(minDb, Math.min(maxDb, db))) / (maxDb - minDb) * graphH;
    for (const db of [-60, -48, -36, -24, -12, 0]) {
      const y = yForDb(db);
      ctx.strokeStyle = "rgba(235,240,242,.09)"; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(left, y); ctx.lineTo(width - right, y); ctx.stroke();
      ctx.fillStyle = "#8da1a6"; ctx.font = "10px ui-monospace,Consolas,monospace"; ctx.textAlign = "right";
      ctx.fillText(`${db}`, left - 7, y + 3);
    }
    const bins = this.profile?.waveform || [];
    if (!bins.length) {
      ctx.fillStyle = "#8da1a6"; ctx.textAlign = "center"; ctx.font = "12px system-ui,sans-serif";
      ctx.fillText("Measuring audio…", width / 2, height / 2);
      return;
    }
    const duration = Number(this.profile?.duration || bins.at(-1)?.end || 1);
    const xForTime = (time) => left + Number(time) / Math.max(duration, .001) * graphW;
    this.plot = { left, graphW, duration };
    const thresholdY = yForDb(this.threshold);
    ctx.fillStyle = "rgba(255,91,73,.07)"; ctx.fillRect(left, thresholdY, graphW, top + graphH - thresholdY);
    // Mark complete quiet candidates as vertical bands so the user can see where
    // a cut would happen, not only how low each waveform bin is.
    for (const range of this.quietRanges()) {
      const x1 = xForTime(range.start), x2 = xForTime(range.end);
      ctx.fillStyle = "rgba(255,91,73,.105)";
      ctx.fillRect(x1, top, Math.max(1, x2 - x1), graphH);
      ctx.fillStyle = "rgba(255,117,95,.9)";
      ctx.fillRect(x1, top + graphH - 3, Math.max(2, x2 - x1), 3);
    }
    for (const bin of bins) {
      const start = Number(bin.start || 0), end = Number(bin.end || start);
      const x = xForTime((start + end) / 2);
      const rms = Number(bin.rms_dbfs ?? -72), peak = Number(bin.peak_dbfs ?? rms);
      ctx.strokeStyle = rms < this.threshold ? "rgba(255,117,95,.90)" : "rgba(68,185,198,.82)";
      ctx.lineWidth = Math.max(1, graphW / bins.length * .72);
      ctx.beginPath(); ctx.moveTo(x, yForDb(Math.max(minDb, rms))); ctx.lineTo(x, yForDb(Math.min(0, peak))); ctx.stroke();
    }
    ctx.strokeStyle = "#c9b62c"; ctx.lineWidth = 1.5; ctx.setLineDash([6,4]);
    ctx.beginPath(); ctx.moveTo(left, thresholdY); ctx.lineTo(width - right, thresholdY); ctx.stroke(); ctx.setLineDash([]);
    ctx.fillStyle = "#c9b62c"; ctx.font = "700 10px ui-monospace,Consolas,monospace"; ctx.textAlign = "left";
    ctx.fillText(`${this.threshold.toFixed(0)} dB`, left + 7, Math.max(11, thresholdY - 5));
    ctx.fillStyle = "#8da1a6"; ctx.font = "10px ui-monospace,Consolas,monospace";
    for (let index = 0; index <= 4; index += 1) {
      const ratio = index / 4;
      const x = left + graphW * ratio;
      if (index > 0 && index < 4) {
        ctx.strokeStyle = "rgba(235,240,242,.055)"; ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(x, top); ctx.lineTo(x, top + graphH); ctx.stroke();
      }
      ctx.textAlign = index === 0 ? "left" : index === 4 ? "right" : "center";
      ctx.fillText(formatCompact(duration * ratio), x, height - 7);
    }
  }
}

function formatCompact(seconds) {
  const value = Math.max(0, Number(seconds) || 0);
  const mins = Math.floor(value / 60), secs = Math.floor(value % 60);
  return `${mins}:${String(secs).padStart(2,"0")}`;
}
