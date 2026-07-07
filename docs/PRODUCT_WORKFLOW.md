# AIR Studio Product Workflow (Project Constitution)

> **이 문서는 AIR Studio의 제품 철학과 사용자 Workflow를 정의하는 최상위 문서이다.**
> 
> 새로운 기능을 설계하거나 구현하기 전에 반드시 이 문서를 읽고 따른다.
> 이 문서와 충돌하는 설계는 구현하지 않는다.

---

## 1. AIR Studio의 역할
AIR Studio는 **AI 생성 플랫폼이 아니다.**

AIR Studio는 다음을 담당한다:
* AI 대본 생성
* AI Scene 분석
* AI Shot 설계
* AI 이미지 프롬프트 생성
* AI 영상 프롬프트 생성
* AI TTS 추천 및 생성
* 업로드된 에셋(Scene/Shot) 자동 매칭
* Timeline 자동 구성
* 영상 편집
* 자막 생성
* 최종 영상 렌더링
* Google Drive 업로드
* YouTube 자동 업로드

---

## 2. AIR Studio가 하지 않는 일
AIR Studio는 아래 작업을 직접 수행하지 않는다:
* ChatGPT 이미지 생성
* Google Flow 영상 생성
* Kling 영상 생성
* Veo 영상 생성
* Flux 이미지 생성
* Midjourney 이미지 생성
* 외부 생성 AI API 직접 호출

외부 생성은 사용자가 직접 수행한다.

---

## 3. 사용자 Workflow

### Step 1
웹 어드민에서 카테고리별 주제를 생성한다.

### Step 2
사용자는 주제 페이지에서 작업할 주제를 선택한다.

### Step 3
AI가 대본을 기획한다.

### Step 4
AI가 전체 대본을 생성한다.

### Step 5
AI가 Scene 분리 및 2×2 이미지 프롬프트 생성을 수행한다.

### Step 6
AI가 영상 프롬프트를 생성한다.

### Step 7 (유일한 외부 작업)
사용자는 플랫폼 밖에서 다음 작업만 수행한다:
* ChatGPT 이미지 생성
* 이미지 Crop
* 이미지 Upscaling
* ChatGPT 또는 Google Flow에서 영상클립 생성

이 과정만 AIR Studio 밖에서 진행된다. 생성된 이미지와 영상은 다시 AIR Studio에 업로드한다.

### Step 8
업로드된 에셋을 AI가 분석한다. AI는 Scene, Shot, 감정, 등장인물, 구도, 움직임 등을 비교하여 가장 적합한 위치에 자동 배치한다. 사용자는 필요 시 수동으로 수정할 수 있다.

### Step 9
AI 추천 음성으로 TTS를 생성한다.

### Step 10
편집 페이지에서 영상, 자막, TTS, BGM을 합성하여 최종 렌더링을 구성한다.

### Step 11
렌더링은 원격 RTX 5060 GPU PC에서 수행한다.

### Step 12
완성된 MP4는 Google Drive에 업로드한다.

### Step 13
YouTube API를 통해 자동 업로드한다.

---

## 4. 핵심 원칙
AIR Studio의 목적은 **생성 AI를 만드는 것이 아니라 생성 과정을 자동화하는 것이다.**
외부 생성 결과물을 가장 효율적으로 관리하고 연결하는 것이 핵심 가치이다.

---

## 5. 기능 우선순위
새로운 기능은 다음 순서를 우선한다:
1. 사용자 Workflow 단축
2. Scene/Shot 자동화
3. Asset 자동 매칭
4. Timeline 자동 동기화
5. 영상 품질 향상

단순한 Export 기능이나 Prompt 다운로드 기능은 위 기능보다 우선순위가 낮다.

---

## 6. 개발 원칙
새로운 Sprint를 시작하기 전에 반드시 아래를 확인한다:
* 이 기능이 실제 사용자 Workflow를 단축하는가?
* 이 기능이 AIR Studio 안에서 수행되는 작업인가?
* 외부 생성 플랫폼의 역할을 침범하지 않는가?
* 기존 Product Workflow와 충돌하지 않는가?

위 질문 중 하나라도 "아니오"라면 구현 전에 CTO 승인을 다시 받아야 한다.
