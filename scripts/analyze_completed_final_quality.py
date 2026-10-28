"""Disentangle encoder quality from a one-source-frame sampling phase difference."""
import json,math,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
    import numpy as np
    import imageio_ffmpeg
    from PIL import Image,ImageDraw
    from moviepy import VideoFileClip
    directory=ROOT/'output/filmcraft/completed-scene-final-comparison'
    report=json.loads((directory/'report.json').read_text(encoding='utf8'))
    times=[.5,2.5,5,7.5,10,12]
    for engine,case in report['cases'].items():
        qa=directory/engine/'quality';source=Path(report['inputs']['sources'][engine]['path'])
        with VideoFileClip(str(source),audio=False) as clip:
            for renderer in ('python','filmcraft'):
                indices=[];offsets=[]
                for index,t in enumerate(times):
                    output=np.asarray(Image.open(qa/f'{renderer}-{index:02}.png').convert('RGB'))[:900].astype(float)
                    expected=math.floor(t*10/(report['inputs']['duration']+.001)*24)
                    candidates=[]
                    for n in range(max(0,expected-1),min(239,expected+1)+1):
                        frame=clip.get_frame(n/24+1e-6)
                        error=float(np.mean((frame[:900].astype(float)-output)**2))
                        candidates.append((error,n,frame))
                    _,n,frame=min(candidates,key=lambda row:row[0])
                    Image.fromarray(frame).save(qa/f'{renderer}-aligned-reference-{index:02}.png')
                    indices.append(n);offsets.append(n-expected)
                command=[imageio_ffmpeg.get_ffmpeg_exe(),'-hide_banner','-i',str(qa/f'{renderer}-%02d.png'),
                    '-i',str(qa/f'{renderer}-aligned-reference-%02d.png'),'-filter_complex',
                    '[0:v]crop=1920:900:0:0[a];[1:v]crop=1920:900:0:0[b];[a][b]ssim','-f','null','-']
                r=subprocess.run(command,capture_output=True,text=True,errors='replace',check=True)
                (qa/f'{renderer}-aligned-ssim.log').write_text(r.stderr,encoding='utf8')
                ssim=float(re.findall(r'All:([\d.]+)',r.stderr)[-1])
                command[command.index('-filter_complex')+1]=command[command.index('-filter_complex')+1].replace('ssim','psnr')
                r=subprocess.run(command,capture_output=True,text=True,errors='replace',check=True)
                psnr=float(re.findall(r'average:([\d.]+)',r.stderr)[-1])
                case['inspection'][renderer]['aligned_quality']={'ssim':ssim,'psnr_db':psnr,'source_frame_indices':indices,
                    'offset_from_common_floor_frames':offsets}
        # Unscaled pixels: this does not hide compression differences through downsampling.
        canvas=Image.new('RGB',(1200,765),'#161a20')
        for column,renderer in enumerate(('python','filmcraft')):
            image=Image.open(qa/f'{renderer}-03.png')
            canvas.paste(image.crop((250,60,850,660)),(column*600,25))
            canvas.paste(image.crop((650,940,1250,1050)),(column*600,650))
            ImageDraw.Draw(canvas).text((column*600+8,5),f'{engine} effects -> {renderer} final / 1:1 pixels',fill='white')
        canvas.save(directory/engine/'detail.png')
    report['quality_method']={'samples_seconds':times,'picture_roi':[0,0,1920,900],
        'reference':'The same completed effect clip, decoded before final rendering. No renderer-specific generated reference.',
        'raw':'Original report quality is same nominal-time/floored-source sample, including frame-sampling phase difference.',
        'aligned':'Also compare each output against the nearest matching source frame within +/-1 frame of expected source time, selected by minimum ROI MSE. Source indices/offsets are reported. This avoids confusing a one-frame resampling phase shift with compression damage.',
        'limit':'Six picture samples, not a full-video perceptual-quality metric. Native and legacy anti-aliasing/color conversion can differ; captions compared visually separately.'}
    (directory/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:{e:v['inspection'][e]['aligned_quality'] for e in ('python','filmcraft')} for k,v in report['cases'].items()}),flush=True)


if __name__=='__main__':main()
