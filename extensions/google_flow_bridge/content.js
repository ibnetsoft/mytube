// Version guard: prevent duplicate listeners from old+new content scripts
if (window._flowBridgeVersion && window._flowBridgeVersion >= 20) {
    console.log('%c[v20] Flow Bridge already loaded, skipping duplicate', 'color: #888');
} else {
window._flowBridgeVersion = 20;

console.log("%c[v20] 🚀 Google Flow Bridge: Hyper-Vision Active", "color: #ff00ff; font-weight: bold; font-size: 14px;");

let _lastClickedAsset = null;
let _lastCapturedUrl = null;
 // Track to prevent duplicates in batch

function trackImageHovers() {
    document.addEventListener('mouseover', (e) => {
        let el = e.target;
        for (let i = 0; i < 8; i++) {
            if (!el || el === document.body) break;
            if (el.tagName?.toLowerCase() === 'img' || 
                (el.tagName?.toLowerCase() !== 'button' && el.querySelector?.('img') && 
                 el.offsetWidth < 800 && el.offsetHeight < 600 && el.offsetHeight > 50)) {
                
                const img = el.tagName.toLowerCase() === 'img' ? el : el.querySelector('img');
                if (!img || !img.src || img.src.startsWith('data:') || !img.offsetParent) {
                    el = el.parentElement;
                    continue;
                }
                _lastClickedAsset = el;
                return;
            }
            el = el.parentElement;
        }
    }, { passive: true });
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', trackImageHovers);
} else {
    trackImageHovers();
}

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === 'ping') {
        sendResponse({ status: 'ok' });
    } else if (request.action === 'scan_media') {
        const videos = Array.from(document.querySelectorAll('video')).map(v => ({
            url: v.src || v.currentSrc || v.querySelector('source')?.src || '',
            type: 'video/mp4',
            timestamp: Date.now(),
            size: 0
        })).filter(v => v.url && !v.url.startsWith('data:'));
        
        const rawImages = Array.from(document.querySelectorAll('img')).map(i => ({
            i_elem: i, // keep reference for DOM context checks
            url: i.src || i.currentSrc || '',
            type: 'image/png',
            timestamp: Date.now(),
            size: (i.naturalWidth * i.naturalHeight) / 5
        }));

        const images = rawImages.filter(item => {
            const img = item.i_elem;
            if (!item.url || item.url.startsWith('data:')) return false;
            if (item.url.includes('/icon') || item.url.includes('logo') || item.url.includes('avatar') || item.url.includes('profile')) return false;
            if (item.size < 20000) return false; // Only capture substantial images

            // Filtering out Video posters (Google Flow Veo assets)
            let p = img.parentElement;
            for(let level=0; level<=3 && p; level++, p=p.parentElement) {
                if (['BODY','MAIN','ARTICLE','SECTION','FORM'].includes(p.tagName)) break;
                
                // If this tight container holds a video, the img is almost certainly its poster
                if (p.querySelector('video')) return false;
                
                // Fallback: Check for Veo watermark or duration pattern indicating a video player wrapper
                const txt = p.innerText || '';
                if ((txt.includes('Veo') || /\b0:\d\d\b/.test(txt)) && p.querySelector('svg')) {
                    return false;
                }
            }

            return true;
        }).map(item => {
            delete item.i_elem; // remove DOM reference before sending to background
            return item;
        });
        
        sendResponse({ videos, images });
        return true;
    } else if (request.action === 'fill_prompt') {
        fillFlowInput(request.text);
        sendResponse({status: 'ok'});
    } else if (request.action === 'collect_video') {
        // Reset tracker if it's the first scene of a batch or a single request
        if (request.index === 0 || request.index === undefined) _lastCapturedUrl = null;
        collectGeneratedVideo(request.prompt, request.index).then(sendResponse);
        return true; 
    } else if (request.action === 'fill_and_generate') {
        fillAndClick(request.text, request.mode).then(sendResponse);
        return true;
    } else if (request.action === 'animate_image') {
        animateImage(request.sceneNum, request.prompt).then(sendResponse);
        return true;
    } else if (request.action === 'animate_all') {
        animateAllImages(request.count, request.prompts).then(sendResponse);
        return true;
    } else if (request.action === 'show_in_flow') {
        showInFlow(request.prompt).then(sendResponse);
        return true;
    } else if (request.action === 'scan_page') {
        const btns = Array.from(document.querySelectorAll('button, [role="button"], a[href]'))
            .filter(b => b.offsetParent !== null)
            .map(b => ({
                tag: b.tagName,
                text: (b.innerText || '').trim().substring(0, 60),
                aria: b.getAttribute('aria-label') || '',
                title: b.title || '',
                href: b.href || '',
                cls: (b.className || '').substring(0, 40)
            }))
            .filter(b => b.text || b.aria || b.title);
        console.log('[FlowBridge] PAGE SCAN:', JSON.stringify(btns, null, 2));
        sendResponse({ status: 'ok', buttons: btns });
        return true;
    } else if (request.action === 'start_picker') {
        startHyperVision(request.sceneNum).then(sendResponse);
        return true;
    } else if (request.action === 'get_media_blob') {
        fetchAndReturn(request.url, request.isVideo).then(sendResponse);
        return true;
    }
});

async function fillFlowInput(text) {
    let input = null;
    
    const candidates = Array.from(document.querySelectorAll('textarea, input[type="text"], [contenteditable="true"], div[role="textbox"]'));
    candidates.sort((a, b) => b.getBoundingClientRect().top - a.getBoundingClientRect().top);

    for (const el of candidates) {
        const placeholder = (el.getAttribute('placeholder') || '').toLowerCase();
        const ariaLabel = (el.getAttribute('aria-label') || '').toLowerCase();
        const innerText = (el.innerText || '').toLowerCase();
        const id = (el.getAttribute('id') || '').toLowerCase();
        const className = (el.className || '').toLowerCase();

        if (id.startsWith('af-') || id.includes('bot') || className.includes('debug')) continue;
        if (id.includes('title') || className.includes('title') || placeholder.includes('title') || ariaLabel.includes('title')) continue;
        if (id.includes('recaptcha') || id.includes('bot') || id.startsWith('at-') || id.startsWith('af-')) continue;

        if (placeholder.includes('무엇을 만들고 싶으신가요') || 
            placeholder.includes('무엇을 만들고') || 
            placeholder.includes('tell us what to') ||
            placeholder.includes('create anything') ||
            placeholder.includes('enter a prompt') ||
            innerText.includes('프롬프트를 입력') ||
            className.includes('slate') ||
            ariaLabel.includes('prompt')) {
            input = el;
            break;
        }
    }

    if (!input && candidates.length > 0) {
        input = candidates.find(el => {
            const id = (el.getAttribute('id') || '').toLowerCase();
            const className = (el.className || '').toLowerCase();
            if (id.startsWith('af-') || id.startsWith('at-') || id.includes('bot') || id.includes('recaptcha') || id.includes('title') || className.includes('title')) return false;
            return el.tagName === 'TEXTAREA' || el.isContentEditable;
        });
    }

    if (input) {
        console.log('📝 Typing into:', input);
        input.focus();
        input.scrollIntoView({ block: 'center' });
        
        if (!input.isContentEditable) {
            const prototype = input.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
            const nativeSetter = Object.getOwnPropertyDescriptor(prototype, "value")?.set;
            if (nativeSetter) nativeSetter.call(input, text);
            else input.value = text;
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
        } else {
            // Natively safe for React Slate editors
            const clearEv = new InputEvent('beforeinput', { bubbles: true, cancelable: true, inputType: 'deleteContentBackward' });
            input.dispatchEvent(clearEv);
            if (!clearEv.defaultPrevented) {
                try { document.execCommand('selectAll', false, null); } catch(e) {}
                try { document.execCommand('delete', false, null); } catch(e) {}
            }

            const insertEv = new InputEvent('beforeinput', { bubbles: true, cancelable: true, data: text, inputType: 'insertText' });
            input.dispatchEvent(insertEv);
            if (!insertEv.defaultPrevented) {
                try { document.execCommand('insertText', false, text); } catch(e) {}
            }
            
            input.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: text }));
            input.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, key: ' ' }));
        }

        input.blur();
        await new Promise(r => setTimeout(r, 100));
        input.focus();
        await new Promise(r => setTimeout(r, 500));
        return true;
    }
    return false;
}

async function collectGeneratedVideo(targetPrompt, targetIndex) {
    try {
        const sceneDisplayNum = targetIndex + 1;
        console.log(`[v19] 🎯 Collecting Scene ${sceneDisplayNum}...`);

        // ══════════════════════════════════════════════════════
        // 전략 1: Background에서 네트워크 포착한 영상 URL 사용
        //   → DOM 클릭 불필요, 가장 안정적
        // ══════════════════════════════════════════════════════
        try {
            const bgResponse = await chrome.runtime.sendMessage({ action: 'get_captured_videos' });
            const capturedVideos = bgResponse?.videos || [];
            console.log(`[v19] 📡 Background captured ${capturedVideos.length} video URLs`);

            if (capturedVideos.length > 0) {
                // 가장 최근 영상들부터, 씬 순서대로 매칭
                // 중복 URL 제거
                const uniqueUrls = [];
                const seen = new Set();
                for (const v of capturedVideos) {
                    if (!seen.has(v.url)) {
                        seen.add(v.url);
                        uniqueUrls.push(v);
                    }
                }

                console.log(`[v19] 📡 Unique video URLs: ${uniqueUrls.length}`);
                uniqueUrls.forEach((v, i) => {
                    console.log(`[v19]   #${i}: ${v.contentType} ${(v.size/1024).toFixed(0)}KB ${v.url.substring(0, 100)}`);
                });

                if (uniqueUrls.length > 0) {
                    const idx = targetIndex;
                    if (idx >= uniqueUrls.length) {
                        return { status: 'error', message: `새로 생성된 영상을 발견하지 못했습니다. (필요: ${targetIndex+1}개, 발견: ${uniqueUrls.length}개)` };
                    }
                    let targetUrl = uniqueUrls[idx].url;

                    // 이전에 캡처한 URL과 같으면 다음 것 사용
                    if (targetUrl === _lastCapturedUrl && idx + 1 < uniqueUrls.length) {
                        targetUrl = uniqueUrls[idx + 1].url;
                    }

                    console.log(`[v19] 📡 Using network URL #${idx}: ${targetUrl.substring(0, 100)}`);

                    try {
                        const res = await fetch(targetUrl);
                        if (res.ok) {
                            const blob = await res.blob();
                            console.log(`[v19] 📦 Network download: ${blob.type} ${(blob.size / 1024).toFixed(1)}KB`);

                            if (blob.size > 5000) { // 5KB 이상이면 유효한 영상
                                _lastCapturedUrl = targetUrl;
                                const isVideo = blob.type.includes('video');

                                return new Promise((resolve) => {
                                    const reader = new FileReader();
                                    reader.onloadend = () => {
                                        const data = reader.result;
                                        if (!data || data.length < 2000) {
                                            resolve({ status: 'error', message: '데이터 변환 실패.' });
                                            return;
                                        }
                                        resolve({
                                            status: 'ok',
                                            data: data,
                                            type: blob.type,
                                            url: targetUrl,
                                            is_video: isVideo
                                        });
                                    };
                                    reader.onerror = () => resolve({ status: 'error', message: 'FileReader 오류.' });
                                    reader.readAsDataURL(blob);
                                });
                            } else {
                                console.log(`[v19] ⚠️ Network file too small (${blob.size}B), trying DOM...`);
                            }
                        }
                    } catch (fetchErr) {
                        console.warn(`[v19] ⚠️ Network URL fetch failed: ${fetchErr.message}, trying DOM...`);
                    }
                }
            }
        } catch (bgErr) {
            console.warn(`[v19] ⚠️ Background unavailable: ${bgErr.message}, trying DOM...`);
        }

        // ══════════════════════════════════════════════════════
        // 전략 2: DOM에서 직접 찾기 (폴백)
        //   → 페이지에 보이는 <video>, <img> 요소 사용
        // ══════════════════════════════════════════════════════
        console.log(`[v19] 🔄 Trying DOM fallback for Scene ${sceneDisplayNum}...`);

        // 페이지의 모든 미디어 수집
        const allMedia = Array.from(document.querySelectorAll('img, video')).filter(n => {
            const src = n.src || n.currentSrc || '';
            if (!src || src.startsWith('data:')) return false;
            const w = n.offsetWidth || n.naturalWidth || n.width || 0;
            const h = n.offsetHeight || n.naturalHeight || n.height || 0;
            return w > 50 || h > 50;
        });

        // <video> 요소 우선 (blob: 또는 https:)
        const videoEls = Array.from(document.querySelectorAll('video')).filter(v => {
            const src = v.src || v.currentSrc || v.querySelector('source')?.src || '';
            return src && (src.startsWith('blob:') || src.startsWith('http'));
        });

        console.log(`[v19] 🔍 DOM: ${videoEls.length} <video>, ${allMedia.length} total media`);

        // <video> 있으면 바로 사용
        if (videoEls.length > 0) {
            const idx = targetIndex;
            if (idx >= videoEls.length) {
                 console.log(`[v20] ⚠️ Scene index ${idx} exceeds available DOM videos (${videoEls.length})`);
            } else {
                const v = videoEls[idx];
                const src = v.src || v.currentSrc || v.querySelector('source')?.src || '';
                if (src && src !== _lastCapturedUrl) {
                    console.log(`[v20] 🎥 DOM video #${idx}: ${src.substring(0, 100)}`);
                    _lastCapturedUrl = src;
                    return await fetchAndReturn(src, true);
                }
            }
        }

        // <img> 요소 사용 (위치순 정렬)
        allMedia.sort((a, b) => {
            const aY = a.getBoundingClientRect().top + window.scrollY;
            const bY = b.getBoundingClientRect().top + window.scrollY;
            if (Math.abs(aY - bY) > 50) return aY - bY;
            return a.getBoundingClientRect().left - b.getBoundingClientRect().left;
        });

        // 중복 제거
        const seenSrc = new Set();
        const uniqueMedia = allMedia.filter(m => {
            const src = m.src || m.currentSrc || '';
            if (seenSrc.has(src)) return false;
            seenSrc.add(src);
            return true;
        });

        if (uniqueMedia.length > 0) {
            const idx = targetIndex;
            if (idx >= uniqueMedia.length) {
                console.log(`[v20] ⚠️ Scene index ${idx} exceeds available DOM media (${uniqueMedia.length})`);
            } else {
                let target = uniqueMedia[idx];
                const src = target.src || target.currentSrc;
                console.log(`[v20] 📍 DOM media #${idx}: ${target.tagName} ${src.substring(0, 100)}`);
                _lastCapturedUrl = src;
                return await fetchAndReturn(src, target.tagName === 'VIDEO');
            }
        }

        return { status: 'error', message: `장면 ${sceneDisplayNum}: 미디어를 찾지 못했습니다. Google Flow 페이지를 새로고침(F5) 후 재시도해주세요.` };

    } catch (e) {
        console.error('[v19] Critical Error:', e);
        return { status: 'error', message: `${e.message}` };
    }
}

// 간단한 fetch → base64 변환
async function fetchAndReturn(url, isVideo) {
    let blob;
    try {
        const res = await fetch(url);
        if (!res.ok) return { status: 'error', message: `다운로드 실패 (HTTP ${res.status})` };
        blob = await res.blob();
    } catch (err) {
        return { status: 'error', message: `다운로드 실패: ${err.message}` };
    }

    console.log(`[v19] 📦 Downloaded: ${blob.type} ${(blob.size / 1024).toFixed(1)}KB`);

    if (blob.size < 1000) {
        return { status: 'error', message: `파일이 너무 작습니다 (${blob.size}B)` };
    }

    return new Promise((resolve) => {
        const reader = new FileReader();
        reader.onloadend = () => {
            const data = reader.result;
            if (!data || data.length < 2000) {
                resolve({ status: 'error', message: '데이터 변환 실패.' });
                return;
            }
            resolve({
                status: 'ok',
                data: data,
                type: blob.type,
                url: url,
                is_video: isVideo || blob.type.includes('video')
            });
        };
        reader.onerror = () => resolve({ status: 'error', message: 'FileReader 오류.' });
        reader.readAsDataURL(blob);
    });
}












async function fillAndClick(text, mode) {
    if (mode) {
        console.log(`[FlowBridge] Checking mode. Target: ${mode}`);
        const modeChips = Array.from(document.querySelectorAll('button, div[role="button"], span[role="button"], .mat-mdc-chip, [role="tab"]'));
        const targetModeLabel = mode === 'video' ? ['동영상', '영상', 'video'] : ['이미지', 'image', '사진', 'photo', 'thumbnail'];
        
        const currentChip = modeChips.find(c => {
            const t = c.innerText.toLowerCase();
            const isActive = c.getAttribute('aria-selected') === 'true' || 
                             c.getAttribute('aria-checked') === 'true' ||
                             c.classList.contains('mdc-chip--selected') || 
                             c.classList.contains('selected') ||
                             c.classList.contains('active');
            return isActive && (t.includes('동영상') || t.includes('영상') || t.includes('video') || t.includes('이미지') || t.includes('image'));
        });

        if (currentChip) {
            const currentLabel = currentChip.innerText.toLowerCase();
            const isCorrect = targetModeLabel.some(l => currentLabel.includes(l));
            if (!isCorrect) {
                const targetChip = modeChips.find(c => targetModeLabel.some(l => c.innerText.toLowerCase().includes(l)));
                if (targetChip) { targetChip.click(); await new Promise(r => setTimeout(r, 1500)); }
            }
        } else {
            const targetChip = modeChips.find(c => targetModeLabel.some(l => c.innerText.toLowerCase().includes(l)));
            if (targetChip) { targetChip.click(); await new Promise(r => setTimeout(r, 1500)); }
        }
    }

    const dashButtons = Array.from(document.querySelectorAll('button, div[role="button"]'));
    const newProjectBtn = dashButtons.find(b => {
        const txt = b.innerText.toLowerCase();
        return txt.includes('새 프로젝트') || txt.includes('new project') || txt.includes('create new');
    });
    if (newProjectBtn && !document.querySelector('textarea, div[role="textbox"]')) {
        console.log('Detected dashboard, clicking New Project...');
        newProjectBtn.click();
        await new Promise(r => setTimeout(r, 3000));
    }

    if (!document.querySelector('textarea, div[role="textbox"]')) {
        const addButtons = Array.from(document.querySelectorAll('button, div[role="button"], span[role="button"]'));
        const addClipBtn = addButtons.find(b => {
            const txt = (b.innerText || '').toLowerCase().trim();
            const aria = (b.getAttribute('aria-label') || '').toLowerCase().trim();
            const labels = ['클립 추가', 'add clip', 'add first', 'create', '만들기', '추가'];
            const icons = ['add', 'plus', '+'];
            const hasLabel = labels.some(l => txt.includes(l) || aria.includes(l));
            const hasIcon = icons.some(i => txt === i || aria === i || txt.includes(i) || aria.includes(i));
            const isAddAria = aria === 'add' || aria === 'create' || aria.includes('add clip');
            if (txt.includes('settings') || txt.includes('설정')) return false;
            return hasLabel || isAddAria || (hasIcon && (b.tagName === 'BUTTON' || aria.includes('add') || b.querySelector('svg')));
        });
        if (addClipBtn) {
            console.log('Empty project detected, clicking Add button...');
            addClipBtn.click();
            await new Promise(r => setTimeout(r, 3000));
        }
    }

    const filled = await fillFlowInput(text);
    if (!filled) return { status: 'error', message: '프롬프트 입력창을 찾지 못했습니다. (+ 새 프로젝트를 눌러 창을 열어주세요)' };
    
    await new Promise(r => setTimeout(r, 2000));

    const buttons = Array.from(document.querySelectorAll('button, div[role="button"], span[role="button"]'));
    let genBtn = buttons.find(b => {
        const id = (b.getAttribute('id') || '').toLowerCase();
        const className = (b.className || '').toLowerCase();
        const txt = (b.innerText || '').toLowerCase().trim();
        const aria = (b.getAttribute('aria-label') || b.getAttribute('title') || '').toLowerCase().trim();
        if (id.includes('bot') || id.includes('diag') || id.startsWith('at-') || id.startsWith('af-') || className.includes('bot')) return false;
        if (txt.includes('새 프로젝트') || txt.includes('new project') || txt.includes('create new')) return false;
        if (b.getAttribute('aria-haspopup') === 'true' || b.getAttribute('aria-haspopup') === 'menu') return false;
        const hints = ['generate', '생성', '제출', '보내기', 'submit', 'send', 'create', '만들기', '미디어 만들기'];
        const matchesHint = hints.some(h => txt.includes(h) || aria.includes(h)) || (txt === 'run' || aria === 'run');
        const isArrow = txt.includes('arrow_forward') || aria.includes('arrow_forward') || txt.includes('arrow_upward') || aria.includes('arrow_upward');
        const isTrap = txt.includes('settings') || txt.includes('설정') || txt.includes('close') || txt.includes('닫기') || txt.includes('diagnostic') || txt.includes('진단') || txt.includes('pro') || (txt.includes('add') && !txt.includes('arrow')) || b.getAttribute('aria-disabled') === 'true';
        return (matchesHint || isArrow) && !isTrap;
    });

    if (!genBtn) {
        // Fallback: Structural search near the textarea
        const textarea = document.querySelector('textarea, div[role="textbox"]');
        if (textarea) {
            let p = textarea.parentElement;
            for(let i=0; i<3; i++) {
                if(!p) break;
                const innerBtns = Array.from(p.querySelectorAll('button, div[role="button"]'));
                for(let b of innerBtns) {
                    if(b.querySelector('svg') && !b.innerText.toLowerCase().includes('settings') && b.getAttribute('aria-disabled') !== 'true') {
                        genBtn = b; break;
                    }
                }
                if(genBtn) break;
                p = p.parentElement;
            }
        }
    }

    if (genBtn) {
        const initialAssetCount = document.querySelectorAll('video, img[src*="blob"], div[data-asset-id], .asset-container').length;
        realClick(genBtn);
        console.log('🚀 Generation started automatically');
        return monitorGeneration(initialAssetCount);
    } else {
        return { status: 'error', message: '생성(Generate) 버튼을 찾지 못했습니다.' };
    }
}

async function monitorGeneration(initialAssetCount) {
    return new Promise((resolve) => {
        let attempts = 0;
        let hasStartedGenerating = false;
        const maxAttempts = 180;
        
        console.log(`Initial asset count: ${initialAssetCount}`);

        const checkStatus = setInterval(() => {
            attempts++;
            
            const bodyText = document.body.innerText;
            const hasPercentage = /\d+%/.test(bodyText);
            
            const isGenerating = document.querySelector('[role="progressbar"]') || 
                               document.querySelector('mat-spinner') || 
                               document.querySelector('svg circle.mdc-circular-progress__indeterminate-circle-graphic') ||
                               document.querySelector('.generating-indicator') ||
                               document.querySelector('.progress-bar') ||
                               hasPercentage;
            
            const currentAssetCount = document.querySelectorAll('video, img[src*="blob"], div[data-asset-id], .asset-container').length;
            const resultArrived = currentAssetCount > initialAssetCount;

            if (isGenerating) {
                hasStartedGenerating = true;
                if (attempts % 10 === 0) console.log('Generation in progress...');
            }
            
            if ((hasStartedGenerating && !isGenerating) || resultArrived) {
                console.log(resultArrived ? '🚀 Result arrived!' : '✅ Progress indicator vanished!');
                console.log(resultArrived ? '[v4] 🚀 Result arrived!' : '[v4] ✅ Progress indicator vanished!');
                clearInterval(checkStatus);
                setTimeout(() => resolve({ status: 'ok', message: '작업 완료' }), 2000);
                return;
            } 
            
            if (!hasStartedGenerating && !resultArrived && attempts > 15) {
                clearInterval(checkStatus);
                resolve({ status: 'error', message: '[v4] 작업이 시작되지 않았거나 인식이 실패했습니다. 화면을 확인해주세요.' });
            }

            if (attempts > maxAttempts) {
                clearInterval(checkStatus);
                resolve({ status: 'timeout', message: '[v4] 시간 초과' });
            }
        }, 1000);
    });
}

// Helper: simulate a real mouse click (not just .click())
function realClick(el) {
    if (!el) return;
    try {
        const rect = el.getBoundingClientRect();
        const cx = rect.left + rect.width / 2;
        const cy = rect.top + rect.height / 2;
        const opts = { bubbles: true, cancelable: true, view: window, clientX: cx, clientY: cy, pointerId: 1, isPrimary: true };
        
        el.dispatchEvent(new PointerEvent('pointerover', opts));
        el.dispatchEvent(new PointerEvent('pointerenter', opts));
        el.dispatchEvent(new MouseEvent('mouseover', opts));
        el.dispatchEvent(new MouseEvent('mouseenter', opts));
        el.dispatchEvent(new MouseEvent('mousemove', opts));
        el.dispatchEvent(new PointerEvent('pointerdown', opts));
        el.dispatchEvent(new MouseEvent('mousedown', opts));
        
        el.focus();
        
        setTimeout(() => {
            el.dispatchEvent(new PointerEvent('pointerup', opts));
            el.dispatchEvent(new MouseEvent('mouseup', opts));
            el.dispatchEvent(new MouseEvent('click', opts));
            el.click();
        }, 50);
    } catch(e) {
        console.warn('[v5] realClick failed, falling back to basic click', e);
        el.click();
    }
}


// ── Motion Prompt Generator ──────────────────────────────────────────
const MOTION_PRESETS = [
    "cinematic slow zoom into the center, high detail, masterpiece",
    "soft camera pan from left to right, cinematic lighting, 4k",
    "dynamic camera movement, subtle character breathing, realistic motion",
    "slow camera pull back, revealing more of the scene, cinematic atmosphere",
    "gentle orbiting camera around the main subject, elegant motion",
    "cinematic dramatic lighting shift, subtle wind effect on hair and clothes",
    "slow vertical tilt up, grand cinematic perspective",
    "epic camera motion with shallow depth of field, focused on the subject"
];

function generateMotionPrompt(index, originalPrompt) {
    const preset = MOTION_PRESETS[index % MOTION_PRESETS.length];
    // If we have an original prompt, we can merge them, or just use the high-quality preset
    return preset;
}

// ─────────────────────────────────────────────────────────
// animateAllImages: 
// Workflow: hover card → ⋮ button → click ⋮ → "애니메이션 적용" 
// (confirmed correct by user on 2026-03-12)
// ─────────────────────────────────────────────────────────
async function animateAllImages(maxCount, prompts) {
    console.log('[AnimateAll] Starting... hover → ⋮ → 애니메이션 적용');
    const promptList = Array.isArray(prompts) ? prompts : [];
    console.log(`[AnimateAll] Received ${promptList.length} prompts from platform`);

    window._animateRunning = true;
    
    // 1. Find all scene cards using common classes
    let cards = Array.from(document.querySelectorAll('.card-container, .scene-card, .asset-card, [role="gridcell"]'))
        .filter(el => el.offsetParent !== null && el.getBoundingClientRect().width > 120);
    
    // Fallback if cards aren't found by class
    if (cards.length === 0) {
        console.log('[AnimateAll] Direct card detection failed, using fallback img heuristic...');
        const allImgs = Array.from(document.querySelectorAll('img'))
            .filter(img => img.offsetParent !== null && (img.width > 100 || img.naturalWidth > 100));
        
        const seen = new Set();
        for (const img of allImgs) {
            let el = img.parentElement;
            for (let j = 0; j < 6 && el; j++) {
                if (el.getBoundingClientRect().width > 120 && !seen.has(el)) {
                    seen.add(el);
                    cards.push(el);
                    break;
                }
                el = el.parentElement;
            }
        }
    }
    
    console.log(`[AnimateAll] Scenes identified: ${cards.length}`);
    if (cards.length === 0) {
        return { status: 'error', message: '화면에서 이미지를 찾을 수 없습니다. (Labs 프로젝트 화면인지 확인해 주세요)' };
    }
    
    let successCount = 0;
    let failCount = 0;
    const limit = maxCount || cards.length;
    
    for (let i = 0; i < Math.min(cards.length, limit); i++) {
        if (!window._animateRunning) break;
        
        const card = cards[i];
        
        // Skip restricted or failed cards
        const lowerText = (card.innerText || '').toLowerCase();
        if (lowerText.includes('failed') || lowerText.includes('violate') || lowerText.includes('policy') || lowerText.includes('실패')) {
            console.warn(`[AnimateAll] Skipping Scene ${i+1} (Failure/Policy restriction)`);
            continue;
        }

        console.log(`[AnimateAll] Card ${i+1}/${Math.min(cards.length, limit)}`);
        
        card.scrollIntoView({ behavior: 'smooth', block: 'center' });
        await new Promise(r => setTimeout(r, 500));
        
        // === STEP 1: Get snapshot of visible buttons BEFORE hover ===
        const getVisibleBtns = () => new Set(
            Array.from(document.querySelectorAll('button, [role="button"]'))
                .filter(b => b.offsetParent !== null)
        );
        const beforeBtns = getVisibleBtns();
        
        // === STEP 2: Hover the card ===
        const rect = card.getBoundingClientRect();
        const cx = rect.left + rect.width / 2;
        const cy = rect.top + rect.height / 2;
        const hoverOpts = { bubbles: true, cancelable: true, view: window, clientX: cx, clientY: cy };
        
        card.dispatchEvent(new MouseEvent('pointerover', hoverOpts));
        card.dispatchEvent(new MouseEvent('mouseover', hoverOpts));
        card.dispatchEvent(new MouseEvent('pointerenter', hoverOpts));
        card.dispatchEvent(new MouseEvent('mouseenter', hoverOpts));
        card.dispatchEvent(new MouseEvent('pointermove', hoverOpts));
        card.dispatchEvent(new MouseEvent('mousemove', hoverOpts));
        
        const cardImg = card.querySelector('img');
        if (cardImg) {
            cardImg.dispatchEvent(new MouseEvent('mouseover', hoverOpts));
            cardImg.dispatchEvent(new MouseEvent('mouseenter', hoverOpts));
        }
        
        await new Promise(r => setTimeout(r, 400));
        
        // === STEP 3: Detect newly visible buttons ===
        const afterBtns = getVisibleBtns();
        const newBtns = Array.from(afterBtns).filter(b => !beforeBtns.has(b));
        console.log(`[AnimateAll] Hover revealed ${newBtns.length} new buttons`);
        newBtns.forEach(b => console.log('  New btn:', (b.innerText || '').trim()));
        
        // === STEP 4: Find ⋮ button INSIDE the current card ===
        // Looking inside the card is much more reliable than searching the whole page
        const findMoreBtnInside = (container) => {
            const candidates = Array.from(container.querySelectorAll('button, [role="button"], mat-icon, .mat-icon, .more-vert'));
            return candidates.find(el => {
                const txt = (el.innerText || el.textContent || el.getAttribute('aria-label') || '').trim();
                return txt.includes('more_vert') || txt === '⋮' || txt.includes('옵션 더보기');
            });
        };

        let moreBtn = findMoreBtnInside(card);
        
        // If not found in card, try newly revealed ones (from hover)
        if (!moreBtn) {
            moreBtn = newBtns.find(b => {
                const txt = (b.innerText || b.getAttribute('aria-label') || '').trim();
                return txt.includes('more_vert') || txt === '⋮' || txt.includes('옵션 더보기');
            });
        }

        if (moreBtn) {
            console.log('[AnimateAll] Found ⋮ button for card, forcing visible with !important');
            moreBtn.style.setProperty('opacity', '1', 'important');
            moreBtn.style.setProperty('visibility', 'visible', 'important');
            moreBtn.style.setProperty('display', 'flex', 'important');
            moreBtn.style.setProperty('pointer-events', 'auto', 'important');
        } else {
            // Last resort: global search restricted to proximity
            const allBtns = Array.from(document.querySelectorAll('button, [role="button"]'));
            moreBtn = allBtns.find(b => {
                const txt = (b.innerText || b.getAttribute('aria-label') || '').trim();
                if (!(txt.includes('more_vert') || txt === '⋮')) return false;
                const r = b.getBoundingClientRect();
                const cb = card.getBoundingClientRect();
                return r.right >= cb.left - 50 && r.left <= cb.right + 50 &&
                       r.bottom >= cb.top - 50 && r.top <= cb.bottom + 50;
            });
        }
        
        if (!moreBtn) {
            console.warn(`[AnimateAll] ❌ No ⋮ button found for card ${i+1}. Skipping.`);
            failCount++;
            continue;
        }
        
        // === STEP 5: Force visible + realClick ⋮ ===
        // realClick is required - it includes hover events (mouseenter/mouseover)
        // that Google Flow's React component needs to activate the button before clicking
        console.log('[AnimateAll] Forcing ⋮ visible and using realClick...');
        const origStyle = moreBtn.getAttribute('style') || '';
        moreBtn.style.opacity = '1';
        moreBtn.style.visibility = 'visible';
        moreBtn.style.display = 'flex';
        moreBtn.style.pointerEvents = 'auto';
        moreBtn.scrollIntoView({ block: 'center' });
        await new Promise(r => setTimeout(r, 200));
        
        // realClick fires ALL mouse events including hover (pointerover, mouseenter, etc.)
        // This is what activates the button in Google Flow's React state
        realClick(moreBtn);
        
        // Restore style after menu opens
        setTimeout(() => moreBtn.setAttribute('style', origStyle), 500);
        
        // === STEP 6: POLL for "애니메이션 적용" ===
        const findAnimMenuItem = () => {
            const menuTexts = ['애니메이션 적용', '움직임 추가', '애니메이션', '변환', 'Animate', 'Apply animation'];
            // 1. Text Search
            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null);
            let node;
            while (node = walker.nextNode()) {
                const txt = node.textContent.trim();
                if (menuTexts.includes(txt)) {
                    let el = node.parentElement;
                    for (let j = 0; j < 8 && el && el !== document.body; j++) {
                        if (el.tagName === 'LI' || el.tagName === 'BUTTON' || el.getAttribute('role') === 'menuitem' || el.classList.contains('mat-mdc-menu-item')) {
                            return el;
                        }
                        el = el.parentElement;
                    }
                    return node.parentElement;
                }
            }
            // 2. Attribute Search
            return Array.from(document.querySelectorAll('[role="menuitem"], mat-menu-item, li, button, .mat-mdc-menu-item'))
                .filter(el => el.offsetParent !== null)
                .find(el => menuTexts.some(t => (el.innerText || '').includes(t)));
        };
        
        let animBtn = null;
        for (let poll = 0; poll < 20; poll++) {
            await new Promise(r => setTimeout(r, 100));
            animBtn = findAnimMenuItem();
            if (animBtn) {
                console.log(`[AnimateAll] ✅ Menu appeared after ${(poll+1)*100}ms`);
                break;
            }
            if (poll === 0 || poll % 5 === 4) console.log(`[AnimateAll] Waiting for menu... ${(poll+1)*100}ms`);
        }
        
        if (!animBtn) {
            // Debug: log visible text for diagnosis
            const walker2 = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null);
            const texts = [];
            let n2;
            while (n2 = walker2.nextNode()) {
                const t = n2.textContent.trim();
                if (t && t.length > 1 && t.length < 25 && n2.parentElement?.offsetParent !== null) texts.push(t);
            }
            console.warn(`[AnimateAll] ❌ Menu not found. Visible short texts: ${[...new Set(texts)].slice(0, 20).join(' | ')}`);
            document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
            failCount++;
            await new Promise(r => setTimeout(r, 300));
            continue;
        }
        
        // === STEP 7: Click "애니메이션 적용" ===
        console.log(`[AnimateAll] ✅ Clicking: "${(animBtn.innerText||'').trim()}" (tag:${animBtn.tagName})`);
        
        // Use realClick to be absolutely sure the menu item is triggered
        realClick(animBtn);
        if (animBtn.parentElement && animBtn.parentElement !== document.body) {
            realClick(animBtn.parentElement);
        }
        
        // CRITICAL: Wait for the bottom animation bar to appear and the UI to settle
        console.log('[AnimateAll] Waiting 1.5s for bottom bar to stabilize...');
        await new Promise(r => setTimeout(r, 1500));
        
        // === STEP 8: Fill prompt and Click "Generate" ===
        const targetText = promptList[i] || generateMotionPrompt(i);
        
        const findAndFillAndClick = async () => {
            console.log(`[AnimateAll] Navigating to bottom bar. Target Prompt: "${targetText}"`);
            
            for (let poll = 0; poll < 40; poll++) {
                // 8a. Find the input - very aggressive search
                const allInputs = Array.from(document.querySelectorAll('input, textarea, [contenteditable="true"], div[role="textbox"], .slate-editor'));
                const promptInput = allInputs.find(el => {
                    if (el.offsetParent === null) return false;
                    const html = el.innerHTML.toLowerCase();
                    const placeholder = (el.getAttribute('placeholder') || el.getAttribute('aria-label') || '').toLowerCase();
                    return placeholder.includes('만들고') || placeholder.includes('create') || placeholder.includes('prompt') || 
                           el.isContentEditable || el.classList.contains('slate-editor') || el.id?.includes('prompt');
                });

                if (promptInput) {
                    const currentVal = (promptInput.value || promptInput.innerText || '').trim();
                    // If empty or still has placeholder text (Google Flow uses '무엇을 만들고 싶으신가요?')
                    if (currentVal.length < 2 || currentVal.includes('만들고 싶으신가요')) {
                        console.log('[AnimateAll] Found input! Typing prompt...');
                        
                        promptInput.scrollIntoView({ block: 'center' });
                        // NO highlighting to avoid React reconciliation errors
                        
                        // Human-like interaction: Click it first
                        realClick(promptInput);
                        await new Promise(r => setTimeout(r, 400));
                        promptInput.focus();
                        
                        // Insert text directly (gentler than selectAll/delete)
                        try {
                            promptInput.dispatchEvent(new InputEvent('beforeinput', { bubbles: true, inputType: 'insertText', data: targetText }));
                            document.execCommand('insertText', false, targetText);
                            promptInput.dispatchEvent(new InputEvent('input', { 
                                bubbles: true, inputType: 'insertText', data: targetText 
                            }));
                        } catch(e) {
                            if (promptInput.contentEditable === 'true') promptInput.innerText = targetText;
                            else promptInput.value = targetText;
                            promptInput.dispatchEvent(new Event('input', { bubbles: true }));
                        }

                        promptInput.dispatchEvent(new Event('change', { bubbles: true }));
                        await new Promise(r => setTimeout(r, 800)); // Wait for app to register
                        promptInput.blur(); // Release focus early
                    }
                }

                // 8b. Find the final arrow button (aggressive search)
                const buttons = Array.from(document.querySelectorAll('button, [role="button"], .mat-mdc-button'))
                    .filter(b => b.offsetParent !== null);
                    
                const finalBtn = buttons.find(b => {
                    const txt = (b.innerText || b.textContent || '').toLowerCase();
                    const aria = (b.getAttribute('aria-label') || '').toLowerCase();
                    const iconEl = b.querySelector('mat-icon, i, span');
                    const iconTxt = iconEl ? iconEl.innerText.toLowerCase() : '';
                    
                    const rect = b.getBoundingClientRect();
                    const isAtBottom = rect.top > window.innerHeight * 0.7;
                    const isAtRight = rect.left > window.innerWidth * 0.6; // Button is usually on the right
                    
                    return isAtBottom && isAtRight && (
                        txt.includes('arrow') || iconTxt.includes('arrow') || iconTxt.includes('send') ||
                        aria.includes('만들기') || aria.includes('generate') || aria.includes('create') ||
                        txt.includes('forward') || txt.includes('right') ||
                        b.classList.contains('mat-primary') || b.classList.contains('mdc-fab') ||
                        (txt === 'arrow_forward' && b.classList.contains('mat-focus-indicator'))
                    );
                });
                
                if (finalBtn) {
                    console.log('[AnimateAll] 🚀 Triggering Final Generation Click...');
                    finalBtn.focus();
                    
                    // Refined, gentler click sequence
                    const triggerClick = (el) => {
                        const opts = { bubbles: true, cancelable: true, view: window };
                        // Single clean sequence: down -> up -> click
                        el.dispatchEvent(new PointerEvent('pointerdown', { ...opts, pointerId: 1, isPrimary: true }));
                        setTimeout(() => {
                            el.dispatchEvent(new PointerEvent('pointerup', { ...opts, pointerId: 1, isPrimary: true }));
                            el.dispatchEvent(new MouseEvent('click', opts));
                            // Release focus to let React close the bar cleanly
                            document.body.focus(); 
                        }, 50);
                    };

                    triggerClick(finalBtn);

                    // VERIFICATION: Be more patient. Google Flow needs time to transition.
                    console.log('[AnimateAll] Generation triggered. Waiting 4s for stability...');
                    await new Promise(r => setTimeout(r, 4500));
                    
                    // Final check: if bar is still there, try one last Enter key
                    const barStillOpen = document.querySelector('.slate-editor, [contenteditable="true"]')?.offsetParent !== null;
                    if (barStillOpen) {
                        const input = document.querySelector('.slate-editor, [contenteditable="true"]');
                        if (input) {
                            input.focus();
                            input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }));
                        }
                    }
                    
                    return true;
                }
                await new Promise(r => setTimeout(r, 300));
            }
            return false;
        };
        
        const triggered = await findAndFillAndClick();
        
        if (triggered) {
            console.log(`[AnimateAll] ✅ Generation triggered on card ${i+1}. Waiting 4s for queue...`);
            successCount++;
            await new Promise(r => setTimeout(r, 4000));
        } else {
            console.warn(`[AnimateAll] ❌ Could not find the final Generate button in the bottom bar for card ${i+1}`);
            failCount++;
            // Close the bar if stuck
            document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
            await new Promise(r => setTimeout(r, 500));
        }
    } // end for loop
    
    window._animateRunning = false;
    return { status: 'ok', message: `배치 완료! 성공: ${successCount}개, 실패: ${failCount}개` };
}

async function animateImage(sceneNum, prompt) {
    console.log(`[Animate] Scene ${sceneNum}: Looking for image to animate...`);
    
    let targetAsset = _lastClickedAsset;
    
    if (targetAsset) {
        console.log('[Animate] Using click-tracked asset:', targetAsset.tagName);
        highlightElement(targetAsset);
        
        targetAsset.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }));
        targetAsset.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
        await new Promise(r => setTimeout(r, 500));
        
        const animateBtns = Array.from(targetAsset.querySelectorAll('button, div[role="button"], [aria-label]'));
        const animateBtn = animateBtns.find(b => {
            const txt = (b.innerText || '').toLowerCase();
            const aria = (b.getAttribute('aria-label') || '').toLowerCase();
            return (txt.includes('animate') || aria.includes('animate') || 
                    txt.includes('movie') || aria.includes('movie') ||
                    txt.includes('play') || aria.includes('play') ||
                    txt.includes('영상') || aria.includes('영상')) && b.offsetParent !== null;
        });
        
        if (animateBtn) {
            console.log('[Animate] Found animate button inside asset, clicking...');
            animateBtn.click();
            return monitorGeneration(0);
        }
        
        console.log('[Animate] No button inside asset. Checking all visible buttons...');
    } else {
        console.log('[Animate] No click tracked! Please click the image in Google Flow first.');
    }

    const allButtons = Array.from(document.querySelectorAll('button, div[role="button"], [aria-label]'));
    const animateBtn = allButtons.find(b => {
        const txt = (b.innerText || '').toLowerCase();
        const aria = (b.getAttribute('aria-label') || '').toLowerCase();
        const isTrap = txt.includes('settings') || txt.includes('설정') || txt.includes('close');
        return !isTrap && (txt.includes('animate') || aria.includes('animate') ||
                txt.includes('movie') || aria.includes('movie')) && b.offsetParent !== null;
    });
    
    if (animateBtn) {
        console.log('[Animate] Found fallback animate button:', animateBtn.innerText);
        animateBtn.click();
        return monitorGeneration(0);
    }

    return { 
        status: 'error', 
        message: '⚠️ 먼저 구글 Flow에서 원하는 사진을 클릭하신 뒤 다시 눌러주세요. (사진 클릭 → [✨ 변환] 버튼)' 
    };
}

async function showInFlow(prompt) {
    if (!prompt) return;
    
    if (_lastClickedAsset) {
        console.log('[FlowBridge] Using last-clicked asset:', _lastClickedAsset.tagName);
        _lastClickedAsset.scrollIntoView({ behavior: 'smooth', block: 'center' });
        highlightElement(_lastClickedAsset);
        return { status: 'ok' };
    }

    console.log('[FlowBridge] No click tracked. Searching for caption...');
    const fullText = prompt.toLowerCase();
    
    const captionEls = Array.from(document.querySelectorAll('p, span, figcaption, label'))
        .filter(el => {
            const txt = (el.innerText || '').trim();
            return txt.length > 5 && txt.length < 120 && el.children.length === 0 && el.offsetParent !== null;
        });

    let bestEl = null;
    let bestScore = 0;

    captionEls.forEach(el => {
        const txt = (el.innerText || '').toLowerCase().trim();
        if (!txt) return;
        const captionWords = txt.split(/\s+/).filter(w => w.length > 2);
        let score = 0;
        captionWords.forEach(w => { if (fullText.includes(w)) score += 3; });
        if (score > bestScore) { bestScore = score; bestEl = el; }
    });

    if (bestEl && bestScore >= 6) {
        let imgTarget = null;
        let container = bestEl.parentElement;
        for (let i = 0; i < 5; i++) {
            if (!container) break;
            const img = container.querySelector('img');
            if (img) { imgTarget = img; break; }
            container = container.parentElement;
        }
        const target = imgTarget || bestEl;
        target.scrollIntoView({ behavior: 'smooth', block: 'center' });
        highlightElement(target);
        return { status: 'ok' };
    }

    return { status: 'error', message: '사진을 찾지 못했습니다. 구글 Flow에서 사진을 한 번 클릭한 뒤 다시 눌러주세요.' };
}

function highlightElement(el) {
    const originalFilter = el.style.filter;
    const originalOutline = el.style.outline;
    const originalZ = el.style.zIndex;

    el.style.zIndex = '10000';
    el.style.outline = '10px solid #ef4444';
    el.style.outlineOffset = '4px';
    el.style.filter = 'drop-shadow(0 0 30px #ef4444) brightness(1.3)';
    
    if (el.animate) {
        el.animate([
            { transform: 'scale(1)', outlineColor: '#ef4444' },
            { transform: 'scale(1.03)', outlineColor: '#ffffff' },
            { transform: 'scale(1)', outlineColor: '#ef4444' }
        ], { duration: 400, iterations: 4 });
    }

    setTimeout(() => {
        el.style.filter = originalFilter;
        el.style.outline = originalOutline;
        el.style.zIndex = originalZ;
    }, 3000);
}

// ========== 웹페이지 ↔ 확장프로그램 브릿지 (localhost용) ==========
// localhost 페이지에서 window.postMessage로 확장프로그램의 포착된 이미지/영상을 요청할 수 있도록 함
window.addEventListener('message', (event) => {
    // 보안: 같은 origin만 허용
    if (event.source !== window) return;
    if (!event.data || event.data.source !== 'FLOW_BRIDGE_PAGE') return;

    const { action, requestId } = event.data;

    if (action === 'get_captured_images') {
        chrome.runtime.sendMessage({ action: 'get_captured_images' }, (response) => {
            window.postMessage({
                source: 'FLOW_BRIDGE_EXT',
                requestId: requestId,
                action: 'captured_images_result',
                data: response
            }, '*');
        });
    } else if (action === 'get_captured_videos') {
        chrome.runtime.sendMessage({ action: 'get_captured_videos' }, (response) => {
            window.postMessage({
                source: 'FLOW_BRIDGE_EXT',
                requestId: requestId,
                action: 'captured_videos_result',
                data: response
            }, '*');
        });
    } else if (action === 'clear_captured_images') {
        chrome.runtime.sendMessage({ action: 'clear_captured_images' }, (response) => {
            window.postMessage({
                source: 'FLOW_BRIDGE_EXT',
                requestId: requestId,
                action: 'clear_images_result',
                data: response
            }, '*');
        });
    }
});

// 확장프로그램 연결 상태를 페이지에 알림
window.postMessage({ source: 'FLOW_BRIDGE_EXT', action: 'extension_ready' }, '*');
console.log('[FlowBridge] Page bridge ready for localhost communication');

} // end version guard

// ══════════════════════════════════════════════════════
// Hyper-Vision: 수동 선택 모드 (Visual Picker)
// ══════════════════════════════════════════════════════
let _pickerOverlay = null;

async function startHyperVision(sceneNum) {
    console.log(`[v20] 🎯 Hyper-Vision Active for Scene ${sceneNum}`);
    
    if (!_pickerOverlay) {
        _pickerOverlay = document.createElement('div');
        _pickerOverlay.style.cssText = `
            position: fixed; top: 20px; left: 50%; transform: translateX(-50%);
            background: #1e293b; color: white; padding: 15px 25px; border-radius: 12px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.5); z-index: 9999999;
            font-family: sans-serif; text-align: center; border: 2px solid #3b82f6;
            pointer-events: none; opacity: 1; transition: opacity 0.3s;
        `;
        document.body.appendChild(_pickerOverlay);
    }
    
    _pickerOverlay.innerHTML = `
        <div style="font-weight:700; font-size:16px; margin-bottom:5px;">🎯 Hyper-Vision 활성화</div>
        <div style="font-size:13px; color:#94a3b8;">가져올 <span style="color:#60a5fa; font-weight:700;">영상 또는 이미지</span>를 클릭하세요.<br>(Scene ${sceneNum}으로 자동 배정됩니다)</div>
        <button id="hv-cancel" style="margin-top:10px; background:#475569; border:none; color:white; padding:4px 12px; border-radius:6px; cursor:pointer; pointer-events:auto;">취소 (ESC)</button>
    `;
    _pickerOverlay.style.display = 'block';
    
    const highlightStyle = 'outline: 5px solid #3b82f6; outline-offset: -5px;';
    let lastEl = null;

    const onMouseOver = (e) => {
        let el = e.target;
        if (el === _pickerOverlay || _pickerOverlay.contains(el)) return;
        for (let i = 0; i < 5; i++) {
            if (!el || el === document.body) break;
            const target = (el.tagName === 'VIDEO' || el.tagName === 'IMG') ? el : el.querySelector('video, img');
            if (target) {
                if (lastEl) lastEl.style.outline = '';
                target.style.cssText += highlightStyle;
                lastEl = target;
                return;
            }
            el = el.parentElement;
        }
    };

    const onClick = async (e) => {
        e.preventDefault(); e.stopPropagation();
        let el = e.target;
        let targetMedia = null;
        for (let i = 0; i < 5; i++) {
            if (!el || el === document.body) break;
            targetMedia = (el.tagName === 'VIDEO' || el.tagName === 'IMG') ? el : el.querySelector('video, img');
            if (targetMedia) break;
            el = el.parentElement;
        }

        if (targetMedia) {
            let src = targetMedia.src || targetMedia.currentSrc;
            if (!src && targetMedia.tagName === 'VIDEO') {
                const sourceEl = targetMedia.querySelector('source');
                if (sourceEl) src = sourceEl.src;
            }
            const isVideo = targetMedia.tagName === 'VIDEO';
            stopHyperVision();
            
            if (!src) {
                console.warn('[FlowBridge] Clicked media has no src:', targetMedia);
                return;
            }
            
            let btn = document.createElement('div');
            btn.style.cssText = 'position:fixed; top:20px; left:50%; transform:translateX(-50%); background:#3b82f6; color:white; padding:10px 20px; border-radius:8px; z-index:999999; font-weight:bold; font-family:sans-serif; box-shadow:0 4px 6px rgba(0,0,0,0.3);';
            btn.innerText = '미디어 가져오는 중...';
            document.body.appendChild(btn);

            console.log(`[FlowBridge] Fetching clicked media: ${src}`);
            const result = await fetchAndReturn(src, isVideo);
            
            if (result.status === 'ok') {
                btn.innerText = '스튜디오로 배정 중...';
                chrome.runtime.sendMessage({ 
                    action: 'manual_pick_result', 
                    sceneNum: sceneNum,
                    result: result 
                }, () => {
                    const lastErr = chrome.runtime.lastError;
                    if (lastErr) {
                        btn.style.background = '#ef4444';
                        btn.innerText = '전송 실패 (브릿지 사이드패널이 안열려있음)';
                    } else {
                        btn.style.background = '#10b981';
                        btn.innerText = '✅ 배정 완료!';
                    }
                    setTimeout(() => btn.remove(), 4000);
                });
            } else {
                btn.style.background = '#ef4444';
                btn.innerText = `가져오기 실패: ${result.message}`;
                setTimeout(() => btn.remove(), 5000);
            }
        }
    };

    const stopHyperVision = () => {
        if (_pickerOverlay) _pickerOverlay.style.display = 'none';
        document.removeEventListener('mouseover', onMouseOver, true);
        document.removeEventListener('click', onClick, true);
        document.removeEventListener('keydown', onKeyDown, true);
        if (lastEl) lastEl.style.outline = '';
    }

    const onKeyDown = (e) => { if (e.key === 'Escape') stopHyperVision(); };

    document.addEventListener('mouseover', onMouseOver, true);
    document.addEventListener('click', onClick, true);
    document.addEventListener('keydown', onKeyDown, true);
    
    setTimeout(() => {
        const btn = document.getElementById('hv-cancel');
        if (btn) btn.onclick = stopHyperVision;
    }, 100);

    return { status: 'picker_started' };
}

// ─────────────────────────────────────────────────────────
// fetchAndReturn: Download blob or real URL and return base64
// ─────────────────────────────────────────────────────────
async function fetchAndReturn(url, isVideo) {
    try {
        if (url.startsWith('blob:')) {
            const res = await fetch(url);
            if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
            const blob = await res.blob();
            
            return new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onloadend = () => resolve({ status: 'ok', data: reader.result });
                reader.onerror = reject;
                reader.readAsDataURL(blob);
            });
        } else {
            // External URL -> use background proxy to avoid CORS
            return await new Promise((resolve) => {
                chrome.runtime.sendMessage({ action: 'fetch_proxy', url: url }, (response) => {
                    if (chrome.runtime.lastError) {
                        resolve({ status: 'error', message: chrome.runtime.lastError.message });
                    } else if (response && response.status === 'ok') {
                        resolve({ status: 'ok', data: response.data });
                    } else {
                        resolve({ status: 'error', message: response ? response.message : 'Unknown proxy error' });
                    }
                });
            });
        }
    } catch (e) {
        console.error('[FlowBridge] fetchAndReturn failed:', e);
        return { status: 'error', message: e.toString() };
    }
}
