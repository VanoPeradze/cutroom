"""Bounded, read-only original-picture review. Never step a proxy or guess FPS."""
from __future__ import annotations

import base64
from bisect import bisect_right
from collections import OrderedDict
from fractions import Fraction
import hashlib
import json
import math
import re
import os
import subprocess
import time
import threading

from .native_paths import native_io_path
from .preview_repair import original_path, PreviewRepairError

MAX_SECONDS = 600
MAX_FRAMES = 50000
MAX_FILE_BYTES = 2 * 1024**3
MAX_INDEX_BYTES = 16 * 1024**2
MAX_PNG_BYTES = 2 * 1024**2
MAX_PIXELS = 16777216
MAX_ERROR_BYTES = 65536


class SourceFrameError(ValueError):
    def __init__(self, message, status=422):
        self.status = status
        super().__init__(message)


def bounded_command(args, *, limit, timeout=15, cancel_check=lambda: None):
    """Drain both pipes concurrently without ever collecting beyond byte caps.

    No communicate() buffer, shell, temporary file, or child process left behind.
    A disconnected browser cannot cancel a server request, so timeout remains
    mandatory even after the client discards an old response.
    """
    cancel_check()
    process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, bufsize=0,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0)
    overflow, failed = threading.Event(), threading.Event()
    output, errors = bytearray(), bytearray()
    def drain(pipe, target, cap):
        try:
            while True:
                chunk=pipe.read(min(8192, cap+1))
                if not chunk:break
                if len(target)+len(chunk)>cap:
                    overflow.set()
                    try:process.kill()
                    except OSError:pass
                    break
                target.extend(chunk)
        except (OSError, ValueError):
            failed.set()
        finally:
            pipe.close()
    readers=[threading.Thread(target=drain,args=(process.stdout,output,limit),daemon=True),
             threading.Thread(target=drain,args=(process.stderr,errors,MAX_ERROR_BYTES),daemon=True)]
    for reader in readers:reader.start()
    started=time.monotonic()
    try:
        while process.poll() is None:
            cancel_check()
            if overflow.is_set():raise SourceFrameError('Original-frame review exceeded its output limit. Ordinary preview remains available.')
            if time.monotonic()-started>=timeout:raise SourceFrameError('Original-frame review timed out. Ordinary preview remains available.')
            time.sleep(.025)
        for reader in readers:reader.join(timeout=2)
        if overflow.is_set():raise SourceFrameError('Original-frame review exceeded its output limit. Ordinary preview remains available.')
        if failed.is_set() or any(reader.is_alive() for reader in readers) or process.returncode:
            raise SourceFrameError('Original-frame decoding could not be verified. Ordinary preview remains available.')
        cancel_check()
        return bytes(output)
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=2)
        for reader in readers:reader.join(timeout=2)


def frame_index(data, duration):
    """Decoded presentation order on the renderer's container-relative clock.

    Every frame must be present. No interval seek, packet DTS, avg_frame_rate,
    truncation or nominal-FPS fallback is accepted.
    """
    try:
        streams = data['streams']
        if len(streams) != 1 or streams[0].get('codec_type') != 'video':
            raise ValueError()
        stream = streams[0]
        if stream.get('disposition', {}).get('attached_pic'):
            raise ValueError()
        tb = Fraction(stream['time_base'])
        origin = Fraction(str(data['format']['start_time']))
        if tb <= 0 or tb.numerator != 1 or abs(origin) > 864000 or not all(int(stream[k])>0 for k in ('width','height')) or int(stream['width'])*int(stream['height']) > MAX_PIXELS:
            raise ValueError()
        # FFmpeg normalizes the container start in the video stream timebase
        # with AV_ROUND_NEAR_INF, then subtracts integer ticks. Subtracting
        # decimal seconds instead is microscopically early at nonzero origins
        # and can export the preceding picture at an exact marked boundary.
        scaled=origin/tb
        origin_ticks=(1 if scaled>=0 else -1)*math.floor(abs(scaled)+Fraction(1,2))
        frames = data['frames']
        if not 1 <= len(frames) <= MAX_FRAMES:
            raise ValueError()
        points = []
        for row in frames:
            raw = row['best_effort_timestamp']
            if isinstance(raw, bool) or not re.fullmatch(r'-?\d+', str(raw)):
                raise ValueError()
            at = round(float((int(raw)-origin_ticks)*tb), 9)
            if not math.isfinite(at) or at < 0 or at >= duration or points and at <= points[-1]:
                raise ValueError()
            points.append(at)
        # A longer audio/container tail is not a video-frame duration. Only a
        # separately declared video stream endpoint may close the final frame.
        end = None
        if 'start_pts' in stream and 'duration_ts' in stream:
            candidate = round(float((int(stream['start_pts'])+int(stream['duration_ts'])-origin_ticks)*tb), 9)
            if candidate <= points[-1] or candidate > duration + 1e-8:
                # Existing rendering clamps source starts to declared picture end.
                # Do not offer exact marks when container timing contradicts the
                # complete decoded index, even if individual stills can decode.
                raise ValueError()
            end = min(candidate, duration)
        return tuple(points), end
    except (ValueError, KeyError, TypeError, ZeroDivisionError, OverflowError) as exc:
        raise SourceFrameError('Original frame timestamps are ambiguous or exceed the review limit. Ordinary preview and editing remain available.') from exc


class SourceFrameReview:
    """One bounded decoder request at a time; small process-local caches only."""
    def __init__(self, store, settings):
        self.store, self.settings = store, settings
        self.gate = threading.Lock()
        self.indices, self.images = OrderedDict(), OrderedDict()

    def _binding(self, project_id, asset_id):
        if not isinstance(asset_id, str) or not re.fullmatch(r'asset_[0-9a-f]{32}', asset_id):
            raise SourceFrameError('Choose a ready imported video.', 404)
        asset = (self.store.load(project_id).get('assets') or {}).get(asset_id)
        if not asset or asset.get('id') != asset_id or asset.get('kind') != 'video' or asset.get('status') != 'ready':
            raise SourceFrameError('Choose a ready imported video.', 404)
        duration = asset.get('duration')
        if isinstance(duration, bool) or not isinstance(duration, (int,float)) or not math.isfinite(duration) or not 0 < duration <= MAX_SECONDS:
            raise SourceFrameError('Exact original-frame review currently supports videos up to 10 minutes. Ordinary preview and editing remain available.')
        width,height=asset.get('width'),asset.get('height')
        if any(isinstance(n,bool) or not isinstance(n,int) or n<=0 for n in (width,height)) or width*height>MAX_PIXELS:
            raise SourceFrameError('This source exceeds the bounded original-picture dimensions. Ordinary preview and editing remain available.')
        try:
            path = native_io_path(original_path(self.store.project_dir(project_id), asset))
            stat = path.stat()
            if not 0 < stat.st_size <= MAX_FILE_BYTES:
                raise SourceFrameError('This original exceeds the bounded frame-review size. Ordinary preview and editing remain available.')
            identity = [project_id, asset_id, str(path), stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns,
                        {k:asset.get(k) for k in ('path','duration','width','height','kind','status','preparation_identity','preview_path','picture_end','_original_content_proof')}]
            token = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
            declared_end=asset.get('picture_end')
            picture_end=min(duration,declared_end) if type(declared_end) in (int,float) and math.isfinite(declared_end) and declared_end>0 else duration
            return path, token, duration, picture_end
        except (OSError, PreviewRepairError) as exc:
            raise SourceFrameError('The owned original is unavailable or changed. Verify the source before reviewing frames.') from exc

    def step(self, project_id, asset_id, query):
        if set(query)-{'time','direction','index','token'} or query.get('direction') not in {'previous','next'}:
            raise SourceFrameError('Choose Previous or Next original frame.',400)
        try:
            at = float(query.get('time',''))
            if not math.isfinite(at) or not 0 <= at <= MAX_SECONDS:
                raise ValueError()
            index = query.get('index')
            if index is not None and (not re.fullmatch(r'\d{1,5}',index) or not re.fullmatch(r'[0-9a-f]{64}',query.get('token',''))):
                raise ValueError()
            if index is None and 'token' in query:
                raise ValueError()
        except (ValueError, TypeError):
            raise SourceFrameError('Choose a valid source time or confirmed frame.',400) from None
        if not self.gate.acquire(blocking=False):
            raise SourceFrameError('Another original frame is decoding. Try again when it finishes.',409)
        try:
            path, token, duration, picture_end = self._binding(project_id,asset_id)
            if at > duration or index is not None and query['token'] != token:
                raise SourceFrameError('The original source changed. Return to playback and review it again.',409)
            def unchanged():
                if self._binding(project_id,asset_id)[1] != token:
                    raise SourceFrameError('The original source changed during frame review.',409)
            if token not in self.indices:
                result = bounded_command([self.settings.ffprobe,'-v','error','-threads','1','-protocol_whitelist','file,pipe',
                    '-select_streams','v:0','-show_frames','-show_streams','-show_format','-show_entries',
                    'frame=best_effort_timestamp:stream=index,codec_type,time_base,start_pts,duration_ts,width,height:stream_disposition=attached_pic:format=start_time',
                    '-of','json',str(path)],limit=MAX_INDEX_BYTES,cancel_check=unchanged)
                points,end = frame_index(json.loads(result),duration)
                if picture_end-points[-1] <= 1e-6:
                    raise SourceFrameError('Original pictures conflict with the verified render endpoint. Exact steps are unavailable; ordinary preview remains available.')
                unchanged();self.indices[token]=(points,end);self.indices.move_to_end(token)
                while len(self.indices)>4:self.indices.popitem(last=False)
            points,end = self.indices[token]
            self.indices.move_to_end(token)
            if index is None:
                current = bisect_right(points,at+1e-10)-1
            else:
                current = int(index)
                if current >= len(points) or abs(points[current]-at)>1e-9:
                    raise SourceFrameError('The confirmed source frame is stale. Return to playback and review it again.',409)
            target = min(len(points)-1,max(0,current+(-1 if query['direction']=='previous' else 1)))
            key=(token,target)
            if key not in self.images:
                png = bounded_command([self.settings.ffmpeg,'-nostdin','-hide_banner','-v','error','-threads','1',
                    '-protocol_whitelist','file,pipe','-i',str(path),'-map','0:v:0','-an','-sn','-dn',
                    '-vf',f"select='eq(n,{target})',scale=w='min(960,iw)':h='min(540,ih)':force_original_aspect_ratio=decrease,format=rgb24",
                    '-fps_mode','passthrough','-frames:v','1','-filter_threads','1','-threads','1','-c:v','png','-f','image2pipe','pipe:1'],
                    limit=MAX_PNG_BYTES,cancel_check=unchanged)
                if not png.startswith(b'\x89PNG\r\n\x1a\n') or len(png)>MAX_PNG_BYTES:
                    raise SourceFrameError('The original frame could not be decoded safely. Ordinary preview remains available.')
                unchanged();self.images[key]=png
                while len(self.images)>8:self.images.popitem(last=False)
            self.images.move_to_end(key);unchanged()
            return {'project_id':project_id,'asset_id':asset_id,'token':token,'index':target,'count':len(points),
                    'time':points[target],'end':points[target+1] if target+1<len(points) else end,
                    'duration':duration,'image':'data:image/png;base64,'+base64.b64encode(self.images[key]).decode('ascii')}
        except SourceFrameError:
            raise
        except Exception as exc:
            raise SourceFrameError('Exact original-frame review timed out or could not be verified. Ordinary preview and editing remain available.') from exc
        finally:
            self.gate.release()
