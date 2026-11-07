# 1·2·3화 충격 연출 품질 기록
기존 대본·확정 녹음·원화·입모양을 보존했다. 실제 원화 검수와 전체 동결 프레임 검사를 수행했다. 웹 재생 및 AE 출력 검증은 별도 확인서로 구분한다.
검증된 충격은 짧은 구간만 원화와 입모양을 함께 이동시키며, 글자는 고정한다. 모든 머리·문자 보호 영역을 검사한다.
1화 S11 효과음은 얼굴 보호를 위해 하단 여백으로 옮겼다. 1화 대본/녹음 사이의 비발화 말줄임표만 구분하도록 검증했으며 녹음의 생성 지문과 시간표는 수정하지 않았다.

## 1화 E01_S09_STATE_02
- 사람 얼굴 3개와 배경 석상 얼굴 5개가 보입니다.
- 대사의 여섯 석상 중 이 이미지에서 얼굴이 보이는 석상은 5개입니다.
- 봉함 아래 돌못의 이탈은 이 정지 이미지에서 확인할 수 없습니다.
- 제외: focus_glow — 중심은 봉함 왼쪽과 장호의 손 부근에 위치합니다. 봉함 밑의 가느다란 돌못이나 그것이 빠지는 모습은 실제 이미지에서 확인되지 않아, 이 발광으로 해당 동작을 정확히 강조할 수 없습니다.

## 1화 E01_S10_STATE_01
- The sword-breaking narration is not depicted in this still.
- The statues face forward; their narrated head turn is not established by this still.

## 1화 E01_S11_STATE_03
- 이미지는 검이 바닥에 박힌 직후의 상태를 보여주며, 정지 이미지에서 충돌 순간 자체는 확인할 수 없습니다.
- 제공된 효과 중심 [0.27, 0.72]과 반경 0.13은 실제 바닥 접촉점보다 오른쪽으로 치우치고 범위가 넓습니다.

## 1화 E01_S13_STATE_02
- 배경 석상 다섯의 보이는 얼굴을 포함했습니다.
- 원래 발광 중심 [0.58,0.67]은 검신의 주요 발광 영역과 어긋납니다.

## 1화 E01_S14_STATE_01
- 보이는 얼굴은 왼쪽 석상 투구 아래의 얼굴 한 개입니다.
- 제공된 효과 중심 [0.72, 0.48]은 실제 검 끝과 벽의 접점보다 위쪽입니다.
- 이미지는 이미 벽이 무너져 통로가 드러난 상태입니다.

## 1화 E01_S15_STATE_03
- 이 이미지는 소매를 붙잡는 대치 상황에는 부합하지만, 입가를 때리는 순간의 시각적 근거는 제공하지 않습니다.
- 제외: impact_shake — 대사의 검 손잡이 타격과 달리 실제 이미지에는 서진이 장호의 옷을 붙잡은 모습만 보입니다. 입가에 닿는 검 손잡이나 타격 접촉은 보이지 않으며, 지정 중심은 배경 계단 위쪽에 있어 해당 타격의 위치와도 맞지 않습니다.

## 1화 E01_S16_STATE_03

## 1화 E01_S19_STATE_04
- Both supplied effect centers are displaced from the visible sword–cart contact; corrected centers are provided.
- Face boxes include four visible background stone-warrior faces and both foreground human faces.

## 1화 E01_S20_STATE_02
- 얼굴 윗부분이 원본 상단 밖으로 잘려 있으며, 얼굴 상자는 실제 보이는 부분만 포함합니다.

## 1화 E01_S22_STATE_02
- The image shows stone hands gripping a raised stone sword; no actual faces or floating letters are visible.

## 1화 E01_S23_STATE_02
- 배경 석상 다섯 개의 노출된 얼굴을 포함했습니다. 얼굴 세부 경계는 배경 흐림으로 인해 근사치입니다.

## 1화 E01_S26_STATE_02
- Four small background statue faces are included alongside the foreground human face.
- The image shows floor impact and airborne debris, but does not clearly establish debris contacting the shoulder.
- Face boxes and suggested effect regions are source-image observations; rendered cropping, shake safety, audio timing, and execution are unverified.
- 제외: speedline_burst — Lowering the shoulder supports brief directional lines, but the supplied region overlaps the visible face. Suggested placement confines lines to the left shoulder and sleeve, clear of facial features; no explosive particles.
- 제외: impact_shake — The sword striking the floor supports a brief impact shake. The supplied center at [0.72, 0.74] misses the visible contact: the blade meets broken flooring at the lower left. Any localized flash or debris belongs at that floor contact.

## 2화 E02_S01_STATE_01
- The second face box conservatively unions the five small background statue faces, excluding their headgear.
- The close foreground framing does not clearly establish the guardian's anatomical right wrist or confirm that its other wrist is undamaged.
- The sword described as immediately behind Seojin's feet is outside this frame.

## 2화 E02_S02_STATE_01
- The still shows the blade lodged against stone and blood on the gripping hand; withdrawal, falling metal dust, the subsequent floor strike, and the torso impact described in the speech are not visible in this image.
- The five small background statue faces are included; their facial boundaries are approximate at this resolution.
- 제외: impact_flash — A brief localized flash suits the blade bending against the stone wrist. The supplied center [0.55, 0.55] lies over the human hand and guard, and radius 0.12 spreads beyond the contact. Place the flash at the blade–stone junction and keep it clear of the face.

## 2화 E02_S07_STATE_02
- 전경 인물 두 명과 큰 석상에서 보이는 얼굴을 포함했습니다. 배경 수호상들은 투구 안에 얼굴 윤곽이 드러나지 않아 얼굴 상자를 추가하지 않았습니다.
- 이미지에서는 두 사람이 같은 고리를 잡고 판을 세운 상태와 아래 통로가 보입니다. 홈을 긁거나 걸쇠를 미는 선행 동작은 이 정지 이미지에서 확인할 수 없습니다.
- 제외: focus_glow — 제공된 중심은 판 아래의 열린 통로보다 오른쪽 인물의 손과 손목에 가깝습니다. '판 아래가 벌어졌습니다.'를 강조하려면 실제 사각 개구부 중심인 약 [0.47, 0.85]로 옮기고 반경을 약 0.08로 줄이는 편이 적절합니다.

## 2화 E02_S09_STATE_01
- 서술의 홈 입구 타격과 달리 그림에서는 돌검이 열린 점검구에서 오른쪽으로 떨어진 바닥에 박혀 있습니다.
- 정지 이미지에서 파편은 확인되지만 발목까지 튀는 움직임이나 서진이 도겸의 다리를 끌어 모으는 동작은 확인할 수 없습니다.

## 2화 E02_S11_STATE_02
- 이미지는 돌검이 이미 바닥에 놓인 정지 상태를 보여주며, 충돌 순간 자체는 확인할 수 없다.
- 전경 인물의 오른손은 기둥이 아니라 기둥 옆 바닥을 짚고 있어 제공된 설명과 차이가 있다.
- 배경 수호병은 투구 아래 드러난 작은 얼굴 부분만 포함했다.

## 2화 E02_S13_STATE_01
- 실제로 보이는 얼굴은 두 사람입니다. 석상 수호자들의 얼굴은 투구로 가려져 있어 얼굴 박스를 추가하지 않았습니다.
- 정지 이미지에서는 나무껍질이 벗겨지는 순간이나 받침이 빠지는 동작을 확인할 수 없습니다.
- 제외: debris_burst — 제공된 중심 [0.5, 0.55]는 전경 인물의 머리카락 부근이며 나무 접촉점과 떨어져 있습니다. 나무껍질이 벗겨지는 서술에 맞춰 왼쪽 아래 나무 받침 표면에 작은 나무 부스러기만 국소적으로 배치해야 합니다.

## 2화 E02_S14_STATE_02
- 대사의 칼끝이 기둥을 긁는 접촉은 원화에 보이지 않습니다. 우두머리의 검은 기둥에서 떨어져 있어 이 이미지로 해당 접촉 효과를 정당화할 수 없습니다.
- 배경 수호자 네 명의 작은 노출 얼굴도 포함했습니다.
- 제외: speedline_burst — 지정 중심은 두 인물 사이의 빈 바닥이며, 손과 기둥의 접촉점이나 발의 정지 지점과 일치하지 않습니다. 연결 문장은 스스로 멈춰 선 순간이고 원화도 기둥을 짚은 정지 자세이므로, 이 위치의 방사형 속도선은 동작과 접촉 근거가 약합니다.

## 2화 E02_S18_STATE_02
- 청록색 천 조각은 돌검 끝에 걸린 모습이 아니라 검 끝과 떨어져 보이므로, 설명의 접촉 상태와 원화가 일치하지 않습니다.
- 전경 서진의 손은 기둥이 아니라 바닥을 짚고 있어 설명 및 발화의 기둥 접촉과 차이가 있습니다.
- 제외: speedline_burst — 제공된 중심 [0.5, 0.55]은 중앙 인물의 다리와 돌검 끝 부근으로, 오른쪽 청록색 옷의 찢긴 부분과 떨어져 있습니다. 옷이 찢기는 순간을 강조하려면 청록색 천의 파손 부위에 작은 방향성 속도선만 국한하는 편이 적절합니다. 실제 검과 천의 접촉은 이미지에서 확인되지 않습니다.

## 2화 E02_S21_STATE_02
- The overhead hatch appears metal, whereas the narration calls it a stone slab.
- The image shows both men crouching, but does not depict the ankle pull or Dokyeom pressing Seojin's head down.
- Face boxes describe the supplied still only; rendered crop safety, audio timing, and effect execution are not verified.

## 3화 E03_S08_STATE_02
- 전경 서진, 중앙 도겸, 외부 보초의 실제 보이는 얼굴 3개를 박스로 표시했다. 머리카락과 두건은 제외했다.
- 서진의 입술 출혈, 펼친 손바닥의 상처, 옆구리 혈흔과 반대 손의 단도가 보인다.
- 어깨에 닿는 검 손잡이나 벽에 충돌하는 순간은 보이지 않는다.
- 도겸의 천을 감은 다리 쪽 발이 바닥에 닿아 있어 비체중부하 상태는 명확하지 않다.
- 이 이미지 단독으로 이전 상태와의 구도·바닥·칼날 연속성을 검증할 수 없다.
- 제외: impact_shake — 실제 이미지는 서진이 벽 아래에 주저앉은 결과 상태이며, 검 손잡이와 어깨의 타격 접촉은 보이지 않는다. 지정 중심은 도겸의 손과 문기둥 사이로 어깨나 벽 충돌 지점에 맞지 않는다. 이 정지화만으로 해당 어깨 타격용 흔들림을 승인하기 어렵다.

## 3화 E03_S11_STATE_01
- 실제 보이는 얼굴은 세 명이며 머리카락, 두건, 상투를 제외해 얼굴 상자를 지정했다.
- 덧문은 이미 비스듬히 내려앉은 상태다. 정지화만으로 낙하 동작은 확인할 수 없다.
- 단도 손잡이는 덧문 하단 보강쇠 아래 바닥에 보이며 칼날은 명확하게 보이지 않는다.
- 도겸은 손을 벽 쪽으로 뻗고 있으며 서진의 소매를 잡는 동작은 이 이미지에 없다.
- 보초는 높은 바깥 발판에 서서 검을 들고 있다. 검이 덧문 틈으로 들어오는 동작은 이 이미지에 없다.

## 3화 E03_S12_STATE_03
- 실제 보이는 얼굴은 세 명이다.
- 덧문은 들린 상태이고 서진의 몸이 문 아래에 있어, 두 사람이 빠져나간 뒤 문이 내려앉는 인용문과 화면 상태가 다르다.
- 서진은 팔뚝 대신 손바닥으로 돌턱을 지지한다.
- 반대편 덧문 고정 접점과 눌린 단도는 보이지 않는다.
- 보초의 검은 허리에 남아 있다.
- 제외: impact_shake — 실제 그림은 보초가 덧문을 들어 올리고 서진이 통과하는 상태다. 인용문의 덧문 낙하와 바닥 충돌은 보이지 않아 이 이미지에 충돌 흔들림을 적용할 근거가 부족하다.
- 제외: debris_burst — 지정 중심은 서진의 노출된 어깨 부근이며 문과 돌의 충돌점이 아니다. 보이는 파손이나 낙하 충돌이 없어 파편 분출은 부적절하며, 사람 어깨에 폭발성 입자를 추가해서는 안 된다.

## 3화 E03_S14_STATE_01
- 실제 보이는 얼굴은 서진과 도겸의 두 개다.
- 도겸은 서진의 옷깃 대신 나무를 짚고 있어 해당 서술과 다르다.
- 연청색 천은 목이 아니라 도겸의 오른쪽 무릎 아래에 보인다.
- 정지화는 충돌 후 자세를 보여 주므로 왼발을 헛디디는 동작 자체는 확인할 수 없다.
## 실제 AE 실행 경로 오류 확인

2026-11-07 실제 1화 작업 결과 26개가 무협 타임라인 합성 MP4가 아니라 원화 PNG 그대로 넘기기로 기록됐다. 구형 AE PC 실행 소스가 새 타임라인을 무시한 상태다. 세 작업을 `awaiting_worker_update` / disabled 상태로 보존했으며 원화·음성·입력·실패 증거는 유지한다. 실제 효과 렌더 완료로 판정하지 않는다. 서버 점유 계약 차단을 적용·검증했으며 갱신된 AE PC에서 복구 도구로 재개한다.

## 화면 검수 접근 상태

Mac 잠금으로 실제 화면 캡처가 차단되었다. Chrome는 확장 UI가 열린 상태로 자동 재생 제어도 차단했다. 사용자에게 잠금 해제와 팝업 닫기를 요청했으며, 실제 최종 웹 재생 확인으로 표시하지 않는다.
