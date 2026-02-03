// AI 썸네일 후킹 문구 생성 함수들

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
        const lang = window.targetLang || 'ko';

        const response = await fetch('/api/thumbnail/generate-text', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                project_id: parseInt(projectId),
                thumbnail_style: style,
                target_language: lang
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
        console.error('Hook text generation error:', e);
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

    if (!section || !list) {
        console.error('Hook texts UI elements not found');
        return;
    }

    section.classList.remove('hidden');

    // 문구 버튼 생성
    list.innerHTML = texts.map((text, i) => `
        <button 
            onclick="applyHookText('${text.replace(/'/g, "\\'")}')" 
            class="px-3 py-2 bg-white dark:bg-gray-700 border-2 border-blue-300 dark:border-blue-600 rounded-lg hover:bg-blue-100 dark:hover:bg-blue-800 transition text-sm font-bold text-gray-800 dark:text-white shadow-sm hover:shadow-md"
            title="클릭하여 적용"
        >
            ${i === 0 ? '⭐ ' : ''}${text}
        </button>
    `).join('');

    // 선택 이유 표시
    if (reasoning && reasoningEl) {
        reasoningEl.textContent = `💡 ${reasoning}`;
    }

    // 스크롤
    section.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// [NEW] 문구 적용
function applyHookText(text) {
    if (typeof textLayers === 'undefined') {
        console.error('textLayers not defined');
        return;
    }

    if (textLayers.length === 0) startNewLayer();

    const currentStyle = document.getElementById('thumbnailStyle').value || 'face';

    // 스타일별 텍스트 설정 (색상, 테두리, 폰트)
    const styleConfigs = {
        'face': { color: '#ffffff', stroke_color: '#000000', stroke_width: 8, font_family: 'Recipekorea' }, // 사실적, 깔끔
        'text': { color: '#ffff00', stroke_color: '#000000', stroke_width: 10, font_family: 'GmarketSansBold' }, // 텍스트 강조 (노랑)
        'contrast': { color: '#ffffff', stroke_color: '#ff0000', stroke_width: 8, font_family: 'GmarketSansBold' }, // 대비 (빨강 테두리)
        'mystery': { color: '#adff2f', stroke_color: '#000000', stroke_width: 6, font_family: 'GmarketSansMedium' }, // 미스터리 (형광초록)
        'minimal': { color: '#000000', stroke_color: '#ffffff', stroke_width: 2, font_family: 'NanumGothic' }, // 미니멀 (검정+흰테두리)
        'dramatic': { color: '#ff0000', stroke_color: '#000000', stroke_width: 10, font_family: 'Recipekorea' }, // 드라마틱 (빨강)
        'japanese_viral': { color: '#00ff00', stroke_color: '#000000', stroke_width: 8, font_family: 'GmarketSansBold' }, // 시니어/바이럴 (초록 시작)
        'ghibli': { color: '#ffffff', stroke_color: '#4a4a4a', stroke_width: 4, font_family: 'NanumPen' }, // 감성 (손글씨 느낌)
        'wimpy': { color: '#000000', stroke_color: 'transparent', stroke_width: 0, font_family: 'NanumPen' } // 윔피 (검정 손글씨)
    };

    const config = styleConfigs[currentStyle] || styleConfigs['face'];

    // 첫 번째 레이어에 적용
    const layer = textLayers[0];
    layer.text = text;

    // 스타일 적용 (사용자가 이미 수정한 경우를 고려해, '기본값' 상태일 때만 덮어쓰거나 항상 덮어쓸지 결정.
    // 여기서는 "자동 최적화" 기능이므로 스타일을 강제 적용함)
    if (config) {
        layer.color = config.color;
        layer.stroke_color = config.stroke_color;
        layer.stroke_width = config.stroke_width;
        layer.font_family = config.font_family; // 폰트는 해당 폰트가 로드되어 있어야 함 (CSS 확인 필요)

        // 위치 자동 조정 (스타일별)
        if (currentStyle === 'japanese_viral') {
            layer.x_offset = -300; // 좌측 정렬
            layer.position = 'row1';
        } else if (currentStyle === 'text') {
            layer.position = 'center';
            layer.font_size = 90;
        }
    }

    // UI 업데이트
    if (typeof renderLayers === 'function') renderLayers();
    if (typeof drawPreview === 'function') drawPreview();

    Utils.showToast(`"${text}" 적용됨 (${currentStyle} 스타일)`, 'success');

    // 미리보기로 스크롤
    const preview = document.getElementById('previewContainer');
    if (preview) {
        preview.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
}

function startNewLayer() {
    if (typeof addLayer === 'function') {
        addLayer();
    } else {
        textLayers.push({
            text: '새 텍스트',
            position: 'center',
            x_offset: 0,
            y_offset: 0,
            font_family: 'Recipekorea',
            font_size: 72,
            color: '#FFFFFF',
            stroke_color: '#000000',
            stroke_width: 5
        });
    }
}
