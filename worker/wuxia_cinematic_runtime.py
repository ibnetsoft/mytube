"""Execute source-reviewed cinematic samples without recomputing the web clock."""
import copy,json,math
from pathlib import Path
import numpy as np
from PIL import Image
CONTRACT='wuxia_cinematic/v1'
def validate(t):
 if t.get('contract')!='wuxia_native_timeline/v6':
  if any('cinematic' in s for s in t.get('samples',[])):raise ValueError('Cinematic samples require native v6')
  return
 from worker.wuxia_cinematic import validate_review
 plan=t['cinematic_plan'];states={s['asset_id']:s for s in t['states']}
 for st in states.values():
  r=st.get('cinematic_review') or {}
  if r.get('graphics',[])!=t.get('cinematic_graphics',[]) or r.get('plan')!=plan or r.get('contract')!=CONTRACT:raise ValueError('Cinematic source plan changed')
  validate_review(r,st,plan)
 for s in t['samples']:
  f=s.get('cinematic');r=states[s['state']]['cinematic_review'];d=t['cinematic_states'][s['state']]
  if not isinstance(f,dict) or f.get('contract')!=CONTRACT or f.get('issues')!=[] or f.get('blur_axis') not in ('x','y'):raise ValueError('Invalid cinematic frozen frame')
  for key,lo,hi in [('vignette_opacity',0,.38),('panel_opacity',0,1),('panel_scale',.86,1.08),('blur_radius',0,12)]:
   if type(f.get(key)) not in (float,int) or not math.isfinite(f[key]) or not lo-1e-8<=f[key]<=hi+1e-8:raise ValueError('Unsafe cinematic '+key)
  if (f['vignette_opacity'] and not (plan['vignette'] and r['passed'] and r['vignette_allowed'] and d.get('mask'))) or (f['panel_opacity'] and not (plan['panel'] and r['passed'] and r['panel_allowed'] and d.get('panel'))) or (f['blur_radius'] and not (plan['slide_blur'] and r['passed'] and r['slide_blur_allowed'] and s.get('transition',{}).get('kind','').startswith('wipe_'))):raise ValueError('Unreviewed cinematic execution')
  if f['blur_radius'] and d.get('lettering_boxes',[])!=r.get('lettering_boxes',[]):raise ValueError('Baked lettering protection changed')
  if d.get('mask') and d['mask']!={'center':r['focus'],'protected_boxes':r['protected_boxes']}:raise ValueError('Vignette protection changed after source review')
  if states[s['state']].get('energy_only_motion') and any(f[k] for k in ('panel_opacity','blur_radius','vignette_opacity')):raise ValueError('Energy-only artwork must stay fixed')
  if d.get('panel') and (d['panel']['rect']!=r['panel_rect'] or not 24<=float(d['panel']['font_size'])<=36):raise ValueError('Panel geometry changed')
  if d.get('panel'):
   import re
   if not isinstance(d['panel'].get('lines'),list) or len(d['panel']['lines'])>6 or re.sub(r'\s','', ''.join(d['panel']['lines']))!=re.sub(r'\s','',plan['panel_text']):raise ValueError('Panel text differs from reviewed information')

def mask_image(mask):
 w,h=960,540;yy,xx=np.mgrid[0:h,0:w];x=xx/(w-1);y=yy/(h-1);cx,cy=mask['center']
 radius=np.hypot((x-cx)/max(cx,1-cx),(y-cy)/max(cy,1-cy))/math.sqrt(2);alpha=np.clip((radius-.15)/.65,0,1)**1.2
 for l,t,r,b in mask['protected_boxes']:
  dx=np.maximum.reduce((l-x,np.zeros_like(x),x-r))*1920;dy=np.maximum.reduce((t-y,np.zeros_like(y),y-b))*1080;alpha*=np.minimum(1,np.hypot(dx,dy)/20)
 pixels=np.zeros((h,w,4),dtype=np.uint8);pixels[:,:,3]=np.floor(alpha*255+.5).astype(np.uint8);return Image.fromarray(pixels)

def prepare(t,directory):
 validate(t)
 if t.get('contract')!='wuxia_native_timeline/v6':return
 directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
 for index,d in enumerate(t['cinematic_states'].values()):
  d.pop('mask_file',None)
  if d.get('mask'):
   path=directory/f'mask-{index}.png';mask_image(d['mask']).save(path);d['mask_file']=str(path.resolve())

def jsx(t):
 if t.get('contract')!='wuxia_native_timeline/v6':return ''
 data=json.dumps({'descriptors':t['cinematic_states'],'samples':[{'at':s['at'],'state':s['state'],**s['cinematic']} for s in t['samples']]},ensure_ascii=True,allow_nan=False)
 return '''
    var WCIN='''+data+''';
    // Equal-weight finite-exposure blur in an artwork-only precomp. Text stays sharp.
    var needsBlur=false;for(var fi=0;fi<WCIN.samples.length;fi++)if(WCIN.samples[fi].blur_radius>0)needsBlur=true;
    if(needsBlur){var exposure=app.project.items.addComp('wuxia_directional_exposure',W,H,1,S.duration,S.fps);
      for(var bi=0;bi<9;bi++){var tap=exposure.layers.add(source);tap.name='art_exposure_'+bi;tap.property('Opacity').setValue(100/(bi+1));var pos=tap.property('Position');
        for(var fi=0;fi<WCIN.samples.length;fi++){var f=WCIN.samples[fi],offset=(bi-4)*f.blur_radius/4;pos.setValueAtTime(f.at,[W/2+(f.blur_axis==='x'?offset:0),H/2+(f.blur_axis==='y'?offset:0)]);}whold(pos);
      }
      for(var stateId in WCIN.descriptors){var letters=WCIN.descriptors[stateId].lettering_boxes||[];for(var li=0;li<letters.length;li++){
        var sharp=exposure.layers.add(source),b=letters[li];sharp.name='sharp_baked_letter_'+li;var mask=sharp.property('ADBE Mask Parade').addProperty('ADBE Mask Atom');mask.property('ADBE Mask Shape').setValue(wshape([[b[0]*W,b[1]*H],[b[2]*W,b[1]*H],[b[2]*W,b[3]*H],[b[0]*W,b[3]*H]],true));var op=sharp.property('Opacity');for(var fi=0;fi<WCIN.samples.length;fi++){var f=WCIN.samples[fi];op.setValueAtTime(f.at,f.state===stateId&&f.blur_radius>0?100:0);}whold(op);
      }}view.replaceSource(exposure,false);
    }
    function cinePose(layer,identity,center){var tr=layer.property('ADBE Transform Group');tr.property('Anchor Point').setValue(center);tr.property('Position').setValue(center);var op=tr.property('Opacity'),sc=tr.property('Scale');
      for(var fi=0;fi<WCIN.samples.length;fi++){var f=WCIN.samples[fi];op.setValueAtTime(f.at,f.state===identity?f.panel_opacity*100:0);sc.setValueAtTime(f.at,[f.panel_scale*100,f.panel_scale*100]);}whold(op);whold(sc);if(typeof cameraRig!=='undefined')layer.setParentWithJump(cameraRig);
    }
    for(var identity in WCIN.descriptors){var d=WCIN.descriptors[identity];
      if(d.mask_file){var vf=app.project.importFile(new ImportOptions(new File(d.mask_file))),vl=comp.layers.add(vf);vl.name='cinematic_partial_vignette_'+identity;vl.property('Position').setValue([O.width/2,O.height/2]);vl.property('Scale').setValue([O.width/960*100,O.height/540*100]);vl.moveBefore(view);
        var op=vl.property('Opacity');for(var fi=0;fi<WCIN.samples.length;fi++){var f=WCIN.samples[fi];op.setValueAtTime(f.at,f.state===identity?f.vignette_opacity*100:0);}whold(op);if(typeof cameraRig!=='undefined')vl.setParentWithJump(cameraRig);
      }
      if(d.panel){var p=d.panel,box=p.rect,c=[(box[0]+box[2])*O.width/2,(box[1]+box[3])*O.height/2],w=(box[2]-box[0])*O.width,h=(box[3]-box[1])*O.height;
        var panel=comp.layers.addShape();panel.name='cinematic_information_panel_'+identity;var contents=panel.property('Contents').addProperty('ADBE Vector Group').property('Contents');var rect=contents.addProperty('ADBE Vector Shape - Rect');rect.property('ADBE Vector Rect Size').setValue([w,h]);rect.property('ADBE Vector Rect Position').setValue(c);rect.property('ADBE Vector Rect Roundness').setValue(12);var fill=contents.addProperty('ADBE Vector Graphic - Fill');fill.property('Color').setValue([16/255,28/255,43/255]);fill.property('Opacity').setValue(76);var stroke=contents.addProperty('ADBE Vector Graphic - Stroke');stroke.property('Color').setValue([215/255,186/255,115/255]);stroke.property('Stroke Width').setValue(2);cinePose(panel,identity,c);
        var text=comp.layers.addText(p.lines.join('\\r'));text.name='cinematic_information_text_'+identity;var prop=text.property('Source Text'),doc=prop.value;doc.font='NotoSansKR-Bold';doc.fontSize=p.font_size;doc.applyFill=true;doc.fillColor=[1,242/255,202/255];doc.applyStroke=false;doc.justification=ParagraphJustification.CENTER_JUSTIFY;doc.autoLeading=false;doc.leading=p.font_size*1.3;prop.setValue(doc);var bounds=text.sourceRectAtTime(0,false);text.property('Anchor Point').setValue([bounds.left+bounds.width/2,bounds.top+bounds.height/2]);text.property('Position').setValue(c);var op=text.property('Opacity'),sc=text.property('Scale');for(var fi=0;fi<WCIN.samples.length;fi++){var f=WCIN.samples[fi];op.setValueAtTime(f.at,f.state===identity?f.panel_opacity*100:0);sc.setValueAtTime(f.at,[f.panel_scale*100,f.panel_scale*100]);}whold(op);whold(sc);if(typeof cameraRig!=='undefined')text.setParentWithJump(cameraRig);
      }
    }
'''


def signature():
 import hashlib
 root=Path(__file__).parent
 names=('wuxia_cinematic_runtime.py','wuxia_native_timeline.py','wuxia_motion_review.py','wuxia_transition.py','wuxia_motion.py','ae_flat_scene.py','ae_scene_animation.py')
 return hashlib.sha256(b''.join((root/n).read_bytes() for n in names)).hexdigest()
