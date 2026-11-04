"""Inventory actual originals and compile local storyboard/direction artifacts.

No database writes, image synthesis, audio generation or rendering happens here.
"""
import hashlib
import html
import json
from pathlib import Path

P = Path(__file__).resolve().parent.parent

def read(name):
    return json.loads((P / name).read_text(encoding='utf-8'))

def write(name, value):
    (P / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')

def inventory():
    from PIL import Image
    jobs = read('image-generation-jobs.json')
    rows = []
    for j in jobs:
        path = P / 'images' / (j['asset_id'] + '.png')
        row = {k:j[k] for k in ('asset_id','scene_id','state_index','description')}
        row.update(file='images/' + path.name, exists=path.is_file())
        if path.is_file():
            with Image.open(path) as im:
                im.verify()
            with Image.open(path) as im:
                row.update(width=im.width,height=im.height,mode=im.mode)
            row.update(bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                       technical_check='decodable PNG',visual_review='not_inferred_from_file_existence')
        rows.append(row)
    write('image-inventory.json',rows)
    return rows

def gallery(rows):
    source = read('script-final.json')
    cards = []
    reviews_path = P / 'direction' / 'visual-reviews.json'
    reviews = json.loads(reviews_path.read_text(encoding='utf-8')) if reviews_path.exists() else {}
    for s in source['scenes']:
        assets = [r for r in rows if r['scene_id']==s['id']]
        media = ''.join('<figure><a href="../'+r['file']+'" target="_blank"><img loading="lazy" src="../'+r['file']+'" alt="'+html.escape(r['description'])+'"></a><figcaption>'+html.escape(r['asset_id']+' · '+r['description'])+'</figcaption></figure>' if r['exists'] else '<div class="missing">'+html.escape(r['asset_id'])+' · 生成中</div>' for r in assets)
        words = ''.join('<p><b>'+html.escape(b['kind']+' '+b.get('speaker',''))+'</b> '+html.escape(b['text'])+'</p>' for b in s['blocks'])
        text = ' / '.join(x['text'] for x in s['screen_text']) or '없음'
        cards.append('<section id="'+s['id']+'"><h2>'+html.escape(s['id']+' · '+s['location'])+'</h2><div class="grid">'+media+'</div><details><summary>대본·장면 텍스트·AE 연출</summary>'+words+'<p><b>타이포그래피</b> '+html.escape(text)+'</p><p><b>AE</b> '+html.escape(s['ae'])+'</p></details></section>')
    chars = ''.join('<figure><a href="../character-sheets/'+c+'-v1.png"><img src="../character-sheets/'+c+'-v1.png"><figcaption>'+n+'</figcaption></a></figure>' for c,n in [('seojin','서진'),('dogyeom','도겸'),('jangho','장호'),('clerk','중개소 서리'),('guard','철산문 무사')])
    count = sum(r['exists'] for r in rows)
    page = '''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>버려진 짐꾼 · 원화와 연출</title><style>
body{margin:0;background:#111821;color:#edf2f5;font:15px/1.7 system-ui,sans-serif}main{max-width:1500px;margin:auto;padding:32px}h1{font-size:30px}h2{font-size:20px}section{margin:36px 0;border-top:1px solid #34404c;padding-top:18px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:14px}figure{margin:0}img{width:100%;height:auto;border-radius:5px;background:#1e2936}figcaption{font-size:12px;color:#aebdca}details{background:#1b2632;padding:14px;margin-top:16px;border-radius:6px}summary{cursor:pointer;color:#8ee5ec}b{color:#9fd6dc}a{color:inherit}.missing{padding:50px;background:#283340}header{position:sticky;top:0;background:#111821ef;padding:8px 0;backdrop-filter:blur(5px)}small{color:#9aaebc}</style><main><header><h1>1화 「버려진 짐꾼」</h1><p>원화 '''+str(count)+''' / 79 · 영상클립 0 · 내레이션 원문 자막 없음</p><small>원화·연출 검토용 보드. 이미지를 누르면 원본을 엽니다. 실제 녹음 전 시간은 확정하지 않습니다.</small></header><section><h2>인물 상세 기준</h2><div class="grid">'''+chars+'''</div></section>'''+''.join(cards)+'''</main></html>'''
    page=page.replace('</header>','<p><a href="motion-preview.html">▶ 장면 연출 미리보기</a> · <a href="../DELIVERY.txt">제작 패키지 안내</a></p></header>')
    (P / 'direction' / 'storyboard.html').write_text(page,encoding='utf-8')

if __name__ == '__main__':
    rows = inventory()
    gallery(rows)
    summary={'expected_still_states':len(rows),'actual_still_images':sum(x['exists'] for x in rows),
             'character_sheets':sum((P/'character-sheets'/(x+'-v1.png')).is_file() for x in ['seojin','dogyeom','jangho','clerk','guard']),
             'image_generation_complete':all(x['exists'] for x in rows),
             'art_and_direction_source_package_complete':all(x['exists'] for x in rows) and (P/'direction'/'source-verification.json').is_file(),
             'motion_preview':'direction/motion-preview.html','editable_text_layers':51,
             'audio_sync_finalized':False,'ae_execution_verified':False,
             'user_web_registered':(P/'packaging'/'registration-receipt.json').is_file(),
             'topic_id':json.loads((P/'packaging'/'registration-receipt.json').read_text(encoding='utf-8')).get('topic_id') if (P/'packaging'/'registration-receipt.json').is_file() else None,
             'ae_rendered':False}
    write('direction/package-status.json',summary)
    print(json.dumps(summary))
