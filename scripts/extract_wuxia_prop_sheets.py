"""Crop approved illustrations without redesigning any prop pixels."""
import json,hashlib
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'docs/wuxia-props';R=D/'references'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
font=ImageFont.truetype(str(ROOT/'auth-web/public/fonts/NotoSansKR-Bold.ttf'),24)
records=[]
for who,title,box in [('seojin','서진 · 단검 / 칼집 고정 참조',(899,12,1043,318)),('jangho','장호 · 검 / 칼집 고정 참조',(861,32,1007,583))]:
 source=R/f'{who}-approved-character-reference-v1.png'
 with Image.open(source) as im:crop=im.crop(box).convert('RGB')
 raw=R/f'{who}-weapon-crop-v1.png';crop.save(raw)
 # Aspect preserved; original crop also kept separately for exact-pixel checking.
 scaled=crop.resize((crop.width*2,crop.height*2),Image.Resampling.LANCZOS)
 sheet=Image.new('RGB',(620,scaled.height+160),'#f5f5f7');draw=ImageDraw.Draw(sheet)
 draw.text((24,18),title,font=font,fill='#202735')
 sheet.paste(scaled,((620-scaled.width)//2,76))
 draw.text((24,sheet.height-65),'승인 원화 추출 · 재설계 없음',font=font,fill='#404650')
 path=R/f'{who}-weapon-sheet-v1.png';sheet.save(path)
 records.append(dict(character_id=who,path=str(path.relative_to(ROOT)),sha256=sha(path),crop_path=str(raw.relative_to(ROOT)),crop_sha256=sha(raw),source_path=str(source.relative_to(ROOT)),source_sha256=sha(source),crop_box=list(box),method='exact_crop_then_uniform_2x_layout',prop_ids=['SEJ_DAGGER_01','SEJ_SHEATH_01'] if who=='seojin' else ['JAN_SWORD_01','JAN_SCABBARD_01']))
manifest=json.loads((D/'reference-manifest.json').read_text())
manifest['weapon_sheets']=records
manifest['new_weapon_sheet_status']='approved_source_crops_complete_no_regeneration'
manifest['review_notes'].append('사용자 요청에 따라 승인 원화 소품 크롭이 형태의 최종 기준이다. 이전 텍스트에서 새로 제안한 치수·리벳 위치보다 실제 추출 이미지가 우선한다. 보이지 않는 측면/뒷면은 새로 그린 것으로 간주하지 않는다.')
(D/'reference-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
print(json.dumps(records,ensure_ascii=False,indent=2))
