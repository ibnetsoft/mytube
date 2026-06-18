# 음악 플레이리스트 생성 재설계

## 목표
총 길이 내에서 3-5분 범위의 음악을 여러 개 생성하고 조합하여 최종 플레이리스트 비디오 제작

## 아키텍처

### 1단계: 기획 생성 (기존 유지)
- Gemini로 플레이리스트 컨셉, 각 트랙 prompt 생성
- **변경**: 각 트랙에 `duration_seconds` 계산값 추가

### 2단계: 개별 트랙 길이 계산 (신규)
```
입력: 총 플레이리스트 길이(초), 트랙 수
계산식:
- 평균 길이 = 총 길이 / 트랙 수
- 범위: 180~300초 (3-5분)
- 조정가능: 사용자가 개별 트랙 길이 슬라이더로 조정 가능
```

예시: 60분, 12곡
- 평균 = 3600 / 12 = 300초 (5분)
- 각 트랙 300초 설정

### 3단계: 개별 트랙 생성 (기존 preview 확장)
- `/api/music/generate-track` 엔드포인트 신규
- ElevenLabs에서 각 트랙을 계획된 길이로 생성
- MP3 파일을 `assets/audio/longform_music/tracks/` 저장
- 상태 저장: `project_settings.music_tracks_generated` JSON

### 4단계: 트랙 조합 (신규)
- ffmpeg로 MP3 파일들 순서대로 연결
- `assets/audio/longform_music/final.mp3` 생성
- 최종 길이 검증

### 5단계: 비디오 렌더링 (기존 영상 시스템 연동)
- 조합된 음악 + 썸네일/정적 이미지 → MP4
- 기존 video_builder_service 활용

## 필요한 변경사항

### A. music_plan_service.py - coerce_tracks()
- 각 트랙에 `duration_seconds` 계산해서 할당
- 범위: 180~300초

### B. music.py - 신규 엔드포인트
- `POST /api/music/generate-full-track` - 각 트랙 생성
- `POST /api/music/combine-tracks` - 트랙 조합
- `POST /api/music/render-video` - 최종 비디오 생성

### C. music_plan.html - UI 개선
- 기획 생성 후 → 트랙별 길이 슬라이더 표시
- "트랙 생성 시작" 버튼 → 모든 트랙 순차 생성
- 생성 진행상황 표시

### D. 신규 서비스 (필요시)
- `services/music_track_combiner.py` - ffmpeg로 조합
- `services/music_render_service.py` - 최종 비디오 생성

## 데이터 흐름

```
프로젝트 설정 저장:
- longform_music_plan_json: 기획 + duration 정보
- music_tracks_generated: [
    {track_id, prompt, duration, file_path, status}
  ]
- music_final_render: {combined_audio_path, video_path, status}
```

## 구현 우선순위
1. ✅ 기획에 duration_seconds 계산 추가
2. 개별 트랙 생성 엔드포인트
3. 트랙 조합 로직
4. 비디오 렌더링 연동
5. UI 개선
