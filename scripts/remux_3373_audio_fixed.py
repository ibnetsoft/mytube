import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
from dotenv import load_dotenv;load_dotenv(ROOT/'.env')
from services.sfx_timing import retime_sfx_cues
from worker.render_audio_reuse import remux_audio_only
D=ROOT/'output/project-recovery-e9233112';run=D/'audio-fixed-v11';cfg=json.loads((run/'config.json').read_text(encoding='utf8'));cues=retime_sfx_cues(cfg['sfx_cues'],cfg['subtitles']);assert len(cues)==2
assert abs(cues[1]['start']-79.72571428571428)<.001
cfg['sfx_cues']=cues;cfg['render_settings']['sfx_cues']=[{**x,'start':next((c['start'] for c in cues if c['id']==x['id']),x.get('start')),'subtitle_index':next((c['subtitle_index'] for c in cues if c['id']==x['id']),x.get('subtitle_index'))} for x in cfg['render_settings']['sfx_cues']]
(run/'config.json').write_text(json.dumps(cfg,ensure_ascii=False),encoding='utf8');print(json.dumps({'sfx':[(c['id'],c['start']) for c in cues],'bgm_start':cfg['render_settings']['bgm_start']}),flush=True)
remux_audio_only(D/'reviewed-final-local/output.mp4',run/'audio/speech_balanced.wav',run,cfg['audio_duration'],cfg['render_settings'],cues)
print('AUDIO_FIXED_REMUX_COMPLETED',flush=True)
