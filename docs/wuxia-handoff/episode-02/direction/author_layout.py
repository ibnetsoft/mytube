import json
from pathlib import Path
P=Path(__file__).resolve().parent.parent
def aid(n,i):return f'E02_S{n:02d}_STATE_{i:02d}'
layout={aid(n,i):{'review':'reviewed_with_quality_notes','review_basis':'Actual stored source/contact-board visual inspection; see quality-notes.md','dialogue_slots':{}} for n in range(1,25) for i in [1,2]}
def bubble(n,i,speaker,c,t,size=(.34,.22),off=False):
 layout[aid(n,i)]['dialogue_slots'][speaker]={'center':c,'size':size,'tail':t,'offscreen_speaker':off,'placement_review':'visually_authored'}
def typo(n,i,c,size=(.30,.18)):
 layout[aid(n,i)]['typography_slot']={'center':c,'size':size,'placement_review':'visually_authored'}
def crop(n,i,c):layout[aid(n,i)]['static_crop']=c
bubble(1,2,'seojin',[.18,.67],[.35,.48],(.31,.18))
bubble(2,2,'dogyeom',[.24,.15],[0,.50],off=True)
bubble(3,1,'dogyeom',[.18,.16],[.38,.42],(.29,.20))
bubble(5,2,'seojin',[.79,.15],[.69,.63],(.31,.24))
bubble(6,1,'dogyeom',[.55,.13],[.40,.34],(.31,.24))
bubble(7,2,'seojin',[.50,.11],[.65,.52],(.37,.18))
bubble(8,2,'seojin',[.50,.13],[.57,.48],(.35,.24))
crop(9,2,[.45,.15,1,.99]);bubble(9,2,'dogyeom',[.20,.13],[0,.45],off=True)
crop(10,1,[.28,.04,1,.76]);bubble(10,1,'dogyeom',[.76,.16],[.49,.42],(.35,.24))
bubble(11,1,'seojin',[.73,.15],[.73,.52],(.28,.18))
crop(11,2,[.30,.20,1,.90]);crop(12,1,[.40,.18,.92,.98]);crop(12,2,[.35,.15,1,.80])
crop(13,2,[.45,.15,.99,.85]);bubble(13,2,'dogyeom',[.21,.14],[0,.42],off=True)
bubble(14,2,'dogyeom',[.73,.14],[0,.65],off=True)
bubble(15,1,'dogyeom',[.52,.13],[.28,.47],(.37,.23))
bubble(15,2,'seojin',[.72,.14],[.66,.55],(.35,.23))
crop(16,1,[.43,.25,1,1])
bubble(16,1,'seojin',[.78,.14],[.83,.52],(.28,.18))
crop(19,2,[.25,0,1,1])
bubble(19,1,'dogyeom',[.78,.14],[.88,.73],(.34,.23))
bubble(20,2,'dogyeom',[.79,.20],[1,.65],(.34,.22),True)
bubble(21,1,'dogyeom',[.18,.15],[.25,.45],(.24,.18))
bubble(22,1,'seojin',[.53,.12],[.34,.43],(.33,.18))
bubble(22,1,'dogyeom',[.53,.12],[.70,.43],(.33,.18))
bubble(24,1,'guard',[.78,.16],[.67,0],(.38,.28),True)
for n,i,c in [(1,1,[.77,.17]),(2,1,[.77,.18]),(4,1,[.80,.22]),(6,2,[.82,.40]),(8,1,[.22,.13]),(9,1,[.70,.79]),(11,1,[.73,.83]),(13,1,[.84,.16]),(14,1,[.75,.84]),(17,2,[.84,.77]),(18,2,[.75,.14]),(20,2,[.20,.79]),(21,2,[.25,.12]),(23,2,[.52,.13])]:typo(n,i,c)
(P/'direction/visual-layout.json').write_text(json.dumps(layout,ensure_ascii=False,indent=2),encoding='utf8')
