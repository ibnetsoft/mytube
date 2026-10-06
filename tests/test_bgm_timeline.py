import unittest
import subprocess
import numpy as np
import imageio_ffmpeg
from services.bgm_timeline import bgm_filter, bgm_window

class BgmTimelineTests(unittest.TestCase):
    def test_rendered_sound_obeys_range_and_fades(self):
        settings = dict(bgm_start=3, bgm_end=9, bgm_fade_in=2, bgm_fade_out=2, bgm_volume=1)
        result = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-f', 'lavfi', '-i',
            'sine=frequency=440:sample_rate=8000:duration=12', '-af', bgm_filter(settings,12)+',apad=whole_dur=12',
            '-f', 'f32le', '-ac', '1', '-ar', '8000', '-'], stdout=subprocess.PIPE, check=True)
        samples = np.frombuffer(result.stdout, dtype=np.float32)
        def rms(time):
            part = samples[int(time*8000):int((time+.1)*8000)]
            return np.sqrt(np.mean(part**2))
        self.assertEqual(rms(1),0)
        self.assertEqual(rms(10),0)
        self.assertLess(rms(3.1),rms(4))
        self.assertLess(rms(4),rms(6))
        self.assertGreater(rms(7),rms(8.8))
    def test_mute_and_short_window(self):
        self.assertIn('volume=0.000000',bgm_filter({'bgm_volume':0},10))
        self.assertEqual(bgm_window(dict(bgm_start=3,bgm_end=4,bgm_fade_in=20,bgm_fade_out=20),10),(3,4,.5,.5))

if __name__ == '__main__': unittest.main()
