import whisper,json,subprocess,numpy as np
from pathlib import Path
ffmpeg=str(Path('venv/Lib/site-packages/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe').resolve())
root=Path('_dev/artifacts/v4-performance-ja');model=whisper.load_model('base',device='cpu');reports=[]
for tag in ['whispers','excited']:
 pcm=subprocess.check_output([ffmpeg,'-v','error','-i',str(root/f'v4-{tag}.mp3'),'-f','f32le','-ar','16000','-ac','1','pipe:1'])
 result=model.transcribe(np.frombuffer(pcm,dtype=np.float32).copy(),language='ja',fp16=False,word_timestamps=True)
 reports.append({'tag':tag,'transcript':result['text'],'segments':result['segments']})
(root/'local-asr.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(reports,ensure_ascii=False))
