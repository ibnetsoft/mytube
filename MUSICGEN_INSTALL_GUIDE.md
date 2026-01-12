# MusicGen 배경음악 생성 기능 - 수동 설치 가이드

## 1. main.py에 추가할 코드

`main.py` 파일을 열고 `if __name__ == "__main__":` 라인을 찾으세요.
그 **바로 위**에 다음 코드를 추가하세요:

```python
# ===========================================
# API: 배경음악 생성 (MusicGen)
# ===========================================

# Pydantic 모델
class MusicGenRequest(BaseModel):
    prompt: str
    duration: int = 10  # 5~30초
    project_id: Optional[int] = None

@app.get("/music-gen", response_class=HTMLResponse)
async def music_gen_page(request: Request):
    """배경음악 생성 페이지"""
    return templates.TemplateResponse("pages/music_gen.html", {
        "request": request,
        "page": "music-gen",
        "title": "배경음악 생성"
    })

@app.post("/api/music/generate")
async def generate_background_music(req: MusicGenRequest):
    """MusicGen으로 배경음악 생성"""
    try:
        from services.music_service import music_service
        
        # 프롬프트 검증
        if not req.prompt or len(req.prompt.strip()) < 3:
            raise HTTPException(400, "프롬프트를 입력해주세요 (최소 3자)")
        
        # 길이 검증
        duration = max(5, min(30, req.duration))
        
        # 파일명 생성
        import time
        timestamp = int(time.time())
        filename = f"bgm_{timestamp}.wav"
        
        # 음악 생성
        file_path = await music_service.generate_music(
            prompt=req.prompt,
            duration_seconds=duration,
            filename=filename,
            project_id=req.project_id
        )
        
        # 웹 접근 경로
        rel_path = os.path.relpath(file_path, config.OUTPUT_DIR)
        web_url = f"/output/{rel_path}".replace("\\", "/")
        
        # DB에 저장 (선택사항)
        if req.project_id:
            db.update_project_setting(req.project_id, 'background_music_path', file_path)
        
        return {
            "status": "ok",
            "path": file_path,
            "url": web_url,
            "duration": duration,
            "prompt": req.prompt
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Music generation error: {e}")
        raise HTTPException(500, f"음악 생성 중 오류가 발생했습니다: {str(e)}")

```

---

## 2. base.html에 추가할 메뉴 코드

`templates/base.html` 파일을 열고 "TTS 생성" 메뉴를 찾으세요.
그 **바로 아래**에 다음 코드를 추가하세요:

```html
                    <li>
                        <a href="/music-gen" class="sidebar-item {% if page == 'music-gen' %}active{% endif %}">
                            <span class="sidebar-icon">🎵</span>
                            <span>배경음악 생성</span>
                        </a>
                    </li>
```

**위치 예시:**
```html
                    <li>
                        <a href="/tts" class="sidebar-item {% if page == 'tts' %}active{% endif %}">
                            <span class="sidebar-icon">🔊</span>
                            <span>TTS 생성</span>
                        </a>
                    </li>
                    <!-- 여기에 위 코드 추가 -->
                    <li>
                        <a href="/subtitle-gen" class="sidebar-item {% if page == 'subtitle-gen' %}active{% endif %}">
                            <span class="sidebar-icon">📝</span>
                            <span>자막 편집</span>
                        </a>
                    </li>
```

---

## 3. 의존성 설치 확인

터미널에서 다음 명령어를 실행하세요:

```bash
pip install transformers audiocraft scipy
```

---

## 4. 서버 재시작

모든 코드를 추가한 후 서버를 재시작하세요:

```bash
python main.py
```

---

## 5. 테스트

1. 브라우저에서 사이드바의 "🎵 배경음악 생성" 메뉴 클릭
2. 프롬프트 입력 또는 프리셋 버튼 클릭
3. 길이 조절 (5~30초)
4. "배경음악 생성하기" 클릭
5. 첫 실행 시 모델 다운로드 (~300MB, 1-3분)
6. 생성 완료 후 재생 및 다운로드

---

## 완료된 파일

✅ `services/music_service.py` - MusicGen 서비스
✅ `templates/pages/music_gen.html` - UI 페이지
⚠️ `main.py` - API 코드 추가 필요 (수동)
⚠️ `templates/base.html` - 메뉴 추가 필요 (수동)

---

## 문제 해결

### 모델 다운로드 실패
- 인터넷 연결 확인
- Hugging Face 접속 가능 여부 확인

### 생성 속도가 느림
- GPU 사용 권장
- CPU 사용 시 1-3분 소요 (정상)

### 메모리 부족
- `musicgen-small` 모델 사용 (현재 설정)
- 다른 프로그램 종료

---

질문이 있으시면 언제든지 물어보세요!
