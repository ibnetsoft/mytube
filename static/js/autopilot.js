// --- Initialization ---

document.addEventListener('DOMContentLoaded', async () => {
    // 1. Load Presets (Styles & Voices)
    await Promise.all([loadStyles(), loadVoices(), fetchPresets()]);

    // 2. Load Saved Settings (Global / Default Project)
    // 2. Load Saved Settings (Global / Default Project)
    await Promise.all([loadSavedSettings(), loadSubtitleDefaults()]);

    // 3. Event Listeners
    const startBtn = document.getElementById('startAutopilotBtn');
    if (startBtn) {
        startBtn.addEventListener('click', startAutopilot);
    }

    const sceneRange = document.getElementById('videoSceneCount');
    const sceneVal = document.getElementById('sceneCountVal');
    const allVideoCheck = document.getElementById('allVideoCheck');

    if (sceneRange && sceneVal) {
        sceneRange.addEventListener('input', (e) => {
            if (allVideoCheck && allVideoCheck.checked) return;
            sceneVal.textContent = `${e.target.value} Scenes`;
        });
    }

    if (allVideoCheck && sceneRange && sceneVal) {
        allVideoCheck.addEventListener('change', (e) => {
            if (e.target.checked) {
                sceneRange.disabled = true;
                sceneRange.classList.add('opacity-30');
                sceneVal.textContent = `ALL Scenes`;
                sceneVal.classList.replace('bg-pink-500/10', 'bg-pink-500');
                sceneVal.classList.replace('text-pink-400', 'text-white');
            } else {
                sceneRange.disabled = false;
                sceneRange.classList.remove('opacity-30');
                sceneVal.textContent = `${sceneRange.value} Scenes`;
                sceneVal.classList.replace('bg-pink-500', 'bg-pink-500/10');
                sceneVal.classList.replace('text-white', 'text-pink-400');
            }
        });
    }

    // [NEW] Check Monitor Mode
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('monitor') === 'true' && urlParams.get('project_id')) {
        const pid = urlParams.get('project_id');
        console.log("🔄 Monitoring Project:", pid);
        const startBtn = document.getElementById('startAutopilotBtn');
        if (startBtn) {
            startBtn.disabled = true;
            startBtn.innerText = "🔄 Processing... (Monitoring Mode)";
        }
        pollStatus(pid);
    }
});

// Styles will be loaded dynamically from API
async function loadStyles() {
    // 1. Visual Styles (fetch from DB)
    const vGrid = document.getElementById('styleSelectorGrid');
    if (vGrid) {
        vGrid.innerHTML = '<div class="col-span-full py-4 text-center text-gray-500 text-[10px]">불러오는 중...</div>';
        try {
            const res = await fetch('/api/settings/style-presets');
            const data = await res.json();

            vGrid.innerHTML = '';
            Object.entries(data).forEach(([key, val]) => {
                // If customized style has image_url, use it. Otherwise, use default path.
                const imgUrl = (typeof val === 'object' && val.image_url) ? val.image_url : `/static/img/styles/style_${key}.png`;

                const style = {
                    id: key,
                    name: (typeof val === 'object' && val.name_ko) ? val.name_ko : key,
                    img: imgUrl
                };
                const div = createStyleCard(style, 'imageStyle');
                vGrid.appendChild(div);
            });

            // Set default
            const currentImgStyle = document.getElementById('imageStyle').value;
            if (currentImgStyle && data[currentImgStyle]) {
                selectStyle('imageStyle', currentImgStyle);
            } else {
                const firstKey = Object.keys(data)[0];
                if (firstKey) selectStyle('imageStyle', firstKey);
            }
        } catch (e) {
            console.error("Failed to load visual styles:", e);
        }
    }

    // 2. Thumbnail Styles (fetch from DB)
    const tGrid = document.getElementById('thumbnailStyleGrid');
    if (tGrid) {
        tGrid.innerHTML = '<div class="col-span-full py-4 text-center text-gray-500 text-[10px]">불러오는 중...</div>';
        try {
            const res = await fetch('/api/settings/thumbnail-style-presets');
            const data = await res.json();

            // Default Korean Labels for system styles
            const defaultNames = {
                'face': '얼굴 강조형',
                'text': '텍스트 중심형',
                'wimpy': '윔피키드 스타일',
                'ghibli': '지브리 감성',
                'dramatic': '드라마틱형',
                'mystery': '미스터리형',
                'minimal': '미니멀형'
            };

            tGrid.innerHTML = '';
            Object.entries(data).forEach(([key, val]) => {
                const imgUrl = (typeof val === 'object' && val.image_url) ? val.image_url : `/static/img/thumbs/${key}.png`;

                const style = {
                    id: key,
                    name: defaultNames[key] || key,
                    img: imgUrl
                };
                const div = createStyleCard(style, 'thumbnailStyle');
                tGrid.appendChild(div);
            });

            // Set default
            const currentThumbStyle = document.getElementById('thumbnailStyle').value;
            if (currentThumbStyle && data[currentThumbStyle]) {
                selectStyle('thumbnailStyle', currentThumbStyle);
            } else {
                const firstKey = Object.keys(data)[0];
                if (firstKey) selectStyle('thumbnailStyle', firstKey);
            }
        } catch (e) {
            console.error("Failed to load thumbnail styles:", e);
        }
    }
}

function createStyleCard(style, inputId) {
    const div = document.createElement('div');
    div.className = `cursor-pointer relative group rounded-xl overflow-hidden border-2 border-transparent hover:border-purple-500 transition-all bg-gray-800 aspect-video style-card-${inputId}`;
    div.dataset.value = style.id;
    div.onclick = () => selectStyle(inputId, style.id);

    // Filter name for display (remove paths if any)
    const displayName = style.name.split('/').pop().replace(/_/g, ' ');

    div.innerHTML = `
        <img src="${style.img}" class="w-full h-full object-cover opacity-80 group-hover:opacity-100 transition-opacity" alt="${style.name}" 
            onerror="this.style.display='none'; this.parentElement.innerHTML='<div class=\\'flex flex-col items-center justify-center h-full p-2 text-center\\'><div class=\\'text-xl mb-1\\'>🎨</div><div class=\\'text-[9px] text-gray-400 font-medium leading-tight truncate w-full\\'>${displayName}</div></div>';">
        <div class="absolute bottom-0 inset-x-0 bg-black/60 p-1.5 text-center transition-transform translate-y-0">
            <span class="text-[10px] text-white font-medium block truncate">${displayName}</span>
        </div>
        <div class="absolute top-2 right-2 bg-purple-600 rounded-full p-1 opacity-0 check-icon transition-opacity shadow-lg">
            <svg class="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7"></path></svg>
        </div>
    `;
    return div;
}

function selectStyle(inputId, val) {
    const input = document.getElementById(inputId);
    if (!input) return;
    input.value = val;

    // Visual Update
    const container = inputId === 'imageStyle' ? document.getElementById('styleSelectorGrid') : document.getElementById('thumbnailStyleGrid');
    if (!container) return;

    // Remove active state from all siblings
    container.querySelectorAll('div[data-value]').forEach(el => {
        el.classList.remove('border-purple-500', 'ring-2', 'ring-purple-500/50');
        el.classList.add('border-transparent');
        el.querySelector('.check-icon')?.classList.add('opacity-0');
    });

    // Add active state to selected
    const selected = container.querySelector(`div[data-value="${val}"]`);
    if (selected) {
        selected.classList.remove('border-transparent');
        selected.classList.add('border-purple-500', 'ring-2', 'ring-purple-500/50');
        selected.querySelector('.check-icon')?.classList.remove('opacity-0');
    }
}

// [NEW] Mode Selection
function setMode(mode) {
    const input = document.getElementById('appMode');
    if (!input) return;
    input.value = mode;

    // Visual update
    const btnLong = document.getElementById('modeLongform');
    const btnShort = document.getElementById('modeShorts');

    if (mode === 'longform') {
        btnLong.classList.replace('text-gray-500', 'bg-purple-600');
        btnLong.classList.replace('text-white', 'text-white'); // ensure text is white
        btnLong.classList.add('bg-purple-600', 'text-white', 'font-bold');

        btnShort.classList.remove('bg-purple-600', 'text-white', 'font-bold');
        btnShort.classList.add('text-gray-500');

        // Update Duration Label to 'Min'
        const durLabel = document.querySelector('#targetDuration + span');
        if (durLabel) durLabel.innerText = '분';
        const durInput = document.getElementById('targetDuration');
        if (durInput && durInput.value == 60) durInput.value = 10; // Reset if it was set for shorts
    } else {
        btnShort.classList.add('bg-purple-600', 'text-white', 'font-bold');
        btnShort.classList.remove('text-gray-500');

        btnLong.classList.remove('bg-purple-600', 'text-white', 'font-bold');
        btnLong.classList.add('text-gray-500');

        // Update Duration Label to 'Sec'
        const durLabel = document.querySelector('#targetDuration + span');
        if (durLabel) durLabel.innerText = '초';
        const durInput = document.getElementById('targetDuration');
        if (durInput) durInput.value = 60; // Default for shorts
    }
}

// [NEW] Motion Method Selection
function setMotionMethod(method) {
    const input = document.getElementById('motionMethod');
    if (!input) return;
    input.value = method;

    // Visual update
    document.querySelectorAll('.motion-method-btn').forEach(btn => {
        if (btn.dataset.value === method) {
            btn.classList.replace('bg-gray-800', 'bg-purple-600');
            btn.classList.replace('text-gray-400', 'text-white');
            btn.classList.add('font-bold', 'shadow-sm');
        } else {
            btn.classList.replace('bg-purple-600', 'bg-gray-800');
            btn.classList.replace('text-white', 'text-gray-400');
            btn.classList.remove('font-bold', 'shadow-sm');
        }
    });
}



async function loadVoices() {
    const providerSelect = document.getElementById('providerSelect');
    const voiceSelect = document.getElementById('voiceSelect');
    const scriptSelect = document.getElementById('scriptStyleSelect');

    if (!providerSelect || !voiceSelect) return;

    // Load Script Styles if select exists
    if (scriptSelect) {
        try {
            const res = await fetch('/api/settings/script-style-presets');
            const data = await res.json();

            // Keep current value if possible
            const currentVal = scriptSelect.value;
            scriptSelect.innerHTML = '';

            Object.keys(data).forEach(key => {
                const opt = document.createElement('option');
                opt.value = key;
                opt.innerText = key;
                scriptSelect.appendChild(opt);
            });

            if (data[currentVal]) scriptSelect.value = currentVal;
            else if (Object.keys(data).length > 0) scriptSelect.value = Object.keys(data)[0];

        } catch (e) {
            console.error("Failed to load script styles:", e);
        }
    }

    // Provider Change Event
    providerSelect.onchange = async () => {
        const provider = providerSelect.value;
        voiceSelect.innerHTML = '<option>Loading...</option>';
        await fetchVoices(provider);
    };

    // Initial fetch triggered in init
}

async function fetchVoices(provider) {
    const voiceSelect = document.getElementById('voiceSelect');
    if (!voiceSelect) return;

    voiceSelect.innerHTML = '<option>Loading...</option>';
    console.log("[Autopilot] Fetching voices for provider:", provider);

    try {
        // For non-API providers, use static lists
        if (provider === 'gemini') {
            voiceSelect.innerHTML = '';
            ['Puck', 'Charon', 'Kore', 'Fenrir', 'Aoede'].forEach(name => {
                const opt = document.createElement('option');
                opt.value = name;
                opt.innerText = `Gemini - ${name}`;
                voiceSelect.appendChild(opt);
            });
            return;
        }

        if (provider === 'google_cloud') {
            voiceSelect.innerHTML = '';
            [
                { id: 'ko-KR-Neural2-A', name: 'G-Neural2 A(여)' },
                { id: 'ko-KR-Neural2-C', name: 'G-Neural2 C(남)' },
                { id: 'ko-KR-Standard-A', name: 'G-Std A(여)' }
            ].forEach(v => {
                const opt = document.createElement('option');
                opt.value = v.id;
                opt.innerText = v.name;
                voiceSelect.appendChild(opt);
            });
            return;
        }

        if (provider === 'openai') {
            voiceSelect.innerHTML = '';
            ['alloy', 'echo', 'shimmer', 'nova', 'onyx', 'fable'].forEach(name => {
                const opt = document.createElement('option');
                opt.value = name;
                opt.innerText = `OpenAI - ${name}`;
                voiceSelect.appendChild(opt);
            });
            return;
        }

        // ElevenLabs - fetch from API
        const res = await fetch('/api/tts/voices');
        const data = await res.json();
        voiceSelect.innerHTML = '';

        console.log("[Autopilot] API returned voices:", data.voices?.length || 0);

        const voices = (data.voices || []).filter(v => v.provider === provider || (!v.provider && provider === 'elevenlabs'));

        if (voices.length === 0) {
            voiceSelect.innerHTML = '<option value="">No voices available (Check API Key)</option>';
            return;
        }

        voices.forEach(v => {
            const opt = document.createElement('option');
            opt.value = v.voice_id || v.id;
            opt.innerText = v.name;
            voiceSelect.appendChild(opt);
        });

        console.log("[Autopilot] Loaded", voices.length, "voices for", provider);

    } catch (e) {
        console.error("Voice load error:", e);
        voiceSelect.innerHTML = '<option value="">Error loading voices</option>';
    }
}

async function loadSavedSettings() {
    try {
        const res = await fetch('/api/settings');
        const data = await res.json();

        if (data) {
            log("⚙️ Loaded Saved Settings");

            if (data.app_mode) {
                setMode(data.app_mode);
            }


            // 1. TTS Settings
            if (data.voice_provider) {
                const pSelect = document.getElementById('providerSelect');
                if (pSelect) {
                    pSelect.value = data.voice_provider;
                    // Wait for voices to load before setting voice_id
                    await fetchVoices(data.voice_provider);
                }
            } else {
                // Default fetch
                await fetchVoices(document.getElementById('providerSelect').value);
            }

            // [FIX] Support both voice_id and voice_name
            const savedVoiceId = data.voice_id || data.voice_name;
            console.log("[Autopilot] Trying to select voice:", savedVoiceId);

            if (savedVoiceId) {
                const vSelect = document.getElementById('voiceSelect');
                if (vSelect) {
                    vSelect.value = savedVoiceId;

                    // If exact match failed (value is empty or first option), try to find by partial match
                    if (!vSelect.value || vSelect.selectedIndex === 0) {
                        console.log("[Autopilot] Exact match failed, trying partial match...");
                        const options = Array.from(vSelect.options);
                        const match = options.find(opt =>
                            opt.value === savedVoiceId ||
                            opt.textContent.toLowerCase().includes(savedVoiceId.toLowerCase())
                        );
                        if (match) {
                            vSelect.value = match.value;
                            console.log("[Autopilot] Partial match found:", match.value);
                        }
                    }

                    console.log("[Autopilot] Voice selected:", vSelect.value);
                }
            }

            // 2. Image Style
            if (data.image_style) {
                selectStyle('imageStyle', data.image_style);
            } else {
                selectStyle('imageStyle', 'realistic'); // Default
            }

            // 3. Thumbnail Style
            console.log("[Autopilot] Loaded thumbnail_style from settings:", data.thumbnail_style);
            if (data.thumbnail_style) {
                selectStyle('thumbnailStyle', data.thumbnail_style);
                console.log("[Autopilot] Applied thumbnail style:", data.thumbnail_style);
            } else if (data.image_style) {
                // Intelligent fallback: Sync with Image Style
                const mapped = mapImageToThumb(data.image_style);
                selectStyle('thumbnailStyle', mapped);
                console.log("[Autopilot] Fallback thumbnail style from image_style:", mapped);
            } else {
                selectStyle('thumbnailStyle', 'face'); // Default
                console.log("[Autopilot] Using default thumbnail style: face");
            }

            // 4. Script Style
            if (data.script_style) {
                const sSelect = document.getElementById('scriptStyleSelect');
                if (sSelect) sSelect.value = data.script_style;
            }

            // [NEW] Duration
            if (data.duration_seconds) {
                const minutes = Math.round(data.duration_seconds / 60);
                const durInput = document.getElementById('targetDuration');
                if (durInput && minutes > 0) {
                    durInput.value = minutes;
                    console.log("[Autopilot] Loaded duration:", minutes, "min");
                }
            }

            // 5. Last Topic (Global)
            if (data.last_topic) {
                const topicInput = document.getElementById('topicInput');
                if (topicInput && !topicInput.value) {
                    topicInput.value = data.last_topic;
                }
            }

            // 6. Duration (Global)
            if (data.duration_seconds) {
                window.loadedDurationSeconds = data.duration_seconds;
                // Estimate scenes: 1 min ~ 1 scene (minimum 3)
                let estScenes = Math.floor(data.duration_seconds / 60);
                if (estScenes < 1) estScenes = 1;
                if (estScenes > 20) estScenes = 20;

                const range = document.getElementById('videoSceneCount');
                if (range) {
                    range.value = estScenes;
                    // Update display
                    const display = document.getElementById('sceneCountVal');
                    if (display) display.innerText = estScenes + " Scenes";
                }
            }
        }
    } catch (e) {
        console.error("Settings load fail:", e);
        // Fallback: Load voices anyway
        await fetchVoices(document.getElementById('providerSelect').value);
    }
}

function mapImageToThumb(imgStyle) {
    const map = {
        'realistic': 'face',
        'anime': 'ghibli',
        'cinematic': 'dramatic',
        'minimal': 'minimal',
        'webtoon': 'wimpy',
        'korean_webtoon': 'japanese_viral',
    };
    return map[imgStyle] || 'face';
}

function log(msg) {
    const area = document.getElementById('consoleLogs');
    if (!area) return;

    const div = document.createElement('div');
    const time = new Date().toLocaleTimeString();
    div.className = `text-gray-400 text-xs border-b border-gray-800 py-1`;
    div.innerHTML = `<span class="opacity-50">[${time}]</span> ${msg}`;

    area.appendChild(div);
    area.scrollTop = area.scrollHeight;
}

function clearLogs() {
    const area = document.getElementById('consoleLogs');
    if (area) area.innerHTML = '<div class="text-gray-500 italic">Logs cleared.</div>';
}

// --- Autopilot Logic ---

let isProcessing = false;

async function startAutopilot() {
    if (isProcessing) return;

    const topicInput = document.getElementById('topicInput');
    const topic = topicInput ? topicInput.value.trim() : '';

    if (!topic) {
        alert("Please enter a topic keyword.");
        topicInput.focus();
        return;
    }

    const startBtn = document.getElementById('startAutopilotBtn');

    // UI Loading State
    isProcessing = true;
    if (startBtn) {
        startBtn.disabled = true;
        startBtn.innerHTML = '🚀 Starting...';
    }
    clearLogs();
    log("🚀 Launching Auto-Pilot...");

    // Build Config
    // Build Config
    const config = {
        keyword: topic,
        mode: document.getElementById('appMode')?.value || 'longform', // [NEW]
        image_style: document.getElementById('imageStyle').value,
        thumbnail_style: document.getElementById('thumbnailStyle').value,
        video_scene_count: parseInt(document.getElementById('videoSceneCount').value || 0),
        all_video: document.getElementById('allVideoCheck')?.checked || false, // [NEW]
        motion_method: document.getElementById('motionMethod')?.value || 'standard', // [NEW]
        script_style: document.getElementById('scriptStyleSelect').value,
        voice_provider: document.getElementById('providerSelect').value,
        voice_id: document.getElementById('voiceSelect').value,
        duration_seconds: (function () {
            const val = parseInt(document.getElementById('targetDuration').value);
            const m = document.getElementById('appMode')?.value || 'longform';
            if (m === 'shorts') return val || 60; // Seconds
            return (val || 10) * 60; // Minutes to Seconds
        })(),
        subtitle_settings: window.currentSubtitleSettings || null, // [NEW]
        preset_id: document.getElementById('presetSelect') ? (parseInt(document.getElementById('presetSelect').value) || null) : null
    };

    log(`🎬 Mode: ${config.mode} | ImageStyle: ${config.image_style} | Thumb: ${config.thumbnail_style}`);

    log(`🎙️ Voice: ${config.voice_provider} / ${config.voice_id}`);

    try {
        const res = await fetch('/api/autopilot/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });
        const data = await res.json();

        if (data.status === 'ok') {
            log("✅ Workflow started. Project ID: " + data.project_id);
            pollStatus(data.project_id);
        } else {
            throw new Error(data.error || "Failed to start");
        }
    } catch (e) {
        log("❌ FAIL: " + e.message);
        isProcessing = false;
        if (startBtn) {
            startBtn.disabled = false;
            startBtn.innerHTML = '🚀 Start Auto-Pilot';
        }
    }
}

function pollStatus(projectId) {
    const interval = setInterval(async () => {
        try {
            const res = await fetch(`/api/projects/${projectId}/full`);
            const data = await res.json();

            const status = data.project?.status || "processing";
            if (document.getElementById('consoleLogs')) {
                const lastLog = document.getElementById('consoleLogs').lastElementChild;
                if (lastLog && lastLog.textContent.includes("Status:")) {
                    lastLog.innerHTML = `<span class="opacity-50">[${new Date().toLocaleTimeString()}]</span> ... Status: ${status}`;
                } else {
                    log(`... Status: ${status}`);
                }
            }

            if (status === 'done') {
                clearInterval(interval);
                isProcessing = false;
                log("🏁 Process Completed!");

                // Done Action
                const startBtn = document.getElementById('startAutopilotBtn');
                if (startBtn) {
                    startBtn.innerText = "✅ View Result";
                    startBtn.onclick = () => window.location.href = `/video-gen`;
                    startBtn.disabled = false;
                }

                // Auto redirect after 2s
                setTimeout(() => {
                    window.location.href = '/video-gen';
                }, 2000);

            } else if (status === 'error') {
                clearInterval(interval);
                isProcessing = false;
                log("❌ Error occurred.");
                document.getElementById('startAutopilotBtn').disabled = false;
            }
        } catch (e) {
            console.error("Poll error:", e);
        }
    }, 5000);
}

/* =========================================
   [NEW] Batch Mode Logic
   ========================================= */

function switchTab(mode) {
    const single = document.getElementById('singleMode');
    const batch = document.getElementById('batchMode');
    const tabSingle = document.getElementById('tabSingle');
    const tabBatch = document.getElementById('tabBatch');

    if (mode === 'single') {
        single.classList.remove('hidden');
        batch.classList.add('hidden');
        tabSingle.classList.add('border-purple-500', 'text-purple-400');
        tabSingle.classList.remove('border-transparent', 'text-gray-400');
        tabBatch.classList.remove('border-purple-500', 'text-purple-400');
        tabBatch.classList.add('border-transparent', 'text-gray-400');
    } else {
        single.classList.add('hidden');
        batch.classList.remove('hidden');
        tabBatch.classList.add('border-purple-500', 'text-purple-400');
        tabBatch.classList.remove('border-transparent', 'text-gray-400');
        tabSingle.classList.remove('border-purple-500', 'text-purple-400');
        tabSingle.classList.add('border-transparent', 'text-gray-400');
        refreshQueue();
    }
}

async function refreshQueue() {
    const list = document.getElementById('queueList');
    const badge = document.getElementById('queueBadge');
    const countEl = document.getElementById('queueCount');

    list.innerHTML = `<div class="text-center py-12 text-gray-500"><div class="loader-sm mx-auto mb-2"></div>로딩 중...</div>`;

    try {
        const res = await fetch('/api/autopilot/queue');
        const data = await res.json();

        const projects = data.projects || [];
        const count = data.count || 0;

        if (badge) {
            badge.innerText = count;
            badge.classList.remove('hidden');
        }
        if (countEl) countEl.innerText = count;

        const btnStart = document.getElementById('btnStartBatch');

        if (count === 0) {
            list.innerHTML = `<div class="text-center py-12 text-gray-500">대기 중인 프로젝트가 없습니다.<br><span class="text-xs">기획 페이지에서 '담기' 버튼을 눌러 추가하세요.</span></div>`;
            if (btnStart) btnStart.disabled = true;
            return;
        }

        if (btnStart) btnStart.disabled = false;

        list.innerHTML = projects.map((p, idx) => `
            <div class="flex items-center justify-between p-4 bg-gray-800/50 rounded-xl border border-gray-700/50 hover:bg-gray-800 transition-all">
                <div class="flex items-center gap-4">
                    <div class="flex flex-col items-center">
                        <span class="text-gray-600 font-mono text-xs mb-1">SEQ</span>
                        <span class="text-purple-400 font-bold bg-purple-500/10 px-2 py-0.5 rounded text-sm">${idx + 1}</span>
                    </div>
                    <div>
                        <h4 class="font-bold text-white text-base mb-1">${p.topic || '제목 없음'}</h4>
                        <p class="text-xs text-gray-400 flex items-center gap-2">
                            <span>ID: ${p.id}</span>
                            <span class="text-gray-600">|</span>
                            <span>${new Date(p.created_at).toLocaleString()}</span>
                            ${p.status === 'queued' ? '<span class="text-yellow-500 bg-yellow-500/10 px-1.5 py-0.5 rounded ml-2">대기중</span>' : ''}
                        </p>
                    </div>
                </div>
                <div class="flex items-center gap-3">
                    <button onclick="deleteFromQueue(${p.id})" class="text-xs text-red-500 bg-red-500/10 px-3 py-1.5 rounded hover:bg-red-500 hover:text-white transition-all ml-2">삭제</button>
                </div>
            </div>
        `).join('');

    } catch (e) {
        console.error(e);
        list.innerHTML = `<div class="text-center py-12 text-red-500">목록 로드 실패</div>`;
    }
}

async function startBatch() {
    if (!confirm("대기열에 있는 모든 프로젝트를 순차적으로 제작하시겠습니까? (이 작업은 시간이 걸립니다)")) return;

    const btn = document.getElementById('btnStartBatch');
    btn.disabled = true;
    btn.innerHTML = `<span>⏳</span> 시작 요청 중...`;

    try {
        const res = await fetch('/api/autopilot/batch-start', { method: 'POST' });
        const data = await res.json();

        if (data.status === 'started') {
            Utils.showToast("일괄 제작이 시작되었습니다! 🚀", "success");
            btn.innerHTML = `<span class="loader-sm border-white"></span> 처리 중...`;

            const logArea = document.getElementById('batchConsoleLogs');
            logArea.innerHTML = `<div class="text-yellow-400 p-2">✅ 일괄 처리 작업이 시작되었습니다. 대기열이 줄어드는지 확인하세요.</div>`;

            // Start Polling Queue Count to show progress
            const interval = setInterval(async () => {
                await refreshQueue();
                const countText = document.getElementById('queueCount')?.innerText || "0";
                if (countText === "0") {
                    clearInterval(interval);
                    btn.disabled = false;
                    btn.innerHTML = `<span>▶️</span> 일괄 처리 시작`;
                    logArea.innerHTML += `<div class="text-green-400 p-2">🏁 모든 작업이 완료되었습니다!</div>`;
                    Utils.showToast("모든 작업 완료!", "success");
                }
            }, 5000);

        }
    } catch (e) {
        alert("실패: " + e.message);
        btn.disabled = false;
        btn.innerHTML = `<span>▶️</span> 일괄 처리 시작`;
    }
}

async function deleteFromQueue(pid) {
    if (!confirm("이 프로젝트를 대기열에서 제거하시겠습니까? (상태가 'planning'으로 되돌아갑니다)")) return;
    try {
        const res = await fetch(`/api/projects/${pid}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: 'planning' })
        });
        refreshQueue();
        Utils.showToast("대기열에서 제거되었습니다.", "info");
    } catch (e) { console.error(e); }
}

async function loadSubtitleDefaults() {
    const panel = document.getElementById('subtitlePreviewPanel');
    if (!panel) return;

    try {
        const res = await fetch('/api/settings/subtitle/defaults');
        const data = await res.json();
        const s = data.settings || {};

        // [NEW] Cache for Preset Saving & Start Payload
        window.currentSubtitleSettings = s;
        renderSubtitlePreview(s);

        if (data.status === 'ok') {
            // Already rendered by renderSubtitlePreview(s)
        } else {
            panel.innerHTML = `<div class="col-span-2 text-red-400 text-xs">설정 로드 실패</div>`;
        }
    } catch (e) {
        console.error(e);
        panel.innerHTML = `<div class="col-span-2 text-red-400 text-xs">연결 오류</div>`;
    }
}

// [NEW] Render Subtitle Preview (Helper)
function renderSubtitlePreview(s) {
    const panel = document.getElementById('subtitlePreviewPanel');
    if (!panel) return;

    // Logic extracted from above for reuse
    const fontName = s.subtitle_font || 'N/A';
    const size = s.subtitle_font_size ? `${s.subtitle_font_size}%` : 'N/A';
    const color = s.subtitle_color || 'N/A';
    const opacity = s.subtitle_bg_opacity !== undefined ? s.subtitle_bg_opacity : 'N/A';
    const stroke = s.subtitle_stroke_width > 0 ? `${s.subtitle_stroke_width}px` : 'None';
    const lineSpace = s.subtitle_line_spacing || '0.1';

    panel.innerHTML = `
        <div class="flex flex-col">
            <span class="text-xs text-gray-500">폰트 (Font)</span>
            <span class="font-bold text-white">${fontName}</span>
        </div>
        <div class="flex flex-col">
            <span class="text-xs text-gray-500">크기 (Size)</span>
            <span class="font-bold text-white">${size}</span>
        </div>
        <div class="flex flex-col">
            <span class="text-xs text-gray-500">색상 (Color)</span>
            <div class="flex items-center gap-2">
                <div class="w-3 h-3 rounded-full border border-gray-600" style="background-color: ${color}"></div>
                <span class="font-bold text-white">${color}</span>
            </div>
        </div>
        <div class="flex flex-col">
            <span class="text-xs text-gray-500">테두리 (Stroke)</span>
            <span class="font-bold text-white">${stroke}</span>
        </div>
        <div class="flex flex-col">
            <span class="text-xs text-gray-500">배경 투명도 (Opacity)</span>
            <span class="font-bold text-white">${opacity}</span>
        </div>
        <div class="flex flex-col">
            <span class="text-xs text-gray-500">줄 간격 (Spacing)</span>
            <span class="font-bold text-white">${lineSpace}</span>
        </div>
    `;
}

// [NEW] Preset Functions
async function fetchPresets() {
    const select = document.getElementById('presetSelect');
    if (!select) return;

    try {
        const res = await fetch('/api/autopilot/presets');
        const data = await res.json();

        select.innerHTML = '<option value="">-- 현재 설정 (Custom) --</option>';
        if (data.presets) {
            data.presets.forEach(p => {
                const opt = document.createElement('option');
                opt.value = p.id;
                opt.innerText = p.name;
                select.appendChild(opt);
            });
        }

    } catch (e) { console.error("Fetch presets error:", e); }
}

async function loadPreset(presetId) {
    if (!presetId) {
        document.getElementById('btnDeletePreset').classList.add('hidden');
        document.getElementById('newPresetName').value = ""; // Clear name
        return;
    }

    document.getElementById('btnDeletePreset').classList.remove('hidden');

    const select = document.getElementById('presetSelect');
    const selectedOption = select.options[select.selectedIndex];
    const presetName = selectedOption ? selectedOption.innerText : "";
    document.getElementById('newPresetName').value = presetName;

    try {
        const res = await fetch('/api/autopilot/presets');
        const data = await res.json();
        const preset = data.presets.find(p => p.id == presetId);

        if (preset && preset.settings) {
            applyPresetSettings(preset.settings);
            Utils.showToast(`프리셋 '${preset.name}' 로드 완료`, 'success');
        }
    } catch (e) {
        console.error(e);
        Utils.showToast('프리셋 로드 실패', 'error');
    }
}

function applyPresetSettings(s) {
    // [NEW] Mode
    if (s.mode) {
        setMode(s.mode);
    }

    // 1. Image Style
    if (s.image_style) selectStyle('imageStyle', s.image_style);
    if (s.visual_style) selectStyle('imageStyle', s.visual_style); // Fallback for old presets

    if (s.thumbnail_style) selectStyle('thumbnailStyle', s.thumbnail_style);

    // 2. Video
    if (s.video_scene_count !== undefined) {
        document.getElementById('videoSceneCount').value = s.video_scene_count;
        document.getElementById('sceneCountVal').innerText = s.video_scene_count + " Scenes";
    }

    // [NEW] All Video Toggle
    if (s.all_video !== undefined) {
        const check = document.getElementById('allVideoCheck');
        if (check) {
            check.checked = s.all_video;
            check.dispatchEvent(new Event('change')); // Trigger visual update
        }
    }

    // [NEW] Motion Method
    if (s.motion_method) {
        setMotionMethod(s.motion_method);
    }
    if (s.duration_seconds) {
        document.getElementById('targetDuration').value = Math.round(s.duration_seconds / 60);
    }

    // 3. Script
    if (s.script_style) {
        document.getElementById('scriptStyleSelect').value = s.script_style;
    }

    // 4. Voice
    if (s.voice_provider) {
        document.getElementById('providerSelect').value = s.voice_provider;
        // Trigger change? No, manually update voice
        // We need to wait for voice fetch? 
        // This is tricky. Simplified for now.
    }

    // 5. Subtitles (Most Important)
    if (s.subtitle_settings) {
        window.currentSubtitleSettings = s.subtitle_settings;
        renderSubtitlePreview(s.subtitle_settings);
    }
}

async function saveCurrentPreset() {
    const nameInput = document.getElementById('newPresetName');
    const name = nameInput.value.trim();
    if (!name) return alert("프리셋 이름을 입력해주세요.");

    const currentSettings = {
        name: name,
        settings: {
            mode: document.getElementById('appMode')?.value || 'longform',
            image_style: document.getElementById('imageStyle').value,
            thumbnail_style: document.getElementById('thumbnailStyle').value,
            video_scene_count: parseInt(document.getElementById('videoSceneCount').value || 0),
            all_video: document.getElementById('allVideoCheck')?.checked || false,
            motion_method: document.getElementById('motionMethod')?.value || 'standard',
            script_style: document.getElementById('scriptStyleSelect').value,
            voice_provider: document.getElementById('providerSelect').value,
            voice_id: document.getElementById('voiceSelect').value,
            target_duration: parseInt(document.getElementById('targetDuration').value || 10),
            subtitle_settings: window.currentSubtitleSettings || null
        }
    };

    try {
        const res = await fetch('/api/autopilot/presets', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(currentSettings)
        });
        const data = await res.json();
        if (data.status === 'ok') {
            Utils.showToast("프리셋이 저장되었습니다!", "success");
            fetchPresets(); // refresh list
        } else {
            alert("Error: " + data.error);
        }
    } catch (e) {
        console.error(e);
    }
}

async function deleteCurrentPreset() {
    const select = document.getElementById('presetSelect');
    const pid = select.value;
    if (!pid) return;

    const name = select.options[select.selectedIndex].innerText;
    if (!confirm(`'${name}' 프리셋을 정말 삭제할까요?`)) return;

    try {
        const res = await fetch(`/api/autopilot/presets/${pid}`, { method: 'DELETE' });
        const data = await res.json();
        if (data.status === 'ok') {
            Utils.showToast("프리셋이 삭제되었습니다.", "success");
            fetchPresets();
            document.getElementById('btnDeletePreset').classList.add('hidden');
            document.getElementById('newPresetName').value = "";
        } else {
            alert("삭제 실패: " + data.error);
        }
    } catch (e) { console.error(e); }
}


