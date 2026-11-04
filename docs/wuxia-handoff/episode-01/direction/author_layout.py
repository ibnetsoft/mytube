"""Authored placements after inspecting source frames; no automatic face guesses."""
import hashlib,json
from pathlib import Path
P=Path(__file__).resolve().parent.parent
D=P/'direction'
def aid(n,k):return f'E01_S{n:02d}_STATE_{k:02d}'
notes={
1:'서진의 이중 지게와 무사 신발 대비. 배경 문 형태의 세부는 역방향 편집에서 연속 매치하지 않는다.',
2:'서진 왼쪽, 서리 오른쪽. 장부·동전·손과 두 얼굴을 말풍선에서 보호한다.',
3:'도겸 왼쪽, 서진 오른쪽. 동전 보따리·물주머니·어깨 자국을 순서대로 읽힌다.',
4:'동일 자세 반복을 발 상세 고정 크롭으로 구별. 지게를 멘 가중 연습으로 읽히는 원화이며 손 떨림은 정지 상태선으로 표시된다.',
5:'장호가 봉함을 얻기 전 허리에 봉함이 없는 상태. 모집장 글은 원화에 구워 넣지 않았다.',
6:'도겸·서진 뒤쪽, 무사 앞쪽. 넘어질 듯한 무사와 서진의 작은 보폭을 하드 컷으로 대비.',
7:'실제 벽화 상세 원화로 교체. 마지막 발 위치는 동적 줌 없이 고정 상세 크롭.',
8:'시신 손의 끊어진 끈은 별도 접사로 수정. 관찰 타이포는 대사와 다른 컷에서만 표시.',
9:'우두머리 1+일반 5. 수레 적재물 보정. 순서 1→3→2로 수레 준비 뒤 봉함을 잡는다.',
10:'순서 2→1→3. 달려듦→문을 받침→석상 반응. 검의 파손 순간은 국소 섬광/SFX로 표현.',
11:'일반 석상만 전진하도록 수정. 도겸 자리 바닥에 실제 돌검이 박힌 결과 컷. 우두머리는 아직 정지.',
12:'석상이 가까운 서진을 지나가고 먼 진기 쪽으로 향함. 우두머리 정지. 관찰 화살표는 원화 바닥의 손가락 흔적.',
13:'첫 컷은 서진·도겸 고정 크롭으로 우두머리의 조기 움직임을 화면 밖에 둔다. 진기 뒤 우두머리 반응.',
14:'측벽 파손→통로→수레 손잡이. 마지막 컷은 도겸 표정에 시선을 두고, 원경 우두머리 준비 자세의 거리 변화는 다음 컷 사이에서 생략한다.',
15:'다리 압박→무사들 탈출→소매 대치. 두 번째는 오른쪽 무사들로 고정 크롭해 서진의 선행 입가 상처를 제외.',
16:'입가 상처 유지. 문 너머 장호의 봉함. 마지막은 걸쇠와 손 상세. 잠금장치 좌우를 역방향 매치하지 않는다.',
17:'기운이 사라진 뒤 일반 석상은 멈칫한다. 도겸은 다리를 누르고 서진은 우두머리 발옆에 몸을 낮춘다.',
18:'서진 시선과 벽 틈, 도겸 구조 결심. 우두머리는 준비 자세로 원경에 두며 다음 컷에서 접근 거리 생략.',
19:'다리 해방 상세를 반드시 유지. 중복 우두머리 제거, 가까운 한 석상의 팔·발로 수레 파괴를 연결.',
20:'왼쪽 옆구리 상처·떨어진 물주머니 유지. 돌검과 도겸 사이의 단절. 마지막 중복 우두머리 제거.',
21:'바닥 검→손목 틈→발끝. 대사·UI 없이 관찰 세부만 하드 컷.',
22:'진화록 글은 손목 주관 컷에만 별도 청백 레이어. 타인 시점에는 글자 없음.',
23:'관절이 닫힌 뒤 실패. 오른손 상처, 반 토막 단도 길이 보정. 성공 섬광·레벨업 표시 금지.',
24:'옆구리와 손 상처 지속. 부러진 단도를 손잡이로 쥠. 도겸은 화면 밖 왼쪽에서 말한다.',
25:'바닥 두드림 접사와 발 고정. 부러진 단도의 형태 유지, 새 무공 오라 없음.',
26:'파고듦 컷의 중복 팔/단도를 수정. 마지막은 관절 접촉 전. 결과·승리·회복을 보이지 않고 암전.'}
layouts={}
for n in range(1,27):
 for p in sorted((P/'images').glob(f'E01_S{n:02d}_STATE_*.png')):
  layouts[p.stem]={'review':'visually_reviewed_with_authored_framing','sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
                   'review_note':notes[n],'dialogue_slots':{}}
def speech(n,k,who,center,tail,size=(.34,.23),off=False):
 layouts[aid(n,k)]['dialogue_slots'][who]={'center':list(center),'tail':list(tail),'size':list(size),
  'offscreen_speaker':off,'placement_review':'authored_from_visible_frame',
  'protect':'faces, eyes, blade tip, wrist joint, hand contact, narrative props'}
speech(1,3,'guard',(.29,.19),(.20,.43))
for k in (1,2,3):
 speech(2,k,'seojin',(.53,.55),(.33,.40),(.31,.23))
 speech(2,k,'clerk',(.53,.55),(.82,.40),(.31,.23))
speech(3,2,'dogyeom',(.51,.13),(.28,.35),(.30,.21))
speech(3,3,'seojin',(.51,.13),(.73,.39),(.29,.17))
speech(5,2,'clerk',(.81,.16),(.90,.45),(.32,.23))
speech(6,3,'dogyeom',(.23,.15),(.13,.45),(.31,.20))
speech(6,3,'seojin',(.29,.16),(.31,.51),(.38,.25))
speech(7,1,'guard',(.22,.13),(.205,.36),(.31,.20))
speech(8,1,'seojin',(.30,.74),(.14,.44),(.36,.22))
speech(8,3,'jangho',(.66,.76),(.46,.45),(.36,.22))
speech(8,3,'seojin',(.64,.76),(.15,.44),(.45,.24))
speech(9,2,'jangho',(.25,.20),(.72,.35),(.37,.23))
speech(10,2,'seojin',(.52,.13),(.35,.45),(.33,.20))
speech(10,3,'dogyeom',(.48,.18),(.61,.57),(.30,.20))
speech(11,1,'jangho',(.22,.16),(.13,.42),(.32,.22))
speech(11,3,'dogyeom',(.78,.19),(.43,.64),(.30,.19))
speech(13,1,'seojin',(.21,.14),(.36,.40),(.36,.22))
speech(13,2,'jangho',(.80,.18),(.40,.42),(.31,.20))
speech(14,2,'dogyeom',(.27,.18),(0,.48),(.34,.22),True)
speech(15,3,'seojin',(.49,.77),(.27,.53),(.34,.21))
speech(15,3,'jangho',(.53,.77),(.74,.35),(.34,.21))
speech(16,1,'seojin',(.60,.15),(.58,.55),(.37,.23))
speech(16,2,'jangho',(.46,.16),(.72,.36),(.38,.22))
speech(18,1,'dogyeom',(.79,.16),(.62,.66),(.33,.22))
speech(19,1,'seojin',(.40,.17),(.41,.47),(.27,.19))
speech(19,4,'dogyeom',(.30,.17),(.23,.57),(.32,.22))
speech(19,4,'seojin',(.52,.16),(.46,.51),(.32,.22))
speech(20,3,'dogyeom',(.72,.15),(.14,.36),(.36,.22))
speech(22,3,'dogyeom',(.27,.14),(.16,.43),(.37,.22))
speech(24,1,'dogyeom',(.23,.13),(0,.50),(.40,.23),True)
speech(25,3,'seojin',(.79,.14),(.67,.40),(.24,.17))
speech(26,1,'dogyeom',(.29,.15),(0,.5),(.27,.19),True)
types={
(4,3):((.82,.60),(.25,.19)),(8,2):((.78,.22),(.25,.20)),
(9,2):((.39,.85),(.23,.16)),(10,1):((.82,.49),(.24,.22)),
(11,3):((.27,.78),(.28,.20)),(13,3):((.80,.72),(.30,.22)),
(14,3):((.82,.83),(.25,.19)),(16,3):((.52,.84),(.26,.20)),
(19,4):((.79,.72),(.28,.22)),(20,2):((.73,.36),(.23,.19)),
(22,2):((.40,.16),(.61,.16)),(23,2):((.80,.16),(.23,.18)),
(25,2):((.18,.74),(.26,.19)),(26,2):((.25,.18),(.31,.16)),
(26,3):((.48,.18),(.42,.22))}
for (n,k),(center,size) in types.items():
 layouts[aid(n,k)]['typography_slot']={'center':list(center),'size':list(size),'placement_review':'authored_from_visible_frame'}
(D/'visual-layout.json').write_text(json.dumps(layouts,ensure_ascii=False,indent=2),encoding='utf-8')
(D/'visual-reviews.json').write_text(json.dumps({'method':'actual full originals and scene contact sheets inspected; no automatic approval from file existence',
 'scope':'art and authored framing; final AE playback not yet asserted','scene_notes':notes},ensure_ascii=False,indent=2),encoding='utf-8')
