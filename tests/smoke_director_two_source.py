from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
import tempfile
import threading
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cutroom.config import load_settings
from cutroom.jobs import Job, JobContext
from cutroom.media import probe_media
from cutroom.projects import ProjectStore
from cutroom.render import render_project
import cutroom.director as director


def make_audio(path: Path, delay_seconds: float = 0.0, duration: float = 14.0, sample_rate: int = 8000) -> None:
    rng = np.random.default_rng(20260825)
    samples = np.zeros(int(duration * sample_rate), dtype=np.float32)
    # Non-stationary speech-like envelope: irregular tone/noise bursts.
    bursts = [
        (0.25, 0.90, 260), (1.35, 0.55, 430), (2.30, 1.10, 310),
        (4.05, 0.75, 510), (5.25, 1.25, 340), (7.20, 0.65, 620),
        (8.45, 1.35, 390), (10.55, 0.80, 470), (12.00, 1.25, 290),
    ]
    for start, length, freq in bursts:
        start += delay_seconds
        begin = int(start * sample_rate)
        end = min(samples.size, begin + int(length * sample_rate))
        if end <= begin:
            continue
        t = np.arange(end - begin, dtype=np.float32) / sample_rate
        fade = np.minimum(1, np.minimum(np.arange(end-begin) / max(1, sample_rate*0.05), np.arange(end-begin)[::-1] / max(1, sample_rate*0.05))).astype(np.float32)
        carrier = 0.45 * np.sin(2 * np.pi * freq * t)
        noise = 0.05 * rng.standard_normal(end - begin).astype(np.float32)
        samples[begin:end] += (carrier + noise) * fade
    samples = np.clip(samples, -0.95, 0.95)
    pcm = (samples * 32767).astype('<i2')
    with wave.open(str(path), 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())


def run(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr[-4000:])


def fake_transcribe(_path, _settings, language='auto', progress=None):
    if progress:
        progress(0.25, 'Preparing transcription model')
        progress(1.0, 'Transcript ready')
    segments = [
        {'id': 's1', 'start': 0.10, 'end': 1.70, 'text': 'Um today I want to explain', 'words': [
            {'start': 0.10, 'end': 0.28, 'word': 'Um'}, {'start': 0.45, 'end': 0.74, 'word': 'today'}], 'avg_logprob': -0.15},
        {'id': 's2', 'start': 1.75, 'end': 4.30, 'text': 'Today I want to explain the complete workflow.', 'words': [], 'avg_logprob': -0.10},
        {'id': 's3', 'start': 4.35, 'end': 7.10, 'text': 'The first important point is that every cut stays editable.', 'words': [], 'avg_logprob': -0.08},
        {'id': 's4', 'start': 7.15, 'end': 9.55, 'text': 'The first important point is that every cut stays editable.', 'words': [], 'avg_logprob': -0.11},
        {'id': 's5', 'start': 9.60, 'end': 12.20, 'text': 'The second point is automatic camera switching for short videos.', 'words': [], 'avg_logprob': -0.07},
        {'id': 's6', 'start': 12.25, 'end': 13.80, 'text': 'That is the finished result.', 'words': [], 'avg_logprob': -0.09},
    ]
    return {
        'language': 'en', 'language_probability': 0.99, 'model': 'test-transcript',
        'device': 'cpu', 'compute_type': 'int8', 'segments': segments,
        'text': ' '.join(item['text'] for item in segments),
    }


def main() -> None:
    work = Path(tempfile.mkdtemp(prefix='cutroom-v5-director-two-source-'))
    try:
        ffmpeg = shutil.which('ffmpeg') or 'ffmpeg'
        audio_a = work / 'audio-a.wav'
        audio_b = work / 'audio-b.wav'
        make_audio(audio_a, 0.0)
        make_audio(audio_b, 0.85)
        source_a = work / 'A.mp4'
        source_b = work / 'B.mp4'
        run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-y',
             '-f', 'lavfi', '-i', 'testsrc2=size=640x360:rate=30:duration=14',
             '-i', str(audio_a), '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p',
             '-c:a', 'aac', '-shortest', str(source_a)])
        run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-y',
             '-f', 'lavfi', '-i', 'smptebars=size=640x360:rate=30:duration=14',
             '-i', str(audio_b), '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p',
             '-c:a', 'aac', '-shortest', str(source_b)])

        config = json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))
        config['data_dir'] = str(work / 'data')
        config['ai']['enabled'] = False
        config['render']['prefer_hardware'] = False
        config_path = work / 'config.json'
        config_path.write_text(json.dumps(config), encoding='utf-8')
        settings = load_settings(config_path)
        store = ProjectStore(settings)
        project = store.create('Director two-source smoke')
        media = store.project_dir(project['id']) / 'media'
        target_a = media / 'source-A.mp4'; target_b = media / 'source-B.mp4'
        shutil.copy2(source_a, target_a); shutil.copy2(source_b, target_b)
        project['sources']['A'] = {'slot':'A','name':'A.mp4','relative_path':'media/source-A.mp4', **probe_media(target_a, settings)}
        project['sources']['B'] = {'slot':'B','name':'B.mp4','relative_path':'media/source-B.mp4', **probe_media(target_b, settings)}
        project['settings'].update({'goal':'clean','aspect':'9:16','pace':'balanced','target_duration':12,'layout':'auto','resolution':'720','quality':'fast','captions':False})
        store.save(project)

        original_transcribe = director.transcribe
        director.transcribe = fake_transcribe
        try:
            job = Job('director-smoke', 'director', project['id'])
            ctx = JobContext(job, threading.Lock())
            result = director.analyze_project(ctx, project['id'], store, settings)
        finally:
            director.transcribe = original_transcribe

        completed = store.load(project['id'])
        sync = completed['analysis']['sync']
        assert sync and abs(float(sync['offset'])) >= 0.5, sync
        assert completed['draft']['keep_ranges'], completed['draft']
        assert completed['draft']['camera_plan'], completed['draft']
        # New drafts keep semantic roles so swapping A/B after analysis does not
        # invalidate the Director's intent. Render resolves ``camera`` through
        # the saved Source Mixer; accept physical B only for legacy drafts.
        assert any(item['camera'] in {'camera', 'B'} for item in completed['draft']['camera_plan']), completed['draft']['camera_plan']

        render_job = Job('render-smoke', 'render', project['id'])
        render_ctx = JobContext(render_job, threading.Lock())
        render_result = render_project(render_ctx, project['id'], store, settings, {'quality':'fast'})
        output = settings.exports_dir / render_result['export']['name']
        metadata = probe_media(output, settings)
        assert (metadata['width'], metadata['height']) == (720, 1280), metadata
        assert metadata['duration'] > 5, metadata
        print(json.dumps({
            'ok': True,
            'engine': result['engine'],
            'sync': sync,
            'draft': {
                'cuts': len(completed['draft']['cuts']),
                'camera_plan': completed['draft']['camera_plan'],
                'output_duration': completed['draft']['output_duration'],
            },
            'render': metadata,
        }, indent=2))
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == '__main__':
    main()
