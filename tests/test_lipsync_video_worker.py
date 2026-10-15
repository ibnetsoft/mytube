import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'worker'))
import lipsync_video_worker as worker

class Response:
    def __init__(self, data): self.data = data
    def json(self): return self.data

class LipSyncWorkerTest(unittest.TestCase):
    def test_final_render_preserves_speed_and_refuses_wrong_duration(self):
        sys.path.insert(0, str(ROOT))
        from services.ffmpeg_slideshow_service import render_ffmpeg_slideshow
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            video, audio = directory / 'source.mp4', directory / 'audio.wav'
            subprocess.run([worker.ffmpeg(), '-y', '-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=24', '-t', '2', '-c:v', 'libx264', str(video)], check=True, capture_output=True)
            with wave.open(str(audio), 'wb') as w:
                w.setnchannels(1);w.setsampwidth(2);w.setframerate(48000);w.writeframes(b'\0\0'*96000)
            args = dict(temp_dir=str(directory), images=[str(video)], audio_path=str(audio), durations=[2], subtitles=[],
                        subtitle_settings={'timing_locked_indices':[0]}, image_effects=[], transition_effects=[], resolution=(320,180), use_gpu=False)
            render_ffmpeg_slideshow(**args)
            graph = (directory / 'ffmpeg.fast.filter.txt').read_text()
            self.assertIn('setpts=PTS-STARTPTS,tpad=', graph)
            self.assertNotIn('*(PTS-STARTPTS)', graph)
            args['durations']=[3]
            with self.assertRaisesRegex(RuntimeError, 'duration differs'):
                render_ffmpeg_slideshow(**args)

    def test_existing_audio_is_cut_and_provider_receipt_survives_resume(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            image = directory / 'source.png'
            Image.new('RGB', (320, 180), (30, 60, 100)).save(image)
            audio = directory / 'voice.wav'
            with wave.open(str(audio), 'wb') as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(48000)
                w.writeframes(b'\0\0' * 96000)
            raw = directory / 'provider.mp4'
            subprocess.run([worker.ffmpeg(), '-y', '-loop', '1', '-i', str(image), '-t', '1', '-r', '24', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(raw)], check=True, capture_output=True)
            asset = lambda name: {'metadata': {'storage_provider': 'gcs', 'gcs_bucket': 'test', 'gcs_path': name}}
            job = {'id': 'job', 'project_id': 'project', 'scene_number': 1, 'updated_at': 'now',
                   'metadata': {'kind': 'lipsync_job', 'state': 'queued', 'fingerprint': 'fingerprint', 'points': {'girl': [.4, .5]},
                    'plan': {'start': 0, 'end': 2, 'scene_number': 1, 'image': asset('image'), 'audio': asset('audio'),
                             'shots': [{'start': .5, 'end': 1.5, 'speaker': 'girl', 'text': '대사'}]}}}
            inserted, submitted = [], []
            def request(method, url, headers, **kwargs):
                if url.endswith('/global_settings'): return Response([{'value': 'test-key'}])
                if url.endswith('/std_projects'): return Response([{'project_payload': {'subtitles': [
                    {'scene_number':1,'dialogue_kind':'dialogue','dialogue_speaker':'girl','text':'대사','start':.5,'end':1.5}]}}])
                if method == 'GET':
                    return Response([] if kwargs.get('params', {}).get('metadata->>gcs_path') else [copy.deepcopy(job)])
                if method == 'PATCH':
                    job.update(kwargs['json']); return Response([copy.deepcopy(job)])
                inserted.append(kwargs['json']); return Response([{'id': 'output'}])
            def download(bucket, path, target): shutil.copy(image if path == 'image' else audio, target)
            def provider(key, method, path, **kwargs):
                if path == '/files':
                    name, handle, mime = kwargs['files']['file']
                    if mime == 'audio/wav':
                        with wave.open(handle, 'rb') as w: self.assertAlmostEqual(w.getnframes()/w.getframerate(), 1, places=2)
                    return {'url': 'https://provider.test/input'}
                if method == 'POST':
                    submitted.append(kwargs['json']); return {'job_id': 'external-job'}
                if path.endswith('/status'): return {'status': 'COMPLETED'}
                return {'outputs': [{'url': 'https://provider.test/output', 'content_type': 'video/mp4', 'duration_ms': 1000}]}
            r = type('Download', (), {'content': raw.read_bytes(), 'raise_for_status': lambda self: None})()
            with patch.object(worker, '_supabase', return_value=('https://db.test', {})), patch.object(worker, '_request', side_effect=request), \
                 patch.object(worker, '_download_gcs', side_effect=download), patch.object(worker, 'hedra', side_effect=provider), \
                 patch.object(worker, '_upload_gcs', return_value=('test', 'output.mp4')), patch.object(worker.requests, 'get', return_value=r), \
                 patch.object(worker.worker_config, 'TEMP_DIR', directory):
                self.assertTrue(worker.process_one())
                self.assertEqual(job['metadata']['state'], 'review_pending')
                self.assertEqual(submitted[0]['input']['bounding_box_target'], [.4, .5])
                self.assertNotIn('voice_id', submitted[0]['input'])
                self.assertEqual(inserted[0]['metadata']['duration_seconds'], 2)
                self.assertTrue(inserted[0]['metadata']['timing_locked'])
                job['metadata']['state'] = 'processing'
                (directory / 'lipsync/job/raw_0.mp4').unlink()
                self.assertTrue(worker.process_one())
                self.assertEqual(len(submitted), 1, 'restart must reuse the paid provider job')

if __name__ == '__main__': unittest.main()
