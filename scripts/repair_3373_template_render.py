"""Re-render the preserved AE package with the corrected transparent template."""
from pathlib import Path
import os,sys,json,shutil,subprocess
ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'_dev/artifacts/final_3373_ae_v3'
os.environ['AIR_FINAL_RUN']=str(RUN);os.environ['AIR_RENDER_VERSION']='3'
sys.path.insert(0,str(ROOT/'scripts'))
from publish_3373_ae_render import api,PID,now
from services.remote_render_service import remote_render_executor_func
from services import ffmpeg_slideshow_service as ff
RUN.mkdir(parents=True,exist_ok=True)
PREVIOUS=ROOT/'_dev/artifacts/final_3373_ae_v2'
settings=json.loads((ROOT/'_dev/artifacts/template_fixed_settings.json').read_text(encoding='utf-8'))
project=api('GET','std_projects',params={'id':'eq.'+PID,'select':'project_payload,updated_at'})[0]
payload=project['project_payload'];current=payload.get('render_settings',{})
assert current.get('std_template_text_layers')==settings.get('std_template_text_layers'), 'Template changed during repair'
fixed={**current,**{k:v for k,v in settings.items() if k.startswith('std_')}}
saved=api('PATCH','std_projects',{'project_payload':{**payload,'render_settings':fixed},'updated_at':now()},
    {'id':'eq.'+PID,'updated_at':'eq.'+project['updated_at']})
assert saved,'Concurrent project update; repair snapshot not saved'
for folder in ['images','audio']:
    (RUN/folder).mkdir(exist_ok=True)
    for source in (PREVIOUS/folder).iterdir():
        if source.is_file():
            target=RUN/folder/source.name
            if not target.exists():os.link(source,target)
config=json.loads((PREVIOUS/'config.json').read_text(encoding='utf-8'))
config.update(render_version=3,render_settings={**config['render_settings'],**fixed},template_overlay_filename=None)
if config.get('thumbnail_filename'):
    shutil.copy2(PREVIOUS/config['thumbnail_filename'],RUN/config['thumbnail_filename'])
(RUN/'config.json').write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
subprocess.run([sys.executable,str(ROOT/'scripts/publish_3373_ae_render.py'),'start'],check=True)
original=ff._run_command
def limited(command,*args,**kwargs):
    # Bound filter scheduling memory for the 101-input graph on this 16GB PC.
    bounded=[]
    for item in command:
        if item == '-i':bounded.extend(['-threads','1'])
        bounded.append(item)
    bounded[1:1]=['-filter_complex_threads','4']
    return original(bounded,*args,**kwargs)
ff._run_command=limited
original_render=ff.render_ffmpeg_slideshow
def batched_render(**options):
    import imageio_ffmpeg
    exe=imageio_ffmpeg.get_ffmpeg_exe()
    durations=options['durations'];images=options['images'];callback=options['progress_callback']
    chunks=[];chunk_durations=[];offset=0.0
    groups=list(range(0,len(images),10))
    for number,start in enumerate(groups):
        end=min(start+10,len(images));base=sum(durations[start:end]);extra=.5 if end<len(images) else 0
        folder=RUN/f'chunk-{number:02d}';folder.mkdir(exist_ok=True)
        output=folder/'output.mp4';audio=folder/'narration.wav'
        expected=base+extra
        valid=output.exists() and output.stat().st_size>1000 and abs(ff._media_duration(exe,str(output))-expected)<.15
        if not valid:
            subprocess.run([exe,'-v','error','-y','-ss',str(offset),'-i',options['audio_path'],
                '-t',str(base+extra),'-c:a','pcm_s16le',str(audio)],check=True)
            chunk_lengths=list(durations[start:end]);chunk_lengths[-1]+=extra
            def progress(p,message):callback(int(20+55*(number+max(0,min(1,(p-50)/40)))/len(groups)),f'장면 묶음 {number+1}/{len(groups)}: {message}')
            chunk_settings={**options['subtitle_settings']}
            if chunk_settings.get('scene_motion_speeds'):chunk_settings['scene_motion_speeds']=chunk_settings['scene_motion_speeds'][start:end]
            original_render(temp_dir=str(folder),images=images[start:end],audio_path=str(audio),durations=chunk_lengths,
                subtitles=[],subtitle_settings=chunk_settings,image_effects=(options['image_effects'] or [])[start:end],
                transition_effects=(options['transition_effects'] or [])[start:end],resolution=options['resolution'],
                use_gpu=True,progress_callback=progress)
        chunks.append(str(output));chunk_durations.append(base);offset+=base
    # Chunk videos include the transition handle. Apply global titles, subtitles
    # and original narration once, preserving crossfades at chunk boundaries.
    final=dict(options);final.update(images=chunks,durations=chunk_durations,image_effects=[],transition_effects=['']*len(chunks),
        progress_callback=lambda p,m:callback(int(75+15*max(0,min(1,(p-50)/40))),m))
    return original_render(**final)
ff.render_ffmpeg_slideshow=batched_render
remote_render_executor_func('3373-template-v3',str(RUN),use_gpu=True)
subprocess.run([sys.executable,str(ROOT/'scripts/qa_3373_final.py')],check=True)
subprocess.run([sys.executable,str(ROOT/'scripts/publish_3373_ae_render.py'),'finish'],check=True)
print('TEMPLATE_REPAIR_COMPLETE',str(RUN/'output.mp4'),flush=True)
