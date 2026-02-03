// --- Initialization ---

document.addEventListener('DOMContentLoaded', async () => {
    // 1. Load Presets (Styles & Voices)
    await Promise.all([loadStyles(), loadVoices()]);

    // 2. Load Saved Settings (Global / Default Project)
    await loadSavedSettings();
});

// Styles Configuration
const VISUAL_STYLES = [
    { id: 'realistic', name: '사실적인 (Realistic)', img: '/static/img/styles/style_realistic.png' },
    { id: 'anime', name: '애니메이션 (Anime)', img: '/static/img/styles/style_anime.png' },
    { id: 'cinematic', name: '시네마틱 (Cinematic)', img: '/static/img/styles/style_cinematic.png' },
    { id: 'minimal', name: '미니멀 (Minimal)', img: '/static/img/styles/style_minimal.png' },
    { id: '3d', name: '3D 렌더 (3D Render)', img: '/static/img/styles/style_3d.png' },
    { id: 'webtoon', name: '웹툰 (Webtoon)', img: '/static/img/styles/style_webtoon.png' },
    { id: 'ghibli', name: '지브리 (Ghibli)', img: '/static/img/styles/style_ghibli.png' },
    { id: 'wimpy', name: '윔피키드 (Wimpy Kid)', img: '/static/img/styles/style_wimpy.png' },
    { id: 'korean_webtoon', name: '한국웹 (Korea)', img: '/static/img/styles/style_korean_webtoon.png' }
];

const THUMBNAIL_STYLES = [
    { id: 'face', name: '얼굴 강조형', img: '/static/img/thumbs/face.png' },
    { id: 'text', name: '텍스트 중심형', img: '/static/img/thumbs/text.png' },
    { id: 'wimpy', name: '윔피키드 스타일', img: '/static/img/thumbs/wimpy.png' },
    { id: '시니어사연2', name: '시니어사연2', img: '/static/img/custom_styles/thumb_시니어사연2_1e07c4d6.png' },
    { id: 'ghibli', name: '지브리 감성', img: '/static/img/thumbs/ghibli.png' },
    { id: 'dramatic', name: '드라마틱형', img: '/static/img/thumbs/dramatic.png' },
    { id: 'mystery', name: '미스터리형', img: '/static/img/thumbs/mystery.png' },
    { id: 'minimal', name: '미니멀형', img: '/static/img/thumbs/minimal.png' }
];

async function loadStyles() {
    // 1. Visual Styles
    const vGrid = document.getElementById('styleSelectorGrid');
    if (vGrid) {
        vGrid.innerHTML = '';
        VISUAL_STYLES.forEach(style => {
            const div = createStyleCard(style, 'imageStyle');
            vGrid.appendChild(div);
        });
    }

    // 2. Thumbnail Styles
    const tGrid = document.getElementById('thumbnailStyleGrid');
    if (tGrid) {
        tGrid.innerHTML = '';
        THUMBNAIL_STYLES.forEach(style => {
            const div = createStyleCard(style, 'thumbnailStyle');
            tGrid.appendChild(div);
        });
    }
}

function createStyleCard(style, inputId) {
    const div = document.createElement('div');
    // Using style-card class conventions from other pages if possible, but tailwind here is self-contained.
    div.className = `cursor-pointer relative group rounded-xl overflow-hidden border-2 border-transparent hover:border-purple-500 transition-all bg-gray-800 aspect-video style-card-${inputId}`;
    div.dataset.value = style.id;
    div.onclick = () => selectStyle(inputId, style.id);

    div.innerHTML = `
        <img src="${style.img}" class="w-full h-full object-cover opacity-80 group-hover:opacity-100 transition-opacity" alt="${style.name}" onerror="this.onerror=null; this.src='data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22160%22 height=%2290%22%3E%3Crect fill=%22%23374151%22 width=%22160%22 height=%2290%22/%3E%3Ctext fill=%22%239CA3AF%22 x=%22%2550%22 y=%22%2550%22 text-anchor=%22middle%22 dy=%22.3em%22%3ENo Image%3C/text%3E%3C/svg%3E';">
        <div class="absolute bottom-0 inset-x-0 bg-black/60 p-1.5 text-center transition-transform translate-y-0">
            <span class="text-[10px] text-white font-medium block truncate">${style.name}</span>
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


async function loadVoices() {
    const providerSelect = document.getElementById('providerSelect');
    const voiceSelect = document.getElementById('voiceSelect');

    if (!providerSelect || !voiceSelect) return;

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

async function startAutoPilot() {
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
    const config = {
        keyword: topic,
        visual_style: document.getElementById('imageStyle').value,
        thumbnail_style: document.getElementById('thumbnailStyle').value, // [NEW]
        video_scene_count: parseInt(document.getElementById('videoSceneCount').value || 0),
        script_style: document.getElementById('scriptStyleSelect').value,
        voice_provider: document.getElementById('providerSelect').value,
        voice_id: document.getElementById('voiceSelect').value,
        duration_seconds: (parseInt(document.getElementById('targetDuration').value) || 10) * 60
    };

    log(`🎬 Visual: ${config.visual_style} | Thumb: ${config.thumbnail_style}`);
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
