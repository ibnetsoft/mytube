import json, os, subprocess, sys
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'worker'))
os.chdir(ROOT)
import worker_config  # noqa: F401
from ae_highlight_worker import GcsRef, _download_gcs_file
from ae_media_utils import ffmpeg

report = json.loads((ROOT / '_dev/artifacts/verify_3381_impact.json').read_text(encoding='utf-8-sig'))
rows = {int(r['scene']): r for r in report['results']}
times = {19: 6.0, 25: 12.0, 33: 6.5, 36: 7.6, 41: 6.2}
out = ROOT / '_dev/artifacts/qa_3381_impact'
out.mkdir(parents=True, exist_ok=True)
frames = []
for scene, timestamp in times.items():
    clip = out / f'scene-{scene:03d}.mp4'
    frame = out / f'scene-{scene:03d}-{timestamp:.1f}.jpg'
    if not clip.exists():
        _download_gcs_file(GcsRef('air-studio-prod', rows[scene]['gcs']), clip)
    subprocess.run([ffmpeg(), '-v', 'error', '-y', '-ss', str(timestamp), '-i', str(clip), '-frames:v', '1', '-q:v', '2', str(frame)], check=True)
    with Image.open(frame) as im:
        frames.append((scene, im.convert('RGB').copy()))

thumbs=[]
for scene, im in frames:
    im.thumbnail((640, 360), Image.Resampling.LANCZOS)
    canvas=Image.new('RGB',(660,400),'white'); canvas.paste(im,((660-im.width)//2,25))
    ImageDraw.Draw(canvas).text((12,8),f'Scene {scene}',fill='black')
    thumbs.append(canvas)
sheet=Image.new('RGB',(1320,1200),'#dddddd')
for i,im in enumerate(thumbs): sheet.paste(im,((i%2)*660,(i//2)*400))
sheet.save(out/'contact-sheet.jpg',quality=92)
print(out/'contact-sheet.jpg')
