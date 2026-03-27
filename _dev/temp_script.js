
        // i18n for JS
        var i18n = Object.assign(window.i18n || {}, {
            status_labels: {
                'draft': "status_start",
                'analyzed': "status_analyzed",
                'planned': "기획완료",
                'scripted': "status_scripted",
                'tts_done': "status_tts_done",
                'rendered': "렌더링 완료",
                'completed': "status_completed"
            },
            select_project_placeholder: "프로젝트 선택...",
            status_label_prefix: "status_label_prefix",
            toast_loading_project_prefix: "toast_loading_project_prefix",
            toast_loading_project_suffix: "toast_loading_project_suffix",
            toast_load_done_prefix: "toast_load_done_prefix",
            toast_load_done_suffix: "toast_load_done_suffix",
            err_fail_load_project: "err_fail_load_project",
            err_no_project_name: "err_no_project_name",
            toast_project_created: "toast_project_created",
            err_fail_create_project: "err_fail_create_project",

            // Autopilot keys
            label_preset: "✨ 프리셋",
            preset_custom: "-- 커스텀 --",
            tab_single_production: "단일 제작",
            tab_queue_management: "큐 관리",
            label_autopilot_start: "오토파일럿 시작",
            helper_autopilot_desc: "주제를 설정하고 원하는 스타일을 선택한 후 제작을 시작하세요. AI가 모든 과정을 자동화합니다.",
            btn_start_production: "제작 시작하기",
            status_ai_server_waiting: "AI 서버 대기중",
            label_subtitle_preview: "자막 미리보기",
            label_script_style: "스크립트 스타일",
            label_target_duration: "목표 길이",
            label_engine: "엔진",
            label_voice_char: "보이스 캐릭터",
            label_yt_upload_settings: "유튜브 업로드 설정",
            label_upload_channel: "업로드 채널",
            label_thumbnail_style: "썸네일 스타일",
            label_video_engine: "영상 생성 엔진",
            label_gen_method: "생성 방식",
            label_standard: "표준",
            label_high_res_8s: "고해상도(8s)",
            label_slowmo_8s: "슬로우모션(8s)",
            label_all_caps: "ALL",
            label_image_focused: "이미지 중심",
            label_video_focused: "영상 중심",
            label_char_analysis: "캐릭터 분석 사용",
            helper_char_analysis: "씬 캐릭터를 분석하여 일관성을 유지합니다.",
            label_queue: "대기 큐",
            label_queue_management_desc: "대기 중인 프로젝트를 순차적으로 처리합니다.",
            label_execution_logs: "실행 로그",
            label_overall_progress: "전체 진행률",
            label_system_logs: "시스템 로그",
            label_privacy_scope: "공개 범위",
            label_scheduled_time: "예약 시간",
            label_creation_mode: "제작 모드",
            label_scene: "씬",
            label_no_title: "제목 없음",
            mode_longform: "롱폼",
            mode_shorts: "숏츠",
            unit_scenes: "개 씬",
            unit_min_short: "분",
            unit_sec_short: "초",
            status_loading: "처리 중...",
            status_loading_thumbnail_styles: "썸네일 스타일 로딩중...",
            status_autopilot_in_progress: "오토파일럿 진행중",
            status_waiting_task: "작업 대기중...",
            status_preparing: "준비중...",
            status_done_redirecting: "완료! 결과 페이지로 이동합니다...",
            status_error_occurred_check_logs: "오류 발생. 로그를 확인하세요.",
            status_processing_monitor: "처리중 (모니터링)...",
            status_no_voices_available: "사용 가능한 보이스 없음",
            status_error_loading_voices: "보이스 로드 오류",
            status_no_queue_items: "대기중인 항목 없음",
            status_no_queued_projects: "큐에 등록된 프로젝트가 없습니다.",
            status_failed_to_load_list: "목록 로드 실패",
            status_load_failed: "로드 실패",
            status_connection_error: "연결 오류",
            status_queued: "대기중",
            status_preset_loaded_prefix: "프리셋",
            status_preset_loaded_suffix: "이 적용되었습니다.",
            status_failed_to_load_preset: "프리셋 로드 실패",
            status_preset_saved: "프리셋이 저장되었습니다.",
            status_preset_deleted: "프리셋이 삭제되었습니다.",
            status_batch_started: "일괄 제작이 시작되었습니다.",
            status_batch_started_check_queue: "일괄 제작 시작! 큐를 확인하세요.",
            status_all_tasks_done: "모든 작업이 완료되었습니다.",
            status_requesting_start: "시작 요청중...",
            status_processing: "처리중...",
            status_removed_from_queue: "큐에서 제거되었습니다.",
            status_system_initialized: "시스템 초기화 완료. 지시를 기다립니다...",
            helper_scene_gen_prefix: "씬",
            helper_scene_gen_mid: "개 영상 생성",
            helper_subtitle_autoreload: "자막 설정 페이지를 저장하면 자동으로 반영됩니다.",
            helper_add_from_plan: "스크립트 기획 페이지에서 큐에 추가하세요.",
            helper_topview_ai: "AI가 제품 URL을 분석하여 광고 영상을 제작합니다.",
            helper_scheduled_warn: "예약 시간은 UTC 기준입니다.",
            helper_do_not_close_browser: "처리 완료 전에 브라우저를 닫지 마세요.",
            btn_start_batch: "일괄 시작",
            btn_clear_logs: "로그 지우기",
            btn_go_to_results: "결과 보러가기",
            btn_delete: "btn_delete",
            confirm_close_modal_keep_task: "작업이 진행중입니다. 닫아도 백그라운드에서 계속 실행됩니다. 닫으시겠습니까?",
            confirm_start_batch: "대기중인 모든 프로젝트를 순차 제작하시겠습니까?",
            confirm_remove_from_queue: "이 프로젝트를 큐에서 제거하시겠습니까?",
            confirm_delete_preset: "을 삭제하시겠습니까?",
            alert_enter_preset_name: "프리셋 이름을 입력해주세요.",
            alert_enter_product_url: "제품 URL을 입력해주세요.",
            privacy_private: "🔒 비공개",
            privacy_public: "🌍 공개",
            privacy_unlisted: "🔗 링크 공유",
            privacy_scheduled: "⏰ 예약 공개",
            channel_default: "-- 기본 채널 --",
            theme_default: "일반",
            theme_commerce_review: "커머스/리뷰",
            badge_topview: "TOP",
            tip_save_presets: "프리셋을 저장해두면 다음 제작 시 빠르게 설정을 불러올 수 있습니다.",
            engine_akool_premium: "Akool 프리미엄",
            style_viral: "🔥 바이럴",
            ethnicity_1: "1. 동북아시아 계열 (East Asian)",
            ethnicity_2: "2. 동남아시아 및 태평양 계열 (Southeast Asian &amp; Pacific Islander)",
            ethnicity_3: "3. 남부 아시아 계열 (South Asian)",
            ethnicity_4: "4. 유럽 및 코카서스 계열 (European / Caucasian)",
            ethnicity_5: "5. 중동 및 북아프리카 계열 (Middle Eastern &amp; North African)",
            ethnicity_6: "6. 아프리카 사하라 이남 계열 (Sub-Saharan African)",
            ethnicity_7: "7. 라틴 아메리카 혼혈 계열 (Hispanic / Latino - Mestizo)",
            ethnicity_8: "8. 원주민 및 오세아니아 계열 (Indigenous / Indigenous Australian)"
        };

        // 프로젝트 목록 로드
        async function loadProjects() {
            try {
                const data = await API.project.list();
                const select = document.getElementById('projectSelect');
                const currentId = getCurrentProject();

                select.innerHTML = `<option value="">${i18n.select_project_placeholder}</option>`;

                const mode = window.APP_MODE || 'longform';
                const filteredProjects = data.projects.filter(p => (p.app_mode || 'longform') === mode);

                filteredProjects.forEach(p => {
                    const option = document.createElement('option');
                    option.value = p.id;
                    option.textContent = `${p.name} (${i18n.status_labels[p.status] || p.status})`;
                    if (p.id == currentId) option.selected = true;
                    select.appendChild(option);
                });

                // 현재 프로젝트 정보 표시 및 전체 상태 복구
                if (currentId) {
                    // onProjectChange를 호출하여 헤더, 진행상태, 로컬 스토리지 데이터 등을 모두 복구
                    onProjectChange(currentId);
                }
            } catch (e) {
                console.error('프로젝트 로드 오류:', e);
            }
        }

        // 프로젝트 정보 업데이트
        function updateProjectInfo(project) {
            const infoDiv = document.getElementById('currentProjectInfo');
            const statusSpan = document.getElementById('projectStatus');

            if (project) {
                infoDiv.classList.remove('hidden');
                statusSpan.textContent = `${i18n.status_label_prefix}: ${i18n.status_labels[project.status] || project.status}`;
            } else {
                infoDiv.classList.add('hidden');
            }
        }

        // 프로젝트 변경
        async function onProjectChange(projectId) {
            if (projectId) {
                // 1. UI 및 로컬 상태 기본 업데이트
                setCurrentProject(projectId);

                // Select Box 업데이트 (프로그램적 호출 시 필요)
                const selectElement = document.getElementById('projectSelect');
                if (selectElement && selectElement.value != projectId) {
                    selectElement.value = projectId;
                }

                // 2. 프로젝트 기본 정보 조회 및 표시
                try {
                    const res = await API.project.get(projectId);
                    // [ROBUST] Handle both wrapped {project: ...} and direct object response
                    const project = (res && res.project) ? res.project : res;

                    if (!project || (!project.id && !project.name)) throw new Error("Invalid project data");

                    updateProjectInfo(project);

                    // Header Display Update
                    const headerDisplay = document.getElementById('currentProjectNameDisplay');
                    if (headerDisplay) {
                        const statusText = i18n.status_labels[project.status] || project.status;
                        headerDisplay.textContent = `${project.name} (${statusText})`;
                        document.getElementById('projectProgressHeader').classList.remove('hidden');
                    }

                    Utils.showToast(`${i18n.toast_loading_project_prefix} "${project.name}" ${i18n.toast_loading_project_suffix}`, 'info');

                    // 3. ✨ 전체 데이터 동기화 (Context Switching 핵심) ✨
                    const fullData = await API.project.getFull(projectId);

                    // 로컬 스토리지에 각 단계 데이터 업데이트
                    if (fullData) {
                        // 대본 기획
                        if (fullData.script_structure) Utils.storage.set('scriptStructure', fullData.script_structure);
                        // 대본 
                        if (fullData.script) Utils.storage.set('fullScript', fullData.script);
                        // 이미지 프롬프트 (image_gen.html용)
                        if (fullData.image_prompts) Utils.storage.set('imagePrompts', fullData.image_prompts);

                        // 캐릭터 정보 동기화 [NEW]
                        if (fullData.characters) Utils.storage.set('characterPrompts', fullData.characters);

                        // 이벤트 발생 (현재 페이지가 리스닝 중이라면 즉시 반영)
                        window.dispatchEvent(new CustomEvent('projectStateRestored', { detail: fullData }));

                        // ✨ UI 진행 상태 업데이트 (Green Light)
                        // 사용자 요청: 각 단계별 실제 데이터 존재 여부만 확인 (Strict Mode)
                        const settings = fullData.settings || {};
                        const steps = {
                            'topic': !!(fullData.project && fullData.project.topic),
                            'thumbnail': !!(settings.thumbnail_url || settings.thumbnail_path || (fullData.project && (fullData.project.thumbnail_url || fullData.project.thumbnail_path))),
                            'plan': !!fullData.script_structure,
                            'script': !!fullData.script || (fullData.shorts && Object.keys(fullData.shorts).length > 0),
                            'intro': !!settings.intro_video_path || !!settings.background_video_url,
                            'image': fullData.image_prompts && fullData.image_prompts.length > 0,
                            'tts': !!fullData.tts,
                            'subtitle': !!settings.subtitle_path || (fullData.tts && !!settings.subtitle_style_enum),
                            'render': project.status === 'rendered' || project.status === 'completed' || !!settings.video_path,
                            'upload': !!settings.is_uploaded
                        };

                        document.querySelectorAll('.step-item').forEach(el => {
                            const stepName = el.dataset.step;
                            const circle = el.querySelector('.step-circle');
                            const indicator = el.querySelector('.step-circle div');
                            const label = el.querySelector('span');

                            // Check if element exists (safety)
                            if (!circle || !indicator || !label) return;

                            // Reset
                            circle.className = 'step-circle w-5 h-5 rounded-full bg-gray-200 dark:bg-gray-700 border-2 border-white dark:border-gray-900 flex items-center justify-center transition-all duration-300';
                            indicator.className = 'w-1.5 h-1.5 rounded-full bg-gray-400 transition-colors';
                            indicator.innerHTML = ''; // Clear SVG
                            label.classList.remove('text-green-500', 'font-bold', 'text-green-600', 'dark:text-green-400');
                            label.classList.add('text-gray-400');

                            if (steps[stepName]) {
                                // Completed Style
                                circle.classList.remove('bg-gray-200', 'dark:bg-gray-700');
                                circle.classList.add('bg-green-500', 'border-green-500', 'dark:bg-green-500', 'dark:border-green-500');

                                indicator.className = 'w-2 h-1.5 text-white'; // Checkmark logic optional or just white dot
                                indicator.innerHTML = `<svg class="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7"></path></svg>`;
                                indicator.classList.remove('rounded-full', 'bg-gray-400', 'w-1.5', 'h-1.5'); // Remove dot styles

                                label.classList.remove('text-gray-400');
                                label.classList.add('text-green-600', 'dark:text-green-400', 'font-bold');
                            }
                        });


                        Utils.showToast(`${i18n.toast_load_done_prefix} "${project.name}" ${i18n.toast_load_done_suffix}`, 'success');
                    }

                } catch (e) {
                    console.error("프로젝트 로드 실패", e);
                    Utils.showToast(i18n.err_fail_load_project, 'error');
                }

            } else {
                setCurrentProject(null);
                document.getElementById('currentProjectInfo').classList.add('hidden');
                document.getElementById('projectProgressHeader').classList.add('hidden');

                // 로컬 스토리지 데이터도 비우는 것이 좋음 (선택 해제 시)
                Utils.storage.remove('scriptStructure');
                Utils.storage.remove('fullScript');
                Utils.storage.remove('imagePrompts');
            }
        }


        // 프로젝트 모달 열기/닫기
        function openProjectModal() {
            document.getElementById('projectModal').classList.remove('hidden');
            document.getElementById('projectModal').classList.add('flex');
            document.getElementById('newProjectName').focus();
        }

        function closeProjectModal() {
            document.getElementById('projectModal').classList.add('hidden');
            document.getElementById('projectModal').classList.remove('flex');
            document.getElementById('newProjectName').value = '';
            document.getElementById('newProjectTopic').value = '';
            document.getElementById('newProjectLanguage').value = 'ko'; // Reset to default
        }

        // 새 프로젝트 생성
        async function createNewProject() {
            const name = document.getElementById('newProjectName').value.trim();
            const topic = document.getElementById('newProjectTopic').value.trim();
            const language = document.getElementById('newProjectLanguage').value; // [NEW] Read language

            if (!name) {
                Utils.showToast(i18n.err_no_project_name, 'warning');
                return;
            }

            try {
                // [CLEANUP] Clear existing project data from local storage to ensure clean state
                Utils.storage.remove('scriptStructure');
                Utils.storage.remove('fullScript');
                Utils.storage.remove('imagePrompts');
                Utils.storage.remove('characterPrompts'); // [NEW]
                localStorage.removeItem('trendKeywords'); // [NEW]
                localStorage.removeItem('topicPageState'); // [NEW]
                localStorage.removeItem('latestScriptStyle'); // Optional: reset style preference

                // [NEW] Get Current Mode from Settings
                let currentMode = 'longform';
                try {
                    // Cache busting to ensure fresh settings
                    const res = await fetch('/api/settings?t=' + new Date().getTime());
                    const settings = await res.json();
                    currentMode = settings.app_mode || 'longform';
                } catch (e) { console.error("Failed to load settings:", e); }

                const result = await API.project.create(name, topic || null, language, currentMode); // [FIX] Pass app_mode
                if (result.project_id) {
                    setCurrentProject(result.project_id);
                    closeProjectModal();
                    Utils.showToast(i18n.toast_project_created, 'success');

                    // [FIX] Redirect to projects page to see the newly created project
                    setTimeout(() => {
                        window.location.href = '/projects';
                    }, 500);
                }
            } catch (e) {
                Utils.showToast(i18n.err_fail_create_project, 'error');
            }
        }

        // API 상태 확인
        async function checkApiStatus() {
            try {
                const response = await fetch('/api/health');
                const data = await response.json();
                const statusDot = document.getElementById('statusDot');
                const apiStatus = document.getElementById('apiStatus');

                if (data.status === 'ok') {
                    const activeApis = Object.entries(data.apis)
                        .filter(([k, v]) => v)
                        .map(([k]) => k);

                    statusDot.className = 'w-2 h-2 rounded-full bg-green-500';
                    apiStatus.innerHTML = `
                        <div class="flex items-center gap-2 mb-1">
                            <span class="w-2 h-2 rounded-full bg-green-500"></span>
                            <span class="text-green-600 dark:text-green-400">연결됨</span>
                        </div>
                        <div class="text-gray-400">${activeApis.join(', ')}</div>
                    `;
                }
            } catch (e) {
                document.getElementById('statusDot').className = 'w-2 h-2 rounded-full bg-red-500';
            }
        }

        // [NEW] App Mode Navigation Logic
        async function applyAppModeToNav() {
            try {
                const res = await fetch('/api/settings');
                const settings = await res.json();
                const mode = settings.app_mode || 'longform';
                window.APP_MODE = mode; // [NEW] Expose globally
                console.log("Global Mode:", mode);

                // Elements to toggle
                const navPlan = document.getElementById('nav-plan');
                const navScript = document.getElementById('nav-script');
                const navIntro = document.getElementById('nav-intro');

                const navImage = document.getElementById('nav-image');
                const navAudio = document.getElementById('nav-audio');
                const navThumbnail = document.getElementById('nav-thumbnail');
                const navTts = document.getElementById('nav-tts');
                const navSubtitle = document.getElementById('nav-subtitle');
                const navRender = document.getElementById('nav-render');

                const navTitle = document.getElementById('nav-title');
                const navShorts = document.getElementById('nav-shorts');
                const navWebtoon = document.getElementById('nav-webtoon');
                const navCommerce = document.getElementById('nav-commerce-shorts');
                const navBlog = document.getElementById('nav-blog');
                const navTopic = document.getElementById('nav-topic');
                const navRepository = document.getElementById('nav-repository');
                const navUpload = document.getElementById('nav-upload');
                const navAutopilot = document.getElementById('nav-autopilot');

                // Helper to hide/show
                const setVisible = (el, show) => {
                    if (!el) return;
                    if (show) el.parentElement.classList.remove('hidden');
                    else el.parentElement.classList.add('hidden');
                };

                if (mode === 'blog') {
                    // Blog Mode: Focused on writing and automation
                    setVisible(navBlog, true);
                    setVisible(navTopic, true);
                    setVisible(navRepository, true);
                    setVisible(navPlan, true);
                    setVisible(navScript, true);

                    // Hide video-specific steps
                    setVisible(navIntro, false);
                    setVisible(navImage, false);
                    setVisible(navAudio, false);
                    setVisible(navThumbnail, false);
                    setVisible(navTts, false);
                    setVisible(navSubtitle, false);
                    setVisible(navRender, false);
                    setVisible(navTitle, false);
                    setVisible(navShorts, false);
                    setVisible(navWebtoon, false);
                    setVisible(navCommerce, false);
                    setVisible(navUpload, false);
                    setVisible(navAutopilot, true);

                } else if (mode === 'commerce') {
                    // Commerce Mode
                    setVisible(navCommerce, true);
                    setVisible(navTopic, true);
                    setVisible(navRepository, true);
                    setVisible(navUpload, true);

                    setVisible(navBlog, false);
                    setVisible(navPlan, false);
                    setVisible(navScript, false);
                    setVisible(navIntro, false);
                    setVisible(navImage, false);
                    setVisible(navAudio, false);
                    setVisible(navThumbnail, false);
                    setVisible(navTts, false);
                    setVisible(navSubtitle, false);
                    setVisible(navRender, false);
                    setVisible(navTitle, false);
                    setVisible(navShorts, false);
                    setVisible(navWebtoon, false);

                } else if (mode === 'shorts') {
                    // Shorts Mode
                    setVisible(navBlog, false);
                    setVisible(navCommerce, false);
                    setVisible(navWebtoon, false);

                    setVisible(navIntro, false);
                    setVisible(navTitle, false);
                    setVisible(navShorts, false);

                    setVisible(navPlan, true);
                    setVisible(navScript, true);
                    setVisible(navImage, true);
                    setVisible(navAudio, true);
                    setVisible(navThumbnail, true);
                    setVisible(navTts, true);
                    setVisible(navSubtitle, true);
                    setVisible(navRender, true);
                    setVisible(navTopic, true);
                    setVisible(navRepository, true);
                    setVisible(navUpload, true);
                    setVisible(navAutopilot, true);

                    // Rename Script Gen
                    if (navScript) {
                        navScript.querySelector('span:last-child').innerText = "쇼츠 대본";
                    }

                } else if (mode === 'webtoon') {
                    // Webtoon Mode
                    setVisible(navBlog, false);
                    setVisible(navCommerce, false);
                    setVisible(navWebtoon, true);

                    setVisible(navTopic, false);
                    setVisible(navRepository, false);
                    setVisible(navPlan, false);
                    setVisible(navThumbnail, false);
                    setVisible(navUpload, false);

                    setVisible(navIntro, false);
                    setVisible(navTitle, false);
                    setVisible(navShorts, false);

                    setVisible(navScript, true);
                    setVisible(navImage, true);
                    setVisible(navAudio, true);
                    setVisible(navTts, true);
                    setVisible(navSubtitle, true);
                    setVisible(navRender, true);

                    setVisible(navAutopilot, false);

                    if (navScript) {
                        navScript.querySelector('span:last-child').innerText = "웹툰 대본";
                    }

                } else {
                    // Longform Mode (default): Show standard production pipeline
                    setVisible(navBlog, false);
                    setVisible(navCommerce, false);
                    setVisible(navWebtoon, false);

                    setVisible(navPlan, true);
                    setVisible(navScript, true);
                    setVisible(navIntro, true);
                    setVisible(navImage, true);
                    setVisible(navAudio, true);
                    setVisible(navThumbnail, true);
                    setVisible(navTts, true);
                    setVisible(navSubtitle, true);
                    setVisible(navRender, true);
                    setVisible(navTitle, true);
                    setVisible(navShorts, true);
                    setVisible(navTopic, true);
                    setVisible(navRepository, true);
                    setVisible(navUpload, true);
                    setVisible(navAutopilot, true);

                    if (navScript) {
                        navScript.querySelector('span:last-child').innerText = "대본 생성";
                    }
                }

            } catch (e) {
                console.error("Failed to apply mode to nav:", e);
            }
        }

        // ESC 키로 모달 닫기
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') closeProjectModal();
        });

        // [NEW] Global function to update step status dynamically
        window.updateStepStatus = function (stepName, isComplete) {
            const el = document.querySelector(`.step-item[data-step="${stepName}"]`);
            if (!el) return;

            const circle = el.querySelector('.step-circle');
            const indicator = el.querySelector('.step-circle div');
            const label = el.querySelector('span');

            if (!circle || !indicator || !label) return;

            if (isComplete) {
                // Completed Style
                circle.className = 'step-circle w-5 h-5 rounded-full bg-green-500 border-2 border-green-500 dark:bg-green-500 dark:border-green-500 flex items-center justify-center transition-all duration-300';

                indicator.className = 'w-2 h-1.5 text-white';
                indicator.innerHTML = `<svg class="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7"></path></svg>`;
                indicator.classList.remove('rounded-full', 'bg-gray-400', 'w-1.5', 'h-1.5');

                label.classList.remove('text-gray-400');
                label.classList.add('text-green-600', 'dark:text-green-400', 'font-bold');
            } else {
                // Reset (if needed)
                circle.className = 'step-circle w-5 h-5 rounded-full bg-gray-200 dark:bg-gray-700 border-2 border-white dark:border-gray-900 flex items-center justify-center transition-all duration-300';
                indicator.className = 'w-1.5 h-1.5 rounded-full bg-gray-400 transition-colors';
                indicator.innerHTML = '';
                label.classList.remove('text-green-600', 'dark:text-green-400', 'font-bold');
                label.classList.add('text-gray-400');
            }
        };


        // 초기화
        async function initApp() {
            await applyAppModeToNav();
            await loadProjects();
            checkApiStatus();
        }
        initApp();
    