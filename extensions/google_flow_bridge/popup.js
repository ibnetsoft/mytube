
let statusBadge, projectInfo, promptList;
window.projectId = null;
window.serverBase = 'http://localhost:8000';

document.addEventListener('DOMContentLoaded', async () => {
    promptList = document.getElementById('prompt-list');
    projectInfo = document.getElementById('project-info');
    statusBadge = document.getElementById('status-badge');

    try {
        const tabs = await chrome.tabs.query({});
        const platformTab = tabs.find(t => t.url && (t.url.includes('127.0.0.1:8000') || t.url.includes('localhost:8000')));
        
        if (!platformTab) {
            statusBadge.innerText = 'Platform Offline';
            statusBadge.style.color = '#ef4444';
            projectInfo.innerText = '피카디리스튜디오(localhost:8000) 탭이 필요합니다.';
            return;
        }

        window.serverBase = platformTab.url.includes('localhost') ? 'http://localhost:8000' : 'http://127.0.0.1:8000';

        try {
            const result = await chrome.scripting.executeScript({
                target: { tabId: platformTab.id },
                func: () => ({
                    projectId: localStorage.getItem('currentProjectId'),
                    projectName: document.title.split(' - ')[0]
                })
            });
            let { projectId, projectName } = result[0].result;
            if (projectId) projectId = projectId.toString().trim();
            window.projectId = projectId;
            window.projectName = projectName;
        } catch (scriptError) {
            console.warn('Scripting failed, trying fallback API...', scriptError);
            // Fallback: Try to get project from server directly if script fails
            try {
                const srvResp = await fetch(`${serverBase}/api/projects/current`);
                const srvData = await srvResp.json();
                window.projectId = srvData.id;
                window.projectName = srvData.name;
            } catch(e) {}
        }
        
        if (!window.projectId) {
            projectInfo.innerHTML = '<span style="color:#94a3b8">프로젝트를 선택해주세요 (localhost:8000)</span>';
            return;
        }

        projectInfo.innerText = `Project: ${window.projectName || window.projectId}`;
        statusBadge.innerText = 'Connected';
        statusBadge.style.color = '#10b981';

        const pResp = await fetch(`${serverBase}/api/projects/${window.projectId}/image-prompts`);
        const pData = await pResp.json();

        if (pData.status === 'ok' && pData.prompts) {
            renderPrompts(pData.prompts, window.projectId, window.serverBase);
        }

    } catch (error) {
        console.error('Fatal Bridge Error:', error);
        statusBadge.innerText = 'Check Permission';
        
        if (error.message.includes('permission') || error.message.includes('access') || error.message.includes('manifest')) {
            projectInfo.innerHTML = `
                <div style="color:#f87171; font-size:11px; margin-bottom:8px;">⚠️ Google Flow 접근 권한이 제한됨</div>
                <button id="grant-btn" style="background:#3b82f6; color:white; border:none; padding:10px; border-radius:8px; cursor:pointer; width:100\%; font-weight:600;">
                    🔓 모든 권한 강제 승인하기
                </button>
            `;
            document.getElementById('grant-btn').onclick = async () => {
                try {
                    const granted = await chrome.permissions.request({
                        origins: ['https://labs.google/*', 'http://localhost:8000/*']
                    });
                    if (granted) {
                        alert('권한이 승인되었습니다. 페이지를 새로고침(F5) 해주세요.');
                        window.location.reload();
                    }
                } catch(e) {
                    alert('권한 요청 실패: ' + e.message + '\n\n확장 프로그램 페이지(chrome://extensions)에서 "모든 사이트 허용"을 켜주세요.');
                }
            };
        } else {
            projectInfo.innerHTML = `<span style="color:#ef4444">오류: ${error.message}</span>`;
        }
    }
});

function renderPrompts(prompts, projectId, serverBase) {
    const list = document.getElementById('prompt-list');
    list.innerHTML = '';
    _sceneCount = prompts.length;

    prompts.forEach((p, i) => {
        const card = document.createElement('div');
        card.className = 'prompt-card';
        
        const text = p.flow_prompt || p.prompt_en || '';
        // Ensure sceneNum is just the number, no 'Scene ' prefix
        let sceneNum = p.scene_number;
        if (typeof sceneNum === 'string') {
            const match = sceneNum.match(/\d+/);
            sceneNum = match ? match[0] : (i + 1).toString();
        } else if (!sceneNum) {
            sceneNum = (i + 1).toString();
        }
        
        card.innerHTML = `
            <div class="prompt-header">
                <div style="display:flex; align-items:center; gap:8px;">
                    <input type="checkbox" class="scene-checkbox" data-scene="${sceneNum}" checked>
                    <span class="scene-num">Scene ${sceneNum}</span>
                </div>
                <div class="actions">
                    <button class="action-btn look-btn" id="look-${sceneNum}" title="위치 확인">👀</button>
                    <button class="action-btn pick-btn" id="pick-${sceneNum}">영상 회수</button>
                    <button class="action-btn fill-btn" data-text="${encodeURIComponent(text)}">입력</button>
                </div>
            </div>
            <div class="prompt-text">${text}</div>
        `;
        list.appendChild(card);

        // 위치 확인 로직
        card.querySelector(`#look-${sceneNum}`).onclick = async (e) => {
            const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
            if (tab) {
                chrome.tabs.sendMessage(tab.id, { 
                    action: 'show_in_flow', 
                    prompt: text 
                });
            }
        };

        // 영상 회수 로직 (Ensure no double listeners)
        const pickBtn = card.querySelector(`#pick-${sceneNum}`);
        pickBtn.onclick = null; // Clear existing
        pickBtn.onclick = async (e) => {
            console.log(`[v16] Manual pick triggered for Scene ${sceneNum}`);
            const btn = e.target;
            btn.innerText = '가져오는 중...';
            btn.disabled = true;

            try {
                // 1. 구글 Flow 탭에서 영상 데이터 가져오기
                const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
                if (!tab || !tab.url.includes('labs.google')) {
                    alert('Google Flow 페이지를 활성화해주세요.');
                    return;
                }

                try {
                    await ensureContentScript(tab.id);
                } catch(e) {
                    alert(e.message);
                    btn.innerText = '실패 (권한)';
                    btn.disabled = false;
                    return;
                }

                chrome.tabs.sendMessage(tab.id, { 
                    action: 'collect_video',
                    prompt: text,
                    index: i 
                }, async (response) => {
                    if (chrome.runtime.lastError || !response || response.status !== 'ok') {
                        const errorMsg = response?.message || '영상을 찾지 못했습니다. 구글 Flow 화면을 활성화하고 재시도하세요.';
                        statusBadge.innerText = 'Collect Fail';
                        projectInfo.innerText = errorMsg;
                        btn.innerText = '실패 (재시도)';
                        btn.disabled = false;
                        return;
                    }

                    // 2. 서버로 전송 (Base64 -> Blob -> File)
                    try {
                        const blobResponse = await fetch(response.data);
                        const blob = await blobResponse.blob();
                        
                        // Determine extension
                        let ext = '.mp4';
                        if (blob.type.includes('image')) ext = '.png';
                        else if (blob.type.includes('webm')) ext = '.webm';
                        
                        console.log(`[Pick] Uploading Scene ${sceneNum} to Project ${window.projectId}...`);
                        
                        const formData = new FormData();
                        formData.append('file', blob, `scene_${sceneNum}${ext}`);

                        const targetUrl = `${window.serverBase}/api/upload-video-to-project/${window.projectId}/${sceneNum}`;
                        console.log(`[Pick] Target URL: ${targetUrl}`);
                        
                        const uploadResp = await fetch(targetUrl, {
                            method: 'POST',
                            body: formData
                        });

                        if (uploadResp.ok) {
                            btn.innerText = '완료 ✅';
                            btn.style.background = '#10b981';
                        } else {
                            let errorDetail = '';
                            try {
                                const errJson = await uploadResp.json();
                                errorDetail = errJson.error || errJson.message || JSON.stringify(errJson);
                            } catch(e) {
                                errorDetail = await uploadResp.text();
                            }
                            throw new Error(`Upload failed (${uploadResp.status}): ${errorDetail}`);
                        }
                    } catch (err) {
                        console.error('Upload error:', err);
                        alert('서버 전송 실패: ' + err.message);
                        btn.innerText = '전송 실패';
                        btn.disabled = false;
                    }
                });
            } catch (err) {
                alert('오류: ' + err.message);
                btn.innerText = '오류';
                btn.disabled = false;
            }
        };
    });

    // 입력 버튼 바인딩
    document.querySelectorAll('.fill-btn').forEach(btn => {
        btn.onclick = async () => {
            const val = decodeURIComponent(btn.dataset.text);
            const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
            if (tab && tab.url.includes('labs.google')) {
                try {
                    await ensureContentScript(tab.id);
                    chrome.tabs.sendMessage(tab.id, { action: 'fill_prompt', text: val });
                    btn.innerText = 'Filled!';
                    setTimeout(() => btn.innerText = '입력', 2000);
                } catch(e) {
                    alert(e.message);
                }
            } else {
                alert('Google Flow 페이지에서 실행해주세요.');
            }
        };
    });
}


// ── Page Scan Debug Button ────────────────────────────
document.getElementById('btn-scan-page')?.addEventListener('click', async () => {
    const scanDiv = document.getElementById('scan-result');
    scanDiv.style.display = 'block';
    scanDiv.textContent = '🔍 스캔 중...';
    
    try {
        // Get the active tab first to show its URL
        const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
        const tabUrl = activeTab?.url || '알 수 없음';
        
        scanDiv.innerHTML = `<b style="color:#f59e0b">현재 탭 URL:</b><br>${tabUrl}<br><br>`;
        
        if (!activeTab) {
            scanDiv.textContent += '❌ 활성 탭을 찾을 수 없습니다.';
            return;
        }
        
        // Inject and execute scan script directly
        const results = await chrome.scripting.executeScript({
            target: { tabId: activeTab.id },
            func: () => {
                const btns = Array.from(document.querySelectorAll('button, [role="button"]'))
                    .map(b => ({
                        text: (b.innerText || '').trim().substring(0, 50),
                        aria: b.getAttribute('aria-label') || '',
                        title: b.title || ''
                    }))
                    .filter(b => b.text || b.aria || b.title);
                return { url: location.href, buttons: btns };
            }
        });
        
        const data = results?.[0]?.result;
        const btns = data?.buttons || [];
        
        if (btns.length > 0) {
            scanDiv.innerHTML += `<b style="color:#6366f1">🔍 버튼 ${btns.length}개 발견:</b><br>` + 
                btns.slice(0, 40).map(b => 
                    `<div style="border-bottom:1px solid #1e293b;padding:2px 0;">text="${b.text}" aria="${b.aria}"</div>`
                ).join('');
        } else {
            scanDiv.innerHTML += '버튼을 찾지 못했습니다.';
        }
    } catch(e) {
        const scanDiv2 = document.getElementById('scan-result');
        scanDiv2.innerHTML = `<b style="color:#ef4444">❌ 오류:</b> ${e.message}<br><br>` +
            `<b>해결방법:</b><br>` +
            `1. chrome://extensions/ 에서 확장프로그램 새로고침<br>` +
            `2. Google Flow 탭 새로고침 (F5)<br>` +
            `3. 현재 탭이 Google Flow인지 확인`;
    }
});

let isBatchRunning = false;
let _sceneCount = 0; // 전체 씬 개수

document.getElementById('batch-image-all').onclick = () => startBatch('image');
document.getElementById('batch-video-all').onclick = () => startBatch('video');
document.getElementById('batch-animate-all').onclick = () => startBatchAnimate();
document.getElementById('batch-stop').onclick = () => {
    isBatchRunning = false;
    statusBadge.innerText = 'Stopping...';
    document.getElementById('batch-stop').style.display = 'none';
};
document.getElementById('select-all-scenes').onchange = (e) => {
    document.querySelectorAll('.scene-checkbox').forEach(cb => cb.checked = e.target.checked);
};

// ── 영상 포착 패널 ──
document.getElementById('btn-refresh-videos').onclick = () => refreshCapturedVideos();
document.getElementById('btn-clear-videos').onclick = async () => {
    try {
        await chrome.runtime.sendMessage({ action: 'clear_captured_videos' });
        document.getElementById('captured-video-list').innerHTML = '초기화 완료. Google Flow에서 영상을 재생하면 여기에 표시됩니다.';
    } catch(e) {
        document.getElementById('captured-video-list').innerHTML = '<span style="color:#ef4444">Background 연결 실패. 확장 프로그램을 새로고침해주세요.</span>';
    }
};

async function refreshCapturedVideos() {
    const container = document.getElementById('captured-video-list');
    container.innerHTML = '<span style="color:#f59e0b">로딩 중...</span>';

    try {
        // 현재 활성 탭의 tabId를 보내서 해당 탭의 영상만 가져옴
        const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
        const response = await chrome.runtime.sendMessage({
            action: 'get_captured_videos',
            tabId: activeTab?.id
        });
        const videos = response?.videos || [];

        if (videos.length === 0) {
            container.innerHTML = '포착된 영상이 없습니다.<br><span style="font-size:10px;">Google Flow에서 영상을 한 번 재생(클릭)하면 자동 포착됩니다.</span>';
            return;
        }

        // 중복 제거
        const unique = [];
        const seen = new Set();
        for (const v of videos) {
            if (!seen.has(v.url)) {
                seen.add(v.url);
                unique.push(v);
            }
        }

        container.innerHTML = '';

        unique.forEach((video, idx) => {
            const item = document.createElement('div');
            item.className = 'video-item';
            item.style.flexWrap = 'wrap';

            // 생성 시각 표시
            const timeStr = new Date(video.timestamp).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });

            // 씬 선택 드롭다운 (순서대로 자동 매칭)
            let sceneOptions = '<option value="">씬 선택</option>';
            for (let s = 1; s <= Math.max(_sceneCount, 20); s++) {
                const selected = (idx + 1 === s && s <= _sceneCount) ? ' selected' : '';
                sceneOptions += `<option value="${s}"${selected}>Scene ${s}</option>`;
            }

            item.innerHTML = `
                <span style="font-weight:700; color:#f59e0b; min-width:20px;">#${idx + 1}</span>
                <span style="font-size:10px; color:#64748b;">${timeStr}</span>
                <button class="preview-btn" style="background:rgba(99,102,241,0.2); color:#818cf8; border:1px solid rgba(99,102,241,0.3); padding:3px 8px; border-radius:5px; font-size:10px; cursor:pointer;">▶ 미리보기</button>
                <select class="scene-select">${sceneOptions}</select>
                <button class="upload-scene-btn" data-idx="${idx}">업로드</button>
                <div class="preview-area" style="display:none; width:100%; margin-top:6px;"></div>
            `;
            container.appendChild(item);

            // 미리보기 토글
            item.querySelector('.preview-btn').onclick = (e) => {
                const area = item.querySelector('.preview-area');
                if (area.style.display === 'none') {
                    area.style.display = 'block';
                    area.innerHTML = `<video src="${video.url}" controls autoplay muted style="width:100%; max-height:180px; border-radius:6px; background:#000;"></video>`;
                    e.target.textContent = '✕ 닫기';
                    e.target.style.background = 'rgba(239,68,68,0.2)';
                    e.target.style.color = '#f87171';
                    e.target.style.borderColor = 'rgba(239,68,68,0.3)';
                } else {
                    area.style.display = 'none';
                    area.innerHTML = '';
                    e.target.textContent = '▶ 미리보기';
                    e.target.style.background = 'rgba(99,102,241,0.2)';
                    e.target.style.color = '#818cf8';
                    e.target.style.borderColor = 'rgba(99,102,241,0.3)';
                }
            };

            // 업로드 버튼
            item.querySelector('.upload-scene-btn').onclick = async (e) => {
                const btn = e.target;
                const select = item.querySelector('.scene-select');
                const sceneNum = select.value;

                if (!sceneNum) {
                    alert('씬 번호를 선택해주세요.');
                    return;
                }
                if (!window.projectId) {
                    alert('프로젝트가 선택되지 않았습니다.');
                    return;
                }

                btn.disabled = true;
                btn.innerText = '전송중...';

                try {
                    // 영상 다운로드
                    const res = await fetch(video.url);
                    if (!res.ok) throw new Error(`HTTP ${res.status}`);
                    const blob = await res.blob();

                    let ext = '.mp4';
                    if (blob.type.includes('webm')) ext = '.webm';
                    else if (blob.type.includes('image')) ext = '.png';

                    // 서버로 업로드
                    const formData = new FormData();
                    formData.append('file', blob, `scene_${sceneNum}${ext}`);

                    const uploadResp = await fetch(
                        `${window.serverBase}/api/upload-video-to-project/${window.projectId}/${sceneNum}`,
                        { method: 'POST', body: formData }
                    );

                    if (uploadResp.ok) {
                        btn.innerText = '완료!';
                        btn.style.background = '#6366f1';
                        item.style.borderColor = '#10b981';
                    } else {
                        const errText = await uploadResp.text();
                        throw new Error(errText);
                    }
                } catch (err) {
                    console.error('Upload error:', err);
                    btn.innerText = '실패';
                    btn.style.background = '#ef4444';
                    btn.disabled = false;
                    alert('업로드 실패: ' + err.message);
                }
            };
        });

        // 일괄 업로드 버튼 추가
        if (unique.length > 1) {
            const batchDiv = document.createElement('div');
            batchDiv.style.cssText = 'margin-top:8px; text-align:center;';
            batchDiv.innerHTML = `<button id="btn-batch-upload" style="background:#f59e0b; color:white; border:none; padding:6px 16px; border-radius:6px; font-size:11px; cursor:pointer; font-weight:600;">순서대로 일괄 업로드 (영상1→Scene1, 영상2→Scene2...)</button>`;
            container.appendChild(batchDiv);

            document.getElementById('btn-batch-upload').onclick = async () => {
                const btn = document.getElementById('btn-batch-upload');
                btn.disabled = true;
                btn.innerText = '업로드 중...';

                const items = container.querySelectorAll('.video-item');
                let success = 0;

                for (let i = 0; i < items.length; i++) {
                    const sceneNum = i + 1;
                    const uploadBtn = items[i].querySelector('.upload-scene-btn');
                    const select = items[i].querySelector('.scene-select');

                    // 씬 번호 자동 설정
                    select.value = sceneNum.toString();

                    // 클릭 시뮬레이션
                    uploadBtn.click();

                    // 완료 대기
                    await new Promise(r => setTimeout(r, 3000));
                    if (uploadBtn.innerText === '완료!') success++;
                }

                btn.innerText = `완료! (${success}/${items.length})`;
            };
        }

    } catch(e) {
        container.innerHTML = `<span style="color:#ef4444">오류: ${e.message}</span><br><span style="font-size:10px;">확장 프로그램을 새로고침(chrome://extensions)해주세요.</span>`;
    }
}

// 팝업 열릴 때 자동 새로고침
setTimeout(() => refreshCapturedVideos(), 500);

async function startBatch(mode) {
    if (isBatchRunning) return;
    isBatchRunning = true;
    
    // UI Update
    document.getElementById('batch-stop').style.display = 'flex';
    document.querySelectorAll('.batch-btn:not(.btn-stop)').forEach(b => b.disabled = true);

    const cards = document.querySelectorAll('.prompt-card');
    
    for (const card of cards) {
        if (!isBatchRunning) {
            console.log('Batch stopped by user.');
            break;
        }

        // Skip if not checked
        const checkbox = card.querySelector('.scene-checkbox');
        if (!checkbox || !checkbox.checked) continue;

        // Robust extraction of scene number (digits only)
        let sceneNum = card.querySelector('.scene-num').innerText.match(/\d+/);
        sceneNum = sceneNum ? sceneNum[0] : (i + 1).toString();
        
        const promptText = card.querySelector('.prompt-text').innerText;
        console.log(`[Batch] Scene ${sceneNum} - Project: ${window.projectId}`);
        
        // Show running status
        card.style.borderColor = '#3b82f6';
        card.style.boxShadow = '0 0 10px rgba(59, 130, 246, 0.3)';
        
        try {
            const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
            if (!tab || !tab.url.includes('labs.google')) {
                statusBadge.innerText = 'Tab Error';
                projectInfo.innerText = 'Google Flow 페이지가 활성화되어 있지 않습니다.';
                break;
            }

            await ensureContentScript(tab.id);

            console.log(`Starting generation for Scene ${sceneNum}...`);
            // 1. Fill and click generate
            const response = await chrome.tabs.sendMessage(tab.id, { 
                action: 'fill_and_generate', 
                text: promptText,
                mode: mode
            });

            if (response && response.status === 'ok') {
                console.log(`Generation completed for Scene ${sceneNum}.`);
                
                // 2. Auto-collect if video mode
                if (mode === 'video') {
                    console.log(`Collecting video for Scene ${sceneNum}...`);
                    await performAutoCollect(card, sceneNum);
                }
                card.style.borderColor = '#10b981';
                card.style.boxShadow = 'none';
            } else {
                console.error(`Error in Scene ${sceneNum}:`, response);
                card.style.borderColor = '#ef4444';
                card.style.boxShadow = 'none';
                const msg = response && typeof response === 'object' ? (response.message || JSON.stringify(response)) : String(response);
                statusBadge.innerText = 'Scene Error';
                projectInfo.innerText = `장면 ${sceneNum} 오류: ${msg}`;
                break; // Stop batch on error
            }
        } catch (e) {
            console.error(`Batch error on Scene ${sceneNum}:`, e);
            card.style.borderColor = '#ef4444';
            card.style.boxShadow = 'none';
            statusBadge.innerText = 'System Error';
            projectInfo.innerText = `장면 ${sceneNum} 시스템 오류: ${e.message}`;
            break;
        }
        
        // Brief pause between tasks
        if (isBatchRunning) {
            console.log('Waiting 3 seconds before next scene...');
            await new Promise(r => setTimeout(r, 3000));
        }
    }

    isBatchRunning = false;
    document.getElementById('batch-stop').style.display = 'none';
    document.querySelectorAll('.batch-btn').forEach(b => b.disabled = false);
    
    // Reset borders
    cards.forEach(card => card.style.boxShadow = 'none');
}

async function startBatchAnimate() {
    if (isBatchRunning) return;
    
    // Collect video prompts from cards
    const cardEls = document.querySelectorAll('.prompt-card');
    const prompts = Array.from(cardEls).map(card => {
        return card.querySelector('.prompt-text')?.innerText || '';
    }); // Don't filter, keep indices aligned with scenes

    if (prompts.length === 0) {
        statusBadge.innerText = 'Empty Project';
        projectInfo.innerText = '장면 리스트가 비어있습니다.';
        return;
    }
    
    isBatchRunning = true;
    document.getElementById('batch-stop').style.display = 'flex';
    document.querySelectorAll('.batch-btn:not(.btn-stop)').forEach(b => b.disabled = true);
    
    try {
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        if (!tab) {
            alert('Google Flow 탭을 찾을 수 없습니다.');
            return;
        }
        
        await ensureContentScript(tab.id);
        
        await chrome.scripting.executeScript({
            target: { tabId: tab.id },
            func: () => { window._animateRunning = true; }
        });
        
        // Pass the collected prompts to the content script
        const response = await chrome.tabs.sendMessage(tab.id, { 
            action: 'animate_all',
            prompts: prompts 
        });
        
        if (response) {
            if (response.status === 'error') {
                statusBadge.innerText = 'Error';
                projectInfo.innerText = response.message;
            } else {
                statusBadge.innerText = 'Finished';
                projectInfo.innerText = response.message || '작업이 완료되었습니다.';
            }
        }
        
    } catch(e) {
        statusBadge.innerText = 'Error';
        projectInfo.innerText = '오류: ' + e.message;
    } finally {
        // CRITICAL: Always reset UI state
        isBatchRunning = false;
        const stopBtn = document.getElementById('batch-stop');
        if (stopBtn) stopBtn.style.display = 'none';
        document.querySelectorAll('.batch-btn').forEach(b => b.disabled = false);
        
        // Clear running flag on the page
        try {
            const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
            if (tab) {
                await chrome.scripting.executeScript({
                    target: { tabId: tab.id },
                    func: () => { window._animateRunning = false; }
                });
            }
        } catch(e) {}
    }
}


async function startBatchCollect() {
    if (isBatchRunning) return;
    if (!window.projectId) {
        alert('프로젝트가 선택되지 않았습니다.');
        return;
    }
    
    isBatchRunning = true;
    const stopBtn = document.getElementById('batch-stop');
    if (stopBtn) stopBtn.style.display = 'flex';
    document.querySelectorAll('.batch-btn:not(.btn-stop)').forEach(b => b.disabled = true);
    
    const cards = document.querySelectorAll('.prompt-card');
    statusBadge.innerText = 'Collecting...';
    console.log(`[v5] [BatchCollect] Starting collection for ${cards.length} scenes...`);

    try {
        for (const card of cards) {
            if (!isBatchRunning) break;
            
            const checkbox = card.querySelector('.scene-checkbox');
            if (checkbox && !checkbox.checked) continue;

            let sceneNum = card.querySelector('.scene-num').innerText.match(/\d+/);
            sceneNum = sceneNum ? sceneNum[0] : '1';

            card.style.borderColor = '#f59e0b';
            statusBadge.innerText = `Scene ${sceneNum}...`;
            console.log(`[v5] [BatchCollect] Collecting Scene ${sceneNum}...`);
            
            await performAutoCollect(card, sceneNum);
            
            card.style.borderColor = '#10b981';
            await new Promise(r => setTimeout(r, 800));
        }
    } catch (e) {
        console.error('[v5] Batch collect error:', e);
    } finally {
        isBatchRunning = false;
        if (stopBtn) stopBtn.style.display = 'none';
        document.querySelectorAll('.batch-btn').forEach(b => b.disabled = false);
        statusBadge.innerText = 'Connected';
    }
}

// Wrapper to programmatically trigger the collect logic we already wrote
async function performAutoCollect(card, sceneNum) {
    const pickBtn = card.querySelector(`#pick-${sceneNum}`);
    if (pickBtn) {
        return new Promise(resolve => {
            // override the default alert/behavior to be non-blocking in batch mode
            const originalClick = pickBtn.onclick;
            
            // Just simulate a click, but since existing click is async, we need a way to know it finished.
            // A simpler approach is to repeat the fetch logic here, or just wrap it in a setTimeout for now 
            // relying on the original UI logic. For true automation, repeating the collect logic is safer.
            
            // To be safe and clean, let's trigger it and wait 10 seconds for upload
            // The user will see the button states changing.
            pickBtn.click(); 
            
            // Check button text periodically to see if it finished (완료 ✅ or 실패)
            let checkInterval = setInterval(() => {
                if (pickBtn.innerText.includes('완료') || pickBtn.innerText.includes('실패') || pickBtn.innerText.includes('오류')) {
                    clearInterval(checkInterval);
                    resolve();
                }
            }, 1000);
            
            // Timeout after 60 seconds
            setTimeout(() => {
                clearInterval(checkInterval);
                resolve();
            }, 60000);
        });
    }
}

// =====================================
// HELPER: Auto-inject content script
// =====================================
async function ensureContentScript(tabId) {
    try {
        await chrome.tabs.sendMessage(tabId, { action: 'ping' });
    } catch (e) {
        if (e.message.includes('Receiving end does not exist')) {
            console.log('Injecting content script dynamically...');
            try {
                await chrome.scripting.executeScript({
                    target: { tabId: tabId },
                    files: ['content.js']
                });
                await new Promise(r => setTimeout(r, 300)); // wait for init
            } catch (err) {
                console.error('Failed to inject script:', err);
                throw new Error("탭에 권한이 없습니다. (페이지 새로고침 한 번 해주세요)");
            }
        } else {
            throw e;
        }
    }
}

// =====================================
// 이미지 포착 패널 (퍼블리시 허브 연동)
// =====================================
document.getElementById('btn-refresh-images')?.addEventListener('click', refreshCapturedImages);
document.getElementById('btn-clear-images')?.addEventListener('click', async () => {
    try {
        await chrome.runtime.sendMessage({ action: 'clear_captured_images' });
        document.getElementById('captured-image-list').innerHTML = '초기화 완료.';
    } catch(e) {
        document.getElementById('captured-image-list').innerHTML = '<span style="color:#ef4444">연결 실패</span>';
    }
});

async function refreshCapturedImages() {
    const container = document.getElementById('captured-image-list');
    if (!container) return;
    container.innerHTML = '<span style="color:#10b981">로딩 중...</span>';

    try {
        const response = await chrome.runtime.sendMessage({ action: 'get_captured_images' });
        const images = response?.images || [];

        if (images.length === 0) {
            container.innerHTML = '포착된 이미지가 없습니다.<br><span style="font-size:10px;">Google ImageFX에서 이미지를 생성하면 자동 포착됩니다.</span>';
            return;
        }

        container.innerHTML = '';
        images.forEach((img, idx) => {
            const timeStr = new Date(img.timestamp).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
            const sizeKB = img.size ? `${(img.size / 1024).toFixed(0)}KB` : '?';
            const item = document.createElement('div');
            item.style.cssText = 'display:flex; align-items:center; gap:8px; padding:6px; margin-bottom:4px; background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.08); border-radius:8px; flex-wrap:wrap;';
            item.innerHTML = `
                <span style="font-weight:700; color:#10b981; min-width:20px;">#${idx + 1}</span>
                <span style="font-size:10px; color:#64748b;">${timeStr}</span>
                <span style="font-size:9px; padding:2px 6px; border-radius:4px; background:rgba(16,185,129,0.2); color:#6ee7b7;">${sizeKB}</span>
                <button class="img-preview-btn" style="background:rgba(99,102,241,0.2); color:#818cf8; border:1px solid rgba(99,102,241,0.3); padding:3px 8px; border-radius:5px; font-size:10px; cursor:pointer;">미리보기</button>
                <button class="img-copy-btn" style="background:#10b981; color:white; border:none; padding:3px 10px; border-radius:5px; font-size:10px; cursor:pointer; font-weight:600;">URL 복사</button>
                <div class="img-preview-area" style="display:none; width:100%; margin-top:6px;"></div>
            `;
            container.appendChild(item);

            item.querySelector('.img-preview-btn').onclick = (e) => {
                const area = item.querySelector('.img-preview-area');
                if (area.style.display === 'none') {
                    area.style.display = 'block';
                    area.innerHTML = `<img src="${img.url}" style="width:100%; max-height:180px; object-fit:contain; border-radius:6px; background:#000;">`;
                    e.target.textContent = '닫기';
                } else {
                    area.style.display = 'none';
                    area.innerHTML = '';
                    e.target.textContent = '미리보기';
                }
            };

            item.querySelector('.img-copy-btn').onclick = () => {
                navigator.clipboard.writeText(img.url).then(() => {
                    const btn = item.querySelector('.img-copy-btn');
                    btn.textContent = '복사됨!';
                    setTimeout(() => { btn.textContent = 'URL 복사'; }, 1500);
                });
            };
        });
    } catch(e) {
        container.innerHTML = `<span style="color:#ef4444">오류: ${e.message}</span>`;
    }
}

// 팝업 열릴 때 이미지도 자동 새로고침
setTimeout(() => refreshCapturedImages(), 700);
