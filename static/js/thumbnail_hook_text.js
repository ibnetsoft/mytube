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
    // 첫 번째 텍스트 레이어에 자동 적용
    if (typeof textLayers === 'undefined') {
        console.error('textLayers not defined');
        return;
    }

    if (textLayers.length === 0) {
        addLayer();
    }

    textLayers[0].text = text;

    // UI 업데이트
    if (typeof renderLayers === 'function') renderLayers();
    if (typeof drawPreview === 'function') drawPreview();

    Utils.showToast(`"${text}" 적용됨`, 'success');

    // 미리보기로 스크롤
    const preview = document.getElementById('previewContainer');
    if (preview) {
        preview.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
}
