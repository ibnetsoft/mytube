# 3화 제작 품질 기록

- 일본어 대본10664자,144씬.35분은 계획값이며 실제음성길이는 미측정.
- 원래 대본·씬순서·시간·합격 검수 원형 보존. 시각 프롬프트만 추가.
- 새 기본값 유지: 영상0씬, 고정효과구간없음, 제출 후 AE레이어.
- 대본단계 재사용안은 저장된 선택을 유지. 캐릭터 키/참고이미지는 후속 이미지 제작에서 고정.
- 기본 씬 이미지144장(1920×1080) 생성·저장·GCS 다운로드 해시·DB 재조회 완료. 음성·AE렌더·관리자게시·YouTube업로드는 미완료.
- 청취 품질: 95점, 기존 검수 critical_issues=0

## 실제 얼굴 구별 검사

- 전체 판정: 미통과. 주인공 三浦直人와 長谷川文子의 얼굴형·코·하관이 비슷해 독립된 3개 축의 구별 근거를 충분히 확보하지 못함. 나이·안경·주름만으로 합격 처리하지 않음.
- 여사장·고양이·동료·점원은 각 비교 검사 통과. 전체 합격으로 표시하지 않음.
- 사용자 방침에 따라 원본을 유지해 제작을 이어가며, face-review-results.json에 실제 판정을 보존함.

## 생성 이미지의 품질 메모

- 씬12는 인물 대신 계약서·유품 중심 구도.
- 씬23의 지폐 더미가 실제 48,000엔보다 과장되어 보임. 대본의 금전 장부는 유지되며 소품 표현 문제로 기록.
- 일부 그리드 경계에 가는 선이 있어 개별 씬 크롭 시 확인.

## 최종 이미지 검증

- 144개 고유 씬 번호, 36개 원본 그리드와 실제 육안검사 기록 확인.
- 모든 최종 PNG1920×1080, 파일 해시 및 GCS 재다운로드 해시, 현재 토픽 이미지 URL·해시 대조 완료.
- 대본 본문 SHA256: c46b8058a3f487cb09fc8dd29857950ca0abbc47d9fa90c4094f37644138136f (생성 후 본문 변경 없음).
- 주제 #3390 유저웹 등록. 본문·씬구조·제목·설명·썸네일 배경 및 미리보기 포함.
- 썸네일 편집기 최종 Save, 음성·최종 AE 영상, 관리자 게시·YouTube업로드는 별도.

## 씬별 실제 검토 메모

- 씬 1~4: Character identity, silver radio-cassette with blue-thread handle, entrance and barred counter match four source beats. / Small tag has indistinct generated marks; record as quality note, not factual readable text.
- 씬 5~8: Actual four panels inspected against narration and prompt: reference identities, modern clothing, pawnshop service window and blue-repaired radio handle retained. / Thin white grid seam present; crop individual panels, do not publish grid as scene.
- 씬 9~12: Actual four panels inspected against narration and prompt: reference identities, modern clothing, pawnshop service window and blue-repaired radio handle retained. / Scene12 is object-focused instead of a visible Naoto close-up; preserve as a quality/composition concern.
- 씬 13~16: Actual panels reviewed for identity, money/contract/radio custody and barred counter geometry. / Very similar static transaction views reflect the supplied first-18 short scenes; monitor pacing in final edit.
- 씬 17~20: Actual panels reviewed for identity, money/contract/radio custody and barred counter geometry. / Very similar static transaction views reflect the supplied first-18 short scenes; monitor pacing in final edit.
- 씬 21~24: Actual panels reviewed: proprietor and protagonist identities, radio in locked shelf, modern rented-room scene. / Scene23 cash stacks are visually oversized for 48,000 yen; monetary prop depiction is a recorded quality concern, not approved arithmetic evidence.
- 씬 25~28: Actual panels checked: first telephone listening at home, neutral phone close-up, unchanged gray jacket/face, no mother apparition.
- 씬 29~32: Actual panels reviewed: silent phone/operation, photographed demolished lot and modest apartment kettle; no mother apparition or radio at home before redemption.
- 씬 33~36: Actual panels checked: writing/listening notes, silent phone, old camera case in wardrobe, drawer with stored papers. No radio in rented home before redemption.
- 씬 37~40: Reviewed pawnshop document check, radio remaining in proprietor custody and transition to warehouse break with Ono. / Radio cabinet/control details vary from earlier frames; prop continuity concern retained. Later requests attach actual first radio image as a visual reference.
- 씬 41~44: Actual panels checked: warehouse lunch with Ono, stored family papers, and next telephone listening/note-taking at home. Work gloves removed for meal. No added mother apparition.
- 씬 45~48: Actual note-writing, marking/erasing mistaken memory and silent phone close-up inspected. Naoto identity and gray home jacket preserved. / Generated handwritten marks and rear-phone camera details are illustrative, not reliable readable/date evidence.
- 씬 49~52: Actual panels checked: call-history timeline marks, demolition papers/lot photograph and hospitalization envelope. No living mother apparition. / Some documents look more weathered than their 2024/2025 dates suggest; visual quality note, not a change to narration dates.
- 씬 53~56: Actual panels checked: death/admission papers, neighbor contact in records, notebook question and daytime call at warehouse. / Documents have ornamental/aged styling and illegible generated marks; narration is authoritative for dates and identities.
- 씬 57~60: Checked warehouse daytime call, evening listening and three note sheets; identity and modern setting retained. / Handwritten sheet numbering/marks are not reliable readable evidence; narration remains the source for dates and numbering.
- 씬 61~64: Actual Fumiko doorway greeting, diary consultation and Naoto note-taking checked. Gray civilian jacket and mulberry/ivory Fumiko outfit retained. / Formal Naoto/Fumiko face distinctness failure remains a quality concern; not overridden by scene inspection.
- 씬 65~68: Actual tea setting, diary discussion, blank/dated diary page and seated conversation inspected. Fumiko clothing and gray hair preserved. / Formal face-distinctness concern remains unchanged.
- 씬 69~72: Inspected Naoto/Fumiko visit, appointment-book discussion and historical mother photograph shown on a phone. Photograph is not a living mother apparition. / The formal source-reference Naoto/Fumiko distinctness concern remains recorded; this scene inspection does not override it.
- 씬 73~76: Checked arranging papers, correcting notes, photographing diary and leaving by demolished home lot. No mother apparition. / Lighting across visit varies; diary glyphs are illustrative, not validated readable records.
- 씬 77~80: Checked demolished lot exterior, fourth-night listening and personal messages/document comparison at home. No radio or mother apparition in rented room.
- 씬 81~84: Checked comparison of old work schedule, messages and red/blue annotation pages. No living mother or pawned radio added at home. / The two-colored-pencil hand pose is unusual; retain as a minor pose quality note.
- 씬 85~88: Actual rent/redemption funds check, single personal camera preparation and fifth-night phone listening inspected. Camera accessories kept in case; no radio returned prematurely.
- 씬 89~92: Checked repayment calculations, personal old work cards and camera-case preparation/phone messages. / Scene92 foreground equipment may read as an extra camera body; keep as a prop-count quality concern. Story establishes only one camera body for sale.
- 씬 93~96: Inspected messages with Fumiko, next pawnshop visit and confirming unchanged redemption terms. Radio stays inside proprietor side; no early return.
- 씬 97~100: Inspected fixed cat/proprietor/key motif, coworker message, separating spare key at home and taking personal camera case toward resale shop. Identity/wardrobe and prop custody retained.
- 씬 101~104: Actual modern camera-resale shop, clerk inspecting equipment, valuation discussion and Naoto hesitation reviewed. Clerk references and practical civilian clothing retained. / Camera body/lens accessory details vary slightly across views; do not use artwork as proof of exact equipment model or valuation.
- 씬 105~108: Inspected camera-sale paperwork, payment/receipt, earmarking funds and sixth-night phone with demolished-lot photo. / Cash bundles in scene107 are visually excessive/ambiguous for narrated amounts; arithmetic remains the unchanged narration ledger, not a visual approval of these bundles.
- 씬 109~112: Inspected sixth-night listening, six note sheets plus blank final slot, phone photo of demolished lot and preparing redemption papers/ID in envelope. No radio returned before redemption.
- 씬 113~116: Actual departure message/lock, stepping onto demolished-home lot, removing gloves into pocket and bare-handed phone wait inspected. No mother apparition.
- 씬 117~120: Actual seventh-night call, changing restrained emotion and wide empty-lot view inspected. Modern clothing and same protagonist retained; no present-time mother shown.
- 씬 121~124: Actual seventh-call listening close-ups and wide demolished-lot position inspected; no mother apparition, unchanged civilian jacket/phone.
- 씬 125~128: Actual emotional listening, quiet lot and call ending inspected. Chest-hand gesture reads as emotion, not established medical collapse; no such collapse added to narration.
- 씬 129~132: Inspected all four panels: site notes, departure, home phone check and pawnshop return. Handwriting is illustrative and not reliably readable.
- 씬 133~136: Inspected redemption payment, return of blue-handle radio and proprietor with black cat. Generated denominations and writing must not establish exact narrated sums; radio cabinet differs slightly from early grids. / Scene 136 cat is awake and its white chin is not clearly visible; narration describes resting chin and closing eyes. Retained as a recorded pose/marking discrepancy.
- 씬 137~140: Inspected rent-related phone/paperwork, returned radio at home, key preparation and coworker conversation. Screen text is illustrative, not exact financial evidence.
- 씬 141~144: Inspected key and phone contact exchange plus final dinner beside returned radio. Generated handwriting is not legible exact evidence. Radio retains blue handle but cabinet details vary from early scenes.
