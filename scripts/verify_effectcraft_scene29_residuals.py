"""Reproduce and audit the bounded scene-29 residual corrections."""
import argparse,copy,json,shutil,subprocess,sys,hashlib
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
import imageio_ffmpeg
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'worker'))
from effectcraft_render import binary,_execute,render_native_video
from effectcraft_compatibility import prepare_project,smooth_mask_replacements,fractional_replacements
OLD=ROOT/'output/effectcraft/psd-3376-scene29-effects-20261021'
PREV=ROOT/'output/effectcraft/psd-3376-scene29-vignette-fix-20261021'
D=ROOT/'output/effectcraft/psd-3376-scene29-residual-fix-20261021';D.mkdir(exist_ok=True)
parser=argparse.ArgumentParser();parser.add_argument('--render',action='store_true');args=parser.parse_args()
ff=imageio_ffmpeg.get_ffmpeg_exe();cli=binary()
if args.render:
    shutil.copy2(OLD/'rich.ecproj',D/'scene.ecproj')
    prepare_project(cli,D/'scene.ecproj',D,_execute)
    export=render_native_video(cli,D/'scene.ecproj','ae_highlight_parallax_layered_scene',D/'effectcraft.mp4',24,D)
    (D/'export-receipt.json').write_text(json.dumps(export,indent=2))
# Correct missing matrix metadata in a comparison copy, without re-encoding samples.
subprocess.run([ff,'-v','error','-y','-i',str(OLD/'rich/ae-reference.mp4'),'-map','0:v:0','-c','copy',
                '-bsf:v','h264_metadata=colour_primaries=1:transfer_characteristics=1:matrix_coefficients=1:video_full_range_flag=0',
                '-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709','-color_range','tv',str(D/'ae-reference.mp4')],check=True)
original=json.loads((OLD/'rich.ecproj').read_text(encoding='utf8'))
project=json.loads((D/'scene.ecproj').read_text(encoding='utf8'))
assert not smooth_mask_replacements(project) and not fractional_replacements(project)
audit=[]
for key,item in original['items'].items():
    if item['kind'].get('type')!='Comp':continue
    layers=item['kind']['layers'];after=project['items'][key]['kind']['layers'];assert len(layers)==len(after)
    for a,b in zip(layers,after):
        assert a['id']==b['id'] and a['name']==b['name']
        normalized=copy.deepcopy(b)
        ag={g['match']:g for g in a['props']['children']};bg={g['match']:g for g in normalized['props']['children']}
        if a['name']=='background' and ag['effects']['children']:
            oldfx=ag['effects']['children'];newfx=bg['effects']['children']
            original_fx=next(e for e in newfx if e['uid']==oldfx[0]['uid'])
            recovered=copy.deepcopy(original_fx);recovered['enabled']=oldfx[0]['enabled'];assert recovered==oldfx[0]
            assert len(newfx)==4 and original_fx['enabled'] is False
            bg['effects']['children']=copy.deepcopy(oldfx)
        elif a['name'].startswith(('ae_effect_subtle_vignette_','ae_effect_light_sweep_')):
            at={p['match']:p for p in ag['transform']['children']};bt={p['match']:p for p in bg['transform']['children']}
            ap={p['match']:p for p in ag['masks']['children'][0]['children']};bp={p['match']:p for p in bg['masks']['children'][0]['children']}
            for av,bv in zip(ap['path']['value']['v']['vertices'],bp['path']['value']['v']['vertices']):
                assert np.allclose(np.array(av)-at['anchor']['value']['v'][:2],np.array(bv)-bt['anchor']['value']['v'][:2])
            assert np.allclose(bp['feather']['value']['v'],np.array(ap['feather']['value']['v'])*.75)
            normalized['comment']=a['comment'];normalized['source']=copy.deepcopy(a['source'])
            for n,v in enumerate(bg['transform']['children']):
                if v['match']=='anchor':bg['transform']['children'][n]=copy.deepcopy(at['anchor'])
            for n,v in enumerate(bg['masks']['children'][0]['children']):
                if v['match'] in ('path','feather'):bg['masks']['children'][0]['children'][n]=copy.deepcopy(ap[v['match']])
        assert normalized==a,a['name']+' unexpectedly changed'
        audit.append(dict(comp=item['name'],layer=a['name'],authored_transforms_timing_opacity_and_geometry_preserved=True))

def image(p):return np.asarray(Image.open(p).convert('RGB')).astype(float)
times=[0,29/24,2.5,3.5,4,4.5,6.5,9,239/24];rows=[]
for i,t in enumerate(times):
    path=D/f'ec-final-{i}.png'
    _execute(cli,['render-frame',str(D/'scene.ecproj'),'--comp','ae_highlight_parallax_layered_scene','--time',str(t),'--out',str(path),'--json'],D,'ec-final-'+str(i))
    ae,before,after=[image(p) for p in [D/f'ae-rich-{i}.png',D/f'ec-rich-{i}.png',path]]
    rows.append(dict(time=t,before_mae_255=float(abs(ae-before).mean()),after_mae_255=float(abs(ae-after).mean()),mean_rgb_delta_ae_minus_ec=(ae-after).mean((0,1)).tolist()))
(D/'lossless-final-metrics.json').write_text(json.dumps(rows,indent=2))
encoded=[]
for i,t in enumerate(times):
    frames=[]
    for name,path in [('ae',D/'ae-reference.mp4'),('before',PREV/'effectcraft.mp4'),('after',D/'effectcraft.mp4')]:
        out=D/f'encoded-{name}-{i}.png'
        subprocess.run([ff,'-v','error','-y','-ss',str(t),'-i',str(path),'-frames:v','1',str(out)],check=True)
        frames.append(image(out))
    a,b,c=frames;encoded.append(dict(time=t,before_mae_255=float(abs(a-b).mean()),after_mae_255=float(abs(a-c).mean())))
(D/'encoded-fair-metrics.json').write_text(json.dumps(encoded,indent=2))
# Explicit matrix decoding must exactly equal the metadata-corrected reference.
out=D/'ae-explicit-709.png'
subprocess.run([ff,'-v','error','-y','-ss','4','-i',str(OLD/'rich/ae-reference.mp4'),'-vf','scale=in_color_matrix=bt709:out_color_matrix=bt709','-frames:v','1',str(out)],check=True)
assert np.array_equal(image(out),image(D/'encoded-ae-4.png'))
for path in [D/'effectcraft.mp4',D/'ae-reference.mp4']:
    assert imageio_ffmpeg.count_frames_and_secs(str(path))==(240,10.)
    subprocess.run([ff,'-v','error','-i',str(path),'-f','null','-'],check=True)

sheet=Image.new('RGB',(1440,588),'#151515');draw=ImageDraw.Draw(sheet)
ae,before,after=[image(p) for p in [D/'ae-rich-4.png',D/'ec-rich-4.png',D/'ec-final-4.png']]
for n,(label,im) in enumerate([('AE lossless',ae),('EffectCraft previous',before),('EffectCraft fixed',after)]):
    sheet.paste(Image.fromarray(im.astype('uint8')).resize((480,270)),(480*n,24));draw.text((480*n+8,7),label,fill='white')
    delta=np.clip(abs(ae-im)*12,0,255).astype('uint8')
    sheet.paste(Image.fromarray(delta).resize((480,270)),(480*n,318));draw.text((480*n+8,301),'Difference from AE x12',fill='white')
sheet.save(D/'residual-before-after.jpg',quality=95)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
summary=dict(lossless_before_mean=float(np.mean([r['before_mae_255'] for r in rows])),lossless_after_mean=float(np.mean([r['after_mae_255'] for r in rows])),
             encoded_before_mean=float(np.mean([r['before_mae_255'] for r in encoded])),encoded_after_mean=float(np.mean([r['after_mae_255'] for r in encoded])),
             source_psd_sha256=sha(OLD/'source.psd'),original_ae_mp4_sha256=sha(OLD/'rich/ae-reference.mp4'),corrected_ae_mp4_sha256=sha(D/'ae-reference.mp4'),
             reference_correction='BT709 limited matrix metadata; stream copy, no video sample re-encode',layers=audit)
(D/'residual-validation.json').write_text(json.dumps(summary,indent=2),encoding='utf8');print(json.dumps({k:v for k,v in summary.items() if k.endswith('_mean')},indent=2),flush=True)
