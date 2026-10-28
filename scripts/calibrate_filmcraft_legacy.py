"""Local caption calibration and native encoder trials; no deployment or queues."""
import json,os,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'worker'))
from filmcraft_native import NativeTimeline
from scripts.filmcraft import sha

D=ROOT/'output/filmcraft/matched-scene-3376-037';D.mkdir(parents=True,exist_ok=True)
OLD=ROOT/'output/filmcraft/existing-scene-3376-037-comparison'


def prepare_font():
    from fontTools.ttLib import TTFont
    source=ROOT/'static/fonts/NotoSansKR-Bold.ttf'
    family='AIR Legacy KR '+sha(source)[:10]
    font=TTFont(source)
    for record in font['name'].names:
        if record.nameID in (1,16):value=family
        elif record.nameID in (2,17):value='SemiBold'
        elif record.nameID==4:value=family+' SemiBold'
        elif record.nameID==6:value=family.replace(' ','')+'-SemiBold'
        else:continue
        record.string=value.encode(record.getEncoding(),errors='replace')
    path=D/'legacy-exact-face.ttf';font.save(path);font.close()
    target=Path(os.environ['LOCALAPPDATA'])/'Microsoft/Windows/Fonts'/path.name.replace('legacy-exact-face',family.replace(' ',''))
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():
        existing=TTFont(target)
        assert existing['name'].getDebugName(1)==family
        existing.close();shutil.copy2(target,path)
    else:shutil.copy2(path,target)
    return family,source,target


def bounds(path):
    import numpy as np
    from PIL import Image
    image=np.asarray(Image.open(path).convert('RGB'));mask=(image.min(axis=2)>180)
    y,x=np.where(mask)
    return {'box':[int(x.min()),int(y.min()),int(x.max()+1),int(y.max()+1)],'pixels':int(mask.sum())}


def main():
    from ae_media_utils import ffmpeg
    from services.ffmpeg_slideshow_service import _write_ass_file,_prepare_fonts_dir
    from services.subtitle_layout import subtitle_font_pixels
    from fontTools.ttLib import TTFont
    info=json.loads((OLD/'inputs.json').read_text(encoding='utf8'))
    family,source,target=prepare_font();settings=info['settings']
    rows=[{'start':0,'end':1,'text':info['subtitles'][0]['text']}]
    ass=D/'reference.ass';fonts=_prepare_fonts_dir(str(D),settings)
    _write_ass_file(ass,rows,settings,(1920,1080),fonts)
    # cwd makes the subtitle path portable through FFmpeg's filter parser.
    subprocess.run([ffmpeg(),'-v','error','-y','-f','lavfi','-i','color=black:s=1920x1080:r=24:d=1',
        '-vf','subtitles=reference.ass:fontsdir='+Path(os.path.relpath(fonts,D)).as_posix(),
        '-frames:v','1',str(D/'legacy-caption.png')],cwd=D,check=True)
    reference=bounds(D/'legacy-caption.png')
    # Explicitly use the exact legacy face rather than the conflicting system VF.
    native=NativeTimeline(D/'caption-calibration',24,(1920,1080),1,lambda:None)
    native.shape('rectangle',(960,540),(1920,1080),0,1,'#000000',track=1)
    style={**settings,'subtitle_font_family':family};native.captions(rows,style)
    f=TTFont(source);factor=f['head'].unitsPerEm/(f['OS/2'].usWinAscent+f['OS/2'].usWinDescent);f.close()
    size=subtitle_font_pixels(settings['subtitle_font_size'],1920)*factor;margin=.05
    trials=[]
    for i in range(3):
        native.call('captions.setStyle',{'track':'C1','size':size,'margin':margin})
        path=D/f'native-caption-{i}.png'
        native.run(['--project',native.project,'render','--seconds','.5','--out',path],'caption-render')
        found=bounds(path);trials.append({'size':size,'margin':margin,**found})
        a=reference['box'];b=found['box'];size*= (a[2]-a[0])/(b[2]-b[0]);margin+=(b[3]-a[3])/1080
    calibration={'family':family,'source_font':str(source),'source_sha256':sha(source),'installed_font':str(target),
        'reference':reference,'trials':trials,'style':{'font':family,'size':trials[-1]['size'],'margin':trials[-1]['margin']},
        'notes':'Exact existing static face, renamed privately to avoid the system variable-font family collision. Native SemiBold resolves this exact face with no synthetic bold.'}
    (D/'caption-calibration.json').write_text(json.dumps(calibration,indent=2),encoding='utf8')
    print(json.dumps(calibration),flush=True)


if __name__=='__main__':main()
