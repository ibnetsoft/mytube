import sys
from pathlib import Path
from PIL import Image
root=Path(__file__).resolve().parent
sys.path.insert(0,str(root.parents[1]))
from services.comic_render_service import ComicFrames,LAYOUTS
font=str(root.parents[1]/'auth-web/public/fonts/NanumSquareExtraBold.ttf')
cards=[]
labels=['좌우 2컷','전체 1컷','정규 격자 2×2','인셋','정규 격자 2×3','비대칭','가로 와이드','세로 롱','대각선','스플래시','양면 펼침','테두리 없음','블리드','연속 동작','대응·평행']
for (name,rects),label in zip(LAYOUTS.items(),labels):
    imgs=[str(root/'images'/f'scene_{i+1:02}.png') for i in range(len(rects))]
    f=ComicFrames(imgs,[5]*len(imgs),[],{'comic':{'version':1,'mode':'comic','layout':name}},(640,360),font)
    Image.fromarray(f.page(0,0)).save(root/'v3'/f'layout_{name}.png');f.close()
    cards.append(f'<figure><img src="layout_{name}.png"><figcaption>{label}</figcaption></figure>')
(root/'v3/layouts.html').write_text('<!doctype html><meta charset="utf-8"><title>무빙툰 컷 배치</title><style>body{background:#171916;color:#eee;font:18px sans-serif;padding:24px}main{display:grid;grid-template-columns:repeat(2,1fr);gap:20px}figure{margin:0}img{width:100%}figcaption{padding:10px}a{color:#ddc79e}</style><h1>컷 배치 샘플</h1><p>배치 비교를 위해 같은 테스트 그림을 재사용했습니다. 경계 돌파형은 별도 투명 인물 전경이 필요합니다.</p><a href="./">영상으로 돌아가기</a><main>'+''.join(cards)+'</main>',encoding='utf8')
