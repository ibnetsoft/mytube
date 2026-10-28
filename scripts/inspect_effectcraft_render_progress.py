"""Read completed H.264 frame starts from this task's growing MP4, without touching it."""
import json
from pathlib import Path
D=Path(__file__).resolve().parents[1]/'output/effectcraft/project-3376-final-20261021'
q=json.loads((D/'queue.json').read_text(encoding='utf8'));p=Path.home()/'AppData/Local/Temp/air-render-checkpoints'/q['id']/'motion-visual.mp4'
if not p.exists():print('Visual encoder has not started');raise SystemExit
b=p.read_bytes();offset=0
while offset+8<=len(b):
    size=int.from_bytes(b[offset:offset+4],'big');kind=b[offset+4:offset+8];head=8
    if size==1:size=int.from_bytes(b[offset+8:offset+16],'big');head=16
    if kind==b'mdat':
        j=offset+head;frames=0
        while j+4<len(b):
            length=int.from_bytes(b[j:j+4],'big');j+=4
            if length<1 or j+length>len(b):break
            if b[j]&31 in (1,5) and length>1 and b[j+1]&128:frames+=1
            j+=length
        print(json.dumps(dict(encoded_frame_starts=frames,encoded_seconds=round(frames/24,1),total_seconds=1614.4196,bytes=len(b))));break
    if not size:break
    offset+=size
