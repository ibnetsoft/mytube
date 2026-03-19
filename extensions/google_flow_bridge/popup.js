let statusBadge, projectInfo, promptList;
window.projectId = null;
window.projectName = null;
window.serverBase = 'http://localhost:8000';
let _isRunning = false;
let currentTab = 'image';
let currentPrompts = [];

document.addEventListener('DOMContentLoaded', async () => {
    promptList = document.getElementById('prompt-list');
    projectInfo = document.getElementById('project-info');
    statusBadge = document.getElementById('status-badge');

    // UI Bindings: Tabs
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.onclick = () => {
            const tab = btn.dataset.tab;
            if (currentTab === tab) return;
            switchTab(tab);
        };
    });

    const manualBtn = document.getElementById('manual-reconnect');
    if (manualBtn) {
        manualBtn.onclick = () => {
             console.log('[Bridge] Manual reconnect triggered');
             initializeBridge();
        };
    }
    
    if (statusBadge) {
        statusBadge.onclick = () => initializeBridge();
    }

    if (document.getElementById('btn-refresh-videos')) {
        document.getElementById('btn-refresh-videos').onclick = () => refreshCapturedVideos();
    }
    if (document.getElementById('btn-clear-videos')) {
        document.getElementById('btn-clear-videos').onclick = () => clearCapturedVideos();
    }
    if (document.getElementById('btn-refresh-images')) {
        document.getElementById('btn-refresh-images').onclick = () => refreshCapturedImages();
    }
    if (document.getElementById('btn-clear-images')) {
        document.getElementById('btn-clear-images').onclick = () => clearCapturedImages();
    }
    
    if (document.getElementById('batch-image-all')) {
        document.getElementById('batch-image-all').onclick = () => startBatch('image');
    }
    if (document.getElementById('batch-animate-all')) {
        document.getElementById('batch-animate-all').onclick = () => startBatchAnimate();
    }

    ['batch-stop-image', 'batch-stop-video'].forEach(id => {
        const btn = document.getElementById(id);
        if (btn) btn.onclick = () => {
             _isRunning = false;
             btn.classList.add('hidden');
        };
    });

    const selectAll = document.getElementById('select-all-scenes');
    if (selectAll) {
        selectAll.onchange = (e) => {
            const checked = e.target.checked;
            document.querySelectorAll('.scene-checkbox').forEach(cb => cb.checked = checked);
        };
    }

    initializeBridge();
    
    // Auto-refresh captured media on open
    setTimeout(() => {
        refreshCapturedVideos();
        refreshCapturedImages();
    }, 500);
});

function switchTab(tab) {
    currentTab = tab;
    // UI update
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
    document.getElementById('section-image').classList.toggle('hidden', tab !== 'image');
    document.getElementById('section-video').classList.toggle('hidden', tab !== 'video');
    
    // Label update
    const label = document.getElementById('label-select-all');
    if (label) {
        label.innerText = tab === 'image' ? '이미지 장면 일괄 선택' : '영상 장면 일괄 선택';
    }

    // Re-render prompts with current tab's specific text
    if (currentPrompts.length > 0) {
        renderPrompts(currentPrompts);
    }
}

async function initializeBridge() {
    if (!statusBadge) return;
    
    statusBadge.innerText = 'Searching...';
    statusBadge.style.color = '#f59e0b';
    projectInfo.innerHTML = `
        <div style="font-size:11px; color:#94a3b8;">피카디리 스튜디오 탭을 찾는 중...</div>
        <div style="font-size:9px; color:#64748b; margin-top:4px;">(localhost:8000 또는 127.0.0.1:8000)</div>
    `;

    try {
        const tabs = await chrome.tabs.query({});
        // Support common local patterns and ports (127.0.0.1 and localhost)
        // [REFINE] prioritize 127.0.0.1 first if multiple exist
        const platformTab = tabs.find(t => t && t.url && 
            (t.url.includes('127.0.0.1') || t.url.includes('localhost')) &&
            (t.url.includes(':8000') || t.url.includes(':5000'))
        );
        
        if (!platformTab) {
            statusBadge.innerText = 'Not Found';
            statusBadge.style.color = '#ef4444';
            projectInfo.innerHTML = `
                <div style="font-size:11px; color:#f87171; margin-bottom:8px;">피카디리 스튜디오 탭이 없습니다.</div>
                <div style="font-size:10px; color:#94a3b8; margin-bottom:10px;">브라우저에 스튜디오(127.0.0.1:8000)를 먼저 띄워주세요.</div>
                <button id="retry-btn" style="background:#3b82f6; color:white; border:none; padding:6px 12px; border-radius:6px; cursor:pointer; width:100%;">🔄 다시 찾기</button>
            `;
            const retry = document.getElementById('retry-btn');
            if (retry) retry.onclick = () => initializeBridge();
            return;
        }

        const url = new URL(platformTab.url);
        window.serverBase = `${url.protocol}//${url.host}`;
        console.log('[Bridge] Connecting to:', window.serverBase);
        
        statusBadge.innerText = 'Syncing...';
        projectInfo.innerHTML = `
            <div style="font-size:11px; color:#3b82f6;">${window.serverBase}</div>
            <div style="font-size:10px; color:#94a3b8;">프로젝트 정보를 가져오는 중...</div>
        `;

        let projectId = null;
        let projectName = null;

        try {
            const result = await chrome.scripting.executeScript({
                target: { tabId: platformTab.id },
                func: () => {
                    const pid = localStorage.getItem('currentProjectId');
                    // Look for the project name in the selector dropdown (the current visible text)
                    const ps = document.querySelector('#project-selector');
                    let pname = ps ? ps.options[ps.selectedIndex]?.text : '';
                    if (!pname || pname.includes('선택')) {
                        pname = document.title.replace(' - 피카디리 스튜디오', '').trim();
                    }
                    // Final cleanup: remove (done) etc if needed or show exactly as in UI
                    return { projectId: pid, projectName: pname };
                }
            });
            if (result && result[0] && result[0].result) {
                const data = result[0].result;
                projectId = data.projectId ? data.projectId.toString().trim() : null;
                projectName = data.projectName;
            }
        } catch (scriptError) {
            console.warn('Scripting failed, trying fallback API...', scriptError);
        }

        // 1. Fallback to 'current' if ID not found yet
        if (!projectId || projectId === "None" || projectId === "null") {
            try {
                const srvResp = await fetch(`${window.serverBase}/api/projects/current`);
                if (srvResp.ok) {
                    const srvData = await srvResp.json();
                    projectId = srvData.id;
                    projectName = srvData.name;
                }
            } catch(e) { console.error('API Fallback failed:', e); }
        }

        // 2. Definitive name fetch (to avoid tool-specific page titles)
        if (projectId && projectId !== "None" && projectId !== "null") {
            try {
                const pResp = await fetch(`${window.serverBase}/api/projects/${projectId}`);
                if (pResp.ok) {
                    const pData = await pResp.json();
                    if (pData && pData.name) projectName = pData.name;
                }
            } catch(e) { console.warn('Failed to fetch detailed project info:', e); }
        }
        
        if (!projectId || projectId === "None" || projectId === "null") {
            statusBadge.innerText = 'No Project';
            statusBadge.style.color = '#f59e0b';
            projectInfo.innerHTML = `
                <div style="font-size:11px; color:#3b82f6;">${window.serverBase}</div>
                <div style="font-size:11px; color:#94a3b8; margin:8px 0;">활성 프로젝트가 없습니다.</div>
                <div style="font-size:10px; color:#64748b; margin-bottom:10px;">스튜디오에서 프로젝트를 먼저 열어주세요.</div>
                <button id="retry-btn" style="background:#475569; color:white; border:none; padding:6px 12px; border-radius:6px; cursor:pointer; width:100%;">🔄 다시 확인</button>
            `;
            const retry = document.getElementById('retry-btn');
            if (retry) retry.onclick = () => initializeBridge();
            return;
        }

        window.projectId = projectId;
        window.projectName = projectName;
        
        // Update header
        const headerName = document.getElementById('header-project-name');
        if (headerName) headerName.innerText = projectName || 'Unnamed Project';
        
        // Compact info area
        projectInfo.innerHTML = `<div style="font-size:9px; color:#64748b; font-family:monospace; margin-top:2px;">Connected (ID: ${projectId})</div>`;

        statusBadge.innerText = 'Connected';
        statusBadge.style.color = '#10b981';

        try {
            const pResp = await fetch(`${window.serverBase}/api/projects/${window.projectId}/image-prompts`);
            const pData = await pResp.json();

            if (pData.status === 'ok' && pData.prompts) {
                renderPrompts(pData.prompts);
            } else {
                promptList.innerHTML = '<div class="empty">가져올 장면 프롬프트가 없습니다.</div>';
            }
        } catch (fetchErr) {
            promptList.innerHTML = `<div class="empty">장면 데이터를 불러오지 못했습니다.<br>(${fetchErr.message})</div>`;
        }

    } catch (error) {
        handleFatalError(error);
    }
}

function handleFatalError(error) {
    console.error('Fatal Bridge Error:', error);
    statusBadge.innerText = 'Error';
    statusBadge.style.color = '#ef4444';
    
    if (error.message.includes('permission') || error.message.includes('access')) {
        projectInfo.innerHTML = `
            <div style="color:#f87171; font-size:11px; margin-bottom:8px;">⚠️ 권한이 제한되었습니다.</div>
            <button id="grant-btn" style="background:#3b82f6; color:white; border:none; padding:8px; border-radius:6px; cursor:pointer; width:100%;">
                🔓 모든 권한 강제 승인
            </button>
        `;
        document.getElementById('grant-btn').onclick = async () => {
            const granted = await chrome.permissions.request({
                origins: ['https://labs.google/*', 'http://localhost:8000/*', 'http://127.0.0.1:8000/*']
            });
            if (granted) window.location.reload();
        };
    } else {
        projectInfo.innerHTML = `<div style="color:#ef4444; font-size:10px;">시스템 오류: ${error.message}</div>
        <button id="retry-btn" style="margin-top:5px; background:#475569; color:white; border:none; padding:4px; width:100%; border-radius:4px;">🔄 재시도</button>`;
        const retry = document.getElementById('retry-btn');
        if (retry) retry.onclick = () => initializeBridge();
    }
}

function renderPrompts(prompts) {
    currentPrompts = prompts; // Store for tab switching
    promptList.innerHTML = '';
    
    if (!prompts || prompts.length === 0) {
        promptList.innerHTML = '<div class="empty">가져올 장면 데이터가 없습니다.</div>';
        return;
    }

    prompts.forEach((p, i) => {
        const card = document.createElement('div');
        card.className = 'prompt-card';
        
        // Pick text: Image tab -> prompt_en / Video tab -> flow_prompt
        const text = (currentTab === 'image') 
            ? (p.prompt_en || p.prompt_ko || '') 
            : (p.flow_prompt || p.prompt_en || '');
            
        let sceneNum = p.scene_number || (i+1);
        const pickLabel = currentTab === 'image' ? '이미지 회수' : '영상 회수';

        // Thumbnail logic: Prefer tab-specific media
        let thumbPath = (currentTab === 'video') ? (p.video_url || p.image_url) : (p.image_url || p.video_url);
        let fullThumbUrl = '';
        let isVideoThumb = false;

        if (thumbPath) {
            fullThumbUrl = thumbPath.startsWith('http') ? thumbPath : `${window.serverBase}${thumbPath}`;
            isVideoThumb = thumbPath.toLowerCase().match(/\.(mp4|webm|mov|ogg)$/) || thumbPath.includes('video');
        }
        
        card.innerHTML = `
            <div class="prompt-header">
                <div>
                    <input type="checkbox" class="scene-checkbox" data-scene="${sceneNum}" checked>
                    <span class="scene-num">Scene ${sceneNum}</span>
                </div>
                <div class="actions">
                    <button class="action-btn pick-btn" id="pick-${sceneNum}">${pickLabel}</button>
                    <button class="action-btn fill-btn" data-text="${encodeURIComponent(text)}">입력</button>
                </div>
            </div>
            <div class="prompt-body">
                <div class="prompt-thumbnail ${fullThumbUrl ? 'has-media' : ''}" id="thumb-${sceneNum}" title="클릭하여 이 장면의 결과물을 페이지에서 직접 선택">
                    ${fullThumbUrl ? (isVideoThumb ? 
                        `<video src="${fullThumbUrl}" muted loop onmouseover="this.play()" onmouseout="this.pause()"></video>` : 
                        `<img src="${fullThumbUrl}">`) : ''}
                </div>
                <div class="prompt-text">${text}</div>
            </div>
        `;
        promptList.appendChild(card);

        // Hyper-Vision UI Bindings
        const triggerPick = async () => {
            const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
            if (!tab || !tab.url.includes('labs.google')) {
                alert('구글 생성 페이지(Flow/ImageFX) 탭을 활성화한 상태에서 눌러주세요.');
                return;
            }
            await ensureContentScript(tab.id);
            chrome.tabs.sendMessage(tab.id, { action: 'start_picker', sceneNum });
        };

        const pickBtn = card.querySelector(`#pick-${sceneNum}`);
        if (pickBtn) pickBtn.onclick = triggerPick;
        
        const thumbBox = card.querySelector(`#thumb-${sceneNum}`);
        if (thumbBox) thumbBox.onclick = triggerPick;
    });

    // Input Fill Action
    document.querySelectorAll('.fill-btn').forEach(btn => {
        btn.onclick = async () => {
            const val = decodeURIComponent(btn.dataset.text);
            const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
            if (tab && (tab.url.includes('labs.google') || tab.url.includes('google.com/search'))) {
                await ensureContentScript(tab.id);
                chrome.tabs.sendMessage(tab.id, { action: 'fill_prompt', text: val });
                btn.innerText = 'Filled!';
                setTimeout(() => btn.innerText = '입력', 2000);
            } else {
                alert('구글 생성 페이지(Flow/ImageFX)에서 실행해주세요.');
            }
        };
    });
}

function getUrlBase(url) {
    if (!url) return '';
    return url.split('#')[0];
}

function getMediaFilename(url, index) {
    try {
        const u = new URL(url);
        // ID extraction
        const docid = u.searchParams.get('docid') || u.searchParams.get('id');
        if (docid) return `Asset ${index} (ID: ${docid.substring(0, 6)})`;
        
        // Fallback: Path segments
        let pathParts = u.pathname.split('/');
        const longPart = pathParts.find(p => p.length > 20);
        if (longPart) return `Asset ${index} (pID: ${longPart.substring(0, 6)})`;
        
        // Final fallback: Use a simple hash of the URL to ensure it's not just "(new)"
        let hash = 0;
        for (let i = 0; i < url.length; i++) hash = ((hash << 5) - hash) + url.charCodeAt(i);
        return `Asset ${index} (h${Math.abs(hash % 1000)})`;
    } catch(e) { return `Asset ${index}`; }
}

// ────────────────────────────────────────────────────────
// Captured Media Management
// ────────────────────────────────────────────────────────
async function getMediaBlob(url, isVideo) {
    // If it's a blob url or a labs.google url, fetch it via the content script
    if (url.startsWith('blob:') || url.includes('google.com')) {
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        if (tab && tab.url.includes('labs.google')) {
            await ensureContentScript(tab.id);
            const resp = await chrome.tabs.sendMessage(tab.id, { action: 'get_media_blob', url, isVideo });
            if (resp && resp.status === 'ok') {
                const dataRes = await fetch(resp.data);
                return await dataRes.blob();
            } else {
                throw new Error(resp?.message || 'Content script fetch failed');
            }
        }
    }
    // Fallback: Direct fetch in popup
    const res = await fetch(url);
    return await res.blob();
}

async function refreshCapturedVideos() {
    const list = document.getElementById('captured-video-list');
    if (!list) return;
    list.innerHTML = '스캔 중...';
    
    chrome.runtime.sendMessage({ action: 'get_captured_videos' }, async (bgResp) => {
        let videos = bgResp?.videos || [];
        const seen = new Set(videos.map(v => getUrlBase(v.url)));
        
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        if (tab && tab.url.includes('labs.google')) {
            try {
                await ensureContentScript(tab.id);
                const domResp = await chrome.tabs.sendMessage(tab.id, { action: 'scan_media' });
                if (domResp?.videos) {
                    domResp.videos.forEach(v => {
                        const base = getUrlBase(v.url);
                        if (!seen.has(base)) {
                            videos.push({...v, isDom: true});
                            seen.add(base);
                        }
                    });
                }
            } catch(e) { console.warn('DOM scan failed:', e); }
        }

        if (videos.length === 0) {
            list.innerHTML = '포착된 영상이 없습니다.<br>(영상을 재생하거나 생성 후 눌러주세요)';
            return;
        }
        
        list.innerHTML = '';
        videos.forEach((v, i) => {
            const item = document.createElement('div');
            item.className = 'video-item';
            const sizeStr = v.size > 0 ? (v.size/1024/1024).toFixed(1) + 'MB' : (v.isDom ? 'Live View' : 'Unknown');
            const timeStr = new Date(v.timestamp).toLocaleTimeString();
            const fileName = getMediaFilename(v.url, i + 1);
            
            item.innerHTML = `
                <div class="preview-box">
                    <video src="${v.url}" muted loop onmouseover="this.play()" onmouseout="this.pause()"></video>
                </div>
                <div class="media-info">
                    <div class="url-text" title="${v.url}">${fileName}</div>
                    <div class="size-text">${timeStr} | ${sizeStr}</div>
                </div>
                <select class="scene-select"></select>
                <button class="upload-scene-btn">배정</button>
            `;
            
            const sel = item.querySelector('.scene-select');
            // If we have real prompts, use that length. If not, fallback to 20 but highlight the real ones.
            const totalScenes = currentPrompts.length > 0 ? currentPrompts.length : 20;
            for(let j=1; j<=totalScenes; j++) {
                const opt = document.createElement('option');
                opt.value = j; opt.innerText = `Scene ${j}`;
                sel.appendChild(opt);
            }
            
            item.querySelector('.upload-scene-btn').onclick = async (e) => {
                const sNum = sel.value;
                const btn = e.target;
                btn.innerText = '전송...';
                btn.disabled = true;
                
                try {
                    const blob = await getMediaBlob(v.url, true);
                    await uploadBlobToServer(blob, sNum, btn);
                } catch(err) {
                    btn.innerText = '실패 ('+err.message.substring(0,10)+')';
                    btn.disabled = false;
                    setTimeout(() => btn.innerText = '배정', 2000);
                }
            };
            list.appendChild(item);
        });
    });
}

async function refreshCapturedImages() {
    const list = document.getElementById('captured-image-list');
    if (!list) return;
    list.innerHTML = '스캔 중...';
    
    chrome.runtime.sendMessage({ action: 'get_captured_images' }, async (bgResp) => {
        let images = bgResp?.images || [];
        const seen = new Set(images.map(img => getUrlBase(img.url)));

        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        if (tab && tab.url.includes('labs.google')) {
            try {
                await ensureContentScript(tab.id);
                const domResp = await chrome.tabs.sendMessage(tab.id, { action: 'scan_media' });
                if (domResp?.images) {
                    domResp.images.forEach(img => {
                        const base = getUrlBase(img.url);
                        if (!seen.has(base)) {
                            images.push({...img, isDom: true});
                            seen.add(base);
                        }
                    });
                }
            } catch(e) { console.warn('DOM scan failed:', e); }
        }

        if (images.length === 0) {
            list.innerHTML = '포착된 이미지가 없습니다.';
            return;
        }
        list.innerHTML = '';
        images.forEach((img, i) => {
            const item = document.createElement('div');
            item.className = 'video-item';
            const sizeDisplay = img.isDom ? 'Display View' : (img.size/1024).toFixed(0) + 'KB';
            const fileName = getMediaFilename(img.url, i + 1);
            
            item.innerHTML = `
                <div class="preview-box"><img src="${img.url}"></div>
                <div class="media-info">
                    <div class="url-text" title="${img.url}">${fileName}</div>
                    <div class="size-text">${sizeDisplay}</div>
                </div>
                <select class="scene-select"></select>
                <button class="upload-scene-btn">배정</button>
            `;
            
            const sel = item.querySelector('.scene-select');
            const totalScenes = currentPrompts.length > 0 ? currentPrompts.length : 20;
            for(let j=1; j<=totalScenes; j++) {
                const opt = document.createElement('option');
                opt.value = j; opt.innerText = `Scene ${j}`;
                sel.appendChild(opt);
            }
            
            item.querySelector('.upload-scene-btn').onclick = async (e) => {
                const sNum = sel.value;
                const btn = e.target;
                btn.innerText = '전송...';
                btn.disabled = true;
                
                try {
                    const blob = await getMediaBlob(img.url, false);
                    await uploadBlobToServer(blob, sNum, btn);
                } catch(err) {
                    btn.innerText = '실패 ('+err.message.substring(0,10)+')';
                    btn.disabled = false;
                    setTimeout(() => btn.innerText = '배정', 2000);
                }
            };
            list.appendChild(item);
        });
    });
}

async function clearCapturedVideos() {
    chrome.runtime.sendMessage({ action: 'clear_captured_videos' }, () => refreshCapturedVideos());
}
async function clearCapturedImages() {
    chrome.runtime.sendMessage({ action: 'clear_captured_images' }, () => refreshCapturedImages());
}

async function uploadBlobToServer(blob, sceneNum, btn) {
    let ext = blob.type.includes('video') ? '.mp4' : '.png';
    const formData = new FormData();
    formData.append('file', blob, `scene_${sceneNum}${ext}`);
    const targetUrl = `${window.serverBase}/api/upload-video-to-project/${window.projectId}/${sceneNum}`;
    
    try {
        const resp = await fetch(targetUrl, { method: 'POST', body: formData });
        if (resp.ok) {
            btn.innerText = '완료 ✅';
            // Refresh logic: Refresh prompts to show new thumbnail
            setTimeout(() => { 
                btn.innerText = '배정'; 
                btn.disabled = false;
                initializeBridge(); 
            }, 1000);
        } else {
            btn.innerText = '전송 실패';
            btn.disabled = false;
        }
    } catch(e) {
        btn.innerText = '연결 오류';
        btn.disabled = false;
    }
}

// ────────────────────────────────────────────────────────
// Hyper-Vision Result Handler
// ────────────────────────────────────────────────────────
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg.action === 'manual_pick_result') {
        const { sceneNum, result } = msg;
        if (result && result.status === 'ok') {
            (async () => {
                try {
                    const blobRes = await fetch(result.data);
                    const blob = await blobRes.blob();
                    const btn = document.getElementById(`pick-${sceneNum}`);
                    if (btn) btn.innerText = '전송...';
                    await uploadBlobToServer(blob, sceneNum, btn);
                    if (btn) btn.innerText = '회수 완료';
                    sendResponse({ status: 'ok' });
                } catch (e) {
                    sendResponse({ status: 'error', message: e.message });
                }
            })();
            return true; // Keep channel open
        } else {
            sendResponse({ status: 'error' });
        }
    }
});

// ────────────────────────────────────────────────────────
// Batch Automation Logic
// ────────────────────────────────────────────────────────
async function startBatch(type) {
    if (_isRunning) return;
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !tab.url.includes('labs.google')) {
        alert('Google Flow/ImageFX 탭을 열어주세요.');
        return;
    }
    
    _isRunning = true;
    const stopBtn = document.getElementById(type === 'image' ? 'batch-stop-image' : 'batch-stop-video');
    const startBtn = document.getElementById(type === 'image' ? 'batch-image-all' : 'batch-video-all');
    
    if (stopBtn) stopBtn.classList.remove('hidden');
    if (startBtn) startBtn.classList.add('hidden');
    
    const selectedCbs = document.querySelectorAll('.scene-checkbox:checked');
    for (const cb of selectedCbs) {
        if (!_isRunning) break;
        const sceneNum = cb.dataset.scene;
        const card = cb.closest('.prompt-card');
        const fillBtn = card.querySelector('.fill-btn');
        const text = decodeURIComponent(fillBtn.dataset.text);
        
        card.style.background = 'rgba(245, 158, 11, 0.15)'; // Indicating generation in progress
        
        await ensureContentScript(tab.id);
        const action = 'fill_and_generate';
        
        try {
            const resp = await chrome.tabs.sendMessage(tab.id, { action, text: text, mode: type });
            console.log(`[Batch] Scene ${sceneNum} result:`, resp);
        } catch (e) {
            console.error(`[Batch] Scene ${sceneNum} error:`, e);
        }
        
        // Short breather before starting next task
        await new Promise(r => setTimeout(r, 2000));
        card.style.background = '';

    }
    
    _isRunning = false;
    if (stopBtn) stopBtn.classList.add('hidden');
    if (startBtn) startBtn.classList.remove('hidden');
    alert('작업이 완료되었습니다.');
}

async function startBatchAnimate() {
    if (_isRunning) return;
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !tab.url.includes('labs.google')) {
        alert('Google Flow/ImageFX 탭을 열어주세요.');
        return;
    }
    
    _isRunning = true;
    const stopBtn = document.getElementById('batch-stop-video');
    const startBtn = document.getElementById('batch-animate-all');
    
    if (stopBtn) stopBtn.classList.remove('hidden');
    if (startBtn) startBtn.classList.add('hidden');
    
    const selectedCbs = Array.from(document.querySelectorAll('.scene-checkbox:checked'));
    const prompts = selectedCbs.map(cb => {
        const card = cb.closest('.prompt-card');
        const fillBtn = card.querySelector('.fill-btn');
        return decodeURIComponent(fillBtn.dataset.text);
    });

    if (prompts.length === 0) {
        alert('선택된 장면이 없습니다.');
        _isRunning = false;
        if (stopBtn) stopBtn.classList.add('hidden');
        if (startBtn) startBtn.classList.remove('hidden');
        return;
    }
    
    await ensureContentScript(tab.id);
    const action = 'animate_all';
    
    try {
        const resp = await chrome.tabs.sendMessage(tab.id, { action, count: prompts.length, prompts: prompts });
        if (resp && resp.status === 'ok') {
            alert(resp.message || '사진을 영상으로 변환하는 작업이 완료되었습니다.');
        } else {
            alert('작업 중지/실패: ' + (resp?.message || '알 수 없는 오류'));
        }
    } catch (e) {
        console.error(`[Batch Animate] Error:`, e);
        alert('통신 오류: 구글 Flow 화면을 새로고침해주세요.');
    }
    
    _isRunning = false;
    if (stopBtn) stopBtn.classList.add('hidden');
    if (startBtn) startBtn.classList.remove('hidden');
}

async function ensureContentScript(tabId) {
    try {
        const resp = await chrome.tabs.sendMessage(tabId, { action: 'ping' });
        return resp;
    } catch (e) {
        return await chrome.scripting.executeScript({
            target: { tabId },
            files: ['content.js']
        });
    }
}
