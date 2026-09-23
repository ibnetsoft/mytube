import json
from pathlib import Path
root=Path(__file__).resolve().parent
out=root/'v2';out.mkdir(exist_ok=True)
scenes=json.loads((root/'source.json').read_text(encoding='utf8'))['pregenerated_structure']['scenes'][:10]
# All speech below is explicitly adapted for this local positioning test.
speech={
3:[('백운','정신 차려! 조금만 더 버텨!','shout',[.57,.42,.38],[.53,.28])],
4:[('백운','괜찮다. 내가 곁에 있다.','whisper',[.06,.52,.52],[.94,.17])],
5:[('백운','사부님… 마지막에 무엇을 남기신 겁니까?','speech',[.04,.53,.59],[.58,.34])],
7:[('백운','내 무공을 잃더라도… 이 아이를 살린다.','speech',[.08,.60,.68],[.96,.48])],
8:[('백운','죽은 자가 보낸 협박장이라니…','speech',[.06,.32,.48],[.64,.24])],
9:[('백운','모두 왼손 검객… 우연이 아니야.','speech',[.53,.46,.43],[.49,.31])],
10:[('제자','사형… 검을… 멈추세요…','whisper',[.05,.67,.48],[.33,.52]),
    ('백운','그 검결을… 네가 어떻게?','speech',[.04,.08,.50],[.66,.30])],
}
events=[]
for i,s in enumerate(scenes,1):
    narration_y=.77 if i in [4,8] else .04
    if i==10:narration_y=.89
    # On the final two-speaker panel, keep narration short and away from both faces.
    text=s['narration'] if i!=10 else '그때, 제자의 입술이 움직였다.'
    events.append({'id':f'{i:02}-n','scene':i,'kind':'narration','speaker':'나레이터','text':text,
        'placement':[.05,narration_y,.90],'rate':1})
    for j,(speaker,text,style,place,target) in enumerate(speech.get(i,[])):
        events.append({'id':f'{i:02}-d{j}','scene':i,'kind':'dialogue','speaker':speaker,'text':text,
            'style':style,'placement':place,'target':target,'rate':-1 if speaker=='백운' else 0,
            'adapted_for_test':True})
(out/'events.json').write_text(json.dumps(events,ensure_ascii=False,indent=2),encoding='utf8')
print('prepared',len(events),'events')
