"""Fit a local native timeline against the previous existing-scene benchmark."""
import json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'worker'))
from filmcraft_native import render_master,NativeTimeline
from filmcraft_render import PIN,VERSION
from scripts.calibrate_filmcraft_legacy import D,OLD,bounds


def main():
    info=json.loads((OLD/'inputs.json').read_text(encoding='utf8'))
    cal=json.loads((D/'caption-calibration.json').read_text())
    settings={**info['settings'],'subtitle_font_family':cal['family'],'subtitle_font_size':cal['style']['size'],
        'subtitle_pos_y':'b:'+str(cal['style']['margin']*100)+'%'}
    snapshot={'renderer':{'engine':'filmcraft','revision':PIN['revision'],'adapter':VERSION},
        'motion':settings['motion'],'settings':settings,'scenes':[{'number':37,'source_kind':'image','start':0,'end':info['duration']}],
        'subtitles':info['subtitles']}
    encoding={'bitrateMode':'vbr1Pass','bitrateKbps':1540,'maxBitrateKbps':2000,'hardwareEncoding':'auto',
        'audio':{'bitrateKbps':192,'channels':1}}
    work=D/'hardware-trial';work.mkdir(exist_ok=True)
    start=time.perf_counter()
    output=render_master(snapshot,sources={37:Path(info['source'])},plans=[{'number':37,'scene':info['shared_plan']}],
        voice=OLD/'original-voice-window.wav',directory=work,fresh=lambda:None,settings=settings,export_settings=encoding)
    receipt=json.loads((work/'filmcraft-receipt.json').read_text(encoding='utf8'))
    result={'seconds':time.perf_counter()-start,'bytes':output.stat().st_size,'encoding':encoding,'settings':settings,
        'snapshot':snapshot,'gpu':receipt['gpu_composition']}
    (D/'hardware-trial.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=True)[:800],flush=True)


if __name__=='__main__':main()
