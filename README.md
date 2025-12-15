# wingsAIStudio Backend

AI 기반 YouTube 영상 자동화 제작 플랫폼 - Python 백엔드

## 빠른 시작

### Windows
```bash
cd backend
run.bat
```

### Mac/Linux
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py
```

## 서버 접속

서버 시작 후 브라우저에서:
```
http://127.0.0.1:8000
```

## 프로젝트 구조

```
backend/
├── main.py              # FastAPI 메인 서버
├── config.py            # 설정 관리
├── requirements.txt     # Python 패키지
├── .env                 # 환경 변수 (API 키)
├── .env.example         # 환경 변수 예시
├── run.bat              # 실행 스크립트 (Windows)
├── services/            # 비즈니스 로직
│   ├── gemini_service.py   # Gemini API
│   ├── tts_service.py      # TTS (ElevenLabs)
│   └── video_service.py    # 영상 합성 (MoviePy)
├── templates/           # HTML 템플릿 (추후)
├── static/              # 정적 파일 (추후)
└── output/              # 생성된 파일 저장
```

## API 엔드포인트

### 상태 확인
- `GET /api/health` - 서버 상태 및 API 키 설정 확인

### YouTube API (프록시)
- `GET /api/youtube/search?q=검색어` - 영상 검색
- `GET /api/youtube/videos?id=영상ID` - 영상 상세 정보
- `GET /api/youtube/comments?videoId=영상ID` - 댓글 조회

### Gemini API (프록시)
- `POST /api/gemini/generate` - 텍스트 생성

### TTS API
- `POST /api/tts/elevenlabs` - ElevenLabs TTS 생성

## 환경 변수 (.env)

```env
# 필수
YOUTUBE_API_KEY=your_key
GEMINI_API_KEY=your_key

# 선택
ELEVENLABS_API_KEY=your_key
TYPECAST_API_KEY=your_key
```

## 다음 단계

1. [ ] 프론트엔드 API 호출을 백엔드 프록시로 전환
2. [ ] 이미지 생성 API (Imagen 3) 연동
3. [ ] 영상 자동 합성 기능 구현
4. [ ] Veo API 연동
