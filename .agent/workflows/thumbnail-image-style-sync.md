---
description: 썸네일 생성 스타일 연동 및 AI 기반 후킹 문구 자동 생성
---

# 썸네일 자동화 기획 (스타일 연동 + AI 문구 생성)

## 📋 목표
1. 이미지 생성 페이지에서 선택한 이미지 스타일을 썸네일 생성 페이지에 자동으로 연동
2. **[NEW]** 대본을 분석하여 클릭률을 높이는 후킹 문구를 AI가 자동 생성
3. 일관된 비주얼 스타일과 효과적인 카피로 썸네일 제작 프로세스 자동화

---

## 🎯 핵심 요구사항

### 1. **스타일 정보 공유**
- 이미지 생성 페이지에서 선택한 스타일을 프로젝트 설정에 저장
- 썸네일 생성 페이지에서 해당 스타일을 자동으로 불러와 적용

### 2. **UI/UX 개선**
- 썸네일 페이지 진입 시 이미지 스타일이 자동 선택됨
- 사용자가 원하면 수동으로 변경 가능 (Override)
- 스타일이 연동되었음을 시각적으로 표시

---

## 🔧 구현 방안

### **Phase 1: 데이터 구조 설계**

#### 1.1 프로젝트 설정에 스타일 저장
**DB 스키마 확장** (`project_settings` 테이블)
```sql
-- 새 컬럼 추가 (또는 JSON settings 내부)
ALTER TABLE project_settings ADD COLUMN image_style TEXT;
```

**또는 기존 JSON 설정 활용**
```json
{
  "image_style": "cinematic",  // 이미지 생성에서 선택한 스타일
  "thumbnail_style": "face"     // 썸네일 스타일 (기본값 또는 Override)
}
```

#### 1.2 스타일 매핑 테이블
이미지 스타일과 썸네일 스타일 간의 매핑 정의:

| 이미지 스타일 (Image Gen) | 추천 썸네일 스타일 (Thumbnail) | 이유 |
|---------------------------|-------------------------------|------|
| `cinematic` | `dramatic` | 영화적 분위기 일치 |
| `anime` | `minimal` | 깔끔한 애니메이션 스타일 |
| `realistic` | `face` | 사실적인 얼굴 강조 |
| `illustration` | `text` | 텍스트 중심 디자인 |
| `3d_render` | `contrast` | 강렬한 대비 효과 |
| `watercolor` | `minimal` | 부드러운 미니멀 |
| `oil_painting` | `dramatic` | 드라마틱한 유화 느낌 |

---

### **Phase 2: Backend 구현**

#### 2.1 이미지 생성 API 수정
**파일**: `main.py` (이미지 생성 엔드포인트)

```python
@app.post("/api/image/generate")
async def generate_image_api(req: ImageGenerateRequest):
    # ... 기존 로직 ...
    
    # [NEW] 선택한 스타일을 프로젝트 설정에 저장
    if req.project_id and req.style:
        await API.project.updateSetting(
            req.project_id, 
            'image_style', 
            req.style
        )
    
    return result
```

#### 2.2 썸네일 페이지 데이터 로드 API
**파일**: `main.py` (썸네일 페이지 렌더링)

```python
@app.get("/thumbnail")
async def thumbnail_page(request: Request):
    project_id = request.cookies.get('current_project')
    
    # [NEW] 이미지 스타일 불러오기
    image_style = None
    recommended_thumbnail_style = "face"  # 기본값
    
    if project_id:
        settings = await API.project.getSettings(project_id)
        image_style = settings.get('image_style')
        
        # 스타일 매핑
        style_map = {
            'cinematic': 'dramatic',
            'anime': 'minimal',
            'realistic': 'face',
            'illustration': 'text',
            '3d_render': 'contrast',
            'watercolor': 'minimal',
            'oil_painting': 'dramatic'
        }
        
        if image_style:
            recommended_thumbnail_style = style_map.get(image_style, 'face')
    
    return templates.TemplateResponse("pages/thumbnail.html", {
        "request": request,
        "image_style": image_style,
        "recommended_style": recommended_thumbnail_style
    })
```

---

### **Phase 3: Frontend 구현**

#### 3.1 썸네일 페이지 초기화 로직
**파일**: `templates/pages/thumbnail.html`

```javascript
document.addEventListener('DOMContentLoaded', async () => {
    const projectId = getCurrentProject();
    
    if (projectId) {
        try {
            // [NEW] 프로젝트 설정에서 이미지 스타일 가져오기
            const settings = await API.project.getSettings(projectId);
            const imageStyle = settings?.image_style;
            
            if (imageStyle) {
                // 스타일 매핑
                const styleMap = {
                    'cinematic': 'dramatic',
                    'anime': 'minimal',
                    'realistic': 'face',
                    'illustration': 'text',
                    '3d_render': 'contrast',
                    'watercolor': 'minimal',
                    'oil_painting': 'dramatic'
                };
                
                const recommendedStyle = styleMap[imageStyle] || 'face';
                
                // 자동 선택
                selectThumbnailStyle(recommendedStyle);
                
                // [NEW] 사용자에게 알림
                Utils.showToast(
                    `이미지 스타일(${imageStyle})에 맞춰 "${recommendedStyle}" 썸네일 스타일이 자동 선택되었습니다.`, 
                    'info'
                );
            }
        } catch (e) {
            console.log('스타일 연동 실패 (선택적 기능)', e);
        }
    }
    
    // ... 기존 로직 ...
});
```

#### 3.2 UI 개선 - 연동 표시
썸네일 스타일 선택 영역에 배지 추가:

```html
<div class="style-grid">
    <div class="style-card-thumb active" onclick="selectThumbnailStyle('dramatic')" data-style="dramatic">
        <img src="/static/img/thumbs/dramatic.png" alt="Dramatic">
        <div class="style-label">
            드라마틱형
            <!-- [NEW] 연동 배지 -->
            <span id="badge-dramatic" class="hidden ml-1 px-1 py-0.5 bg-blue-500 text-white text-[8px] rounded">
                연동됨
            </span>
        </div>
    </div>
    <!-- ... 다른 스타일들 ... -->
</div>
```

```javascript
function selectThumbnailStyle(styleId, isAutoLinked = false) {
    // ... 기존 로직 ...
    
    // [NEW] 연동 배지 표시
    document.querySelectorAll('[id^="badge-"]').forEach(b => b.classList.add('hidden'));
    if (isAutoLinked) {
        const badge = document.getElementById(`badge-${styleId}`);
        if (badge) badge.classList.remove('hidden');
    }
}
```

---

### **Phase 4: 고급 기능 (선택사항)**

#### 4.1 스타일 프리뷰 동기화
이미지 생성에서 만든 이미지를 썸네일 배경으로 자동 제안:

```javascript
// 썸네일 페이지 로드 시
const generatedImages = await API.project.getImages(projectId);
if (generatedImages && generatedImages.length > 0) {
    // 첫 번째 이미지를 배경으로 자동 설정
    const firstImage = generatedImages[0];
    currentBackgroundUrl = firstImage.url;
    currentBackgroundPath = firstImage.path;
    
    // 미리보기 업데이트
    loadBackgroundImage(firstImage.url);
}
```

#### 4.2 스타일 불일치 경고
사용자가 다른 스타일을 선택하려 할 때 확인 메시지:

```javascript
function selectThumbnailStyle(styleId) {
    const linkedStyle = sessionStorage.getItem('linked_thumbnail_style');
    
    if (linkedStyle && linkedStyle !== styleId) {
        const confirm = window.confirm(
            `이미지 스타일과 연동된 "${linkedStyle}" 대신 "${styleId}"를 선택하시겠습니까?\n` +
            `일관성을 위해 연동 스타일 사용을 권장합니다.`
        );
        
        if (!confirm) return;
    }
    
    // ... 기존 로직 ...
}
```

---

## 📊 구현 우선순위

### **High Priority (필수)**
1. ✅ 이미지 스타일을 프로젝트 설정에 저장
2. ✅ 썸네일 페이지에서 자동으로 스타일 불러오기
3. ✅ 스타일 매핑 테이블 정의

### **Medium Priority (권장)**
4. ✅ UI에 연동 상태 표시 (배지)
5. ✅ 사용자 알림 (Toast)

### **Low Priority (선택)**
6. ⚪ 생성된 이미지를 썸네일 배경으로 자동 제안
7. ⚪ 스타일 변경 시 확인 메시지

---

## 🧪 테스트 시나리오

### Test Case 1: 정상 연동
1. 이미지 생성 페이지에서 "Cinematic" 스타일 선택
2. 이미지 생성 완료
3. 썸네일 생성 페이지로 이동
4. **Expected**: "Dramatic" 스타일이 자동 선택됨
5. **Expected**: "연동됨" 배지 표시

### Test Case 2: 스타일 Override
1. 연동된 스타일이 자동 선택된 상태
2. 사용자가 다른 스타일 클릭
3. **Expected**: 선택 가능 (경고 메시지 선택사항)
4. **Expected**: 배지 사라짐

### Test Case 3: 이미지 스타일 없음
1. 이미지 생성을 하지 않은 프로젝트
2. 썸네일 생성 페이지로 이동
3. **Expected**: 기본 스타일("Face") 선택
4. **Expected**: 연동 배지 없음

---

## 🎨 UI 목업 (간략)

```
┌─────────────────────────────────────────────────┐
│  2️⃣ 썸네일 아이디어 생성                          │
├─────────────────────────────────────────────────┤
│  스타일 선택                                      │
│  ┌──────┐ ┌──────┐ ┌──────┐                     │
│  │ Face │ │ Text │ │Drama │ ← 연동됨 💡          │
│  └──────┘ └──────┘ └──────┘                     │
│                                                  │
│  ℹ️ 이미지 스타일(Cinematic)에 맞춰              │
│     "Dramatic" 스타일이 자동 선택되었습니다.      │
└─────────────────────────────────────────────────┘
```

---

## 🤖 **[NEW] Feature: AI 기반 썸네일 문구 자동 생성**

### **개요**
대본을 분석하여 클릭률(CTR)을 극대화하는 후킹 문구를 AI가 자동으로 생성합니다.

---

### **A. 프롬프트 설계**

#### A.1 Gemini 프롬프트 템플릿
**파일**: `services/prompts.py`

```python
GEMINI_THUMBNAIL_HOOK_TEXT = """당신은 유튜브 썸네일 카피라이팅 전문가입니다.
아래 영상 대본을 분석하여 클릭률을 극대화하는 썸네일 문구를 생성해주세요.

[영상 대본]
{script}

[스타일 가이드]
- 썸네일 스타일: {thumbnail_style}
- 이미지 스타일: {image_style}
- 타겟 언어: {target_language}

[문구 생성 원칙]
1. **후킹 (Hook)**: 호기심을 자극하는 질문이나 충격적인 진술
2. **간결성**: 3-7단어 (한글 기준 10-20자)
3. **감정 유발**: 놀람, 궁금증, 공감 중 하나 이상
4. **가독성**: 큰 글씨로 읽기 쉬운 단어 선택
5. **스타일 매칭**: 
   - Face/Dramatic: 감정적, 충격적 ("믿을 수 없는 진실", "충격적인 반전")
   - Text/Minimal: 정보성, 명확한 ("TOP 5", "핵심 정리")
   - Mystery: 질문형, 미스터리 ("진짜 이유는?", "숨겨진 비밀")

[출력 형식]
JSON 형식으로 5개의 후보 문구를 생성하세요:
{{
    "texts": [
        "후보 문구 1 (가장 강력한 후킹)",
        "후보 문구 2 (감정 유발)",
        "후보 문구 3 (질문형)",
        "후보 문구 4 (숫자/리스트형)",
        "후보 문구 5 (대비/반전형)"
    ],
    "reasoning": "선택 이유 (1-2문장)"
}}

**중요**: 대본의 핵심 메시지를 왜곡하지 말고, 클릭베이트가 아닌 진정성 있는 후킹을 만드세요.
JSON만 반환하세요.
"""
```

#### A.2 스타일별 문구 전략

| 썸네일 스타일 | 문구 전략 | 예시 |
|--------------|----------|------|
| **Face** | 감정 표현 + 인물 중심 | "그가 울었던 진짜 이유", "그녀의 충격 고백" |
| **Text** | 명확한 정보 전달 | "TOP 5 핵심 정리", "3분 완벽 이해" |
| **Dramatic** | 극적 표현 + 반전 | "믿을 수 없는 결말", "충격적인 진실" |
| **Mystery** | 질문형 + 호기심 | "진짜 이유는?", "숨겨진 비밀" |
| **Minimal** | 간결 + 임팩트 | "핵심만", "이것만 보세요" |
| **Contrast** | 대비 + 변화 | "Before vs After", "과거 vs 현재" |

---

### **B. Backend 구현**

#### B.1 새 API 엔드포인트
**파일**: `main.py`

```python
from pydantic import BaseModel

class ThumbnailTextRequest(BaseModel):
    project_id: int
    thumbnail_style: str = "face"
    target_language: str = "ko"

@app.post("/api/thumbnail/generate-text")
async def generate_thumbnail_text(req: ThumbnailTextRequest):
    """대본 기반 썸네일 문구 자동 생성"""
    try:
        # 1. 프로젝트 데이터 가져오기
        project = await API.project.get(req.project_id)
        settings = await API.project.getSettings(req.project_id)
        
        # 2. 대본 가져오기
        script = project.get('full_script') or project.get('script')
        if not script:
            return {"status": "error", "error": "대본이 없습니다"}
        
        # 3. 이미지 스타일 가져오기 (연동)
        image_style = settings.get('image_style', 'realistic')
        
        # 4. AI 프롬프트 생성
        from services.prompts import prompts
        prompt = prompts.GEMINI_THUMBNAIL_HOOK_TEXT.format(
            script=script[:2000],  # 대본 앞부분만 (토큰 절약)
            thumbnail_style=req.thumbnail_style,
            image_style=image_style,
            target_language=req.target_language
        )
        
        # 5. Gemini 호출
        from services.gemini_service import gemini_service
        result = await gemini_service.generate_text(prompt, temperature=0.8)
        
        # 6. JSON 파싱
        import json, re
        json_match = re.search(r'\{[\s\S]*\}', result)
        if json_match:
            data = json.loads(json_match.group())
            return {"status": "ok", "texts": data.get("texts", []), "reasoning": data.get("reasoning")}
        
        return {"status": "error", "error": "JSON 파싱 실패"}
        
    except Exception as e:
        return {"status": "error", "error": str(e)}
```

#### B.2 Gemini Service 확장
**파일**: `services/gemini_service.py`

```python
async def generate_thumbnail_texts(self, script: str, style: str, language: str = "ko") -> List[str]:
    """썸네일 후킹 문구 생성"""
    prompt = prompts.GEMINI_THUMBNAIL_HOOK_TEXT.format(
        script=script,
        thumbnail_style=style,
        image_style="",  # Optional
        target_language=language
    )
    
    text = await self.generate_text(prompt, temperature=0.8)
    
    # JSON 파싱
    import json, re
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        data = json.loads(match.group())
        return data.get("texts", [])
    
    return []
```

---

### **C. Frontend 구현**

#### C.1 UI 추가 - 자동 생성 버튼
**파일**: `templates/pages/thumbnail.html`

기존 "아이디어 생성하기" 버튼 옆에 추가:

```html
<div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
    <button onclick="generateIdeas()" id="ideaBtn" class="btn-primary">
        💡 아이디어 생성하기
    </button>
    
    <!-- [NEW] AI 문구 생성 버튼 -->
    <button onclick="generateHookTexts()" id="hookTextBtn" class="btn-secondary">
        🤖 AI 후킹 문구 생성 (대본 기반)
    </button>
</div>

<!-- [NEW] 생성된 문구 표시 영역 -->
<div id="hookTextsSection" class="hidden mb-4 p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
    <h4 class="text-sm font-bold text-blue-800 dark:text-blue-300 mb-2">
        🎯 AI 추천 후킹 문구
    </h4>
    <div id="hookTextsList" class="flex flex-wrap gap-2"></div>
    <p id="hookReasoning" class="text-xs text-blue-600 dark:text-blue-400 mt-2"></p>
</div>
```

#### C.2 JavaScript 로직
**파일**: `templates/pages/thumbnail.html` (Script Section)

```javascript
// [NEW] AI 후킹 문구 생성
async function generateHookTexts() {
    const projectId = getCurrentProject();
    if (!projectId) {
        Utils.showToast('프로젝트를 먼저 선택하세요', 'warning');
        return;
    }
    
    const btn = document.getElementById('hookTextBtn');
    Utils.setLoading(btn, true, '생성 중...');
    
    try {
        const style = document.getElementById('thumbnailStyle').value;
        const targetLang = window.TARGET_LANGUAGE || 'ko';
        
        const response = await fetch('/api/thumbnail/generate-text', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                project_id: projectId,
                thumbnail_style: style,
                target_language: targetLang
            })
        });
        
        const result = await response.json();
        
        if (result.status === 'ok') {
            displayHookTexts(result.texts, result.reasoning);
            Utils.showToast('후킹 문구가 생성되었습니다!', 'success');
        } else {
            Utils.showToast('생성 실패: ' + result.error, 'error');
        }
        
    } catch (e) {
        Utils.showToast('오류: ' + e.message, 'error');
    } finally {
        Utils.setLoading(btn, false);
    }
}

// [NEW] 생성된 문구 표시
function displayHookTexts(texts, reasoning) {
    const section = document.getElementById('hookTextsSection');
    const list = document.getElementById('hookTextsList');
    const reasoningEl = document.getElementById('hookReasoning');
    
    section.classList.remove('hidden');
    
    // 문구 버튼 생성
    list.innerHTML = texts.map((text, i) => `
        <button 
            onclick="applyHookText('${text.replace(/'/g, "\\'")}')" 
            class="px-3 py-2 bg-white dark:bg-gray-700 border-2 border-blue-300 dark:border-blue-600 rounded-lg hover:bg-blue-100 dark:hover:bg-blue-800 transition text-sm font-bold text-gray-800 dark:text-white"
            title="클릭하여 적용"
        >
            ${i === 0 ? '⭐ ' : ''}${text}
        </button>
    `).join('');
    
    // 선택 이유 표시
    if (reasoning) {
        reasoningEl.textContent = `💡 ${reasoning}`;
    }
}

// [NEW] 문구 적용
function applyHookText(text) {
    // 첫 번째 텍스트 레이어에 자동 적용
    if (textLayers.length === 0) {
        addLayer();
    }
    
    textLayers[0].text = text;
    renderLayers();
    drawPreview();
    
    Utils.showToast(`"${text}" 적용됨`, 'success');
}
```

---

### **D. 고급 기능 (선택사항)**

#### D.1 다국어 문구 생성
```javascript
// 언어별 문구 동시 생성
async function generateMultilingualTexts() {
    const languages = ['ko', 'en', 'ja'];
    const results = {};
    
    for (const lang of languages) {
        const res = await fetch('/api/thumbnail/generate-text', {
            method: 'POST',
            body: JSON.stringify({
                project_id: projectId,
                target_language: lang
            })
        });
        results[lang] = await res.json();
    }
    
    return results;
}
```

#### D.2 A/B 테스트 추천
AI가 여러 버전을 생성하고 클릭률 예측:

```python
# Prompt 추가
"""
각 문구에 대해 예상 클릭률(CTR)을 1-10점으로 평가하세요:
{{
    "texts": [
        {{"text": "문구", "ctr_score": 9, "reason": "강력한 호기심 유발"}}
    ]
}}
"""
```

#### D.3 실시간 미리보기
문구를 선택하면 썸네일 캔버스에 즉시 반영:

```javascript
function applyHookText(text) {
    // ... 기존 로직 ...
    
    // 즉시 캔버스에 그리기
    drawPreview();
    
    // 스크롤하여 미리보기로 이동
    document.getElementById('previewContainer').scrollIntoView({
        behavior: 'smooth',
        block: 'center'
    });
}
```

---

### **E. 테스트 시나리오**

#### Test Case 1: 대본 기반 생성
1. 대본 작성 완료된 프로젝트 선택
2. 썸네일 페이지에서 "AI 후킹 문구 생성" 클릭
3. **Expected**: 5개의 후킹 문구 생성
4. **Expected**: 대본 내용과 관련성 있음

#### Test Case 2: 스타일별 문구 차이
1. Dramatic 스타일 선택 → 생성
2. **Expected**: "충격적인", "믿을 수 없는" 등 극적 표현
3. Minimal 스타일 선택 → 생성
4. **Expected**: "핵심만", "간단 정리" 등 간결한 표현

#### Test Case 3: 문구 적용
1. 생성된 문구 중 하나 클릭
2. **Expected**: 첫 번째 텍스트 레이어에 자동 입력
3. **Expected**: 캔버스 미리보기 업데이트

---

### **F. UI 목업**

```
┌─────────────────────────────────────────────────┐
│  1️⃣ 썸네일 아이디어 생성                          │
├─────────────────────────────────────────────────┤
│  [💡 아이디어 생성]  [🤖 AI 후킹 문구 생성]       │
│                                                  │
│  ┌───────────────────────────────────────────┐  │
│  │ 🎯 AI 추천 후킹 문구                       │  │
│  ├───────────────────────────────────────────┤  │
│  │ [⭐ 믿을 수 없는 진실] [충격적인 반전]     │  │
│  │ [진짜 이유는?] [TOP 5 정리] [Before vs After] │
│  │                                            │  │
│  │ 💡 대본의 핵심 메시지를 강조하면서        │  │
│  │    호기심을 자극하는 문구를 선택했습니다.  │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

---

## ✅ 결론

**가능 여부**: ✅ **완전히 가능합니다!**

**구현 난이도**: 
- **스타일 연동**: ⭐⭐☆☆☆ (중하)
- **AI 문구 생성**: ⭐⭐⭐☆☆ (중)

**예상 소요 시간**: 
- Phase 1-3 (스타일 연동): 1-2시간
- **[NEW] AI 문구 생성 (A-C)**: 2-3시간
- Phase 4 (고급 기능): 추가 1-2시간

**장점**:
- ✅ 일관된 비주얼 스타일 유지 (이미지 ↔ 썸네일)
- ✅ **대본 기반 자동 후킹 문구 생성으로 클릭률 향상**
- ✅ 사용자 편의성 대폭 향상 (자동화)
- ✅ 워크플로우 개선 및 시간 절약
- ✅ **AI가 스타일별 최적화된 문구 제안**

**단점**:
- ⚠️ 스타일 매핑이 주관적일 수 있음 (사용자 피드백 필요)
- ⚠️ **AI 생성 문구가 항상 완벽하지 않을 수 있음 (수동 수정 가능)**
- ⚠️ Gemini API 호출 비용 증가 (문구 생성 시)

---

## 🚀 다음 단계

### **우선순위 1: 스타일 연동 (필수)**
1. ✅ 이미지 스타일을 프로젝트 설정에 저장
2. ✅ 썸네일 페이지에서 자동으로 스타일 불러오기
3. ✅ 스타일 매핑 테이블 정의

### **우선순위 2: AI 문구 생성 (강력 권장)**
4. ✅ Gemini 프롬프트 작성 (`prompts.py`)
5. ✅ Backend API 구현 (`/api/thumbnail/generate-text`)
6. ✅ Frontend UI 및 로직 추가

### **우선순위 3: UI/UX 개선 (권장)**
7. ✅ 연동 상태 표시 (배지)
8. ✅ 사용자 알림 (Toast)
9. ✅ 문구 클릭 시 자동 적용

### **우선순위 4: 고급 기능 (선택)**
10. ⚪ 다국어 문구 생성
11. ⚪ CTR 예측 점수
12. ⚪ 실시간 미리보기 개선

---

## 📊 구현 로드맵

```
Week 1: 스타일 연동 (Phase 1-3)
  ├─ Day 1-2: Backend (DB, API)
  └─ Day 3: Frontend (UI, 자동 선택)

Week 2: AI 문구 생성 (Section A-C)
  ├─ Day 1: Prompt 설계 및 테스트
  ├─ Day 2: Backend API 구현
  └─ Day 3: Frontend UI 및 통합

Week 3: 테스트 및 최적화
  ├─ Day 1-2: 사용자 테스트
  └─ Day 3: 피드백 반영 및 배포
```

---

구현을 시작할까요? 🚀
