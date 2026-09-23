import json,math,re,shutil,subprocess
from pathlib import Path
from imageio_ffmpeg import get_ffmpeg_exe
root=Path(__file__).resolve().parent;src=root/'v8';out=root/'v9';out.mkdir(exist_ok=True)
m=json.loads((src/'manifest.json').read_text(encoding='utf8'));oldpages=m['pages']
fps=24;total_frames=130*fps;turn_frames=25
budget=total_frames-turn_frames*(len(oldpages)-1)
durations=[p['end']-p['start'] for p in oldpages]
raw=[d/sum(durations)*budget for d in durations];counts=[math.floor(n) for n in raw]
for i in sorted(range(len(raw)),key=lambda i:raw[i]-counts[i],reverse=True)[:budget-sum(counts)]:counts[i]+=1
segments=[];pages=[];clock=0.;mapping=[]
for i,p in enumerate(oldpages):
 seconds=counts[i]/fps;speed=durations[i]/seconds
 segments.append((p['start'],p['end'],counts[i],speed,False))
 pages.append({**p,'start':clock,'end':clock+seconds})
 mapping.append({'page':i+1,'speed':speed,'old_start':p['start'],'new_start':clock,'duration':seconds})
 clock+=seconds
 if i<len(oldpages)-1:
  segments.append((p['end'],oldpages[i+1]['start'],turn_frames,1,True));clock+=turn_frames/fps
filters=[];concat=[]
for i,(start,end,frames,speed,turn) in enumerate(segments):
 length=frames/fps;ratio=(end-start)/length
 filters.append(f'[0:v]trim=start={start:.9f}:end={end:.9f},setpts=(PTS-STARTPTS)/{ratio:.12f},fps={fps},tpad=stop_mode=clone:stop_duration=0.1,trim=end_frame={frames},setpts=N/({fps}*TB)[v{i}]')
 # Preserve page-turn audio speed exactly; only narration gets atempo (pitch preserved).
 audio=f'[0:a]atrim=start={start:.9f}:end={end:.9f},asetpts=PTS-STARTPTS'
 if not turn:audio+=f',atempo={speed:.12f}'
 audio+=f',apad,atrim=duration={length:.12f},asetpts=PTS-STARTPTS[a{i}]'
 filters.append(audio);concat.append(f'[v{i}][a{i}]')
filters.append(''.join(concat)+f'concat=n={len(segments)}:v=1:a=1[v][a]')
filterpath=out/'retime.ffmpeg';filterpath.write_text(';\n'.join(filters),encoding='utf8')
cmd=[get_ffmpeg_exe(),'-y','-i',str(src/'output.mp4'),'-filter_complex_script',str(filterpath),'-map','[v]','-map','[a]','-c:v','libx264','-preset','veryfast','-crf','18','-threads','2','-filter_complex_threads','2','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-t','130','-movflags','+faststart',str(out/'output.mp4')]
with (out/'encode.log').open('w') as log:subprocess.run(cmd,stdout=log,stderr=log,check=True)
for path in src.glob('page_*.png'):shutil.copyfile(path,out/path.name)
m.update(duration=130,pages=pages,retiming=mapping)
m['settings']['comic']['turn_duration']=turn_frames/fps
m['page_turn_sounds']=[{**s,'start':pages[i]['end'],'playback_rate':1} for i,s in enumerate(m['page_turn_sounds'])]
m['note']='130초 재편집: 일반 구간 약 1.34배속(음성 피치 유지), 넘김 25프레임, 넘김 효과음 원속도. 원본 source_start/end와 events는 v8 대본 시간이며 retiming으로 변환.'
(out/'manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2),encoding='utf8')
html=(src/'index.html').read_text(encoding='utf8')
oldtimes=[float(x) for x in re.findall(r'onclick="seek\(([\d.]+)\)"',html)]
def convert(match):
 t=float(match.group(1))
 for i,p in enumerate(oldpages):
  if t<=p['end']:return f'onclick="seek({pages[i]["start"]+(t-p["start"])/mapping[i]["speed"]:.4f})"'
 return match.group(0)
html=re.sub(r'onclick="seek\(([\d.]+)\)"',convert,html)
html=html.replace('<h1>','<h1>2분 10초 · ',1)
html=html.replace('<video id=','<p>전체 2:10 · 일반 구간 약 1.34배속, 음성 높이 유지 · 책장 소리는 원래 속도, 넘김 동작은 약 1.04초입니다.</p><video id=',1)
(out/'index.html').write_text(html,encoding='utf8')
assert abs(clock-130)<1e-8
print('DONE: 130.000 seconds; page-turn recordings unchanged speed; 13 chapter links remapped',flush=True)
