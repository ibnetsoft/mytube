"""Coordinates only for the nine requested ORIGINAL scene images. No animation."""
import json,hashlib,math,sys
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1]
DIR=ROOT/'output/codex-local-console/mouth-data-nine-3373'
# Pixel anchors are measured from the actual source images, not model boxes.
# speaker, face rect, lip endpoints, nose tip, chin, orientation
MEASUREMENTS={
22:[('大五郎',[353,85,571,320],[437,258],[502,270],[489,239],[468,309],'three_quarter_right')],
23:[('お鈴',[1005,231,1337,613],[1118,529],[1164,540],[1134,489],[1158,603],'three_quarter_left')],
24:[('大五郎',[562,108,858,478],[655,386],[758,406],[740,368],[708,470],'three_quarter_right')],
25:[('大五郎',[402,130,608,392],[514,325],[562,341],[579,303],[513,383],'three_quarter_right'),
    ('お鈴',[1281,230,1475,446],[1358,389],[1400,382],[1350,365],[1391,438],'three_quarter_left')],
30:[('仙太郎',[354,120,552,403],[419,332],[486,334],[463,296],[454,395],'frontal'),
    ('次郎',[973,149,1150,415],[1037,358],[1086,357],[1061,320],[1060,409],'frontal')],
31:[('大五郎',[864,150,1059,389],[943,327],[1009,334],[995,305],[969,380],'three_quarter_right')],
32:[('仙太郎',[877,168,1079,407],[987,351],[1041,343],[1028,318],[1009,398],'three_quarter_right')],
33:[('次郎',[1101,149,1285,355],[1129,300],[1167,308],[1144,274],[1175,343],'three_quarter_left')],
34:[('仙太郎',[603,101,821,384],[679,311],[738,317],[721,271],[707,378],'three_quarter_right')],
}
assets={a['scene_number']:a for a in json.loads((DIR/'source-assets.json').read_text(encoding='utf8'))}
OPEN_BOUNDS={(25,'お鈴'):[1350,372,1408,420],(30,'仙太郎'):[411,312,495,353],
             (30,'次郎'):[1029,342,1093,376],(33,'次郎'):[1121,285,1175,324],(34,'仙太郎'):[671,296,747,334]}
OPEN_CONTOURS={(25,'お鈴'):[[1358,389],[1378,381],[1400,379],[1402,386],[1395,403],[1380,413],[1369,410],[1358,399]],
 (30,'仙太郎'):[[419,324],[446,318],[478,323],[488,331],[485,341],[455,347],[428,342],[418,334]],
 (30,'次郎'):[[1039,350],[1061,348],[1085,351],[1088,358],[1083,367],[1060,371],[1040,367],[1036,359]],
 (33,'次郎'):[[1129,290],[1152,294],[1167,303],[1170,312],[1163,318],[1142,315],[1129,310],[1126,300]],
 (34,'仙太郎'):[[679,303],[705,304],[731,309],[739,316],[732,324],[708,325],[687,320],[678,313]]}
records=[];tiles=[]
font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',16)
for number,people in MEASUREMENTS.items():
 source=DIR/f'scene-{number:03}.png';image=Image.open(source).convert('RGB');w,h=image.size
 sha=hashlib.sha256(source.read_bytes()).hexdigest();asset=assets[number]
 assert Path(asset['metadata']['gcs_path']).stem.split('-')[-1]==sha
 speakers=[];annotated=image.copy();overlay=ImageDraw.Draw(annotated)
 for idx,(name,face,left,right,nose,chin,orientation) in enumerate(people):
  center=[(left[0]+right[0])/2,(left[1]+right[1])/2]
  width=math.dist(left,right);margin=6
  mouth=[min(left[0],right[0])-margin,min(left[1],right[1])-12,max(left[0],right[0])+margin,max(left[1],right[1])+12]
  mouth=OPEN_BOUNDS.get((number,name),mouth)
  def point(p):return [p[0]/w,p[1]/h]
  def box(b):return [b[0]/w,b[1]/h,b[2]/w,b[3]/h]
  fl,ft,fr,fb=face
  outline=[[fl+10,ft],[fr-10,ft],[fr,ft+(fb-ft)*.55],[fr-18,fb-18],chin,[fl+18,fb-30],[fl,ft+(fb-ft)*.55]]
  geometry={'version':2,'source_sha256':sha,'orientation':orientation,'pitch':'level',
   'mouth_visibility':'clear','render_policy':'animate','face_outline':[point(p) for p in outline],
   'landmarks':{'nose_tip':point(nose),'chin':point(chin),'lip_left':point(left),'lip_right':point(right),'lip_center':point(center)},
   'roll_degrees':math.degrees(math.atan2(right[1]-left[1],right[0]-left[0])),
   'original_mouth_pose':'open' if (number,name) in OPEN_BOUNDS else 'closed',
   'lip_contour':[point(p) for p in OPEN_CONTOURS[(number,name)]] if (number,name) in OPEN_CONTOURS else [point(left),point(center),point(right)],
   'protected_features':['moustache'] if name=='仙太郎' and number in (32,34) else [],
   'evidence':'Actual original-image lip contour measured in pixels; review overlays before animation.',
   'review':{'passed':False,'reason':'Awaiting actual annotated-crop inspection','proof':'annotated-face-crop-v4'}}
  s={'speaker':name,'status':'visible','confidence':1,'face_box':box(face),'mouth_box':box(mouth),'mouth_geometry':geometry,
    'pixel_coordinates':{'face_box':face,'mouth_box':mouth,'lip_left':left,'lip_right':right,'lip_center':center,'nose_tip':nose,'chin':chin},
    'reason':'Named speaker matched to original costume/face and saved dialogue assignment'}
  speakers.append(s)
  overlay.rectangle(mouth,outline='lime',width=2)
  for p in [left,right,center]:overlay.ellipse([p[0]-2,p[1]-2,p[0]+2,p[1]+2],fill='red')
  area=(max(0,fl-20),max(0,ft-20),min(w,fr+20),min(h,fb+20))
  crop=annotated.crop(area);crop.thumbnail((390,460))
  tile=Image.new('RGB',(420,500),'#181d26');tile.paste(crop,((420-crop.width)//2,35));draw=ImageDraw.Draw(tile)
  draw.text((12,8),f'Scene {number} speaker {idx+1} / {orientation}',font=font,fill='white');tiles.append(tile)
  # A high-resolution mouth-only view with source pixel coordinates.
  rect=(max(0,int(mouth[0]-20)),max(0,int(mouth[1]-25)),min(w,int(mouth[2]+20)),min(h,int(mouth[3]+25)))
  zoom=annotated.crop(rect).resize(((rect[2]-rect[0])*5,(rect[3]-rect[1])*5),Image.Resampling.NEAREST)
  zoom.save(DIR/f'scene-{number:03}-speaker-{idx+1}-mouth-zoom.png')
 record={'number':number,'image_id':asset['id'],'source_bucket':asset['metadata'].get('gcs_bucket',asset.get('storage_bucket')),
  'source_path':asset['metadata']['gcs_path'],'source_sha256':sha,'image_size':[w,h],'speakers':speakers,'state':'draft'}
 records.append(record);annotated.save(DIR/f'scene-{number:03}-coordinates.png')
(DIR/'mouth-data.json').write_text(json.dumps({'topic':3373,'project_id':'e9233112-f0d7-4b35-91bf-2f892844eb30','schema':'mouth_geometry/v2','scenes':records},ensure_ascii=False,indent=2),encoding='utf8')
sheet=Image.new('RGB',(420*4,500*3),'#0c1119')
for i,tile in enumerate(tiles):sheet.paste(tile,((i%4)*420,(i//4)*500))
sheet.save(DIR/'coordinate-review-sheet.png')
print('Nine scenes,',sum(len(r['speakers']) for r in records),'mouths; draft coordinates generated')
