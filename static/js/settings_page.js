// Tab switching
    function switchTab(tabName) {
        if (IS_STANDARD_MEMBER && !['api', 'history', 'withdrawal', 'referral'].includes(tabName)) {
            tabName = 'api';
        }
        console.log('Switching to tab:', tabName);

        // Hide all tabs
        document.querySelectorAll('.tab-content').forEach(tab => {
            tab.classList.remove('active');
            console.log('Hiding tab:', tab.id);
        });
        document.querySelectorAll('.tab-button').forEach(btn => {
            btn.classList.remove('active');
        });

        // Show selected tab
        const targetTab = document.getElementById(`tab-content-${tabName}`);
        const targetBtn = document.getElementById(`tab-${tabName}`);

        if (targetTab && targetBtn) {
            targetTab.classList.add('active');
            targetBtn.classList.add('active');
            console.log('Showing tab:', targetTab.id);
        } else {
            console.error('Tab not found:', tabName, 'targetTab:', targetTab, 'targetBtn:', targetBtn);
        }

        // Load data if needed
        if (tabName === 'image-styles') {
            loadStylePresets();
        } else if (tabName === 'script-styles') {
            loadScriptStylePresets();
        } else if (tabName === 'thumbnail-styles') {
            loadThumbnailStylePresets();
        } else if (tabName === 'withdrawal') {
            if (typeof fetchWithdrawalHistory === 'function') {
                fetchWithdrawalHistory();
            }
        } else if (tabName === 'referral') {
            if (typeof loadReferralData === 'function') {
                loadReferralData();
            }
        } else if (tabName === 'history') {
            if (typeof fetchWorkHistory === 'function') {
                fetchWorkHistory();
            }
        } else if (tabName === 'settlement') {
            if (typeof fetchSettlementData === 'function') {
                fetchSettlementData();
            }
        }
    }

    // Gemini Constants
    const GEMINI_VOICES = [
        "Puck", "Charon", "Kore", "Fenrir", "Aoede", "Zephyr", "Orpheus", "Cupid",
        "Autonoe", "Callirrhoe", "Laomedeia", "Leda", "Despina", "Sulafat",
        "Algenib", "Alnilam", "Achernar", "Achird", "Enceladus", "Vega",
        "Ursa", "Pegasus", "Nova", "Eclipse", "Lyra", "Orbit", "Dipper",
        "Capella", "Orion"
    ];

    const currentProjectId = window.SETTINGS_CURRENT_PROJECT_ID || '';

    const GEMINI_LANGUAGES = [
        "ko-KR", "en-US", "ja-JP", "es-US", "fr-FR", "de-DE", "hi-IN", "id-ID",
        "it-IT", "pt-BR", "ru-RU", "nl-NL", "pl-PL", "th-TH", "tr-TR", "vi-VN",
        "ro-RO", "uk-UA", "bn-BD", "en-IN", "mr-IN", "ta-IN", "te-IN", "ar-EG"
    ];

    async function updateProjectName() {
        const nameInput = document.getElementById('projectNameInput');
        const newName = nameInput.value.trim();
        
        if (!currentProjectId) {
            Utils.showToast(i18n.toast_project_not_selected, "error");
            return;
        }
        
        if (!newName) {
            Utils.showToast(i18n.toast_enter_new_name, "warning");
            return;
        }
        
        try {
            const res = await fetch(`/api/projects/${currentProjectId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: newName })
            });
            
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || "이름 변경 실패");
            }
            
            Utils.showToast(i18n.toast_project_renamed, "success");
            
            // Reload after a short delay
            setTimeout(() => {
                location.reload();
            }, 1000);
            
        } catch (e) {
            Utils.showToast("오류 발생: " + e.message, "error");
        }
    }

    // [NEW] Default Master Prompt for Script Writing
    const DEFAULT_SCRIPT_MASTER_PROMPT = `최종 확정: '딥-다이브' 대본 빌드업 4단계 프로세스 (Ver. 4.0)

[1단계] 대본 정밀 해부 및 흥행 잠재력 진단
임무: 대본을 문장 단위로 정밀 분석하고, '흥행 심리 지도(5070 타겟 제목 리스트)'와 '전문 드라마 기법'을 사용하여 잠재력과 개선점에 대한 '대본 정밀 해부 리포트'를 발행합니다.

실행 원칙:
- [종합 진단] 작품의 가장 매력적인 설정과 개선 필요 지점 명확하게 요약
- [톤앤매너 분석] 나레이션은 시청자에게 정중한 '존댓말' 원칙 (5070 시청자 정서적 유대감)
- [대사 현미경 분석] 감정 설명 대사를 '극적 아이러니(Dramatic Irony)'가 담긴 상황으로 개선
- [장면 구조 분석] 도입부는 '인 미디어스 레스(In medias res)' + '체호프의 총(Chekhov's Gun)' 기법 적용
- [인물 매력도 분석] 주인공에게 '복선(Foreshadowing)'을 통한 숨겨진 능력 암시

[2단계] '감독판 샘플' 제작 및 공동 창작 방향 확정
임무: 지정된 장면을 드라마 기법 + 흥행 코드 + 존댓말 나레이션에 따라 '원본 vs 감독 수정본' 형태로 제공

[3단계] 감독판 대본 전체 집필
임무: 합의된 개선 방향과 스타일을 대본 전체에 일관되게 적용하여 최종 [감독판 대본] 완성

[4단계] 최종 마케팅 에셋 시화
임무: 완성된 대본의 핵심 컨셉을 보여줄 썸네일 비주얼을 구체적으로 묘사`;

    // Reset Master Prompt to Default
    function resetMasterPrompt() {
        document.getElementById('promptScriptMaster').value = DEFAULT_SCRIPT_MASTER_PROMPT;
        Utils.showToast(i18n.toast_master_prompt_reset, 'success');
    }

    // App Mode Toggle
    function setAppMode(mode) {
        const currentMode = document.getElementById('appMode').value;

        // 현재 모드와 같은 모드를 선택한 경우 아무것도 하지 않음
        if (currentMode === mode) {
            return;
        }

        // 모드 변경 적용 (팝업 제거됨)

        // 모드 변경 적용
        document.getElementById('appMode').value = mode;

        const btnLong = document.getElementById('btnModeLong');
        const btnLongMusic = document.getElementById('btnModeLongMusic');
        const btnShort = document.getElementById('btnModeShort');
        const btnCommerce = document.getElementById('btnModeCommerce');

        const activeClass = "bg-[#1c2027] dark:bg-gray-600 shadow text-gray-800 dark:text-white font-bold";
        const inactiveClass = "text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 font-medium";

        if (mode === 'longform') {
            btnLong.className = `px-4 py-1.5 rounded-md text-xs transition-all ${activeClass}`;
            if (btnLongMusic) btnLongMusic.className = `px-4 py-1.5 rounded-md text-xs transition-all ${inactiveClass}`;
            btnShort.className = `px-4 py-1.5 rounded-md text-xs transition-all ${inactiveClass}`;
            btnCommerce.className = `px-4 py-1.5 rounded-md text-xs transition-all ${inactiveClass}`;
        } else if (mode === 'longform_music') {
            btnLong.className = `px-4 py-1.5 rounded-md text-xs transition-all ${inactiveClass}`;
            if (btnLongMusic) btnLongMusic.className = `px-4 py-1.5 rounded-md text-xs transition-all ${activeClass}`;
            btnShort.className = `px-4 py-1.5 rounded-md text-xs transition-all ${inactiveClass}`;
            btnCommerce.className = `px-4 py-1.5 rounded-md text-xs transition-all ${inactiveClass}`;
        } else if (mode === 'shorts') {
            btnShort.className = `px-4 py-1.5 rounded-md text-xs transition-all ${activeClass}`;
            btnLong.className = `px-4 py-1.5 rounded-md text-xs transition-all ${inactiveClass}`;
            if (btnLongMusic) btnLongMusic.className = `px-4 py-1.5 rounded-md text-xs transition-all ${inactiveClass}`;
            btnCommerce.className = `px-4 py-1.5 rounded-md text-xs transition-all ${inactiveClass}`;
        } else if (mode === 'commerce') {
            btnCommerce.className = `px-4 py-1.5 rounded-md text-xs transition-all ${activeClass}`;
            btnLong.className = `px-4 py-1.5 rounded-md text-xs transition-all ${inactiveClass}`;
            if (btnLongMusic) btnLongMusic.className = `px-4 py-1.5 rounded-md text-xs transition-all ${inactiveClass}`;
            btnShort.className = `px-4 py-1.5 rounded-md text-xs transition-all ${inactiveClass}`;
        }

        // 저장 버튼 강조 (사용자에게 저장 필요성 알림)
        const saveBtn = document.querySelector('button[onclick="saveAllSettings()"]');
        if (saveBtn) {
            saveBtn.classList.add('animate-pulse');
            setTimeout(() => {
                saveBtn.classList.remove('animate-pulse');
            }, 3000);
        }
    }

    // Populate Select Options
    function populateOptions() {
        const voiceSelect = document.getElementById('geminiVoice');
        const langSelect = document.getElementById('geminiLanguage');

        voiceSelect.innerHTML = GEMINI_VOICES.map(v => `<option value="${v}">${v}</option>`).join('');
        langSelect.innerHTML = GEMINI_LANGUAGES.map(l => `<option value="${l}">${l}</option>`).join('');
    }


    // API 키는 어드민 웹 대시보드에서 관리됩니다. 로컬 저장 비활성화.

    // [NEW] Template Image Functions
    async function uploadTemplate(input) {
        if (!input.files || !input.files[0]) return;
        const file = input.files[0];

        const formData = new FormData();
        formData.append('file', file);
        formData.append('type', 'template'); // flag

        Utils.showToast(i18n.toast_uploading_image, 'info');

        try {
            const res = await fetch('/api/upload/template', {
                method: 'POST',
                body: formData
            });
            const data = await res.json();

            if (res.ok) {
                Utils.showToast(i18n.toast_template_upload_done, 'success');
                // Update UI
                updateTemplatePreview(data.url);
            } else {
                Utils.showToast(i18n.toast_upload_fail + ': ' + (data.error || 'Unknown'), 'error');
            }
        } catch (e) {
            console.error(e);
            Utils.showToast(i18n.err_occurred, 'error');
        } finally {
            input.value = ''; // Reset input
        }
    }

    async function deleteTemplate() {
        if (!confirm(i18n.confirm_delete_template)) return;

        try {
            const res = await fetch('/api/settings/template', { method: 'DELETE' });
            if (res.ok) {
                Utils.showToast(i18n.toast_deleted, 'success');
                updateTemplatePreview(null);
            } else {
                Utils.showToast(i18n.err_delete_fail, 'error');
            }
        } catch (e) {
            console.error(e);
        }
    }

    function updateTemplatePreview(url) {
        const img = document.getElementById('templatePreview');
        const ph = document.getElementById('templatePlaceholder');
        const delBtn = document.getElementById('btnDeleteTemplate');

        if (url) {
            img.src = url;
            img.classList.remove('hidden');
            ph.classList.add('hidden');
            delBtn.classList.remove('hidden');
        } else {
            img.src = '';
            img.classList.add('hidden');
            ph.classList.remove('hidden');
            delBtn.classList.add('hidden');
        }
    }

    // API 연결 상태 확인
    // API 연결 상태 확인은 어드민 대시보드에서 관리됩니다.

    function exportData() {
        const data = {
            analysisData: Utils.storage.get('analysisData'),
            scriptStructure: Utils.storage.get('scriptStructure'),
            fullScript: Utils.storage.get('fullScript'),
            imagePrompts: Utils.storage.get('imagePrompts'),
            exportedAt: new Date().toISOString()
        };

        Utils.downloadFile(JSON.stringify(data, null, 2), 'picadillystudio_backup.json', 'application/json');
        Utils.showToast(i18n.toast_data_exported, 'success');
    }

    function clearData() {
        if (!confirm(i18n.confirm_delete_all_data)) return;

        Utils.storage.remove('analysisData');
        Utils.storage.remove('scriptStructure');
        Utils.storage.remove('fullScript');
        Utils.storage.remove('imagePrompts');
        Utils.storage.remove('ttsAudio');

        Utils.showToast(i18n.toast_all_data_deleted, 'success');
    }

    // 채널 로드
    async function loadChannels() {
        const list = document.getElementById('channelList');
        if (!list) return;
        try {
            const res = await fetch('/api/channels');
            if (!res.ok) throw new Error('채널 목록 로드 실패');
            const channels = await res.json();

            if (channels.length === 0) {
                list.innerHTML = `<p class="text-gray-500 text-sm text-center py-4 dark:text-gray-400">${i18n.msg_no_channels}</p>`;
                return;
            }

            // credentials_path가 있으면 인증된 것으로 간주
            list.innerHTML = channels.map(ch => {
                const isAuthenticated = !!ch.credentials_path;
                const statusBadge = isAuthenticated
                    ? `<span class="text-green-600 border border-green-200 bg-[#1c2027] px-2 py-0.5 rounded text-xs">${i18n.label_connected}</span>`
                    : `<span class="text-gray-500 border border-gray-200 bg-[#1c2027] px-2 py-0.5 rounded text-xs dark:text-gray-400 bg-[#1c2027] dark:border-gray-700">${i18n.label_disconnected}</span>`;

                const authBtn = isAuthenticated
                    ? `<button onclick="authenticateChannel(${ch.id}, '${ch.name}')" class="text-blue-500 hover:text-blue-700 text-xs border border-blue-200 px-2 py-1 rounded">${i18n.btn_ch_reconnect}</button>`
                    : `<button onclick="authenticateChannel(${ch.id}, '${ch.name}')" class="text-white bg-blue-500 hover:bg-blue-600 px-3 py-1 rounded text-xs shadow-sm">${i18n.btn_ch_login}</button>`;

                return `
                <div class="flex items-center justify-between p-3 bg-[#1c2027] border dark:border-gray-600 rounded-lg shadow-sm">
                    <div>
                        <div class="flex items-center gap-2 mb-1">
                            <span class="font-medium text-gray-800 dark:text-white">${ch.name}</span>
                            <span class="text-xs text-gray-500 font-normal dark:text-gray-400">${ch.handle}</span>
                            ${statusBadge}
                        </div>
                        ${ch.description ? `<p class="text-xs text-gray-500 dark:text-gray-400">${ch.description}</p>` : ''}
                    </div>
                    <div class="flex items-center gap-2">
                        ${authBtn}
                        <button onclick="deleteChannel(${ch.id})" class="text-red-500 hover:text-red-700 p-2" title="삭제">
                            🗑️
                        </button>
                    </div>
                </div>
            `}).join('');

        } catch (e) {
            console.error(e);
            list.innerHTML = `<p class="text-red-500 text-sm">${i18n.err_load_list}</p>`;
        }
    }

    // 채널 인증 (OAuth)
    async function authenticateChannel(id, name) {
        if (!confirm(i18n.confirm_yt_login.replace('{name}', name))) return;

        try {
            Utils.showToast(i18n.toast_auth_window_opening, 'info');

            const res = await fetch(`/api/channels/${id}/login`, { method: 'POST' });
            const data = await res.json();

            if (res.ok && data.status === 'ok') {
                Utils.showToast(data.message || '인증 완료!', 'success');
                // 목록 갱신을 위해 약간의 지연 (토큰 저장 완료 대기)
                setTimeout(loadChannels, 1000);
            } else {
                Utils.showToast(data.error || i18n.err_auth_failed, 'error');
            }
        } catch (e) {
            console.error(e);
            Utils.showToast(i18n.err_auth_failed, 'error');
        }
    }


    // 채널 추가
    async function addChannel() {

        const nameInput = document.getElementById('newChannelName');
        const handleInput = document.getElementById('newChannelHandle');
        const descInput = document.getElementById('newChannelDesc');

        const name = nameInput.value.trim();
        let handle = handleInput.value.trim();
        const description = descInput.value.trim();

        if (!name || !handle) {
            Utils.showToast(i18n.toast_enter_ch_name_handle, 'warning');
            return;
        }

        if (!handle.startsWith('@')) {
            handle = '@' + handle;
        }

        try {
            const res = await fetch('/api/channels', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, handle, description })
            });

            if (res.ok) {
                Utils.showToast(i18n.toast_ch_added, 'success');
                nameInput.value = '';
                handleInput.value = '';
                descInput.value = '';
                loadChannels(); // 목록 갱신
            } else {
                const err = await res.json();
                Utils.showToast(err.detail || i18n.err_add_fail, 'error');
            }
        } catch (e) {
            console.error(e);
            Utils.showToast(i18n.err_server_error, 'error');
        }
    }

    // 채널 삭제
    async function deleteChannel(id) {
        if (!confirm(i18n.confirm_delete_channel)) return;

        try {
            const res = await fetch(`/api/channels/${id}`, { method: 'DELETE' });
            if (res.ok) {
                Utils.showToast(i18n.toast_ch_deleted, 'success');
                loadChannels();
            } else {
                Utils.showToast(i18n.err_delete_fail, 'error');
            }
        } catch (e) {
            console.error(e);
            Utils.showToast(i18n.err_server_short, 'error');
        }
    }

    // [NEW] 이미지 스타일 프리셋 관리 (최종 통합 버전)

    async function loadStylePresets() {
        const list = document.getElementById('stylePresetList');
        if (!list) return;

        try {
            const res = await fetch('/api/settings/style-presets');
            const presets = await res.json();

            list.innerHTML = Object.entries(presets).map(([key, data]) => {
                const prompt = typeof data === 'string' ? data : (data.prompt_value || '');
                const imageUrl = typeof data === 'object' ? data.image_url : null;
                const geminiInstruction = typeof data === 'object' ? (data.gemini_instruction || '') : '';
                const mode = typeof data === 'object' ? (data.mode || 'image') : 'image';

                const displayName = (typeof data === 'object' && (window_lang == 'vi' ? (data.display_name_vi || data.display_name_ko) : data.display_name_ko)) || {
                    'realistic': i18n.sname_realistic, 'anime': i18n.sname_anime, 'cinematic': i18n.sname_cinematic,
                    'cartoon': i18n.sname_cartoon, 'oil_painting': i18n.sname_oil_painting, 'watercolor': i18n.sname_watercolor,
                    'sketch': i18n.sname_sketch, 'pixel_art': i18n.sname_pixel_art, '3d': i18n.sname_3d,
                    'k_webtoon': i18n.sname_k_webtoon, 'k_manhwa': i18n.sname_k_manhwa,
                    'ghibli': i18n.style_display_ghibli, 'minimal': i18n.style_display_minimal, 
                    'nursery_rhyme': i18n.style_display_nursery, '2d웹': i18n.style_display_2d_webtoon,
                    '블랙카툰': i18n.style_display_black_cartoon, '사물캐릭터': i18n.style_display_object_char,
                    '역사/동양철/다큐': i18n.style_display_philosophical, '후드티민머리': i18n.style_display_bald_hoodie
                }[key] || key;

                const isDefault = DEFAULT_STYLE_KEYS.includes(key);
                const hasInstruction = geminiInstruction.trim().length > 0;
                const modeBadge = mode === 'all' ? `<span class="inline-flex items-center gap-0.5 text-[9px] font-bold bg-blue-500 text-white px-1.5 py-0.5 rounded-full shadow-sm">🌐 ${i18n.label_all}</span>`
                    : '';

                return `
                    <div class="bg-[#1c2027]/15 p-4 rounded-xl border border-gray-100 dark:border-gray-700/50 relative group transition-all hover:shadow-md ${hasInstruction ? 'ring-1 ring-purple-100 dark:ring-purple-900/30' : ''}">
                        <div class="flex justify-between items-start mb-3">
                            <div class="flex items-center gap-3">
                                <div class="relative group/img cursor-pointer" onclick="document.getElementById('file_${key}').click()">
                                    ${imageUrl ?
                         `<img id="img_preview_${key}" src="${imageUrl}" class="w-12 h-12 rounded-lg border border-gray-200 object-cover bg-[#1c2027] dark:border-gray-700 shadow-sm" title="${i18n.label_img_change_click}">`
                         : `<span id="img_preview_${key}" class="w-12 h-12 rounded-lg bg-gray-200 bg-[#1c2027]/50 flex items-center justify-center text-[10px] text-gray-500 hover:bg-gray-300 transition-colors dark:text-gray-400">No Img</span>`
                     }
                                     <input type="file" id="file_${key}" class="hidden" accept="image/*" onchange="previewStyleImage(this, '${key}')">
                                 </div>
                                 <div class="space-y-0.5">
                                     <div class="flex items-center gap-1.5 flex-wrap">
                                         <label class="text-sm font-bold text-gray-800 dark:text-gray-100 block leading-tight">${displayName}</label>
                                         ${hasInstruction ? '<span class="inline-flex items-center gap-0.5 text-[9px] font-bold bg-purple-600 text-white px-1.5 py-0.5 rounded-full shadow-sm">🧠 Grounded</span>' : ''}
                                         ${modeBadge}
                                     </div>
                                     <div class="flex items-center gap-2">
                                         <span class="text-[10px] text-gray-400 font-mono bg-[#1c2027] px-1 rounded">${key}</span>
                                     </div>
                                 </div>
                            </div>
                            <div class="flex gap-1.5">
                                <button onclick="toggleEditStylePreset('${key}')" id="edit_btn_${key}" class="text-[10px] bg-[#1c2027] text-gray-600 dark:text-gray-300 border border-gray-200 dark:border-gray-600 px-2 py-1.5 rounded-lg hover:bg-[#1c2027] transition-colors">✏️ ${i18n.btn_edit}</button>
                                <button onclick="saveOneStylePreset('${key}')" id="save_btn_${key}" class="hidden text-[10px] bg-blue-600 text-white px-3 py-1.5 rounded-lg shadow-sm">💾 ${i18n.btn_save_short}</button>
                                <button onclick="deleteStylePreset('${key}')" class="text-[10px] bg-[#1c2027] text-red-500 border border-red-100 px-2 py-1.5 rounded-lg hover:bg-red-100 transition-colors">🗑️</button>
                            </div>
                        </div>
                        <div class="space-y-2">
                            <div>
                                <label class="text-[9px] font-bold text-gray-400 mb-1 block uppercase tracking-wider">Base Style Prompt</label>
                                <textarea id="preset_${key}" class="input-field w-full text-[11px] font-mono bg-[#1c2027] border-gray-100 dark:border-white/5" rows="2" readonly>${prompt}</textarea>
                            </div>
                            <div class="${hasInstruction ? '' : 'opacity-60'}">
                                <label class="text-[9px] font-bold text-purple-500 dark:text-purple-400 mb-1 block uppercase tracking-wider flex items-center gap-1">
                                    <span>🤖 Gemini Grounding Instruction</span>
                                    ${hasInstruction ? ' <i class="fas fa-check-circle text-[8px]"></i>' : ''}
                                </label>
                                <textarea id="ginst_${key}" class="input-field w-full text-[11px] font-mono ${hasInstruction ? 'bg-[#1c2027] dark:bg-[#1c2027] border-purple-100 dark:border-purple-900/30' : 'bg-[#1c2027]'} " rows="${hasInstruction ? 5 : 2}" readonly placeholder="${i18n.placeholder_no_instruction}">${geminiInstruction}</textarea>
                            </div>
                        </div>
                    </div>
                `;
            }).join('');
        } catch (e) {
            console.error(e);
            list.innerHTML = `<p class="text-red-500 text-xs">${i18n.err_load_styles}</p>`;
        }
    }

    function previewStyleImage(input, key) {
        if (input.files && input.files[0]) {
            const reader = new FileReader();
            reader.onload = function (e) {
                const preview = document.getElementById(`img_preview_${key}`);
                const parent = preview.parentElement;

                // Remove old preview (img or span)
                preview.remove();

                // Create new preview img
                const img = document.createElement('img');
                img.id = `img_preview_${key}`;
                img.src = e.target.result;
                img.className = "w-10 h-10 rounded border border-gray-300 object-cover bg-[#1c2027]";
                img.title = i18n.label_img_change_click;

                // Insert as first child of parent (.relative.group/img)
                parent.prepend(img);
            }
            reader.readAsDataURL(input.files[0]);
        }
    }

    function toggleEditStylePreset(key) {
        const textarea = document.getElementById(`preset_${key}`);
        const ginstArea = document.getElementById(`ginst_${key}`);
        const editBtn = document.getElementById(`edit_btn_${key}`);
        const saveBtn = document.getElementById(`save_btn_${key}`);

        if (textarea.hasAttribute('readonly')) {
            // Enable editing
            textarea.removeAttribute('readonly');
            textarea.classList.remove('bg-[#1c2027]', 'bg-[#1c2027]');
            textarea.classList.add('bg-[#1c2027]', 'bg-[#1c2027]', 'ring-2', 'ring-yellow-400');
            if (ginstArea) {
                ginstArea.removeAttribute('readonly');
                ginstArea.classList.remove('bg-[#1c2027]', 'bg-[#1c2027]');
                ginstArea.classList.add('bg-[#1c2027]', 'bg-[#1c2027]', 'ring-2', 'ring-purple-400');
                ginstArea.rows = Math.max(6, ginstArea.value.split('\n').length + 2);
            }
            textarea.focus();
            editBtn.classList.add('hidden');
            saveBtn.classList.remove('hidden');
        } else {
            // Disable editing (cancel)
            textarea.setAttribute('readonly', true);
            textarea.classList.add('bg-[#1c2027]', 'bg-[#1c2027]');
            textarea.classList.remove('bg-[#1c2027]', 'bg-[#1c2027]', 'ring-2', 'ring-yellow-400');
            if (ginstArea) {
                ginstArea.setAttribute('readonly', true);
                ginstArea.classList.add('bg-[#1c2027]', 'bg-[#1c2027]');
                ginstArea.classList.remove('bg-[#1c2027]', 'bg-[#1c2027]', 'ring-2', 'ring-purple-400');
            }
            editBtn.classList.remove('hidden');
            saveBtn.classList.add('hidden');
        }
    }

    async function saveOneStylePreset(key) {
        const val = document.getElementById(`preset_${key}`).value;
        const ginstEl = document.getElementById(`ginst_${key}`);
        const geminiInstruction = ginstEl ? ginstEl.value : null;
        const fileInput = document.getElementById(`file_${key}`);
        const file = fileInput && fileInput.files[0];

        try {
            let res;
            if (file) {
                // multipart: 이미지 업로드 + prompt_value 저장
                const formData = new FormData();
                formData.append('style_key', key);
                formData.append('prompt_value', val);
                formData.append('file', file);

                Utils.showToast(i18n.toast_img_uploading, 'info');
                res = await fetch('/api/settings/style-presets/custom', {
                    method: 'POST',
                    body: formData
                });
                // gemini_instruction도 저장 (업로드된 image_url 유지)
                if (res.ok && geminiInstruction !== null) {
                    const uploadResult = await res.json();
                    const savedImageUrl = uploadResult.image_url || null;
                    await fetch('/api/settings/style-presets', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ style_key: key, prompt_value: val, gemini_instruction: geminiInstruction, image_url: savedImageUrl })
                    });
                }
            } else {
                // 파일 없음: image_url=null 전달 → DB가 기존 image_url 유지
                res = await fetch('/api/settings/style-presets', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        style_key: key,
                        prompt_value: val,
                        gemini_instruction: geminiInstruction,
                        image_url: null
                    })
                });
            }

            if (res.ok) {
                if (file) fileInput.value = '';
                Utils.showToast(`[${key}] ${i18n.toast_style_saved}`, 'success');

                // Exit edit mode
                const textarea = document.getElementById(`preset_${key}`);
                const editBtn = document.getElementById(`edit_btn_${key}`);
                const saveBtn = document.getElementById(`save_btn_${key}`);
                const ginstArea = document.getElementById(`ginst_${key}`);

                textarea.setAttribute('readonly', true);
                textarea.classList.add('bg-[#1c2027]', 'bg-[#1c2027]');
                textarea.classList.remove('bg-[#1c2027]', 'bg-[#1c2027]', 'ring-2', 'ring-yellow-400');
                if (ginstArea) {
                    ginstArea.setAttribute('readonly', true);
                    ginstArea.classList.add('bg-[#1c2027]', 'bg-[#1c2027]');
                    ginstArea.classList.remove('bg-[#1c2027]', 'bg-[#1c2027]', 'ring-2', 'ring-purple-400');
                }
                editBtn.classList.remove('hidden');
                saveBtn.classList.add('hidden');
            }
        } catch (e) {
            console.error(e);
            Utils.showToast(i18n.err_occurred, 'error');
        }
    }

    // [NEW] Style Image Preview Handler
    function handleStyleImageSelect(input, type) {
        if (input.files && input.files[0]) {
            const reader = new FileReader();
            reader.onload = function (e) {
                const previewId = type === 'char' ? 'customStyleImgPreviewChar' : 'customStyleImgPreviewStyle';
                const placeholderId = type === 'char' ? 'customStyleImgPlaceholderChar' : 'customStyleImgPlaceholderStyle';
                
                const preview = document.getElementById(previewId);
                const placeholder = document.getElementById(placeholderId);
                
                preview.src = e.target.result;
                preview.classList.remove('hidden');
                placeholder.classList.add('hidden');
            };
            reader.readAsDataURL(input.files[0]);
        }
    }

    // [NEW] AI Style/Character Analysis (Dual Image)
    async function analyzeStyleImage() {
        const styleInput = document.getElementById('customStyleImageStyle');
        const charInput = document.getElementById('customStyleImageChar');
        const instructionInput = document.getElementById('customStyleInstruction');
        const analyzeBtn = document.getElementById('analyzeStyleBtn');

        const styleFile = styleInput.files[0];
        const charFile = charInput.files[0];

        if (!styleFile && !charFile) {
            Utils.showToast('분석할 이미지를 하나 이상 선택하세요.', 'warning');
            return;
        }

        analyzeBtn.disabled = true;
        const originalText = analyzeBtn.innerHTML;
        analyzeBtn.innerHTML = '<span>⏳</span> 통합 분석 중...';
        Utils.showToast('AI가 화풍과 캐릭터를 정밀 분석하고 있습니다...', 'info');

        try {
            const formData = new FormData();
            if (styleFile) formData.append('style_file', styleFile);
            if (charFile) formData.append('char_file', charFile);

            const res = await fetch('/api/settings/style-presets/analyze', {
                method: 'POST',
                body: formData
            });

            if (res.ok) {
                const data = await res.json();
                instructionInput.value = data.description;
                Utils.showToast('화풍과 캐릭터가 결합된 지침이 생성되었습니다.', 'success');
            } else {
                const err = await res.json();
                Utils.showToast(err.detail || '분석 실패', 'error');
            }
        } catch (e) {
            console.error(e);
            Utils.showToast('서버 오류가 발생했습니다.', 'error');
        } finally {
            analyzeBtn.disabled = false;
            analyzeBtn.innerHTML = originalText;
        }
    }

    // [NEW] Add Custom Style
    async function addCustomStylePreset() {
        const nameInput = document.getElementById('customStyleName');
        const promptInput = document.getElementById('customStylePrompt');
        const instructionInput = document.getElementById('customStyleInstruction');
        const styleFileInput = document.getElementById('customStyleImageStyle');
        const charFileInput = document.getElementById('customStyleImageChar');
        const modeSelect = document.getElementById('customStyleMode');

        const name = nameInput.value.trim();
        const prompt = promptInput.value.trim();
        const instruction = instructionInput.value.trim();
        const styleFile = styleFileInput.files[0];
        const charFile = charFileInput.files[0];
        const mode = modeSelect ? modeSelect.value : 'image';

        if (!name || !prompt) {
            Utils.showToast(i18n.toast_enter_name_prompt, 'warning');
            return;
        }

        Utils.showToast(i18n.toast_syncing_style, 'info');

        try {
            let imageUrl = null;
            // 썸네일로 사용할 이미지를 결정 (화풍 이미지를 우선순위로 사용하거나 둘 중 있는 것 사용)
            const uploadFile = styleFile || charFile;

            if (uploadFile) {
                // 1. Image Upload (Thumbnail)
                const formData = new FormData();
                formData.append('style_key', name);
                formData.append('prompt_value', prompt);
                formData.append('file', uploadFile);
                
                const uploadRes = await fetch('/api/settings/style-presets/custom', {
                    method: 'POST',
                    body: formData
                });
                const uploadData = await uploadRes.json();
                imageUrl = uploadData.image_url;
            }

            // 2. Save JSON fields
            const saveRes = await fetch('/api/settings/style-presets', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    style_key: name,
                    prompt_value: prompt,
                    gemini_instruction: instruction,
                    image_url: imageUrl,
                    mode: mode
                })
            });

            if (saveRes.ok) {
                Utils.showToast(i18n.toast_new_style_added, 'success');
                // Clear inputs
                nameInput.value = '';
                promptInput.value = '';
                instructionInput.value = '';
                styleFileInput.value = '';
                charFileInput.value = '';
                
                document.getElementById('customStyleImgPreviewStyle').src = '';
                document.getElementById('customStyleImgPreviewStyle').classList.add('hidden');
                document.getElementById('customStyleImgPlaceholderStyle').classList.remove('hidden');
                
                document.getElementById('customStyleImgPreviewChar').src = '';
                document.getElementById('customStyleImgPreviewChar').classList.add('hidden');
                document.getElementById('customStyleImgPlaceholderChar').classList.remove('hidden');

                // Reload list
                loadStylePresets();
            } else {
                const err = await saveRes.json();
                Utils.showToast(err.detail || i18n.err_add_fail, 'error');
            }
        } catch (e) {
            console.error(e);
            Utils.showToast(i18n.err_server_error, 'error');
        }
    }

    // [NEW] Delete Style
    async function deleteStylePreset(key) {
        if (!confirm(i18n.confirm_delete_style)) return;

        try {
            const res = await fetch(`/api/settings/style-presets/${key}`, { method: 'DELETE' });
            if (res.ok) {
                Utils.showToast(i18n.toast_deleted, 'success');
                loadStylePresets();
            } else {
                Utils.showToast(i18n.err_delete_fail, 'error');
            }
        } catch (e) {
            console.error(e);
            Utils.showToast(i18n.err_server_short, 'error');
        }
    }

    // [NEW] 대본 스타일 프리셋 관리
    async function loadScriptStylePresets() {
        const list = document.getElementById('scriptStylePresetList');
        try {
            const res = await fetch('/api/settings/script-style-presets?detailed=true');
            const presets = await res.json();

            list.innerHTML = Object.entries(presets).map(([key, data]) => {
                const val = typeof data === 'string' ? data : (data.prompt_value || '');
                const displayName = (typeof data === 'object' && (window_lang == 'vi' ? (data.display_name_vi || data.display_name_ko) : data.display_name_ko)) || {
                    'default': i18n.ss_default,
                    'news': i18n.ss_news,
                    'story': i18n.ss_story,
                    'senior_story': i18n.ss_senior_story,
                    'bgm': i18n.ss_bgm,
                    'classic_50s': i18n.ss_classic_50s,
                    'joseon_sageuk': i18n.ss_joseon_sageuk,
                    'north_korean_drama': i18n.ss_north_korean_drama,
                    'silent_20s': i18n.ss_silent_20s,
                    'camcorder_90s': i18n.ss_camcorder_90s,
                    'modern_drama': i18n.ss_modern_drama,
                    'mystery_thriller': i18n.ss_mystery_thriller,
                    'horror_suspense': i18n.ss_horror_suspense,
                    'melodrama': i18n.ss_melodrama,
                    'crime_drama': i18n.ss_crime_drama,
                    'cyberpunk_neon': i18n.ss_cyberpunk_neon,
                    'watercolor_analog': i18n.ss_watercolor_analog,
                    'digital_webtoon': i18n.ss_digital_webtoon,
                    'graphite_sketch': i18n.ss_graphite_sketch,
                    'joseon_2d_anime': i18n.ss_joseon_2d_anime,
                    'oriental_ink': i18n.ss_oriental_ink,
                    'neonsign_citypop': i18n.ss_neonsign_citypop,
                    'buddhist_minimal': i18n.ss_buddhist_minimal,
                    'renaissance_sacred': i18n.ss_renaissance_sacred,
                    'cute_animal_char': i18n.ss_cute_animal_char,
                    'k_webtoon': i18n.ss_k_webtoon,
                    'k_manhwa': i18n.ss_k_manhwa,
                    'script_master': i18n.ss_script_master
                }[key] || key;

                const rows = val.length > 200 ? 8 : val.length > 100 ? 5 : 3;

                return `
                            <div class="bg-[#1c2027]/50 p-3 rounded-md border border-gray-100 dark:border-gray-700">
                                <div class="flex justify-between items-center mb-2">
                                    <label class="text-sm font-bold text-gray-700 dark:text-gray-200">${displayName}</label>
                                    <div class="flex gap-1">
                                        <button onclick="toggleEditScriptStylePreset('${key}')" id="script_edit_btn_${key}" class="text-[10px] bg-yellow-500 text-white px-2 py-1 rounded hover:bg-yellow-600 transition-colors">✏️ ${i18n.btn_edit}</button>
                                        <button onclick="saveOneScriptStylePreset('${key}')" id="script_save_btn_${key}" class="hidden text-[10px] bg-blue-500 text-white px-2 py-1 rounded hover:bg-blue-600 transition-colors">💾 ${i18n.btn_save_short}</button>
                                    </div>
                                </div>
                                <textarea id="script_preset_${key}" class="input-field w-full text-[11px] font-mono leading-tight bg-[#1c2027]" rows="${rows}" readonly>${val}</textarea>
                            </div>
                        `;
            }).join('');
        } catch (e) {
            console.error(e);
            list.innerHTML = `<p class="text-red-500 text-xs">${i18n.err_load_script_styles}</p>`;
        }
    }

    function toggleEditScriptStylePreset(key) {
        const textarea = document.getElementById(`script_preset_${key}`);
        const editBtn = document.getElementById(`script_edit_btn_${key}`);
        const saveBtn = document.getElementById(`script_save_btn_${key}`);

        if (textarea.hasAttribute('readonly')) {
            // Enable editing
            textarea.removeAttribute('readonly');
            textarea.classList.remove('bg-[#1c2027]', 'bg-[#1c2027]');
            textarea.classList.add('bg-[#1c2027]', 'bg-[#1c2027]', 'ring-2', 'ring-yellow-400');
            textarea.focus();

            // Toggle buttons
            editBtn.classList.add('hidden');
            saveBtn.classList.remove('hidden');
        } else {
            // Disable editing (cancel)
            textarea.setAttribute('readonly', true);
            textarea.classList.add('bg-[#1c2027]', 'bg-[#1c2027]');
            textarea.classList.remove('bg-[#1c2027]', 'bg-[#1c2027]', 'ring-2', 'ring-yellow-400');

            // Toggle buttons
            editBtn.classList.remove('hidden');
            saveBtn.classList.add('hidden');
        }
    }

    async function saveOneScriptStylePreset(key) {
        const val = document.getElementById(`script_preset_${key}`).value;
        try {
            const res = await fetch('/api/settings/script-style-presets', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ style_key: key, prompt_value: val })
            });

            if (res.ok) {
                Utils.showToast(`[${key}] ${i18n.toast_script_style_saved}`, 'success');

                // Exit edit mode
                const textarea = document.getElementById(`script_preset_${key}`);
                const editBtn = document.getElementById(`script_edit_btn_${key}`);
                const saveBtn = document.getElementById(`script_save_btn_${key}`);

                textarea.setAttribute('readonly', true);
                textarea.classList.add('bg-[#1c2027]', 'bg-[#1c2027]');
                textarea.classList.remove('bg-[#1c2027]', 'bg-[#1c2027]', 'ring-2', 'ring-yellow-400');
                editBtn.classList.remove('hidden');
                saveBtn.classList.add('hidden');
            } else {
                Utils.showToast(i18n.err_save_fail, 'error');
            }
        } catch (e) {
            console.error(e);
            Utils.showToast(i18n.err_occurred, 'error');
        }
    }

    // [NEW] 썸네일 스타일 프리셋 관리
    const DEFAULT_THUMB_KEYS = ['face', 'text', 'contrast', 'mystery', 'minimal', 'dramatic', 'japanese_viral', 'ghibli', 'k_manhwa'];

    async function loadThumbnailStylePresets() {
        const list = document.getElementById('thumbnailStylePresetList');
        try {
            const res = await fetch('/api/settings/thumbnail-style-presets');
            const presets = await res.json();

            list.innerHTML = Object.entries(presets).map(([key, data]) => {
                // Compatibility
                const prompt = typeof data === 'string' ? data : (data.prompt_value || '');
                const imageUrl = typeof data === 'object' ? data.image_url : null;

                const displayName = (typeof data === 'object' && (window_lang == 'vi' ? (data.display_name_vi || data.display_name_ko) : data.display_name_ko)) || {
                    'face': i18n.ts_face,
                    'text': i18n.ts_text,
                    'contrast': i18n.ts_contrast,
                    'mystery': i18n.ts_mystery,
                    'minimal': i18n.ts_minimal,
                    'dramatic': i18n.ts_dramatic,
                    'japanese_viral': i18n.ts_japanese_viral,
                    'ghibli': i18n.ts_ghibli,
                    'k_manhwa': i18n.ts_k_manhwa
                }[key] || key;

                const isDefault = DEFAULT_THUMB_KEYS.includes(key);
                // Fallback image url if none provided, old way (optional, but new way handles null)
                // If imageUrl is null, we show placeholder. 
                // Previously we had `/static/thumbnail_samples/${key}.png`. We can keep checking that if we want legacy support, 
                // but for now let's rely on data.image_url. If user wants legacy images they need to migrate or we rely on 'No Img'

                return `
                    <div class="bg-[#1c2027]/50 p-3 rounded-md border border-gray-100 dark:border-gray-700 relative group">
                        <div class="flex justify-between items-start mb-2">
                             <div class="flex items-center gap-2">
                                <div class="relative group/img cursor-pointer" onclick="document.getElementById('thumb_file_${key}').click()">
                                    ${imageUrl ?
                        `<img id="thumb_img_preview_${key}" src="${imageUrl}" class="w-10 h-10 rounded border border-gray-300 object-cover bg-[#1c2027] dark:border-gray-700" title="${i18n.label_img_change_click}">`
                        : `<span id="thumb_img_preview_${key}" class="w-10 h-10 rounded bg-gray-200 bg-[#1c2027]/50 flex items-center justify-center text-[10px] text-gray-500 hover:bg-gray-300 transition-colors dark:text-gray-400" title="${i18n.label_img_upload_click}">No Img</span>`
                    }
                                    <div class="absolute inset-0 bg-[#1c2027]/30 rounded flex items-center justify-center opacity-0 group-hover/img:opacity-100 transition-opacity">
                                        <span class="text-white text-[10px]">📷</span>
                                    </div>
                                    <input type="file" id="thumb_file_${key}" class="hidden" accept="image/*" onchange="previewThumbnailStyleImage(this, '${key}')">
                                </div>
                                <div>
                                    <label class="text-sm font-bold text-gray-700 dark:text-gray-200 block leading-none mb-1">${displayName}</label>
                                    <span class="text-[10px] text-gray-400 font-mono">${key}</span>
                                </div>
                            </div>

                            <div class="flex gap-1">
                                <button onclick="toggleEditThumbnailStylePreset('${key}')" id="thumb_edit_btn_${key}" class="text-[10px] bg-yellow-500 text-white px-2 py-1 rounded hover:bg-yellow-600 transition-colors">✏️ ${i18n.btn_edit}</button>
                                <button onclick="saveOneThumbnailStylePreset('${key}')" id="thumb_save_btn_${key}" class="hidden text-[10px] bg-blue-500 text-white px-2 py-1 rounded hover:bg-blue-600 transition-colors">💾 ${i18n.btn_save_short}</button>
                                ${!isDefault ?
                        `<button onclick="deleteThumbnailStylePreset('${key}')" class="text-[10px] bg-[#1c2027] text-red-500 border border-red-200 px-2 py-1 rounded hover:bg-red-100 transition-colors" title="삭제">🗑️</button>`
                        : ''
                    }
                            </div>
                        </div>
                        <textarea id="thumbnail_preset_${key}" class="input-field w-full text-[11px] font-mono leading-tight mt-1 bg-[#1c2027]" rows="3" readonly>${prompt}</textarea>
                    </div>
                `;
            }).join('');
        } catch (e) {
            console.error(e);
            list.innerHTML = `<p class="text-red-500 text-xs">${i18n.err_load_thumb_styles}</p>`;
        }
    }

    function previewThumbnailStyleImage(input, key) {
        if (input.files && input.files[0]) {
            const reader = new FileReader();
            reader.onload = function (e) {
                const preview = document.getElementById(`thumb_img_preview_${key}`);
                const parent = preview.parentElement;
                preview.remove();

                const img = document.createElement('img');
                img.id = `thumb_img_preview_${key}`;
                img.src = e.target.result;
                img.className = "w-10 h-10 rounded border border-gray-300 object-cover bg-[#1c2027]";
                img.title = i18n.label_img_change_click;

                parent.prepend(img);
            }
            reader.readAsDataURL(input.files[0]);
        }
    }

    function toggleEditThumbnailStylePreset(key) {
        const textarea = document.getElementById(`thumbnail_preset_${key}`);
        const editBtn = document.getElementById(`thumb_edit_btn_${key}`);
        const saveBtn = document.getElementById(`thumb_save_btn_${key}`);

        if (textarea.hasAttribute('readonly')) {
            // Enable editing
            textarea.removeAttribute('readonly');
            textarea.classList.remove('bg-[#1c2027]', 'bg-[#1c2027]');
            textarea.classList.add('bg-[#1c2027]', 'bg-[#1c2027]', 'ring-2', 'ring-yellow-400');
            textarea.focus();

            // Toggle buttons
            editBtn.classList.add('hidden');
            saveBtn.classList.remove('hidden');
        } else {
            // Disable editing (cancel)
            textarea.setAttribute('readonly', true);
            textarea.classList.add('bg-[#1c2027]', 'bg-[#1c2027]');
            textarea.classList.remove('bg-[#1c2027]', 'bg-[#1c2027]', 'ring-2', 'ring-yellow-400');

            // Toggle buttons
            editBtn.classList.remove('hidden');
            saveBtn.classList.add('hidden');
        }
    }

    async function saveOneThumbnailStylePreset(key) {
        const val = document.getElementById(`thumbnail_preset_${key}`).value;
        const fileInput = document.getElementById(`thumb_file_${key}`);
        const file = fileInput && fileInput.files[0];

        try {
            let res;
            if (file) {
                const formData = new FormData();
                formData.append('style_key', key);
                formData.append('prompt_value', val);
                formData.append('file', file);

                Utils.showToast(i18n.toast_thumb_style_img_uploading, 'info');
                res = await fetch('/api/settings/thumbnail-style-presets/custom', {
                    method: 'POST',
                    body: formData
                });
            } else {
                res = await fetch('/api/settings/thumbnail-style-presets', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        style_key: key,
                        prompt_value: val,
                        image_url: null
                    })
                });
            }

            if (res.ok) {
                if (file) fileInput.value = '';
                Utils.showToast(`[${key}] ${i18n.toast_thumb_style_saved}`, 'success');

                // Exit edit mode
                const textarea = document.getElementById(`thumbnail_preset_${key}`);
                const editBtn = document.getElementById(`thumb_edit_btn_${key}`);
                const saveBtn = document.getElementById(`thumb_save_btn_${key}`);

                textarea.setAttribute('readonly', true);
                textarea.classList.add('bg-[#1c2027]', 'bg-[#1c2027]');
                textarea.classList.remove('bg-[#1c2027]', 'bg-[#1c2027]', 'ring-2', 'ring-yellow-400');
                editBtn.classList.remove('hidden');
                saveBtn.classList.add('hidden');
            } else {
                Utils.showToast(i18n.err_save_fail, 'error');
            }
        } catch (e) {
            console.error(e);
            Utils.showToast(i18n.err_occurred, 'error');
        }
    }

    async function addCustomThumbnailStylePreset() {
        const nameInput = document.getElementById('customThumbStyleName');
        const promptInput = document.getElementById('customThumbStylePrompt');
        const fileInput = document.getElementById('customThumbStyleImage');
        const name = nameInput.value.trim();
        const prompt = promptInput.value.trim();
        const file = fileInput.files[0];

        if (!name || !prompt) {
            Utils.showToast(i18n.toast_enter_name_prompt, 'warning');
            return;
        }

        const formData = new FormData();
        formData.append('style_key', name);
        formData.append('prompt_value', prompt);
        if (file) {
            formData.append('file', file);
        } else {
            // Even if no file, the API expects 'file' field for UploadFile. 
            // We might need to split API or make file optional in `add_custom...`.
            // The python endpoint: `file: UploadFile = File(...)` implies required.
            // But we allow string-only create? 
            // Wait, previous implementation of `custom` endpoint requires file.
            // If user doesn't upload file, we should warn or support it. "Thumbnail must have image" is not strict rule but good for UI.
            // Let's require file for now for Custom, or fallback to regular POST if no file.
        }

        try {
            let res;
            if (file) {
                res = await fetch('/api/settings/thumbnail-style-presets/custom', {
                    method: 'POST',
                    body: formData
                });
            } else {
                // Use normal endpoint creates entry with null image
                res = await fetch('/api/settings/thumbnail-style-presets', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ style_key: name, prompt_value: prompt })
                });
            }

            if (res.ok) {
                Utils.showToast(i18n.toast_new_thumb_style_added, 'success');
                nameInput.value = '';
                promptInput.value = '';
                fileInput.value = '';
                document.getElementById('customThumbStyleImgName').textContent = '';
                loadThumbnailStylePresets();
            } else {
                const err = await res.json();
                Utils.showToast(err.detail || i18n.err_add_fail, 'error');
            }
        } catch (e) {
            console.error(e);
            Utils.showToast(i18n.err_server_error, 'error');
        }
    }

    async function deleteThumbnailStylePreset(key) {
        if (!confirm(i18n.confirm_delete_style)) return;

        try {
            const res = await fetch(`/api/settings/thumbnail-style-presets/${key}`, { method: 'DELETE' });
            if (res.ok) {
                Utils.showToast(i18n.toast_deleted, 'success');
                loadThumbnailStylePresets();
            } else {
                Utils.showToast(i18n.err_delete_fail, 'error');
            }
        } catch (e) {
            Utils.showToast(i18n.err_server_short, 'error');
        }
    }

    // [NEW] Webtoon Plan Prompt Management
    const DEFAULT_WEBTOON_PLAN_PROMPT = `
    # ROLE: Hollywood Trailer Editor & VFX Supervisor
    You are creating a high-end cinematic video production plan for a webtoon.
    Follow the [USER CINEMATIC MASTER GUIDE] strictly when generating specifications for each scene.

    [INPUT DATA (JSON SCENES)]
    [[SCENES_JSON]]

    [USER CINEMATIC MASTER GUIDE (STRICT ADHERENCE - MUST BE DYNAMIC!)]
    0. Base Master Setting (Common for ALL cuts):
       "Vertical cinematic animation, 9:16 aspect ratio, 1080x1920, DRAMATIC CAMERA MOVEMENT, smooth physics, high quality anime webtoon style. NEVER BE STATIC."

    1. Production Types (scene_type):
       - TYPE 1 (Vertical Long): "Show Space" -> Fast or slow upward/downward camera pan (pan_down, pan_up), strong parallax.
       - TYPE 2 (Horizontal Wide): "Panoramic Vista" -> ALWAYS use continuous side-panning (pan_left or pan_right) across the wide image to reveal details.
       - TYPE 3 (Small/Empty): "Fill Space" -> Zoom in continuously or push in to character.
       - TYPE 4 (Transition): "Consistency" -> Fade with particles.
       - TYPE 5 (PSD Depth): "3D Illusion" -> 3D camera move, foreground parallax.
       - TYPE 6 (Unified Tone): High contrast, dramatic animated motion.

    [CORE INSTRUCTIONS]
    1. **overall_strategy**: Summarize the production direction in Korean.
    2. **bgm_style**: Recommend BGM style in Korean.
    3. **scene_specifications**: For each scene, generate:
       - **scene_number**: The number from input.
       - **engine**: "veo" (PRIMARY - High-quality AI video), or "image" (2D still). ALWAYS use "veo" as default.
       - **effect**: MUST NOT BE 'static'! ALWAYS pick "pan_left", "pan_right", "pan_up", "pan_down", "zoom_in", or "zoom_out". 
         * If image is wide (Type 2 or character face), strongly prefer "pan_left" or "pan_right" to explore the scene.
       - **motion**: FULL CINEMATIC PROMPT in English. 
         * MUST include explicit camera movement instructions (e.g., "Camera pans continuously from left to right", "Camera zooms in smoothly").
         * MUST include character micro-expressions (e.g., "Lips are quivering slightly", "Eyes blinking", "Hair blowing aggressively in wind").
       - **rationale**: (Korean) Why this dynamic motion is crucial.
       - **cropping_advice**: (Korean) Focus on Zoom-to-Fill 9:16 aspect ratio so there are no black letterboxes.

    [OUTPUT FORMAT (JSON ONLY)]
    {
        "overall_strategy": "Overall direction (Korean)",
        "bgm_style": "BGM (Korean)",
        "scene_specifications": [
            {
                "scene_number": 1,
                "engine": "veo | image",
                "effect": "zoom_in | pan_down | pan_left | pan_right | pan_up | zoom_out",
                "motion": "Detailed cinematic prompt in English focusing heavily on CAMERA PANNING and CHARACTER MOTION (e.g., lip quivering).",
                "rationale": "Reason (Korean)",
                "cropping_advice": "Advice on filling 9:16 screen tight (Korean)"
            }
        ]
    }
    
    **IMPORTANT**: For NARRATOR (내레이션), always use the voice 'Brian'. 
    Videos MUST NOT BE STATIC. Provide clear, strong camera movement keywords in the 'motion' string.
`.trim();

    // [NEW] Default Webtoon Optimization Prompts
    const DEFAULT_WEBTOON_VERTICAL_PROMPT = "Preserve full original composition, fit into 9:16 vertical canvas, no distortion, extend background naturally if needed, maintain original webtoon art style, high resolution, clean edges, no motion, no animation, static illustration";
    const DEFAULT_WEBTOON_HORIZONTAL_PROMPT = "Convert horizontal image to vertical 9:16 format. If too small, extend background boundaries with matching colors or blurred original image to fill the 9:16 screen. Focus on the central character, maintain original webtoon art style, high resolution, soft rim lighting, no extreme motion.";

    // [NEW] Default Webtoon Motion Prompts
    const DEFAULT_WEBTOON_MOTION_PAN = "TRUE VERTICAL SCROLL: Smooth and slow cinematic vertical camera scan (from high angle down to low angle or vice-versa) covering the full length of the extremely tall image. Feel like scrolling a webtoon. Maintain original aspect width, subtle parallax depth effect separating foreground and background, no distortion, consistent webtoon style. Lens flare or atmospheric particles like dust/embers falling.";
    const DEFAULT_WEBTOON_MOTION_ZOOM = "SMART KEN BURNS FOCAL POINT ZOOM: Progressive smooth cinematic Ken Burns style push-in or pan-and-zoom focusing organically from character eyes/tears to background. Full screen coverage with no black borders. Subtle breathing motion, soft cinematic depth of field, delicate emotional atmosphere, extremely slow and stable.";
    const DEFAULT_WEBTOON_MOTION_ACTION = "DYNAMIC ACTION & VFX: High-impact cinematic motion covering full screen width. Strong 3D parallax depth separation (fast characters, slow background). Glow effects on magic circles/weapons, dust particles and dynamic embers floating, light flickers, intense dramatic lighting. Include intense screen shake effect. Fast-paced intensity, perfect for deciding battles or dynamic webtoon cuts.";

    async function loadWebtoonSettings() {
        try {
            const res = await fetch('/api/settings');
            const data = await res.json();

            // setCheckbox('ws_auto_split', data.webtoon_auto_split ?? true);
            // setCheckbox('ws_smart_pan', data.webtoon_smart_pan ?? true);
            // setCheckbox('ws_convert_zoom', data.webtoon_convert_zoom ?? true);

            // Plan Prompt
            const promptEl = document.getElementById('ws_plan_prompt');
            if (promptEl) {
                promptEl.value = data.webtoon_plan_prompt || DEFAULT_WEBTOON_PLAN_PROMPT;
            }

            // [NEW] Opt Prompts
            const vertEl = document.getElementById('ws_vertical_prompt');
            const horizEl = document.getElementById('ws_horizontal_prompt');
            if (vertEl) vertEl.value = data.webtoon_vertical_prompt || DEFAULT_WEBTOON_VERTICAL_PROMPT;
            if (horizEl) horizEl.value = data.webtoon_horizontal_prompt || DEFAULT_WEBTOON_HORIZONTAL_PROMPT;

            // [NEW] Motion Prompts
            const panEl = document.getElementById('ws_motion_pan');
            const zoomEl = document.getElementById('ws_motion_zoom');
            const actionEl = document.getElementById('ws_motion_action');
            if (panEl) panEl.value = data.webtoon_motion_pan || DEFAULT_WEBTOON_MOTION_PAN;
            if (zoomEl) zoomEl.value = data.webtoon_motion_zoom || DEFAULT_WEBTOON_MOTION_ZOOM;
            if (actionEl) actionEl.value = data.webtoon_motion_action || DEFAULT_WEBTOON_MOTION_ACTION;

            // [NEW] Video Engine
            const engine = data.video_engine || "veo";
            const radio = document.querySelector(`input[name="ws_video_engine"][value="${engine}"]`);
            if (radio) { radio.checked = true; onVideoEngineChange(); }

            // Veo version
            const veoVer = data.veo_model_version || "veo-2.0-generate-001";
            const veoRadio = document.querySelector(`input[name="veo_model_version"][value="${veoVer}"]`);
            if (veoRadio) veoRadio.checked = true;

        } catch (e) {
            console.error('웹툰 설정 로드 실패:', e);
        }
    }

    function resetWebtoonPrompt() {
        if (confirm(i18n.confirm_reset_plan_prompt)) {
            document.getElementById('ws_plan_prompt').value = DEFAULT_WEBTOON_PLAN_PROMPT;
        }
    }

    function resetWebtoonOptPrompts() {
        if (confirm(i18n.confirm_reset_image_prompt)) {
            document.getElementById('ws_vertical_prompt').value = DEFAULT_WEBTOON_VERTICAL_PROMPT;
            document.getElementById('ws_horizontal_prompt').value = DEFAULT_WEBTOON_HORIZONTAL_PROMPT;
        }
    }

    function resetWebtoonMotionPrompts() {
        if (confirm(i18n.confirm_reset_motion_prompt)) {
            document.getElementById('ws_motion_pan').value = DEFAULT_WEBTOON_MOTION_PAN;
            document.getElementById('ws_motion_zoom').value = DEFAULT_WEBTOON_MOTION_ZOOM;
            document.getElementById('ws_motion_action').value = DEFAULT_WEBTOON_MOTION_ACTION;
        }
    }

    function setCheckbox(id, val) {
        const el = document.getElementById(id);
        if (el) el.checked = !!val;
    }

    // Video Engine 변경 시 Veo 패널 토글
    function onVideoEngineChange() {
        const engine = document.querySelector('input[name="ws_video_engine"]:checked')?.value;
        const panel = document.getElementById('veo-version-panel');
        if (panel) panel.classList.toggle('hidden', engine !== 'veo');
    }

    function toggleRemoteUrl() {
        const select = document.getElementById('renderTarget');
        if (!select) return;
        const target = select.value;
        const container = document.getElementById('remoteUrlContainer');
        if (container) {
            if (target === 'remote') {
                container.classList.remove('hidden');
            } else {
                container.classList.add('hidden');
            }
        }
    }

    // [MODIFIED] saveAllSettings to include Webtoon Prompt


    // [NEW] setAppMode to handle 'webtoon'
    function setAppMode(mode) {
        document.getElementById('appMode').value = mode;
        
        const updateBtn = (btnId, active) => {
            const btn = document.getElementById(btnId);
            if (!btn) return;
            if (active) {
                btn.className = "px-4 py-1.5 rounded-md text-xs font-bold transition-all bg-[#1c2027] dark:bg-gray-600 shadow text-gray-800 dark:text-white";
            } else {
                btn.className = "px-4 py-1.5 rounded-md text-xs font-medium text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200";
            }
        };

        updateBtn('btnModeLong', mode === 'longform');
        updateBtn('btnModeLongMusic', mode === 'longform_music');
        updateBtn('btnModeShort', mode === 'shorts');
        updateBtn('btnModeWebtoon', mode === 'webtoon');
        updateBtn('btnModeCommerce', mode === 'commerce');
        updateBtn('btnModeBlog', mode === 'blog');
    }

    // [NEW] ElevenLabs Voice List
    async function refreshElevenVoices() {
        const listEl = document.getElementById('elevenVoiceList');
        if (!listEl) return;

        listEl.innerHTML = `<p class="text-[9px] text-gray-400 text-center py-2 animate-pulse">${i18n.msg_eleven_loading}</p>`;

        try {
            // API call to fetch voices
            const res = await fetch('/api/tts/voices');
            if (!res.ok) throw new Error("API call failed");

            const data = await res.json();

            if (!data || data.length === 0) {
                listEl.innerHTML = `<p class="text-[9px] text-gray-400 text-center py-2">${i18n.msg_no_voices}</p>`;
                return;
            }

            listEl.innerHTML = data.map(v => {
                const gender = v.labels && v.labels.gender ? v.labels.gender : 'Unknown';
                const genderBadge = gender === 'male' ? 'bg-blue-100 text-blue-600' :
                    gender === 'female' ? 'bg-pink-100 text-pink-600' :
                        'bg-[#1c2027] text-gray-600';

                return `
                    <div class="flex justify-between items-center p-1.5 hover:bg-[#1c2027] dark:hover:bg-[#1c2027] rounded border-b border-gray-50 dark:border-white/5 last:border-0 transition-colors group bg-[#1c2027]">
                        <div class="flex flex-col overflow-hidden">
                            <span class="text-[10px] font-bold text-gray-700 dark:text-gray-300 truncate pr-2 group-hover:text-blue-600 transition-colors" title="${v.name}">${v.name}</span>
                            <span class="text-[8px] text-gray-400 font-mono truncate" title="Voice ID: ${v.voice_id}">${v.voice_id}</span>
                        </div>
                        <div class="flex flex-col items-end flex-shrink-0">
                            <span class="text-[8px] ${genderBadge} px-1.5 rounded-full capitalize font-medium">${gender}</span>
                            <span class="text-[8px] text-gray-400">${v.category || ''}</span>
                        </div>
                    </div>
                `;
            }).join('');

        } catch (e) {
            console.error(e);
            listEl.innerHTML = `<p class="text-[9px] text-red-500 text-center py-2">${i18n.err_voice_load_fail}</p>`;
        }
    }

    function toggleVoiceList(btn) {
        const container = document.getElementById('elevenVoicesContainer');
        if (!container) return;

        if (container.classList.contains('hidden')) {
            container.classList.remove('hidden');
            if (btn) btn.textContent = i18n.btn_voice_list_hide;
            refreshElevenVoices();
        } else {
            container.classList.add('hidden');
            if (btn) btn.textContent = i18n.btn_voice_list_show;
        }
    }

    // [FINAL OVERRIDE] Ensure saveAllSettings handles EVERYTHING
    async function saveAllSettings() {
        try {
            // Save Remote Render Settings to localStorage
            const renderTarget = document.getElementById('renderTarget')?.value || 'local';
            const remoteUrl = document.getElementById('remoteUrl')?.value || '';
            localStorage.setItem('remote_render_target', renderTarget);
            localStorage.setItem('remote_render_url', remoteUrl);

            // Gather All Global Settings
            const safeVal = (id) => document.getElementById(id)?.value || '';
            const safeCheck = (id) => document.getElementById(id)?.checked ?? false;

            const settings = {
                // Base Settings
                app_mode: safeVal('appMode'),

                // Gemini TTS
                gemini_tts: {
                    voice_name: safeVal('geminiVoice'),
                    language_code: safeVal('geminiLanguage'),
                    style_prompt: safeVal('geminiStylePrompt')
                },

                // Script Styles
                script_styles: {
                    news: safeVal('promptNews'),
                    story: safeVal('promptStory'),
                    script_master: safeVal('promptScriptMaster'),
                    senior_story: safeVal('promptSeniorStory')
                },

                // Webtoon Settings
                // webtoon_auto_split: safeCheck('ws_auto_split'),
                // webtoon_smart_pan: safeCheck('ws_smart_pan'),
                // webtoon_convert_zoom: safeCheck('ws_convert_zoom'),
                // webtoon_smart_pan: safeCheck('ws_smart_pan'),
                // webtoon_convert_zoom: safeCheck('ws_convert_zoom'),
                webtoon_plan_prompt: safeVal('ws_plan_prompt'),
                webtoon_vertical_prompt: safeVal('ws_vertical_prompt'),
                webtoon_horizontal_prompt: safeVal('ws_horizontal_prompt'),
                webtoon_motion_pan: safeVal('ws_motion_pan'),
                webtoon_motion_zoom: safeVal('ws_motion_zoom'),
                webtoon_motion_action: safeVal('ws_motion_action'),
                video_engine: document.querySelector('input[name="ws_video_engine"]:checked')?.value || "veo",
                veo_model_version: document.querySelector('input[name="veo_model_version"]:checked')?.value || "veo-3.1-fast-generate-preview",
                blog_client_id: safeVal('blogClientId'),
                blog_client_secret: safeVal('blogClientSecret'),
                blog_id: safeVal('blogId'),
                // [NEW] WordPress Settings
                wp_url: safeVal('wpUrl'),
                wp_username: safeVal('wpUsername'),
                wp_password: safeVal('wpPassword'),
                user_name: safeVal('userName'),
                user_nationality: safeVal('userNationality'),
                user_phone: safeVal('userPhone'),
                user_email: safeVal('userEmail')
            };

            if (document.getElementById('useExternalRender')) {
                settings.use_external_render = safeCheck('useExternalRender');
            }
            if (document.getElementById('drivePathKo')) {
                settings.drive_path_ko = safeVal('drivePathKo');
            }
            if (document.getElementById('drivePathEn')) {
                settings.drive_path_en = safeVal('drivePathEn');
            }
            if (document.getElementById('drivePathJa')) {
                settings.drive_path_ja = safeVal('drivePathJa');
            }
            if (document.getElementById('driveActiveLang')) {
                settings.drive_active_lang = safeVal('driveActiveLang');
            }

            if (IS_STANDARD_MEMBER) {
                Object.keys(settings).forEach((key) => {
                    if (![
                        'app_mode',
                        'user_name',
                        'user_nationality',
                        'user_phone',
                        'user_email',
                        'use_external_render',
                        'drive_path_ko',
                        'drive_path_en',
                        'drive_path_ja',
                        'drive_active_lang'
                    ].includes(key)) {
                        delete settings[key];
                    }
                });
            }

            const res = await fetch('/api/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(settings)
            });

            if (res.ok) {
                const data = await res.json();
                if (data.mode_changed) {
                    localStorage.removeItem('currentProjectId');
                    if (data.previous_mode) localStorage.removeItem(`currentProjectId:${data.previous_mode}`);
                    if (data.new_mode) {
                        localStorage.setItem('currentAppMode', data.new_mode);
                        localStorage.setItem('app_mode', data.new_mode);
                    }
                    ['scriptStructure', 'fullScript', 'imagePrompts', 'characterPrompts'].forEach(key => {
                        try { localStorage.removeItem(key); } catch (e) {}
                    });
                    ['trendKeywords', 'topicPageState', 'latestScriptStyle'].forEach(key => {
                        try { localStorage.removeItem(key); } catch (e) {}
                    });
                    Utils.showToast(i18n.toast_settings_mode_switched, 'success');
                    setTimeout(() => window.location.reload(), 1500);
                } else {
                    Utils.showToast(i18n.toast_all_settings_saved, 'success');
                }
            } else {
                const errData = await res.json().catch(() => ({ detail: 'Server error' }));
                Utils.showToast(i18n.err_save_fail + ': ' + (errData.detail || i18n.err_occurred), 'error');
            }
        } catch (e) {
            console.error('설정 저장 오류:', e);
            Utils.showToast(i18n.err_settings_save_fail, 'error');
        }
    }

    // [FINAL OVERRIDE] Ensure loadAllSettings calls Webtoon settings
    const originalLoadAllSettings = loadAllSettings;
    // Wait, reusing name causes recursion if we are not careful or if let/const. 
    // Browsers hoist function declarations. The last one overrides.
    // So we just redefine it.

    async function loadAllSettings() {
        try {
            const res = await fetch('/api/settings');
            const data = await res.json();

            // Base Settings
            if (data.app_mode) setAppMode(data.app_mode);
            if (data.template_image_url) updateTemplatePreview(data.template_image_url);

            // User Info
            if (document.getElementById('userName')) document.getElementById('userName').value = data.user_name || '';
            if (document.getElementById('userNationality')) document.getElementById('userNationality').value = data.user_nationality || '';
            if (document.getElementById('userPhone')) document.getElementById('userPhone').value = data.user_phone || '';
            if (document.getElementById('userEmail')) document.getElementById('userEmail').value = data.user_email || '';

            // Google Drive Queue Settings
            if (document.getElementById('useExternalRender')) document.getElementById('useExternalRender').checked = !!data.use_external_render;
            if (document.getElementById('drivePathKo')) document.getElementById('drivePathKo').value = data.drive_path_ko || '';
            if (document.getElementById('drivePathEn')) document.getElementById('drivePathEn').value = data.drive_path_en || '';
            if (document.getElementById('drivePathJa')) document.getElementById('drivePathJa').value = data.drive_path_ja || '';
            if (document.getElementById('driveActiveLang')) document.getElementById('driveActiveLang').value = data.drive_active_lang || 'ko';

            // Gemini TTS
            if (data.gemini_tts) {
                if (document.getElementById('geminiVoice')) document.getElementById('geminiVoice').value = data.gemini_tts.voice_name || 'Puck';
                if (document.getElementById('geminiLanguage')) document.getElementById('geminiLanguage').value = data.gemini_tts.language_code || 'ko-KR';
                if (document.getElementById('geminiStylePrompt')) document.getElementById('geminiStylePrompt').value = data.gemini_tts.style_prompt || '';
            }

            // Script Styles
            if (data.script_styles) {
                if (document.getElementById('promptNews')) document.getElementById('promptNews').value = data.script_styles.news || '';
                if (document.getElementById('promptStory')) document.getElementById('promptStory').value = data.script_styles.story || '';
                if (document.getElementById('promptScriptMaster')) document.getElementById('promptScriptMaster').value = data.script_styles.script_master || DEFAULT_SCRIPT_MASTER_PROMPT;
                if (document.getElementById('promptSeniorStory')) document.getElementById('promptSeniorStory').value = data.script_styles.senior_story || '';
            }

            // Webtoon Settings
            await loadWebtoonSettings();

            // Restore Remote Render Settings from localStorage
            const storedUrl = localStorage.getItem('remote_render_url') || '';
            const storedTarget = localStorage.getItem('remote_render_target') || 'local';
            if (document.getElementById('remoteUrl')) {
                document.getElementById('remoteUrl').value = storedUrl;
            }
            if (document.getElementById('renderTarget')) {
                document.getElementById('renderTarget').value = storedTarget;
                toggleRemoteUrl();
            }

            Utils.showToast(i18n.toast_settings_loaded, 'info');
        } catch (e) {
            console.error('설정 로드 실패:', e);
        }
    }

    // Webtoon Learning Rules API Fetch
    async function loadWebtoonRules() {
        try {
            const res = await fetch('/api/settings/webtoon-rules');
            if (!res.ok) return;
            const data = await res.json();
            const tbody = document.getElementById('webtoonRulesTableBody');
            if (!tbody) return;

            if (data.rules && data.rules.length > 0) {
                tbody.innerHTML = data.rules.map(rule => `
                    <tr class="bg-[#1c2027] border-b bg-[#1c2027] dark:border-gray-700 hover:bg-[#1c2027] dark:hover:bg-gray-600">
                        <td class="px-4 py-2 font-medium text-gray-900 dark:text-white">${rule.condition_type} / <span class="text-blue-500">${rule.condition_value}</span></td>
                        <td class="px-4 py-2"><span class="bg-blue-100 text-blue-800 text-[10px] font-semibold px-2.5 py-0.5 rounded dark:bg-[#1c2027] dark:text-blue-300">${rule.action_type}</span></td>
                        <td class="px-4 py-2">${rule.description || ''}</td>
                        <td class="px-4 py-2 text-right">
                            <button onclick="deleteWebtoonRule(${rule.id})" class="text-xs text-red-500 hover:underline">${i18n.btn_delete_short}</button>
                        </td>
                    </tr>
                `).join('');
            } else {
                tbody.innerHTML = `<tr><td colspan="4" class="px-4 py-4 text-center text-gray-500 dark:text-gray-400">${i18n.msg_no_rules}</td></tr>`;
            }
        } catch (e) {
            console.error('Failed to load webtoon rules:', e);
        }
    }

    async function addWebtoonRule() {
        const ct = document.getElementById('newConditionType').value;
        const cv = document.getElementById('newConditionValue').value.trim();
        const at = document.getElementById('newActionType').value;
        const desc = document.getElementById('newRuleDescription').value.trim();

        if (!cv) {
            Utils.showToast(i18n.toast_enter_condition, 'error');
            return;
        }

        try {
            const res = await fetch('/api/settings/webtoon-rules', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    condition_type: ct,
                    condition_value: cv,
                    action_type: at,
                    description: desc
                })
            });
            if (res.ok) {
                Utils.showToast(i18n.toast_rule_added, 'success');
                document.getElementById('newConditionValue').value = '';
                document.getElementById('newRuleDescription').value = '';
                loadWebtoonRules();
            }
        } catch (e) {
            Utils.showToast(i18n.toast_general_error, 'error');
        }
    }

    async function deleteWebtoonRule(id) {
        if (!confirm(i18n.confirm_delete_rule)) return;
        try {
            const res = await fetch('/api/settings/webtoon-rules/' + id, { method: 'DELETE' });
            if (res.ok) {
                Utils.showToast(i18n.toast_deleted, 'success');
                loadWebtoonRules();
            }
        } catch (e) {
            Utils.showToast(i18n.toast_general_error, 'error');
        }
    }

    // [NEW] Tistory Authorize
    function authorizeTistory() {
        // 먼저 현재 입력된 Client ID와 Secret을 저장 시도 (백엔드 세션/DB 연동 위해)
        saveAllSettings().then(() => {
            const width = 600;
            const height = 700;
            const left = (window.screen.width / 2) - (width / 2);
            const top = (window.screen.height / 2) - (height / 2);
            window.open('/api/settings/tistory/authorize', 'tistory_auth', `width=${width},height=${height},left=${left},top=${top}`);
        });
    }

    // Message Listener for Tistory Auth Callback
    window.addEventListener('message', async (event) => {
        if (event.data.type === 'TISTORY_CODE') {
            const code = event.data.code;
            try {
                const res = await fetch('/api/settings/tistory/token', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ code: code })
                });
                const result = await res.json();
                if (result.status === 'ok') {
                    Utils.showToast(i18n.toast_tistory_auth_done, 'success');
                } else {
                    Utils.showToast('❌ 토큰 발급 실패: ' + result.message, 'error');
                }
            } catch (e) {
                console.error('Tistory Token Exchange Error:', e);
                Utils.showToast(i18n.err_auth_processing, 'error');
            }
        }
    });

    async function syncAllPresetsFromServer() {
        const confirmSync = confirm(window_lang === 'vi' ? 'Bạn có muốn đồng bộ hóa tất cả các phong cách từ máy chủ?' : '서버로부터 모든 스타일 프리셋을 동기화하시겠습니까?');
        if (!confirmSync) return;
        
        try {
            Utils.showToast(window_lang === 'vi' ? 'Đang đồng bộ...' : '동기화 중...', 'info');
            const res = await fetch('/api/settings/sync-presets', {
                method: 'POST'
            });
            const data = await res.json();
            if (data.status === 'ok') {
                Utils.showToast(data.message, 'success');
                // Reload all presets in UI
                loadStylePresets();
                loadScriptStylePresets();
                loadThumbnailStylePresets();
            } else {
                Utils.showToast('Sync Failed: ' + (data.detail || 'Unknown error'), 'error');
            }
        } catch (e) {
            console.error(e);
            Utils.showToast(window_lang === 'vi' ? 'Lỗi kết nối đồng bộ' : '서버 동기화 중 오류 발생', 'error');
        }
    }

    // [NEW] Withdrawal and History Functions
    async function fetchWithdrawalHistory() {
        const tbody = document.getElementById('withdrawalHistoryBody');
        if (!tbody) return;

        tbody.innerHTML = `<tr><td colspan="4" class="px-4 py-4 text-center text-gray-500">${window.i18n?.msg_loading_data || 'Loading data...'}</td></tr>`;

        try {
            const res = await fetch('/api/settings/withdrawal-history');
            if (!res.ok) throw new Error('Failed to load withdrawal history');

            const data = await res.json();

            if (data.withdrawals && data.withdrawals.length > 0) {
                tbody.innerHTML = data.withdrawals.map(w => {
                    const date = new Date(w.created_at).toLocaleDateString();
                    const status = w.status === 'completed'
                        ? `<span class="bg-green-100 text-green-700 px-2 py-1 rounded text-[9px] font-bold">${window.i18n?.status_completed || 'Completed'}</span>`
                        : `<span class="bg-yellow-100 text-yellow-700 px-2 py-1 rounded text-[9px] font-bold">${window.i18n?.status_pending || 'Pending'}</span>`;

                    return `
                        <tr class="border-b border-gray-700 hover:bg-[#1c2027] transition-colors">
                            <td class="px-4 py-3 text-center text-gray-300">${date}</td>
                            <td class="px-4 py-3 text-center text-gray-400 font-mono text-[10px]">${w.destination_address.substring(0, 10)}...${w.destination_address.substring(-6)}</td>
                            <td class="px-4 py-3 text-right text-green-400 font-bold">${w.amount} USDT</td>
                            <td class="px-4 py-3 text-center">${status}</td>
                        </tr>
                    `;
                }).join('');
            } else {
                tbody.innerHTML = `<tr><td colspan="4" class="px-4 py-4 text-center text-gray-500">${window.i18n?.msg_no_withdrawals || 'No withdrawal history'}</td></tr>`;
            }
        } catch (e) {
            console.error(e);
            tbody.innerHTML = `<tr><td colspan="4" class="px-4 py-4 text-center text-red-500">${window.i18n?.err_load_fail || 'Failed to load'}</td></tr>`;
        }
    }

    async function fetchWorkHistory() {
        const tbody = document.getElementById('history-tbody');
        if (!tbody) return;

        tbody.innerHTML = `<tr><td colspan="6" class="px-4 py-4 text-center text-gray-500">${window.i18n?.msg_loading_data || 'Loading data...'}</td></tr>`;

        try {
            const res = await fetch('/api/settings/work-history');
            if (!res.ok) throw new Error('Failed to load work history');

            const data = await res.json();

            if (data.history && data.history.length > 0) {
                tbody.innerHTML = data.history.map(h => {
                    const date = new Date(h.created_at).toLocaleDateString();
                    return `
                        <tr class="border-b border-gray-700 hover:bg-[#2a323d] transition-colors">
                            <td class="px-4 py-3 text-gray-300">${date}</td>
                            <td class="px-4 py-3 text-gray-300">${h.project_name || 'N/A'}</td>
                            <td class="px-4 py-3 text-center text-gray-300">${h.video_duration || 0} min</td>
                            <td class="px-4 py-3 text-center text-gray-300">${h.video_scenes || 0}</td>
                            <td class="px-4 py-3 text-center text-gray-300">${h.image_scenes || 0}</td>
                            <td class="px-4 py-3 text-right text-green-400 font-bold">${h.estimated_payout || 0} USDT</td>
                        </tr>
                    `;
                }).join('');
            } else {
                tbody.innerHTML = `<tr><td colspan="6" class="px-4 py-4 text-center text-gray-500">${window.i18n?.msg_no_history || 'No work history'}</td></tr>`;
            }
        } catch (e) {
            console.error(e);
            tbody.innerHTML = `<tr><td colspan="6" class="px-4 py-4 text-center text-red-500">${window.i18n?.err_load_fail || 'Failed to load'}</td></tr>`;
        }
    }

    async function requestWithdrawal() {
        const address = document.getElementById('wdDestAddress').value.trim();
        const amount = parseFloat(document.getElementById('wdAmount').value || '0');

        if (!address) {
            Utils.showToast(window.i18n?.err_missing_address || 'Please enter withdrawal wallet address.', 'warning');
            return;
        }

        if (amount <= 0) {
            Utils.showToast(window.i18n?.err_invalid_amount || 'Please enter a valid withdrawal amount.', 'warning');
            return;
        }

        if (amount < 10) {
            Utils.showToast((window.i18n?.label_minimum_withdrawal || 'Minimum withdrawal') + ': 10 USDT', 'warning');
            return;
        }

        if (!confirm(window.i18n?.msg_withdrawal_confirm || 'Proceed with withdrawal request?')) {
            return;
        }

        try {
            const res = await fetch('/api/settings/withdrawal', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    amount: amount,
                    dest_address: address
                })
            });

            if (res.ok) {
                Utils.showToast(window.i18n?.msg_withdrawal_success || 'Withdrawal request completed.', 'success');
                document.getElementById('wdAmount').value = '';
                fetchWithdrawalHistory();
            } else {
                const err = await res.json();
                Utils.showToast(window.i18n?.msg_withdrawal_failed || 'Withdrawal request failed', 'error');
            }
        } catch (e) {
            console.error(e);
            Utils.showToast(window.i18n?.err_occurred || 'An error occurred', 'error');
        }
    }

    async function pasteWithdrawalAddress() {
        try {
            const text = await navigator.clipboard.readText();
            document.getElementById('wdDestAddress').value = text;
        } catch (e) {
            Utils.showToast(window.i18n?.msg_clipboard_error || 'Failed to read address from clipboard.', 'warning');
        }
    }

    // Settlement tab functions for admin
    async function fetchSettlementData() {
        const startDate = document.getElementById('settlementStartDate')?.value;
        const endDate = document.getElementById('settlementEndDate')?.value;
        const tbody = document.getElementById('settlementTableBody');

        if (!tbody) return;

        tbody.innerHTML = `<tr><td colspan="8" class="px-4 py-4 text-center text-gray-500">${window.i18n?.msg_loading_data || 'Loading data...'}</td></tr>`;

        try {
            let url = '/api/settings/settlement-summary';
            const params = new URLSearchParams();
            if (startDate) params.append('start_date', startDate);
            if (endDate) params.append('end_date', endDate);
            if (params.toString()) url += '?' + params.toString();

            const res = await fetch(url);
            if (!res.ok) throw new Error('Failed to load settlement data');

            const data = await res.json();

            if (data.summary && data.summary.length > 0) {
                tbody.innerHTML = data.summary.map(s => `
                    <tr class="border-b border-gray-700 hover:bg-[#2a323d] transition-colors">
                        <td class="px-4 py-3 text-gray-300">${s.worker}</td>
                        <td class="px-4 py-3 text-center text-gray-300">${s.total_projects || 0}</td>
                        <td class="px-4 py-3 text-center text-green-400">${s.completed_projects || 0}</td>
                        <td class="px-4 py-3 text-center text-gray-300">${s.total_ai_tasks || 0}</td>
                        <td class="px-4 py-3 text-center text-green-400">${s.success_ai_tasks || 0}</td>
                        <td class="px-4 py-3 text-center text-gray-300">${s.tts_tasks || 0}</td>
                        <td class="px-4 py-3 text-center text-gray-300">${s.media_tasks || 0}</td>
                        <td class="px-4 py-3 text-right text-yellow-400 font-bold">${s.total_estimated_payout.toFixed(2)} USDT</td>
                    </tr>
                `).join('');
            } else {
                tbody.innerHTML = `<tr><td colspan="8" class="px-4 py-4 text-center text-gray-500">${window.i18n?.msg_no_data || 'No data found'}</td></tr>`;
            }
        } catch (e) {
            console.error(e);
            tbody.innerHTML = `<tr><td colspan="8" class="px-4 py-4 text-center text-red-500">${window.i18n?.err_load_fail || 'Failed to load'}</td></tr>`;
        }
    }

    async function exportSettlementCSV() {
        const startDate = document.getElementById('settlementStartDate')?.value;
        const endDate = document.getElementById('settlementEndDate')?.value;

        try {
            let url = '/api/settings/settlement-export';
            const params = new URLSearchParams();
            if (startDate) params.append('start_date', startDate);
            if (endDate) params.append('end_date', endDate);
            if (params.toString()) url += '?' + params.toString();

            const res = await fetch(url);
            if (!res.ok) throw new Error('Failed to export');

            const blob = await res.blob();
            const downloadUrl = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = downloadUrl;
            a.download = `settlement_${new Date().toISOString().split('T')[0]}.csv`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(downloadUrl);
            document.body.removeChild(a);

            Utils.showToast('Settlement exported successfully', 'success');
        } catch (e) {
            console.error(e);
            Utils.showToast('Failed to export settlement', 'error');
        }
    }

    // 초기화
    document.addEventListener('DOMContentLoaded', () => {
        populateOptions();
        loadAllSettings();
        loadChannels();
        loadStylePresets(); // [NEW] 스타일 프리셋 로드
        loadThumbnailStylePresets();
        loadWebtoonRules();

        // Load history on tab switch
        if (document.getElementById('history-tbody')) {
            fetchWorkHistory();
        }
        if (document.getElementById('withdrawalHistoryBody')) {
            fetchWithdrawalHistory();
        }
    });
