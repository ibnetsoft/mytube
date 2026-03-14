// background.js - Google Flow 영상 URL 자동 포착 v2
// 모든 도메인에서 영상 네트워크 요청을 캡처하고 중복 제거

const capturedVideos = new Map(); // tabId -> [{url, timestamp, contentType, size}]

// URL에서 쿼리/해시 제거한 기본 경로 추출 (중복 비교용)
function getUrlBase(url) {
    try {
        const u = new URL(url);
        return u.origin + u.pathname;
    } catch {
        return url.split('?')[0].split('#')[0];
    }
}

// 카메라 무브먼트 프리셋 영상 필터 (Google Flow UI 요소)
function isCameraPreset(url) {
    const presets = ['Dolly_in', 'Dolly_out', 'Orbit_left', 'Orbit_right',
        'Orbit_up', 'Orbit_down', 'Dolly_in_zoom_out', 'Dolly_out_zoom_in',
        'Truck_left', 'Truck_right', 'Pedestal_up', 'Pedestal_down',
        'Zoom_in', 'Zoom_out', 'Pan_left', 'Pan_right', 'Tilt_up', 'Tilt_down'];
    return presets.some(p => url.includes(p));
}

// 이미 동일 영상이 저장됐는지 확인 (URL 기본 경로 비교)
function isDuplicate(list, url) {
    const base = getUrlBase(url);
    return list.some(v => getUrlBase(v.url) === base);
}

function addVideo(tabId, details, contentType, contentLength) {
    // 카메라 프리셋 영상 무시
    if (isCameraPreset(details.url)) return;

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

// 1) Content-Type 기반 캡처 (모든 도메인)
chrome.webRequest.onHeadersReceived.addListener(
    (details) => {
        const ctHeader = details.responseHeaders?.find(
            h => h.name.toLowerCase() === 'content-type'
        );
        const contentType = ctHeader?.value || '';

        const isVideo = contentType.includes('video');
        if (!isVideo) return;

        // 너무 작은 응답 무시 (썸네일 등)
        const clHeader = details.responseHeaders?.find(
            h => h.name.toLowerCase() === 'content-length'
        );
        const contentLength = parseInt(clHeader?.value || '0', 10);
        if (contentLength > 0 && contentLength < 100000) return; // 100KB 미만 무시

        addVideo(details.tabId, details, contentType, contentLength);
    },
    { urls: ['<all_urls>'] },
    ['responseHeaders']
);

// 2) media 리소스 타입 캡처 (브라우저가 media로 분류한 요청)
chrome.webRequest.onCompleted.addListener(
    (details) => {
        if (details.type !== 'media') return;
        if (isCameraPreset(details.url)) return;

        if (!capturedVideos.has(details.tabId)) {
            capturedVideos.set(details.tabId, []);
        }
        const list = capturedVideos.get(details.tabId);
        if (isDuplicate(list, details.url)) return;

        list.push({
            url: details.url,
            timestamp: Date.now(),
            contentType: 'media',
            size: 0,
        });

        console.log(`[FlowBridge BG] 🎬 Media: ${details.url.substring(0, 150)}`);
    },
    { urls: ['<all_urls>'] }
);

// 메시지 핸들러
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg.action === 'get_captured_videos') {
        const allVideos = [];

        // 전체 탭에서 수집 (탭 제한 없이)
        for (const [, videos] of capturedVideos) {
            allVideos.push(...videos);
        }

        // 전체 결과에서도 URL 기반 중복 제거
        const seen = new Set();
        const deduped = [];
        for (const v of allVideos) {
            const base = getUrlBase(v.url);
            if (!seen.has(base)) {
                seen.add(base);
                deduped.push(v);
            }
        }

        // 최근 2시간 내 영상만, 시간순 정렬
        const recent = deduped
            .filter(v => Date.now() - v.timestamp < 2 * 60 * 60 * 1000)
            .sort((a, b) => a.timestamp - b.timestamp);

        console.log(`[FlowBridge BG] Returning ${recent.length} captured videos (from ${allVideos.length} total)`);
        sendResponse({ videos: recent });
        return true;
    }

    if (msg.action === 'clear_captured_videos') {
        capturedVideos.clear();
        console.log('[FlowBridge BG] Cleared all captured videos');
        sendResponse({ status: 'ok' });
        return true;
    }

    if (msg.action === 'get_video_count') {
        let total = 0;
        for (const [, videos] of capturedVideos) {
            total += videos.filter(v => Date.now() - v.timestamp < 2 * 60 * 60 * 1000).length;
        }
        sendResponse({ count: total });
        return true;
    }
});

console.log('[FlowBridge BG] v2 started - monitoring ALL domains for video URLs');
