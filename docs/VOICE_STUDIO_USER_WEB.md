# 유저웹 자막 내레이션 Voice Studio 연결

## 변경 내용

- 상단 내레이션 성우: Voice Studio 30개 목소리, 성별/이름 검색, 한국어 샘플, 말투 선택.
- 내레이션 일괄 적용: 내레이션 블록에만 `gemini:목소리`와 `voice_direction` 저장.
- 각 섹션 상단 마이크: Voice Studio 선택창, 섹션 단위 목소리와 말투 적용.
- 각 자막 줄 마이크와 대사 일괄 선택: 기존 ElevenLabs 선택창 유지.
- 최종 TTS: 지정된 구간 순서대로 Gemini와 ElevenLabs 생성 결과를 합침.
- 연속된 같은 Gemini 목소리/말투 구간은 1,000자 이내로 묶어 호출 수를 줄임.
- Gemini 오류 시 ElevenLabs로 자동 대체하지 않음.
- 원격 main의 dde7194까지 반영. 다른 PC의 렌더/업로드 변경을 보존함.

## 서버 설정

웹은 기존 MP3 저장/렌더 흐름에 맞춰 공식 Cloud Text-to-Speech API의 Gemini
2.5 Flash TTS를 사용한다. 워커의 Vertex PCM 어댑터와 인증 전달 방식은 별개다.
서버에서 아래 프로젝트와 ADC 또는 워크로드/서비스 계정 인증을 설정해야 한다.
인증은 서버 전용이며 `NEXT_PUBLIC_` 변수나 브라우저로 전달하지 않는다.

```
VOICE_STUDIO_CLOUD_PROJECT=secret-well-480907-a4
```

2026-09-10 해당 프로젝트에 `texttospeech.googleapis.com`을 활성화했다.
이 PC의 ADC로 실제 MP3(44.1 kHz mono, 약 3.92초) 생성 성공.
운영 웹 서버에는 이 PC의 ADC가 자동 전달되지 않는다. 크레딧의 실제 차감 여부는
별도 결제 내역 확인이 필요하다.

### Vercel 운영 인증

`voiceStudioAuth.ts`는 로컬에서는 ADC, Vercel에서는 `@vercel/oidc`와 Google
Workload Identity Federation을 사용한다. 운영 설정 누락 시 ADC로 대체하지 않는다.
아래 값은 Vercel `eclozers-projects / mytube`의 Production 환경에만 등록한다.

```dotenv
VOICE_STUDIO_CLOUD_PROJECT=secret-well-480907-a4
GCP_PROJECT_NUMBER=326186078696
GCP_WORKLOAD_IDENTITY_POOL_ID=air-voice-studio
GCP_WORKLOAD_IDENTITY_POOL_PROVIDER_ID=vercel-production
GCP_SERVICE_ACCOUNT_EMAIL=voice-studio-web@secret-well-480907-a4.iam.gserviceaccount.com
```

2026-09-10 Google 측 구성 완료:
- 전용 서비스 계정과 커스텀 역할 `voiceStudioSynthesizer`.
- 역할 권한: `aiplatform.endpoints.predict`, `serviceusage.services.use`.
- OIDC issuer: `https://oidc.vercel.com/eclozers-projects`.
- 허용 audience: `https://vercel.com/eclozers-projects`.
- 허용 subject: `owner:eclozers-projects:project:mytube:environment:production`.
- 위 subject에만 서비스 계정 `roles/iam.workloadIdentityUser` 부여.

서비스 계정 JSON 키와 로컬 ADC 파일을 Vercel에 복사하지 않는다.
Vercel 계정 인증 및 Production 환경 변수 등록 완료. 실제 운영 배포의 issuer,
audience, subject가 위 조건과 일치함을 확인했다. 프로젝트 연결 ID도 확인했다.
2026-09-10 배포 `dpl_2DYz5bPnj1EaKFA82u6ZGHHCuiFh`가 READY이며
`https://studio.airing.work`에 연결됐다. 최신 main(dde7194)에 로컬 웹 변경을
포함한 소스 스냅샷으로 배포했다. 이후 섹션 상단 마이크도 Voice Studio로
연결한 배포 `dpl_H452PkPAyLeSmH4zcfANF1uvubEK`를 운영에 반영했다.
이 문서와 웹 변경은 함께 커밋하며, 다른 PC에서는 최신 main을 받아 사용한다.
참고: https://vercel.com/docs/oidc/gcp

샘플과 Gemini 구간은 서버 임시 디스크 캐시를 재사용한다. 서버 교체/캐시 삭제
후에는 다시 생성될 수 있다. 대본 전체를 한 번에 호출하는 기존 웹 API의
300초 실행 제한은 유지되므로, 긴 대본은 구간 미리듣기 캐시를 활용하거나
향후 워커 큐 방식으로 이전해야 한다. 서버 샘플은 새 생성 시 Cloud 비용 발생.

## 검증

- 실제 Google API MP3 생성과 FFprobe 형식 확인.
- 신규 모듈/라우트 TypeScript 검사: 오류 0.
- `node auth-web/tests/voice-studio.cjs`: 목록, 공급자 순서, 말투 전달, 실패 시
  ElevenLabs 호출 금지, 연속 Gemini 구간 묶기 확인.
- 독립 UI 하네스에서 모달 표시, 30개 목록, 검색, Kore 선택 전달 확인.
- 기존 자막/렌더 관련 테스트 23개 통과, 2개 실패: 변경 전에도 없는 화면 문자열을
  찾는 테스트와 누락된 sample_render 픽스처. 원격 업로드 테스트는 이 Python에
  googleapiclient가 없어 수집 불가.
- 전체 TypeScript 검사는 기존 페이지 타입 오류 및 오래된 .next 타입 파일로 실패.
- 운영 로그인 상태에서 프로젝트 저장/Drive 업로드까지의 종단 테스트는 미실행.
- 운영 로그인된 자막 페이지에서 Voice Studio 30개 목록 확인. Charon 샘플을
  실제 생성했고 샘플 오디오 duration 10.475063초, readyState 4, error null 확인.
  이는 Vercel OIDC → Google 계정 위임 → Cloud TTS 호출의 운영 검증이다.
  검증 중 기존 프로젝트 성우 일괄 적용이나 전체 TTS 재생성은 하지 않았다.
