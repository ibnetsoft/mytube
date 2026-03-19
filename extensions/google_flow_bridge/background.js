// background.js - Google Flow 영상/이미지 URL 자동 포착 v3.1
// 모든 도메인에서 영상+이미지 네트워크 요청을 캡처하고 중복 제거

const capturedVideos = new Map(); // tabId -> [{url, timestamp, contentType, size}]
const capturedImages = []; // [{url, timestamp, contentType, size}]

// URL에서 쿼리/해시 제거한 기본 경로 추출 (중복 비교용)
function getUrlBase(url) {
    if (!url) return '';
    try {
        // Stop stripping query params! They are critical for Google asset uniqueness.
        // Only strip the hash fragment.
        return url.split('#')[0];
    } catch {
        return url.split('#')[0];
    }
}

// 영상 필터링 패턴
const BLACKLIST = [
    'intro', 'hero', 'banner', 'landing', 'tutorial', 'promo', 
    'background', 'nano-banana', 'site-video', 'marketing',
    'Dolly_in', 'Orbit_left', 'Zoom_in' // Camera presets
];

function isBlacklisted(url) {
    const u = url.toLowerCase();
    return BLACKLIST.some(p => u.includes(p.toLowerCase()));
}

// 이미 동일 영상이 저장됐는지 확인
function isDuplicate(list, url) {
    const base = getUrlBase(url);
    return list.some(v => getUrlBase(v.url) === base);
}

function addVideo(tabId, details, contentType, contentLength) {
    if (isBlacklisted(details.url)) return;

    if (!capturedVideos.has(tabId)) {
        capturedVideos.set(tabId, []);
    }

    const list = capturedVideos.get(tabId);
    if (isDuplicate(list, details.url)) return;

    list.push({
        url: details.url,
        timestamp: Date.now(),
        contentType: contentType,
        size: contentLength,
    });

    console.log(`[FlowBridge BG] 🎥 Captured: ${contentType} ${(contentLength / 1024).toFixed(0)}KB ${details.url.substring(0, 150)}`);
}

// 1) Content-Type 기반 캡처
chrome.webRequest.onHeadersReceived.addListener(
    (details) => {
        const ctHeader = details.responseHeaders?.find(h => h.name.toLowerCase() === 'content-type');
        const contentType = ctHeader?.value || '';

        const isVideo = contentType.includes('video');
        const isImage = contentType.includes('image/png') || contentType.includes('image/jpeg') || contentType.includes('image/webp');

        const clHeader = details.responseHeaders?.find(h => h.name.toLowerCase() === 'content-length');
        const contentLength = parseInt(clHeader?.value || '0', 10);

        if (isVideo) {
            // 최소 50KB 이상이면 포착 (모바일용/저화질 대응)
            if (contentLength > 0 && contentLength < 50000) return;
            addVideo(details.tabId, details, contentType, contentLength);
        }

        if (isImage && contentLength > 30000) { // 30KB 이상 이미지로 하향
            const url = details.url;
            if (url.includes('/icon') || url.includes('favicon') || url.includes('logo') || url.includes('.svg')) return;
            if (isBlacklisted(url)) return;

            const base = getUrlBase(url);
            if (!capturedImages.some(img => getUrlBase(img.url) === base)) {
                capturedImages.push({
                    url: url,
                    timestamp: Date.now(),
                    contentType: contentType,
                    size: contentLength
                });
                console.log(`[FlowBridge BG] 🖼️ Image captured: ${(contentLength / 1024).toFixed(0)}KB`);
            }
        }
    },
    { urls: ['https://labs.google/*', 'https://*.google.com/*', 'https://*.googleusercontent.com/*', 'https://*.gstatic.com/*'] },
    ['responseHeaders']
);

// 메시지 핸들러
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg.action === 'get_captured_videos') {
        const allVideos = [];
        for (const [, videos] of capturedVideos) {
            allVideos.push(...videos);
        }

        const seen = new Set();
        const专용_deduped = [];
        for (const v of allVideos) {
            const base = getUrlBase(v.url);
            if (!seen.has(base)) {
                seen.add(base);
                专용_deduped.push(v);
            }
        }

        // 최근 2시간 내 영상만 최신순
        const recent = 专용_deduped
            .filter(v => Date.now() - v.timestamp < 2 * 60 * 60 * 1000)
            .sort((a, b) => b.timestamp - a.timestamp);

        sendResponse({ videos: recent });
        return true;
    }

    if (msg.action === 'clear_captured_videos') {
        capturedVideos.clear();
        sendResponse({ status: 'ok' });
        return true;
    }

    if (msg.action === 'get_captured_images') {
        const recent = capturedImages
            .filter(v => Date.now() - v.timestamp < 2 * 60 * 60 * 1000)
            .sort((a, b) => b.timestamp - a.timestamp);
        sendResponse({ images: recent });
        return true;
    }

    if (msg.action === 'clear_captured_images') {
        capturedImages.length = 0;
        sendResponse({ status: 'ok' });
        return true;
    }

    if (msg.action === 'fetch_proxy') {
        fetch(msg.url)
            .then(res => res.blob())
            .then(blob => {
                const reader = new FileReader();
                reader.onloadend = () => sendResponse({ status: 'ok', data: reader.result });
                reader.onerror = () => sendResponse({ status: 'error', message: 'FileReader failed' });
                reader.readAsDataURL(blob);
            })
            .catch(err => sendResponse({ status: 'error', message: err.message }));
        return true;
    }
});

// ===============================================
// Side-Panel Behavior (v3 Migration)
// ===============================================
chrome.runtime.onInstalled.addListener(() => {
    // 클릭 시 사이드 패널 열리도록 설정
    if (chrome.sidePanel) {
        chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true })
            .catch((error) => console.error('[FlowBridge BG] SidePanel Behavior Error:', error));
    }
});

console.log('[FlowBridge BG] v3.1 started - Side Panel + Filtering active');
